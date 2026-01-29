#!/usr/bin/env python3
"""
Prepare the Kaggle Simpsons Characters dataset for YOLOv8 training.

This script:
1. Downloads the dataset from Kaggle (requires KAGGLE_USERNAME and KAGGLE_KEY env vars)
2. Converts it to YOLO classification format
3. Splits into train/val sets

Dataset: https://www.kaggle.com/datasets/alexattia/the-simpsons-characters-dataset
"""

import os
import shutil
import random
from pathlib import Path
from collections import defaultdict

# Characters to train on (most common ones with enough samples)
TARGET_CHARACTERS = [
    "homer_simpson",
    "marge_simpson",
    "bart_simpson",
    "lisa_simpson",
    "maggie_simpson",
    "abraham_grampa_simpson",
    "apu_nahasapeemapetilon",
    "barney_gumble",
    "charles_montgomery_burns",
    "chief_wiggum",
    "comic_book_guy",
    "edna_krabappel",
    "groundskeeper_willie",
    "krusty_the_clown",
    "lenny_leonard",
    "milhouse_van_houten",
    "moe_szyslak",
    "ned_flanders",
    "nelson_muntz",
    "principal_skinner",
    "sideshow_bob",
]

# Minimum images per character to include
MIN_IMAGES = 50

# Train/val split ratio
TRAIN_RATIO = 0.8


def download_dataset(output_dir: str = "data/raw"):
    """Download dataset from Kaggle."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Check if already downloaded
    if (output_path / "simpsons_dataset").exists():
        print("Dataset already downloaded")
        return output_path / "simpsons_dataset"

    try:
        import kaggle
        print("Downloading dataset from Kaggle...")
        kaggle.api.dataset_download_files(
            "alexattia/the-simpsons-characters-dataset",
            path=str(output_path),
            unzip=True
        )
        print("Download complete!")
        return output_path / "simpsons_dataset"
    except Exception as e:
        print(f"Error downloading: {e}")
        print("\nManual download instructions:")
        print("1. Go to: https://www.kaggle.com/datasets/alexattia/the-simpsons-characters-dataset")
        print("2. Download and extract to: data/raw/simpsons_dataset/")
        print("3. Re-run this script")
        raise


def prepare_yolo_classification(
    raw_dir: str = "data/raw/simpsons_dataset",
    output_dir: str = "data/simpsons_yolo",
    min_images: int = MIN_IMAGES,
    train_ratio: float = TRAIN_RATIO
):
    """
    Convert Kaggle dataset to YOLO classification format.

    YOLO classification format:
    data/
      train/
        class1/
          img1.jpg
          img2.jpg
        class2/
          ...
      val/
        class1/
          ...
    """
    raw_path = Path(raw_dir)
    output_path = Path(output_dir)

    if not raw_path.exists():
        raise FileNotFoundError(f"Raw dataset not found at {raw_path}")

    # Find the actual image directory
    img_dir = raw_path / "simpsons_dataset"
    if not img_dir.exists():
        img_dir = raw_path

    # Get all character folders
    char_dirs = [d for d in img_dir.iterdir() if d.is_dir()]
    print(f"Found {len(char_dirs)} character folders")

    # Count images per character
    char_counts = {}
    for char_dir in char_dirs:
        images = list(char_dir.glob("*.jpg")) + list(char_dir.glob("*.png"))
        char_counts[char_dir.name] = len(images)

    # Filter characters with enough images
    valid_chars = {k: v for k, v in char_counts.items() if v >= min_images}
    print(f"\nCharacters with >= {min_images} images: {len(valid_chars)}")

    # Prioritize target characters
    final_chars = []
    for char in TARGET_CHARACTERS:
        if char in valid_chars:
            final_chars.append(char)

    # Add other valid characters
    for char in sorted(valid_chars.keys()):
        if char not in final_chars:
            final_chars.append(char)

    print(f"Training on {len(final_chars)} characters:")
    for i, char in enumerate(final_chars):
        print(f"  {i}: {char} ({char_counts[char]} images)")

    # Create output directories
    train_dir = output_path / "train"
    val_dir = output_path / "val"

    if output_path.exists():
        shutil.rmtree(output_path)

    train_dir.mkdir(parents=True)
    val_dir.mkdir(parents=True)

    # Copy images with train/val split
    total_train = 0
    total_val = 0

    for char in final_chars:
        char_path = img_dir / char
        images = list(char_path.glob("*.jpg")) + list(char_path.glob("*.png"))

        # Shuffle and split
        random.shuffle(images)
        split_idx = int(len(images) * train_ratio)
        train_images = images[:split_idx]
        val_images = images[split_idx:]

        # Create character directories
        (train_dir / char).mkdir()
        (val_dir / char).mkdir()

        # Copy images
        for img in train_images:
            shutil.copy(img, train_dir / char / img.name)
        for img in val_images:
            shutil.copy(img, val_dir / char / img.name)

        total_train += len(train_images)
        total_val += len(val_images)

    print(f"\nDataset prepared:")
    print(f"  Train: {total_train} images")
    print(f"  Val: {total_val} images")
    print(f"  Output: {output_path}")

    # Save class names
    with open(output_path / "classes.txt", "w") as f:
        for char in final_chars:
            f.write(f"{char}\n")

    return output_path, final_chars


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Prepare Simpsons dataset for YOLOv8")
    parser.add_argument("--skip-download", action="store_true", help="Skip Kaggle download")
    parser.add_argument("--raw-dir", default="data/raw/simpsons_dataset", help="Raw dataset directory")
    parser.add_argument("--output-dir", default="data/simpsons_yolo", help="Output directory")
    parser.add_argument("--min-images", type=int, default=MIN_IMAGES, help="Minimum images per character")

    args = parser.parse_args()

    if not args.skip_download:
        download_dataset("data/raw")

    prepare_yolo_classification(
        raw_dir=args.raw_dir,
        output_dir=args.output_dir,
        min_images=args.min_images
    )


if __name__ == "__main__":
    main()
