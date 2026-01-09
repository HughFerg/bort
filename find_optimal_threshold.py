#!/usr/bin/env python3
"""
Find optimal character detection threshold to balance coverage vs false positives.
"""
import torch
from pathlib import Path
from PIL import Image
import open_clip
import lancedb
import random

# Load database
db = lancedb.connect("data/simpsons.lance")
table = db.open_table("frames")

# Get sample of frames
dummy_vector = [0.0] * 512
all_frames = table.search(dummy_vector).limit(5915).to_list()
samples = random.sample(all_frames, min(30, len(all_frames)))

# Load model
print("Loading CLIP model...")
model, _, preprocess = open_clip.create_model_and_transforms(
    'ViT-B-32',
    pretrained='laion2b_s34b_b79k'
)
tokenizer = open_clip.get_tokenizer('ViT-B-32')
model.eval()

characters = [
    "Homer Simpson", "Marge Simpson", "Bart Simpson", "Lisa Simpson", "Maggie Simpson",
    "Mr. Burns", "Smithers", "Ned Flanders", "Moe Szyslak", "Barney Gumble",
    "Chief Wiggum", "Apu Nahasapeemapetilon", "Krusty the Clown", "Milhouse Van Houten",
    "Nelson Muntz", "Principal Skinner", "Edna Krabappel", "Groundskeeper Willie",
    "Comic Book Guy", "Sideshow Bob", "Otto Mann", "Patty Bouvier", "Selma Bouvier"
]

def get_top_scores(image_path):
    """Get top character match scores."""
    image = preprocess(Image.open(image_path)).unsqueeze(0)
    text = tokenizer([f"{char}" for char in characters])

    with torch.no_grad():
        image_features = model.encode_image(image)
        text_features = model.encode_text(text)

        image_features /= image_features.norm(dim=-1, keepdim=True)
        text_features /= text_features.norm(dim=-1, keepdim=True)

        similarity = (image_features @ text_features.T)[0]

    scores = [(characters[i], similarity[i].item()) for i in range(len(characters))]
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores

# Analyze score distributions
print("\nAnalyzing score distributions across 30 random frames...")
print("=" * 80)

all_scores = []
for frame in samples:
    scores = get_top_scores(frame["path"])
    all_scores.extend([s[1] for s in scores])

# Statistics
import statistics
mean_score = statistics.mean(all_scores)
median_score = statistics.median(all_scores)
stdev_score = statistics.stdev(all_scores)

print(f"\nScore Statistics (all character matches across 30 frames):")
print(f"  Mean: {mean_score:.3f}")
print(f"  Median: {median_score:.3f}")
print(f"  Std Dev: {stdev_score:.3f}")
print()

# Look at top-1 scores (most likely character in each frame)
top1_scores = []
for frame in samples:
    scores = get_top_scores(frame["path"])
    top1_scores.append(scores[0][1])

print(f"Top-1 Character Scores (most confident match per frame):")
print(f"  Mean: {statistics.mean(top1_scores):.3f}")
print(f"  Min: {min(top1_scores):.3f}")
print(f"  Max: {max(top1_scores):.3f}")
print()

# Recommendation
print("=" * 80)
print("RECOMMENDATIONS:")
print("=" * 80)

# Count how many frames would detect characters at different thresholds
for threshold in [0.26, 0.27, 0.28, 0.29, 0.30]:
    count = sum(1 for score in top1_scores if score >= threshold)
    pct = count / len(top1_scores) * 100
    print(f"  min_score={threshold:.2f}: {count}/{len(top1_scores)} frames ({pct:.1f}%) would detect characters")

print()
print("SUGGESTED SETTINGS:")
print("  For balanced accuracy (fewer false positives):")
print("    min_score=0.27, score_gap=0.03, max_chars=2")
print()
print("  For high coverage (current setting):")
print("    min_score=0.24, score_gap=0.05, max_chars=3")
print()
print("  Note: Moe Szyslak and Smithers appear too frequently because they're")
print("        generic-looking yellow cartoon characters that CLIP confuses with")
print("        other background characters.")
print("=" * 80)
