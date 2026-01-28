#!/usr/bin/env python3
"""
Database optimization script for Bort Search.

Creates vector indexes and optimizes LanceDB for faster search.
"""

import argparse
from pathlib import Path

import lancedb


def create_vector_index(db_path: str = "data/simpsons.lance", force: bool = False):
    """
    Create an IVF-PQ vector index for faster similarity search.

    For ~23k vectors, recommended settings:
    - num_partitions: 64-128 (sqrt of row count is a good starting point)
    - num_sub_vectors: 16-32 (for 512-dim CLIP embeddings)
    """
    print(f"Connecting to database: {db_path}")
    db = lancedb.connect(db_path)
    table = db.open_table("frames")

    row_count = table.count_rows()
    print(f"Table has {row_count:,} rows")

    # Check if index already exists
    indices = table.list_indices()
    if indices and not force:
        print(f"Index already exists: {indices}")
        print("Use --force to rebuild")
        return

    # Calculate optimal partitions (roughly sqrt of row count, min 16)
    import math
    num_partitions = max(16, min(256, int(math.sqrt(row_count))))

    # For 512-dim CLIP embeddings, 16 sub-vectors works well
    num_sub_vectors = 16

    print(f"\nCreating IVF-PQ index...")
    print(f"  num_partitions: {num_partitions}")
    print(f"  num_sub_vectors: {num_sub_vectors}")
    print(f"  metric: cosine (best for CLIP embeddings)")

    table.create_index(
        metric="cosine",
        num_partitions=num_partitions,
        num_sub_vectors=num_sub_vectors,
    )

    print("\n✓ Vector index created successfully!")
    print("\nNew indices:")
    for idx in table.list_indices():
        print(f"  - {idx}")


def get_db_stats(db_path: str = "data/simpsons.lance"):
    """Print database statistics."""
    print(f"Database: {db_path}")
    print("-" * 50)

    db = lancedb.connect(db_path)
    table = db.open_table("frames")

    row_count = table.count_rows()
    print(f"Total frames: {row_count:,}")

    # Get unique episodes
    dummy_vector = [0.0] * 512
    sample = table.search(dummy_vector).limit(row_count).to_list()

    episodes = set(r["episode"] for r in sample)
    print(f"Episodes: {len(episodes)}")

    # Count by season
    seasons = {}
    for ep in episodes:
        match = ep.lower()
        if "s01" in match:
            seasons["S01"] = seasons.get("S01", 0) + 1
        elif "s02" in match:
            seasons["S02"] = seasons.get("S02", 0) + 1
        elif "s03" in match:
            seasons["S03"] = seasons.get("S03", 0) + 1
        else:
            seasons["Other"] = seasons.get("Other", 0) + 1

    print("\nEpisodes by season:")
    for season, count in sorted(seasons.items()):
        print(f"  {season}: {count} episodes")

    # Check indices
    indices = table.list_indices()
    print(f"\nVector indices: {len(indices)}")
    for idx in indices:
        print(f"  - {idx}")

    # Character stats
    chars_count = sum(1 for r in sample if r.get("characters"))
    print(f"\nFrames with characters: {chars_count:,} ({chars_count/row_count*100:.1f}%)")

    captions_count = sum(1 for r in sample if r.get("caption"))
    print(f"Frames with captions: {captions_count:,} ({captions_count/row_count*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Optimize LanceDB for Bort Search")
    parser.add_argument("--db", default="data/simpsons.lance", help="Database path")
    parser.add_argument("--create-index", action="store_true", help="Create vector index")
    parser.add_argument("--force", action="store_true", help="Force rebuild index")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")

    args = parser.parse_args()

    if args.stats:
        get_db_stats(args.db)

    if args.create_index:
        create_vector_index(args.db, args.force)

    if not args.stats and not args.create_index:
        # Default: show stats
        get_db_stats(args.db)


if __name__ == "__main__":
    main()
