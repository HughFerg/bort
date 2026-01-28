#!/usr/bin/env python3
"""
Generate WebP thumbnails for existing frame images.

This script creates optimized thumbnails for the grid view, significantly
reducing storage and bandwidth usage while maintaining visual quality.

Thumbnails are:
- 480x270 resolution (16:9 aspect ratio)
- WebP format with 80% quality
- ~15-25KB each vs ~170KB for full-res JPEGs

Usage:
    python generate_thumbnails.py                    # Process all frames
    python generate_thumbnails.py --workers 8       # Use 8 parallel workers
    python generate_thumbnails.py --quality 75      # Lower quality, smaller files
    python generate_thumbnails.py --dry-run         # Preview without processing
"""

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image
from tqdm import tqdm

# Thumbnail settings
THUMB_WIDTH = 480
THUMB_HEIGHT = 270
THUMB_QUALITY = 80
THUMB_SUFFIX = "_thumb.webp"


def generate_thumbnail(args: tuple) -> tuple[str, bool, str]:
    """
    Generate a single thumbnail.

    Args:
        args: Tuple of (source_path, thumb_path, quality)

    Returns:
        Tuple of (source_path, success, message)
    """
    source_path, thumb_path, quality = args

    try:
        # Skip if thumbnail already exists and is newer than source
        if thumb_path.exists():
            if thumb_path.stat().st_mtime >= Path(source_path).stat().st_mtime:
                return (str(source_path), True, "skipped (exists)")

        # Open and resize image
        with Image.open(source_path) as img:
            # Convert to RGB if necessary (for PNG with alpha)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # Resize maintaining aspect ratio
            img.thumbnail((THUMB_WIDTH, THUMB_HEIGHT), Image.Resampling.LANCZOS)

            # Ensure exact dimensions by padding if needed (shouldn't happen for 16:9)
            if img.size != (THUMB_WIDTH, THUMB_HEIGHT):
                # Create new image with exact dimensions
                new_img = Image.new('RGB', (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0))
                # Paste centered
                offset = ((THUMB_WIDTH - img.width) // 2, (THUMB_HEIGHT - img.height) // 2)
                new_img.paste(img, offset)
                img = new_img

            # Save as WebP
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(thumb_path, 'WEBP', quality=quality, method=6)

        return (str(source_path), True, "created")

    except Exception as e:
        return (str(source_path), False, str(e))


def get_frame_paths(frames_dir: Path) -> list[tuple[Path, Path]]:
    """Get all source frames and their corresponding thumbnail paths."""
    pairs = []

    for episode_dir in sorted(frames_dir.iterdir()):
        if not episode_dir.is_dir():
            continue

        # Create thumbnails directory structure
        thumb_dir = frames_dir.parent / "thumbnails" / episode_dir.name

        for frame_path in sorted(episode_dir.glob("*.jpg")):
            thumb_name = frame_path.stem + THUMB_SUFFIX
            thumb_path = thumb_dir / thumb_name
            pairs.append((frame_path, thumb_path))

    return pairs


def main():
    parser = argparse.ArgumentParser(
        description="Generate WebP thumbnails for frame images"
    )
    parser.add_argument(
        "--frames-dir",
        type=str,
        default="data/frames",
        help="Directory containing frame images (default: data/frames)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)"
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=THUMB_QUALITY,
        help=f"WebP quality 1-100 (default: {THUMB_QUALITY})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without processing"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate all thumbnails even if they exist"
    )

    args = parser.parse_args()

    frames_dir = Path(args.frames_dir)
    if not frames_dir.exists():
        print(f"Error: Frames directory not found: {frames_dir}")
        sys.exit(1)

    # Get all frame paths
    print(f"Scanning {frames_dir}...")
    frame_pairs = get_frame_paths(frames_dir)

    if not frame_pairs:
        print("No frames found to process")
        sys.exit(0)

    print(f"Found {len(frame_pairs)} frames")

    # Filter out existing thumbnails unless --force
    if not args.force:
        to_process = []
        skipped = 0
        for source, thumb in frame_pairs:
            if thumb.exists() and thumb.stat().st_mtime >= source.stat().st_mtime:
                skipped += 1
            else:
                to_process.append((source, thumb))

        if skipped:
            print(f"Skipping {skipped} existing thumbnails (use --force to regenerate)")
        frame_pairs = to_process

    if not frame_pairs:
        print("All thumbnails are up to date")
        sys.exit(0)

    if args.dry_run:
        print(f"\nDry run - would process {len(frame_pairs)} frames:")
        for source, thumb in frame_pairs[:10]:
            print(f"  {source} -> {thumb}")
        if len(frame_pairs) > 10:
            print(f"  ... and {len(frame_pairs) - 10} more")
        sys.exit(0)

    # Calculate expected savings
    avg_source_size = 170 * 1024  # ~170KB average
    avg_thumb_size = 20 * 1024    # ~20KB average
    total_source = len(frame_pairs) * avg_source_size
    total_thumb = len(frame_pairs) * avg_thumb_size
    savings = total_source - total_thumb

    print(f"\nGenerating {len(frame_pairs)} thumbnails...")
    print(f"Expected storage for thumbnails: ~{total_thumb / (1024*1024):.1f} MB")
    print(f"Potential bandwidth savings: ~{savings / (1024*1024):.1f} MB per full load")
    print()

    # Prepare work items
    work_items = [(str(source), thumb, args.quality) for source, thumb in frame_pairs]

    # Process in parallel
    created = 0
    failed = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(generate_thumbnail, item): item for item in work_items}

        with tqdm(total=len(futures), desc="Generating thumbnails") as pbar:
            for future in as_completed(futures):
                source, success, message = future.result()
                if success:
                    if message == "created":
                        created += 1
                else:
                    failed += 1
                    tqdm.write(f"Error: {source}: {message}")
                pbar.update(1)

    print(f"\nComplete: {created} created, {failed} failed")

    # Report actual storage
    thumb_dir = frames_dir.parent / "thumbnails"
    if thumb_dir.exists():
        total_size = sum(f.stat().st_size for f in thumb_dir.rglob("*.webp"))
        print(f"Total thumbnail storage: {total_size / (1024*1024):.1f} MB")


if __name__ == "__main__":
    main()
