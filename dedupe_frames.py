#!/usr/bin/env python3
"""
Find and remove duplicate/very similar consecutive frames.

Consecutive frames that are nearly identical (e.g., static shots) can be
deduplicated to reduce index size and improve search diversity.
"""

import argparse
from collections import defaultdict
from pathlib import Path

import lancedb
import numpy as np
from tqdm import tqdm


def cosine_similarity(v1: list, v2: list) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(v1)
    b = np.array(v2)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def find_duplicates(
    db_path: str = "data/simpsons.lance",
    similarity_threshold: float = 0.98,
    dry_run: bool = True
) -> list[str]:
    """
    Find duplicate frames based on embedding similarity.

    Args:
        db_path: Path to LanceDB database
        similarity_threshold: Frames above this similarity are considered duplicates
        dry_run: If True, only report findings without deleting

    Returns:
        List of paths to duplicate frames
    """
    print(f"Connecting to database: {db_path}")
    db = lancedb.connect(db_path)
    table = db.open_table("frames")

    row_count = table.count_rows()
    print(f"Total frames: {row_count:,}")
    print(f"Similarity threshold: {similarity_threshold}")

    # Get all frames grouped by episode
    print("\nLoading all frames...")
    dummy_vector = [0.0] * 512
    all_frames = table.search(dummy_vector).limit(row_count).to_list()

    # Group by episode
    by_episode = defaultdict(list)
    for frame in all_frames:
        by_episode[frame["episode"]].append(frame)

    # Sort each episode's frames by timestamp
    for episode in by_episode:
        by_episode[episode].sort(key=lambda x: x["timestamp"])

    duplicates = []
    total_checked = 0

    print(f"\nChecking {len(by_episode)} episodes for consecutive duplicates...")

    for episode, frames in tqdm(by_episode.items(), desc="Checking episodes"):
        if len(frames) < 2:
            continue

        prev_frame = frames[0]
        for frame in frames[1:]:
            total_checked += 1

            # Only check consecutive frames (within ~6 seconds)
            time_diff = frame["timestamp"] - prev_frame["timestamp"]
            if time_diff > 6:
                prev_frame = frame
                continue

            # Calculate similarity
            sim = cosine_similarity(prev_frame["vector"], frame["vector"])

            if sim >= similarity_threshold:
                # Keep the first frame, mark the second as duplicate
                duplicates.append({
                    "path": frame["path"],
                    "episode": episode,
                    "timestamp": frame["timestamp"],
                    "similarity": sim,
                    "prev_timestamp": prev_frame["timestamp"]
                })
            else:
                # Update prev_frame only if current is not a duplicate
                prev_frame = frame

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"Frames checked: {total_checked:,}")
    print(f"Duplicates found: {len(duplicates):,} ({len(duplicates)/row_count*100:.1f}%)")

    if duplicates:
        # Show sample duplicates
        print(f"\nSample duplicates (first 10):")
        for dup in duplicates[:10]:
            print(f"  {dup['episode']} @ {dup['timestamp']}s (sim: {dup['similarity']:.3f})")

        if not dry_run:
            print(f"\nDeleting {len(duplicates)} duplicate frames...")
            for dup in tqdm(duplicates, desc="Deleting"):
                table.delete(f"path = '{dup['path']}'")

            new_count = table.count_rows()
            print(f"\n✓ Deleted {len(duplicates)} frames")
            print(f"Frames remaining: {new_count:,}")
        else:
            print(f"\nDRY RUN: Would delete {len(duplicates)} frames")
            print("Run with --delete to actually remove them")

    return [d["path"] for d in duplicates]


def main():
    parser = argparse.ArgumentParser(
        description="Find and remove duplicate frames from the index"
    )
    parser.add_argument(
        "--db",
        default="data/simpsons.lance",
        help="Path to LanceDB database"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.98,
        help="Similarity threshold (0.0-1.0, default: 0.98)"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete duplicates (default: dry run)"
    )

    args = parser.parse_args()

    find_duplicates(
        db_path=args.db,
        similarity_threshold=args.threshold,
        dry_run=not args.delete
    )


if __name__ == "__main__":
    main()
