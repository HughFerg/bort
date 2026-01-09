#!/usr/bin/env python3
"""
Detect duplicate or near-duplicate frames using perceptual hashing.
Also detect credits/intro sequences based on timing patterns.
"""
import lancedb
from collections import defaultdict, Counter
import numpy as np

db = lancedb.connect("data/simpsons.lance")
table = db.open_table("frames")

# Get all frames
dummy_vector = [0.0] * 512
all_frames = table.search(dummy_vector).limit(5915).to_list()

print("=" * 80)
print("DUPLICATE AND REPETITIVE FRAME ANALYSIS")
print("=" * 80)
print()

# Group by episode
episodes = defaultdict(list)
for frame in all_frames:
    episodes[frame["episode"]].append(frame)

print(f"Total frames: {len(all_frames)}")
print(f"Total episodes: {len(episodes)}")
print()

# Method 1: Detect duplicate embeddings (exact or near-exact visual matches)
print("1. DETECTING DUPLICATE EMBEDDINGS (visually identical frames)")
print("-" * 80)

def vectors_similar(v1, v2, threshold=0.99):
    """Check if two vectors are very similar (cosine similarity)."""
    v1_norm = np.array(v1) / np.linalg.norm(v1)
    v2_norm = np.array(v2) / np.linalg.norm(v2)
    similarity = np.dot(v1_norm, v2_norm)
    return similarity >= threshold

# Find duplicate clusters (this is expensive, so we'll sample)
duplicates_found = 0
sample_size = 500
import random
sampled = random.sample(all_frames, min(sample_size, len(all_frames)))

for i, frame1 in enumerate(sampled):
    if i % 100 == 0:
        print(f"  Checking frame {i}/{len(sampled)}...")

    for frame2 in sampled[i+1:]:
        if frame1["episode"] == frame2["episode"]:
            if vectors_similar(frame1["vector"], frame2["vector"]):
                duplicates_found += 1
                if duplicates_found <= 5:  # Show first 5 examples
                    print(f"  Duplicate: {frame1['episode']} @ {frame1['timestamp']}s <-> @ {frame2['timestamp']}s")

print(f"  Found ~{duplicates_found} near-duplicate pairs in sample of {sample_size} frames")
estimated_total = int(duplicates_found * (len(all_frames) / sample_size))
print(f"  Estimated ~{estimated_total} duplicates across full dataset")
print()

# Method 2: Detect credits/intro by timing patterns
print("2. DETECTING INTRO/CREDIT SEQUENCES")
print("-" * 80)

for ep_name, frames in sorted(episodes.items())[:3]:  # Show first 3 episodes
    timestamps = sorted([f["timestamp"] for f in frames])

    # Intro typically at start (0-90 seconds)
    intro_frames = [t for t in timestamps if t <= 90]

    # Credits typically at end (last 60 seconds of episode)
    if timestamps:
        episode_length = max(timestamps)
        credits_frames = [t for t in timestamps if t >= episode_length - 60]

        print(f"{ep_name}:")
        print(f"  Total frames: {len(frames)}")
        print(f"  Intro frames (0-90s): {len(intro_frames)}")
        print(f"  Credits frames (last 60s): {len(credits_frames)}")
        print(f"  Main content: {len(frames) - len(intro_frames) - len(credits_frames)}")
        print()

# Method 3: Detect repetitive captions (static screens, repeated text)
print("3. DETECTING REPETITIVE CAPTIONS")
print("-" * 80)

caption_counts = Counter(frame.get("caption", "") for frame in all_frames if frame.get("caption"))
most_common = caption_counts.most_common(20)

print("Most repeated captions (likely credits, title cards, static screens):")
for caption, count in most_common:
    if count > 10:  # Only show captions appearing >10 times
        pct = count / len(all_frames) * 100
        print(f"  {count:3d}x ({pct:4.1f}%) - {caption}")

print()
print("=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)
print()
print("1. FILTER OUT INTRO/CREDITS:")
print("   - Remove frames with timestamp 0-90s (intro sequence)")
print("   - Remove frames in last 60s of episode (credits)")
print(f"   - This would remove ~{sum(len([f for f in frames if f['timestamp'] <= 90 or f['timestamp'] >= max(f2['timestamp'] for f2 in frames) - 60]) for frames in episodes.values())} frames")
print()
print("2. DEDUPLICATE BASED ON EMBEDDINGS:")
print(f"   - Could remove ~{estimated_total} near-duplicate frames")
print("   - Use cosine similarity threshold of 0.99 on embeddings")
print()
print("3. FILTER REPETITIVE CAPTIONS:")
print("   - Remove frames with captions appearing >50 times (title cards, etc)")
print()
print("Would you like me to implement these filters in the indexing pipeline?")
print("=" * 80)
