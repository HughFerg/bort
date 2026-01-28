#!/usr/bin/env python3
"""
Detect and remove black/white/blank frames from the index.

These frames are common in:
- Credits (black screen with white text)
- Scene transitions (fade to black/white)
- End of episodes
- Commercial breaks
"""

import argparse
from pathlib import Path

import lancedb
import numpy as np
from PIL import Image
from tqdm import tqdm


def analyze_frame(image_path: str) -> dict:
    """
    Analyze a frame for black/white/blank characteristics.

    Args:
        image_path: Path to image file

    Returns:
        Dict with analysis results
    """
    try:
        img = Image.open(image_path).convert('L')  # Convert to grayscale
        pixels = np.array(img)

        # Basic stats
        mean_brightness = np.mean(pixels)
        std_dev = np.std(pixels)
        min_val = np.min(pixels)
        max_val = np.max(pixels)

        # Count dark and bright pixels
        black_pixels = np.sum(pixels < 30)
        white_pixels = np.sum(pixels > 225)
        total_pixels = pixels.size

        return {
            "mean": mean_brightness,
            "std": std_dev,
            "min": min_val,
            "max": max_val,
            "black_pct": black_pixels / total_pixels,
            "white_pct": white_pixels / total_pixels,
            "error": None
        }

    except Exception as e:
        return {"error": str(e)}


def is_blank_frame(image_path: str, black_threshold: int = 30, white_threshold: int = 225,
                   percentage: float = 0.95, min_std: float = 10.0) -> tuple[bool, str, float]:
    """
    Detect if a frame is blank (black, white, or very low contrast).

    Args:
        image_path: Path to image file
        black_threshold: Pixels below this are "black" (0-255)
        white_threshold: Pixels above this are "white" (0-255)
        percentage: Percentage of pixels for black/white detection
        min_std: Minimum standard deviation for "content" (low = uniform/blank)

    Returns:
        Tuple of (is_blank, reason, value)
    """
    analysis = analyze_frame(image_path)

    if analysis.get("error"):
        return False, "error", 0.0

    # Check for mostly black
    if analysis["black_pct"] >= percentage:
        return True, "black", analysis["black_pct"]

    # Check for mostly white
    if analysis["white_pct"] >= percentage:
        return True, "white", analysis["white_pct"]

    # Check for very low contrast (uniform color)
    if analysis["std"] < min_std and analysis["mean"] < 50:
        return True, "low_contrast_dark", analysis["std"]

    if analysis["std"] < min_std and analysis["mean"] > 200:
        return True, "low_contrast_bright", analysis["std"]

    return False, "ok", 0.0


def is_black_frame(image_path: str, threshold: int = 30, black_percentage: float = 0.95) -> tuple[bool, float]:
    """
    Detect if a frame is mostly black (legacy function for compatibility).

    Args:
        image_path: Path to image file
        threshold: Pixel brightness threshold (0-255). Pixels below this are "black"
        black_percentage: Percentage of pixels that must be black (0.0-1.0)

    Returns:
        Tuple of (is_black, actual_black_percentage)
    """
    is_blank, reason, value = is_blank_frame(image_path, black_threshold=threshold, percentage=black_percentage)
    if reason == "black":
        return True, value
    return False, 0.0


def detect_blank_frames(
    db_path: str = "data/simpsons.lance",
    black_threshold: int = 30,
    white_threshold: int = 225,
    percentage: float = 0.95,
    min_std: float = 10.0,
    dry_run: bool = True
) -> list[dict]:
    """
    Scan database for blank frames (black, white, or low contrast).

    Args:
        db_path: Path to LanceDB database
        black_threshold: Pixels below this are "black" (0-255)
        white_threshold: Pixels above this are "white" (0-255)
        percentage: Percentage of pixels for black/white detection
        min_std: Minimum standard deviation for "content"
        dry_run: If True, only report findings without deleting

    Returns:
        List of blank frames found
    """
    print("Connecting to database...")
    db = lancedb.connect(db_path)
    table = db.open_table("frames")

    print("Loading all frames...")
    dummy_vector = [0.0] * 512
    count = table.count_rows()
    all_frames = table.search(dummy_vector).limit(count).to_list()

    print(f"Scanning {len(all_frames)} frames for blank frames...")
    print(f"Black threshold: pixels < {black_threshold} brightness")
    print(f"White threshold: pixels > {white_threshold} brightness")
    print(f"Required: {percentage * 100}% black/white pixels")
    print(f"Min std deviation: {min_std}\n")

    blank_frames = []

    for frame in tqdm(all_frames, desc="Checking frames"):
        path = frame["path"]

        if not Path(path).exists():
            continue

        is_blank, reason, value = is_blank_frame(
            path, black_threshold, white_threshold, percentage, min_std
        )

        if is_blank:
            blank_frames.append({
                "path": path,
                "episode": frame["episode"],
                "frame": frame["frame"],
                "timestamp": frame["timestamp"],
                "reason": reason,
                "value": value,
                "caption": frame.get("caption", "")
            })

    # Sort by episode and timestamp
    blank_frames.sort(key=lambda x: (x["episode"], x["timestamp"]))

    # Count by reason
    from collections import Counter, defaultdict
    reason_counts = Counter(bf["reason"] for bf in blank_frames)

    print(f"\n{'='*80}")
    print(f"RESULTS: Found {len(blank_frames)} blank frames ({len(blank_frames)/len(all_frames)*100:.1f}%)")
    print(f"{'='*80}")
    for reason, cnt in reason_counts.most_common():
        print(f"  {reason}: {cnt}")
    print()

    if blank_frames:
        # Group by episode
        by_episode = defaultdict(list)
        for bf in blank_frames:
            by_episode[bf["episode"]].append(bf)

        for episode, frames in sorted(by_episode.items()):
            print(f"{episode}: {len(frames)} blank frames")
            for bf in frames[:3]:  # Show first 3
                print(f"  - {bf['frame']} @ {bf['timestamp']}s ({bf['reason']}: {bf['value']:.2f})")
            if len(frames) > 3:
                print(f"  ... and {len(frames)-3} more")
            print()

    if not dry_run and blank_frames:
        print(f"\nDeleting {len(blank_frames)} blank frames from index...")
        for bf in tqdm(blank_frames, desc="Deleting"):
            table.delete(f"path = '{bf['path']}'")
        print("✓ Deletion complete")

        # Show new stats
        new_count = table.count_rows()
        print(f"\nFrames remaining: {new_count} (removed {count - new_count})")
    elif blank_frames:
        print(f"\nDRY RUN: Would delete {len(blank_frames)} frames")
        print("Run with --delete to actually remove them")

    return blank_frames


# Legacy function name for compatibility
def detect_black_frames(
    db_path: str = "data/simpsons.lance",
    threshold: int = 30,
    black_percentage: float = 0.95,
    dry_run: bool = True
) -> list[dict]:
    """Legacy function - now calls detect_blank_frames."""
    return detect_blank_frames(
        db_path=db_path,
        black_threshold=threshold,
        percentage=black_percentage,
        dry_run=dry_run
    )


def main():
    parser = argparse.ArgumentParser(
        description="Detect and remove black frames from the index"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/simpsons.lance",
        help="Path to LanceDB database (default: data/simpsons.lance)"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=30,
        help="Brightness threshold for black pixels (0-255, default: 30)"
    )
    parser.add_argument(
        "--percentage",
        type=float,
        default=0.95,
        help="Percentage of pixels that must be black (0.0-1.0, default: 0.95)"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete black frames (default: dry run only)"
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show all black frames, not just first 3 per episode"
    )

    args = parser.parse_args()

    black_frames = detect_black_frames(
        db_path=args.db,
        threshold=args.threshold,
        black_percentage=args.percentage,
        dry_run=not args.delete
    )

    if args.show_all and black_frames:
        print(f"\n{'='*80}")
        print("ALL BLACK FRAMES:")
        print(f"{'='*80}\n")
        for bf in black_frames:
            print(f"{bf['episode']} - {bf['frame']} @ {bf['timestamp']}s")
            print(f"  Path: {bf['path']}")
            print(f"  Black: {bf['black_percentage']*100:.1f}%")
            if bf['caption']:
                print(f"  Caption: {bf['caption']}")
            print()


if __name__ == "__main__":
    main()
