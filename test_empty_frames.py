#!/usr/bin/env python3
"""
Test character detection on frames that currently have no characters.
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

# Get frames with no characters
dummy_vector = [0.0] * 512
all_frames = table.search(dummy_vector).limit(5915).to_list()
empty_frames = [f for f in all_frames if not f.get("characters", "").strip()]

print(f"Found {len(empty_frames)} frames with no characters detected")
print(f"Sampling 15 random frames to test...\n")

# Sample some
samples = random.sample(empty_frames, min(15, len(empty_frames)))

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

def detect_with_threshold(image_path, min_score, score_gap, max_chars):
    """Detect characters with given thresholds."""
    image = preprocess(Image.open(image_path)).unsqueeze(0)
    text = tokenizer([f"{char}" for char in characters])

    with torch.no_grad():
        image_features = model.encode_image(image)
        text_features = model.encode_text(text)

        image_features /= image_features.norm(dim=-1, keepdim=True)
        text_features /= text_features.norm(dim=-1, keepdim=True)

        similarity = (image_features @ text_features.T)[0]

    scores = [(i, similarity[i].item()) for i in range(len(characters))]
    scores.sort(key=lambda x: x[1], reverse=True)

    detected = []
    if scores and scores[0][1] >= min_score:
        top_score = scores[0][1]
        for i, score in scores[:max_chars]:
            if score >= min_score and (top_score - score) <= score_gap:
                char_name = characters[i].replace(" Simpson", "")
                detected.append((char_name, score))

    return detected, scores[:5]

configs = [
    {"min_score": 0.30, "score_gap": 0.03, "max_chars": 2, "name": "CURRENT"},
    {"min_score": 0.24, "score_gap": 0.05, "max_chars": 3, "name": "RECOMMENDED"},
]

improved_count = 0

print("=" * 80)
for i, frame in enumerate(samples, 1):
    frame_path = frame["path"]
    print(f"\nFrame {i}: {frame['episode']}/{Path(frame_path).name}")
    print(f"Caption: {frame.get('caption', 'N/A')}")
    print("-" * 80)

    current_detected, _ = detect_with_threshold(frame_path, 0.30, 0.03, 2)
    recommended_detected, top_scores = detect_with_threshold(frame_path, 0.24, 0.05, 3)

    print(f"CURRENT (0.30):       ", end="")
    if current_detected:
        print(", ".join([f"{name} ({score:.3f})" for name, score in current_detected]))
    else:
        print("No characters")

    print(f"RECOMMENDED (0.24):   ", end="")
    if recommended_detected:
        print(", ".join([f"{name} ({score:.3f})" for name, score in recommended_detected]))
        if not current_detected:
            improved_count += 1
            print("  ✓ IMPROVEMENT!")
    else:
        print("No characters")
        # Show why it failed
        print(f"  Top scores: {', '.join([f'{characters[idx]} ({score:.3f})' for idx, score in top_scores[:3]])}")

print("\n" + "=" * 80)
print(f"SUMMARY: Recommended settings would detect characters in {improved_count}/{len(samples)} previously empty frames")
print("=" * 80)
