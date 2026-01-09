#!/usr/bin/env python3
"""
Create a ground truth test set for evaluation.

This helps you manually label some frames so you can measure precision/recall.
"""
import json
import random
import lancedb

db = lancedb.connect("data/simpsons.lance")
table = db.open_table("frames")

# Get random sample
count = table.count_rows()
samples = []

print("Creating ground truth test set...")
print("This will show you 10 random frames for manual labeling.")
print()

for i in range(10):
    offset = random.randint(0, count - 1)
    dummy_vector = [0.0] * 512
    result = table.search(dummy_vector).limit(1).offset(offset).to_list()[0]

    print(f"Frame {i+1}/10:")
    print(f"  Episode: {result['episode']}")
    print(f"  Time: {result['timestamp']}s")
    print(f"  Caption: {result['caption']}")
    print(f"  Detected Characters: {result.get('characters', 'None')}")
    print(f"  Path: {result['path']}")
    print()

    # You would manually review the image and add true labels
    samples.append({
        "episode": result['episode'],
        "frame": result['frame'],
        "timestamp": result['timestamp'],
        "detected_caption": result['caption'],
        "detected_characters": result.get('characters', ''),
        "true_caption": "",  # Fill in manually
        "true_characters": [],  # Fill in manually
        "notes": ""  # Fill in manually
    })

# Save for manual labeling
with open("ground_truth.json", "w") as f:
    json.dump(samples, f, indent=2)

print("✅ Saved to ground_truth.json")
print("Next steps:")
print("  1. Open each frame image")
print("  2. Fill in 'true_caption' and 'true_characters' fields")
print("  3. Run evaluation script to compare detected vs. true labels")
