#!/usr/bin/env python3
"""
Frame extraction and embedding pipeline for Simpsons Scene Search.

This script:
1. Extracts frames from video files at regular intervals using ffmpeg
2. Generates CLIP embeddings for each frame
3. Stores embeddings and metadata in LanceDB for fast similarity search
4. Optionally uses improved character detection via HuggingFace ViT
5. Optionally uses auto intro/credits detection
"""

import argparse
import json
import subprocess
from pathlib import Path
from typing import Optional

import lancedb
import open_clip
import torch
from PIL import Image
from tqdm import tqdm
from transformers import BlipProcessor, BlipForConditionalGeneration


def extract_frames(video_path: str, output_dir: str, interval: int = 3) -> None:
    """
    Extract one frame every `interval` seconds from video.

    Args:
        video_path: Path to video file
        output_dir: Directory to save frames
        interval: Seconds between frames (default 3)
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval}",
        "-q:v", "2",
        f"{output_dir}/frame_%05d.jpg",
        "-loglevel", "error"
    ]

    print(f"Extracting frames from {Path(video_path).name}...")
    subprocess.run(cmd, check=True)

    frame_count = len(list(output_path.glob("*.jpg")))
    print(f"  → Extracted {frame_count} frames")


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


def detect_characters_clip(image_path: str, model, preprocess, tokenizer, max_chars: int = 10, min_score: float = 0.27, score_gap: float = 0.04) -> list[str]:
    """
    Detect Simpsons characters in an image using zero-shot CLIP classification.
    (Legacy method - use detect_characters_vit for better accuracy)

    Args:
        image_path: Path to image file
        model: CLIP model
        preprocess: CLIP image preprocessor
        tokenizer: CLIP text tokenizer
        max_chars: Maximum number of characters to return (default 3, increased for better detection)
        min_score: Minimum absolute score to consider (default 0.24, lowered from 0.30 for 87% more detections)
        score_gap: Maximum score difference from top score to include (default 0.05, increased for secondary characters)

    Returns:
        List of detected character names (top N by confidence)
    """
    # Main Simpsons characters
    characters = [
        "Homer Simpson", "Marge Simpson", "Bart Simpson", "Lisa Simpson", "Maggie Simpson",
        "Mr. Burns", "Smithers", "Ned Flanders", "Moe Szyslak", "Barney Gumble",
        "Chief Wiggum", "Apu Nahasapeemapetilon", "Krusty the Clown", "Milhouse Van Houten",
        "Nelson Muntz", "Principal Skinner", "Edna Krabappel", "Groundskeeper Willie",
        "Comic Book Guy", "Sideshow Bob", "Otto Mann", "Patty Bouvier", "Selma Bouvier"
    ]

    # Load and preprocess image
    image = preprocess(Image.open(image_path)).unsqueeze(0)

    # Tokenize character names - simpler prompt works better
    text = tokenizer([f"{char}" for char in characters])

    # Compute similarities
    with torch.no_grad():
        image_features = model.encode_image(image)
        text_features = model.encode_text(text)

        image_features /= image_features.norm(dim=-1, keepdim=True)
        text_features /= text_features.norm(dim=-1, keepdim=True)

        similarity = (image_features @ text_features.T)[0]

    # Sort by similarity
    scores = [(i, similarity[i].item()) for i in range(len(characters))]
    scores.sort(key=lambda x: x[1], reverse=True)

    # Only include characters that are:
    # 1. Above minimum score threshold
    # 2. Within score_gap of the top score
    # 3. Within max_chars limit
    detected = []
    if scores and scores[0][1] >= min_score:
        top_score = scores[0][1]

        for i, score in scores[:max_chars]:
            if score >= min_score and (top_score - score) <= score_gap:
                # Remove "Simpson" suffix for main family members to shorten tags
                char_name = characters[i].replace(" Simpson", "")
                detected.append(char_name)

    return detected


def load_intro_cache(cache_file: str = "intro_credits.json") -> dict:
    """Load cached intro/credits timestamps if available."""
    cache_path = Path(cache_file)
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    return {}


def get_episode_timestamps(filename: str, cache: dict, default_intro: int = 90, default_credits: int = 40) -> tuple[int, int]:
    """
    Get intro end and credits start timestamps for an episode.

    Args:
        filename: Video/episode filename
        cache: Loaded cache from detect_intro.py
        default_intro: Default intro duration in seconds
        default_credits: Default credits duration in seconds

    Returns:
        Tuple of (intro_end_seconds, credits_start_seconds)
    """
    # Try exact match
    if filename in cache:
        data = cache[filename]
        return (int(data.get("intro_end", default_intro)),
                int(data.get("credits_start", -default_credits)))

    # Try partial match
    for cached_name, data in cache.items():
        if filename.split(".")[0] in cached_name or cached_name.split(".")[0] in filename:
            return (int(data.get("intro_end", default_intro)),
                    int(data.get("credits_start", -default_credits)))

    return (default_intro, -default_credits)


def index_frames(
    frames_dir: str,
    db_path: str = "data/simpsons.lance",
    frame_interval: int = 3,
    use_vit_detection: bool = False,
    intro_cache_file: str = None
) -> None:
    """
    Index all frames in directory to LanceDB.

    Args:
        frames_dir: Root directory containing episode subdirectories with frames
        db_path: Path to LanceDB database
        frame_interval: Seconds between frames (for timestamp calculation)
        use_vit_detection: Use HuggingFace ViT for character detection (more accurate)
        intro_cache_file: Path to intro/credits cache JSON (from detect_intro.py)
    """
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

    # Load improved character detector if requested
    char_detector = None
    if use_vit_detection:
        try:
            from character_detection import SimpsonsCharacterDetector
            print("Loading ViT character detector...")
            char_detector = SimpsonsCharacterDetector(use_vit=True, use_clip_fallback=True)
        except ImportError as e:
            print(f"Warning: Could not load ViT detector ({e}), using CLIP fallback")

    # Load intro/credits cache if provided
    intro_cache = {}
    if intro_cache_file:
        intro_cache = load_intro_cache(intro_cache_file)
        if intro_cache:
            print(f"Loaded intro/credits timestamps for {len(intro_cache)} episodes")

    db = lancedb.connect(db_path)
    frames_path = Path(frames_dir)
    episode_dirs = sorted([d for d in frames_path.iterdir() if d.is_dir()])

    total_frames = 0
    first_episode = True

    for episode_dir in episode_dirs:
        episode_id = episode_dir.name
        frame_paths = sorted(episode_dir.glob("*.jpg"))

        if not frame_paths:
            continue

        # Calculate episode length to filter credits
        max_frame_num = max(int(p.stem.split("_")[1]) for p in frame_paths)
        episode_length_sec = max_frame_num * frame_interval

        # Get intro/credits timestamps (from cache or defaults)
        intro_end, credits_start = get_episode_timestamps(episode_id, intro_cache)
        if credits_start < 0:  # Negative means "from end"
            credits_start = episode_length_sec + credits_start

        print(f"Indexing {episode_id} ({len(frame_paths)} frames)...")
        print(f"  Filtering: intro < {intro_end}s, credits > {credits_start}s")

        # Process frames for this episode
        records = []
        skipped_intro = 0
        skipped_credits = 0
        for frame_path in tqdm(frame_paths, desc=f"  {episode_id}", leave=False):
            frame_num = int(frame_path.stem.split("_")[1])
            timestamp_sec = frame_num * frame_interval

            # Skip intro and credits
            if timestamp_sec <= intro_end:
                skipped_intro += 1
                continue
            if timestamp_sec >= credits_start:
                skipped_credits += 1
                continue

            embedding = embed_image(str(frame_path), model, preprocess)
            caption = generate_caption(str(frame_path), processor, caption_model)

            # Use ViT detector if available, otherwise fall back to CLIP
            if char_detector:
                characters = char_detector.detect(str(frame_path))
            else:
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

        # Write this episode to database
        if records:
            if first_episode:
                # Check if table already exists
                existing_tables = db.table_names()
                if "frames" in existing_tables:
                    print(f"  → Appending {len(records)} frames to existing database...")
                    table = db.open_table("frames")
                    table.add(records)
                else:
                    print(f"  → Creating new database with {len(records)} frames...")
                    db.create_table("frames", records)
                first_episode = False
            else:
                print(f"  → Appending {len(records)} frames to database...")
                table = db.open_table("frames")
                table.add(records)

            total_frames += len(records)
            print(f"  ✓ {episode_id} indexed ({total_frames} total frames so far)")
            if skipped_intro or skipped_credits:
                print(f"    (Skipped {skipped_intro} intro + {skipped_credits} credits frames)")

    if total_frames > 0:
        print(f"\n✓ Indexing complete: {total_frames} frames across {len(episode_dirs)} episodes")
    else:
        print("No frames found to index")


def process_videos(
    videos_path: str,
    output_dir: str = "data/frames",
    interval: int = 3
) -> None:
    """
    Extract frames from all video files in a directory.

    Args:
        videos_path: Directory containing video files
        output_dir: Root directory to save extracted frames
        interval: Seconds between frames
    """
    videos_dir = Path(videos_path)

    if not videos_dir.exists():
        raise ValueError(f"Videos directory not found: {videos_path}")

    video_files = []
    for ext in ['*.mp4', '*.mkv', '*.avi', '*.mov']:
        video_files.extend(videos_dir.rglob(ext))

    if not video_files:
        print(f"No video files found in {videos_path}")
        return

    print(f"Found {len(video_files)} video files")

    for video_path in sorted(video_files):
        stem = video_path.stem
        episode_dir = Path(output_dir) / stem

        if episode_dir.exists() and list(episode_dir.glob("*.jpg")):
            print(f"Skipping {stem} (frames already exist)")
            continue

        try:
            extract_frames(str(video_path), str(episode_dir), interval)
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Error processing {stem}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract and index frames from Simpsons episodes"
    )
    parser.add_argument(
        "--videos",
        type=str,
        help="Path to directory containing video files"
    )
    parser.add_argument(
        "--frames",
        type=str,
        default="data/frames",
        help="Directory to store extracted frames (default: data/frames)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Seconds between extracted frames (default: 3)"
    )
    parser.add_argument(
        "--index-only",
        action="store_true",
        help="Skip frame extraction, only index existing frames"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/simpsons.lance",
        help="Path to LanceDB database (default: data/simpsons.lance)"
    )
    parser.add_argument(
        "--use-vit",
        action="store_true",
        help="Use HuggingFace ViT model for improved character detection"
    )
    parser.add_argument(
        "--intro-cache",
        type=str,
        help="Path to intro/credits cache JSON (from detect_intro.py)"
    )

    args = parser.parse_args()

    if not args.index_only:
        if not args.videos:
            parser.error("--videos is required unless --index-only is specified")
        process_videos(args.videos, args.frames, args.interval)

    index_frames(
        args.frames,
        args.db,
        args.interval,
        use_vit_detection=args.use_vit,
        intro_cache_file=args.intro_cache
    )


if __name__ == "__main__":
    main()
