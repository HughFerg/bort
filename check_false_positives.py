#!/usr/bin/env python3
"""
Check for false positive character detections.
"""
import lancedb
import random
from pathlib import Path

db = lancedb.connect("data/simpsons.lance")
table = db.open_table("frames")

# Get all frames
dummy_vector = [0.0] * 512
all_frames = table.search(dummy_vector).limit(5915).to_list()

# Get frames with characters
frames_with_chars = [f for f in all_frames if f.get("characters", "").strip()]

# Sample some
samples = random.sample(frames_with_chars, min(20, len(frames_with_chars)))

print("=" * 80)
print("CHECKING FOR FALSE POSITIVE CHARACTER DETECTIONS")
print("=" * 80)
print()
print("Review these frames to see if character detections look reasonable:")
print()

for i, frame in enumerate(samples, 1):
    episode = frame["episode"]
    frame_name = Path(frame["path"]).name
    caption = frame.get("caption", "")
    characters = frame.get("characters", "")
    timestamp = frame["timestamp"]

    print(f"{i}. {episode} @ {timestamp}s ({frame_name})")
    print(f"   Caption: {caption}")
    print(f"   Detected: {characters}")
    print(f"   Path: {frame['path']}")
    print()

print("=" * 80)
print("MANUAL REVIEW NEEDED:")
print("Open a few of these images and check if the character tags are correct.")
print("If you see many false positives, we may need to raise min_score from 0.24")
print("=" * 80)
