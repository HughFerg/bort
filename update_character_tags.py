#!/usr/bin/env python3
"""
Update character tags in the database using the trained YOLO model.
"""

import lancedb
from pathlib import Path
from tqdm import tqdm

# Import YOLO
from ultralytics import YOLO

# Character name mapping (YOLO class names to display names)
NAME_MAP = {
    "homer_simpson": "Homer",
    "marge_simpson": "Marge",
    "bart_simpson": "Bart",
    "lisa_simpson": "Lisa",
    "maggie_simpson": "Maggie",
    "abraham_grampa_simpson": "Grampa",
    "apu_nahasapeemapetilon": "Apu",
    "barney_gumble": "Barney",
    "charles_montgomery_burns": "Mr. Burns",
    "chief_wiggum": "Chief Wiggum",
    "comic_book_guy": "Comic Book Guy",
    "edna_krabappel": "Edna Krabappel",
    "groundskeeper_willie": "Groundskeeper Willie",
    "krusty_the_clown": "Krusty",
    "lenny_leonard": "Lenny",
    "milhouse_van_houten": "Milhouse",
    "moe_szyslak": "Moe",
    "ned_flanders": "Ned Flanders",
    "nelson_muntz": "Nelson",
    "principal_skinner": "Principal Skinner",
    "sideshow_bob": "Sideshow Bob",
    "carl_carlson": "Carl",
    "kent_brockman": "Kent Brockman",
    "martin_prince": "Martin",
    "mayor_quimby": "Mayor Quimby",
    "patty_bouvier": "Patty",
    "professor_john_frink": "Professor Frink",
    "ralph_wiggum": "Ralph",
    "selma_bouvier": "Selma",
    "snake_jailbird": "Snake",
    "waylon_smithers": "Smithers",
}


def clean_name(name: str) -> str:
    """Convert YOLO class name to display name."""
    return NAME_MAP.get(name, name.replace("_", " ").title())


def detect_characters(model, image_path: str, threshold: float = 0.5, max_chars: int = 3) -> list[str]:
    """Detect characters using YOLO model."""
    results = model(image_path, verbose=False)

    detected = []
    for result in results:
        probs = result.probs
        if probs is None:
            continue

        # Get top predictions above threshold
        for idx, conf in zip(probs.top5, probs.top5conf):
            if conf.item() >= threshold and len(detected) < max_chars:
                name = model.names[idx]
                clean = clean_name(name)
                detected.append(clean)

    return detected


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Update character tags with YOLO")
    parser.add_argument("--db", default="data/simpsons.lance", help="Database path")
    parser.add_argument("--model", default="models/simpsons_classifier.pt", help="YOLO model path")
    parser.add_argument("--threshold", type=float, default=0.5, help="Confidence threshold")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for updates")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually update, just show stats")
    args = parser.parse_args()

    # Load model
    print(f"Loading YOLO model: {args.model}")
    model = YOLO(args.model)
    print(f"  Can detect {len(model.names)} characters")

    # Connect to database
    print(f"Connecting to database: {args.db}")
    db = lancedb.connect(args.db)
    table = db.open_table("frames")

    # Get all records
    print("Reading all frames from database...")
    df = table.to_pandas()
    total = len(df)
    print(f"  Found {total} frames")

    if args.dry_run:
        # Just test on a few frames
        print("\nDry run - testing on first 10 frames...")
        for i, row in df.head(10).iterrows():
            old_chars = row['characters']
            new_chars = detect_characters(model, row['path'], args.threshold)
            print(f"  {row['frame']}: '{old_chars}' -> '{', '.join(new_chars)}'")
        return

    # Process all frames and update characters
    print(f"\nUpdating character tags (threshold={args.threshold})...")

    updated_records = []
    for i, row in tqdm(df.iterrows(), total=total, desc="Processing"):
        # Detect characters with YOLO
        new_chars = detect_characters(model, row['path'], args.threshold)

        # Create updated record
        record = row.to_dict()
        record['characters'] = ", ".join(new_chars) if new_chars else ""
        updated_records.append(record)

    # Recreate table with updated records
    print(f"\nWriting {len(updated_records)} updated records to database...")
    db.create_table("frames", updated_records, mode="overwrite")

    print("Done!")

    # Show stats
    chars_count = sum(1 for r in updated_records if r['characters'])
    print(f"\nStats:")
    print(f"  Total frames: {len(updated_records)}")
    print(f"  Frames with characters: {chars_count} ({100*chars_count/len(updated_records):.1f}%)")


if __name__ == "__main__":
    main()
