#!/usr/bin/env python3
"""
Analyze character detection accuracy across the database.
"""
import lancedb

db = lancedb.connect("data/simpsons.lance")
table = db.open_table("frames")

# Get all frames using dummy search
dummy_vector = [0.0] * 512
all_frames = table.search(dummy_vector).limit(5915).to_list()

print("📊 CHARACTER DETECTION ANALYSIS")
print("=" * 70)

# Stats
total_frames = len(all_frames)
frames_with_chars = sum(1 for f in all_frames if f.get("characters", "").strip())
frames_without = total_frames - frames_with_chars

print(f"Total frames: {total_frames}")
print(f"Frames with characters detected: {frames_with_chars} ({frames_with_chars/total_frames*100:.1f}%)")
print(f"Frames without characters: {frames_without} ({frames_without/total_frames*100:.1f}%)")
print()

# Character frequency
from collections import Counter
char_counts = Counter()

for frame in all_frames:
    chars = frame.get("characters", "")
    if chars:
        for char in chars.split(", "):
            if char.strip():
                char_counts[char.strip()] += 1

print("Top 20 Most Detected Characters:")
print("-" * 70)
for char, count in char_counts.most_common(20):
    percentage = count / total_frames * 100
    print(f"{char:30s} {count:5d} frames ({percentage:5.1f}%)")

print()
print(f"Total unique characters detected: {len(char_counts)}")
