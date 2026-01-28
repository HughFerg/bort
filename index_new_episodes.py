#!/usr/bin/env python3
"""
Index only new episodes that aren't already in the database.
"""

import argparse
from pathlib import Path

import lancedb
import open_clip
import torch
from PIL import Image
from tqdm import tqdm
from transformers import BlipProcessor, BlipForConditionalGeneration


def embed_image(image_path: str, model, preprocess) -> list[float]:
    """Generate CLIP embedding for an image."""
    image = preprocess(Image.open(image_path)).unsqueeze(0)
    with torch.no_grad():
        embedding = model.encode_image(image)
        embedding /= embedding.norm(dim=-1, keepdim=True)
    return embedding[0].tolist()


def generate_caption(image_path: str, processor, caption_model) -> str:
    """Generate a caption for an image using BLIP."""
    image = Image.open(image_path).convert('RGB')
    inputs = processor(image, return_tensors="pt")
    with torch.no_grad():
        outputs = caption_model.generate(**inputs, max_length=50)
    caption = processor.decode(outputs[0], skip_special_tokens=True)
    return caption


def detect_characters_clip(image_path: str, model, preprocess, tokenizer) -> list[str]:
    """Detect Simpsons characters using zero-shot CLIP classification."""
    characters = [
        "Homer Simpson", "Marge Simpson", "Bart Simpson", "Lisa Simpson", "Maggie Simpson",
        "Mr. Burns", "Smithers", "Ned Flanders", "Moe Szyslak", "Barney Gumble",
        "Chief Wiggum", "Apu Nahasapeemapetilon", "Krusty the Clown", "Milhouse Van Houten",
        "Nelson Muntz", "Principal Skinner", "Edna Krabappel", "Groundskeeper Willie",
        "Comic Book Guy", "Sideshow Bob", "Otto Mann", "Patty Bouvier", "Selma Bouvier"
    ]

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
    min_score = 0.27
    score_gap = 0.04
    max_chars = 10

    if scores and scores[0][1] >= min_score:
        top_score = scores[0][1]
        for i, score in scores[:max_chars]:
            if score >= min_score and (top_score - score) <= score_gap:
                char_name = characters[i].replace(" Simpson", "")
                detected.append(char_name)

    return detected


def index_new_episodes(
    frames_dir: str = "data/frames",
    db_path: str = "data/simpsons.lance",
    frame_interval: int = 3,
    season_filter: str = None
):
    """Index only episodes not already in database."""

    print("Loading CLIP model...")
    model, _, preprocess = open_clip.create_model_and_transforms(
        'ViT-B-32',
        pretrained='laion2b_s34b_b79k'
    )
    tokenizer = open_clip.get_tokenizer('ViT-B-32')
    model.eval()

    print("Loading BLIP caption model...")
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    caption_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
    caption_model.eval()

    print("Connecting to database...")
    db = lancedb.connect(db_path)

    # Get existing frames (by path) to prevent duplicates
    existing_paths = set()
    existing_episodes = set()
    if "frames" in db.table_names():
        table = db.open_table("frames")
        count = table.count_rows()
        if count > 0:
            dummy_vector = [0.0] * 512
            all_frames = table.search(dummy_vector).limit(count).to_list()
            existing_paths = set(r["path"] for r in all_frames)
            existing_episodes = set(r["episode"] for r in all_frames)
            print(f"Found {len(existing_episodes)} existing episodes ({len(existing_paths)} frames) in database")

    # Find new episode directories
    frames_path = Path(frames_dir)
    episode_dirs = sorted([d for d in frames_path.iterdir() if d.is_dir()])

    # Filter by season if specified
    if season_filter:
        episode_dirs = [d for d in episode_dirs if season_filter.lower() in d.name.lower()]

    # Find episodes not yet indexed
    new_episodes = [d for d in episode_dirs if d.name not in existing_episodes]

    if not new_episodes:
        print("No new episodes to index!")
        return

    print(f"\nFound {len(new_episodes)} new episodes to index:")
    for ep in new_episodes[:10]:
        print(f"  - {ep.name}")
    if len(new_episodes) > 10:
        print(f"  ... and {len(new_episodes) - 10} more")

    # Index new episodes
    total_frames = 0

    for episode_dir in new_episodes:
        episode_id = episode_dir.name
        frame_paths = sorted(episode_dir.glob("*.jpg"))

        if not frame_paths:
            continue

        # Calculate episode length for credits filtering
        max_frame_num = max(int(p.stem.split("_")[1]) for p in frame_paths)
        episode_length_sec = max_frame_num * frame_interval

        # Default intro/credits filtering
        intro_end = 90  # Skip first 90 seconds
        credits_start = episode_length_sec - 40  # Skip last 40 seconds

        print(f"\nIndexing {episode_id} ({len(frame_paths)} frames)...")

        records = []
        skipped = 0

        for frame_path in tqdm(frame_paths, desc=f"  {episode_id}", leave=False):
            # Skip if frame already exists in database
            if str(frame_path) in existing_paths:
                skipped += 1
                continue

            frame_num = int(frame_path.stem.split("_")[1])
            timestamp_sec = frame_num * frame_interval

            # Skip intro and credits
            if timestamp_sec <= intro_end or timestamp_sec >= credits_start:
                skipped += 1
                continue

            embedding = embed_image(str(frame_path), model, preprocess)
            caption = generate_caption(str(frame_path), processor, caption_model)
            characters = detect_characters_clip(str(frame_path), model, preprocess, tokenizer)

            records.append({
                "episode": episode_id,
                "frame": frame_path.name,
                "path": str(frame_path),
                "timestamp": timestamp_sec,
                "caption": caption,
                "characters": ", ".join(characters) if characters else "",
                "vector": embedding
            })

        # Add to database
        if records:
            table = db.open_table("frames")
            table.add(records)
            total_frames += len(records)
            print(f"  ✓ Added {len(records)} frames (skipped {skipped} intro/credits)")

    print(f"\n✓ Indexing complete: Added {total_frames} new frames")
    print(f"Total frames in database: {table.count_rows()}")


def main():
    parser = argparse.ArgumentParser(description="Index new episodes only")
    parser.add_argument("--frames", default="data/frames", help="Frames directory")
    parser.add_argument("--db", default="data/simpsons.lance", help="Database path")
    parser.add_argument("--interval", type=int, default=3, help="Frame interval in seconds")
    parser.add_argument("--season", type=str, help="Filter to specific season (e.g., 's04')")

    args = parser.parse_args()

    index_new_episodes(
        frames_dir=args.frames,
        db_path=args.db,
        frame_interval=args.interval,
        season_filter=args.season
    )


if __name__ == "__main__":
    main()
