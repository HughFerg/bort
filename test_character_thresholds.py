#!/usr/bin/env python3
"""
Test different character detection thresholds on sample frames.
"""
import torch
from pathlib import Path
from PIL import Image
import open_clip
import random

# Load model
print("Loading CLIP model...")
model, _, preprocess = open_clip.create_model_and_transforms(
    'ViT-B-32',
    pretrained='laion2b_s34b_b79k'
)
tokenizer = open_clip.get_tokenizer('ViT-B-32')
model.eval()

# Character list
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

    return detected, scores[:5]  # Return detected + top 5 scores for analysis

# Get sample frames
frames_dir = Path("data/frames")
all_frames = []
for episode_dir in frames_dir.iterdir():
    if episode_dir.is_dir():
        all_frames.extend(list(episode_dir.glob("*.jpg")))

# Test on random sample
sample_size = 10
samples = random.sample(all_frames, min(sample_size, len(all_frames)))

print(f"\n{'='*80}")
print("TESTING DIFFERENT THRESHOLDS ON {len(samples)} RANDOM FRAMES")
print(f"{'='*80}\n")

configs = [
    {"min_score": 0.30, "score_gap": 0.03, "max_chars": 2, "name": "CURRENT"},
    {"min_score": 0.25, "score_gap": 0.05, "max_chars": 2, "name": "RELAXED"},
    {"min_score": 0.22, "score_gap": 0.06, "max_chars": 3, "name": "MORE RELAXED"},
    {"min_score": 0.20, "score_gap": 0.08, "max_chars": 3, "name": "VERY RELAXED"},
]

for i, frame_path in enumerate(samples, 1):
    print(f"Frame {i}: {frame_path.parent.name}/{frame_path.name}")
    print("-" * 80)

    for config in configs:
        detected, top_scores = detect_with_threshold(
            frame_path,
            config["min_score"],
            config["score_gap"],
            config["max_chars"]
        )

        print(f"{config['name']:15s} (min={config['min_score']}, gap={config['score_gap']}, max={config['max_chars']})")
        if detected:
            chars_str = ", ".join([f"{name} ({score:.3f})" for name, score in detected])
            print(f"  → {chars_str}")
        else:
            print(f"  → No characters detected")
            print(f"     Top scores: {', '.join([f'{characters[idx]} ({score:.3f})' for idx, score in top_scores[:3]])}")

    print()

# Statistics
print(f"\n{'='*80}")
print("SUMMARY - Detection Rate Comparison")
print(f"{'='*80}\n")

for config in configs:
    detected_count = 0
    for frame_path in samples:
        detected, _ = detect_with_threshold(
            frame_path,
            config["min_score"],
            config["score_gap"],
            config["max_chars"]
        )
        if detected:
            detected_count += 1

    rate = detected_count / len(samples) * 100
    print(f"{config['name']:15s}: {detected_count}/{len(samples)} frames ({rate:.1f}%) have characters detected")
