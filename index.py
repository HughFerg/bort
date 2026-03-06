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
import re
import subprocess
from pathlib import Path

import lancedb
import numpy as np
import open_clip
import torch
from PIL import Image
from tqdm import tqdm
from transformers import BlipProcessor, BlipForConditionalGeneration

# --- Thresholds ---
HARD_SKIP_INTRO_SEC = 20       # Always skip first N seconds (opening title card)
DEDUP_THRESHOLD = 0.96         # Skip frame entirely if this similar to previous indexed frame
CAPTION_REUSE_THRESHOLD = 0.85 # Reuse previous caption if this similar (saves BLIP calls)
INTRO_FINGERPRINT_THRESHOLD = 0.97  # Skip intro frame if this similar to season fingerprint

# Episodes with non-standard openings — skipped entirely from intro fingerprint logic.
# If one of these is the first episode of a season it would poison the fingerprint for
# all subsequent episodes. They're also skipped from filtering so their unique openings
# are always preserved in full.
NON_STANDARD_INTRO_EPISODES = {
    "s08e01",  # Treehouse of Horror VII  (S8 premiere)
    "s12e01",  # Treehouse of Horror XI   (S12 premiere)
}


def extract_frames(video_path: str, output_dir: str, interval: int = 1) -> None:
    """Extract one frame every `interval` seconds from video."""
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
    return processor.decode(outputs[0], skip_special_tokens=True)


def detect_characters_clip(image_path: str, model, preprocess, tokenizer, max_chars: int = 10, min_score: float = 0.27, score_gap: float = 0.04) -> list[str]:
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
    if scores and scores[0][1] >= min_score:
        top_score = scores[0][1]
        for i, score in scores[:max_chars]:
            if score >= min_score and (top_score - score) <= score_gap:
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


def get_episode_intro_end(filename: str, cache: dict, default_intro: int = 90) -> int:
    """Get intro end timestamp for an episode from cache."""
    if filename in cache:
        return int(cache[filename].get("intro_end", default_intro))
    for cached_name, data in cache.items():
        if filename.split(".")[0] in cached_name or cached_name.split(".")[0] in filename:
            return int(data.get("intro_end", default_intro))
    return default_intro


def index_frames(
    frames_dir: str,
    db_path: str = "data/simpsons.lance",
    frame_interval: int = 1,
    use_vit_detection: bool = False,
    intro_cache_file: str = None,
    season_filter: str = None,
) -> None:
    """
    Index all frames in directory to LanceDB.

    Args:
        frames_dir: Root directory containing episode subdirectories with frames
        db_path: Path to LanceDB database
        frame_interval: Seconds between frames (for timestamp calculation)
        use_vit_detection: Use HuggingFace ViT for character detection (more accurate)
        intro_cache_file: Path to intro/credits cache JSON (from detect_intro.py)
        season_filter: Only process episodes from this season (e.g. "s01")
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

    char_detector = None
    if use_vit_detection:
        try:
            from character_detection import SimpsonsCharacterDetector
            print("Loading ViT character detector...")
            char_detector = SimpsonsCharacterDetector(use_vit=True, use_clip_fallback=True)
        except ImportError as e:
            print(f"Warning: Could not load ViT detector ({e}), using CLIP fallback")

    intro_cache = {}
    if intro_cache_file:
        intro_cache = load_intro_cache(intro_cache_file)
        if intro_cache:
            print(f"Loaded intro timestamps for {len(intro_cache)} episodes")

    db = lancedb.connect(db_path)
    frames_path = Path(frames_dir)
    episode_dirs = sorted([d for d in frames_path.iterdir() if d.is_dir()])

    # Get existing frames to avoid re-indexing
    existing_paths = set()
    if "frames" in db.table_names():
        table = db.open_table("frames")
        count = table.count_rows()
        if count > 0:
            dummy_vector = [0.0] * 512
            all_frames = table.search(dummy_vector).limit(count).to_list()
            existing_paths = set(r["path"] for r in all_frames)
            print(f"Found {len(existing_paths)} existing frames in database")

    # Per-season intro fingerprints for "one intro" deduplication.
    # Built from the first 2 episodes of each season so atypical ep-1 openings
    # (early S1/S2 variants, specials) don't poison the fingerprint.
    # Filtering only activates from episode 3 onward, so Treehouse of Horror
    # and other non-standard intros naturally survive (they won't match).
    season_intro_vectors: dict[str, list] = {}
    season_episode_count: dict[str, int] = {}  # how many episodes indexed per season
    FINGERPRINT_BUILD_EPS = 1   # build fingerprint from first N standard-intro eps
    FINGERPRINT_APPLY_EPS = 1   # start filtering from ep N+1 onward

    total_frames = 0
    first_write = True

    for episode_dir in episode_dirs:
        episode_id = episode_dir.name

        # Season filter for staging / partial runs
        if season_filter and season_filter.lower() not in episode_id.lower():
            continue

        frame_paths = sorted(episode_dir.glob("*.jpg"))
        if not frame_paths:
            continue

        # Determine season and episode position within it
        season_match = re.search(r's(\d+)', episode_id, re.I)
        season = season_match.group(0).lower() if season_match else None
        # Strip to e.g. "s08e01" for lookup — handles filenames like "s08e01_title"
        episode_key = re.search(r's\d+e\d+', episode_id, re.I)
        episode_key = episode_key.group(0).lower() if episode_key else None
        has_standard_intro = episode_key not in NON_STANDARD_INTRO_EPISODES
        # Only count episodes with standard intros — keeps the fingerprint build
        # window accurate when a non-standard ep (e.g. TOH VII) is the season premiere
        if season and has_standard_intro:
            season_episode_count[season] = season_episode_count.get(season, 0) + 1
        ep_num = season_episode_count.get(season, 0) if season else 0
        is_building_fingerprint = has_standard_intro and season is not None and ep_num <= FINGERPRINT_BUILD_EPS
        is_filtering_intro = has_standard_intro and season is not None and ep_num > FINGERPRINT_APPLY_EPS

        intro_end = get_episode_intro_end(episode_id, intro_cache)

        print(f"Indexing {episode_id} ({len(frame_paths)} frames)...")
        if not has_standard_intro:
            label = "Non-standard opening — skipping fingerprint"
        elif is_building_fingerprint:
            label = f"Building fingerprint (ep {ep_num}/{FINGERPRINT_BUILD_EPS})"
        elif is_filtering_intro:
            label = "Filtering intro against fingerprint"
        else:
            label = "No fingerprint yet (keeping all intro frames)"
        print(f"  Intro ends at ~{intro_end}s | {label}")

        # Per-episode state (reset each episode)
        last_embedding_arr = None
        last_caption = None
        records = []
        skipped_title_card = 0
        skipped_dedup = 0
        skipped_intro_repeat = 0
        skipped_existing = 0

        for frame_path in tqdm(frame_paths, desc=f"  {episode_id}", leave=False):
            if str(frame_path) in existing_paths:
                skipped_existing += 1
                continue

            frame_num = int(frame_path.stem.split("_")[1])
            timestamp_sec = frame_num * frame_interval

            # Always hard-skip the opening title card
            if timestamp_sec < HARD_SKIP_INTRO_SEC:
                skipped_title_card += 1
                continue

            in_intro_region = timestamp_sec <= intro_end

            # Compute CLIP embedding (needed for dedup and fingerprint checks)
            embedding = embed_image(str(frame_path), model, preprocess)
            embedding_arr = np.array(embedding)

            # Inline deduplication — skip if too similar to last indexed frame.
            # Also flag for caption reuse if similar but not identical.
            reuse_caption = False
            if last_embedding_arr is not None:
                sim = float(np.dot(embedding_arr, last_embedding_arr))
                if sim >= DEDUP_THRESHOLD:
                    skipped_dedup += 1
                    continue
                reuse_caption = sim >= CAPTION_REUSE_THRESHOLD

            # Intro fingerprint check — skip intro frames that match the
            # season's standard elements, but only once we have enough episodes
            # to have a reliable fingerprint (avoids false positives from
            # atypical ep-1 openings like early S1 or specials).
            if in_intro_region and is_filtering_intro:
                fingerprint = season_intro_vectors.get(season, [])
                if fingerprint:
                    max_sim = max(float(np.dot(embedding_arr, fp)) for fp in fingerprint)
                    if max_sim > INTRO_FINGERPRINT_THRESHOLD:
                        skipped_intro_repeat += 1
                        continue

            # Caption: reuse from previous frame if visually similar, otherwise run BLIP
            if reuse_caption and last_caption:
                caption = last_caption
            else:
                caption = generate_caption(str(frame_path), processor, caption_model)

            # Character detection
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

            # Update per-episode rolling state
            last_embedding_arr = embedding_arr
            last_caption = caption

            # Add to season fingerprint while still in the build window
            if in_intro_region and is_building_fingerprint:
                season_intro_vectors.setdefault(season, []).append(embedding_arr)

        # Write episode to database
        if records:
            if first_write:
                if "frames" in db.table_names():
                    table = db.open_table("frames")
                    table.add(records)
                else:
                    db.create_table("frames", records)
                first_write = False
            else:
                table = db.open_table("frames")
                table.add(records)

            total_frames += len(records)
            print(f"  ✓ {episode_id}: {len(records)} frames indexed ({total_frames} total)")
            skips = []
            if skipped_title_card: skips.append(f"{skipped_title_card} title card")
            if skipped_dedup:      skips.append(f"{skipped_dedup} duplicates")
            if skipped_intro_repeat: skips.append(f"{skipped_intro_repeat} intro repeats")
            if skipped_existing:   skips.append(f"{skipped_existing} existing")
            if skips:
                print(f"    Skipped: {' + '.join(skips)}")

        # Log fingerprint status after each episode
        if season and is_building_fingerprint:
            fp_size = len(season_intro_vectors.get(season, []))
            print(f"  → Season {season.upper()} fingerprint: {fp_size} frames (ep {ep_num}/{FINGERPRINT_BUILD_EPS})")

    if total_frames > 0:
        print(f"\n✓ Indexing complete: {total_frames} frames indexed")
    else:
        print("No new frames found to index")


def process_videos(
    videos_path: str,
    output_dir: str = "data/frames",
    interval: int = 1,
    season_filter: str = None,
) -> None:
    """Extract frames from all video files in a directory."""
    videos_dir = Path(videos_path)

    if not videos_dir.exists():
        raise ValueError(f"Videos directory not found: {videos_path}")

    video_files = []
    for ext in ['*.mp4', '*.mkv', '*.avi', '*.mov']:
        video_files.extend(videos_dir.rglob(ext))

    if not video_files:
        print(f"No video files found in {videos_path}")
        return

    if season_filter:
        video_files = [v for v in video_files if season_filter.lower() in v.stem.lower()]
        print(f"Season filter '{season_filter}': {len(video_files)} videos")
    else:
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
    parser.add_argument("--videos", type=str, help="Path to directory containing video files")
    parser.add_argument("--frames", type=str, default="data/frames", help="Directory to store extracted frames")
    parser.add_argument("--interval", type=int, default=1, help="Seconds between extracted frames (default: 1)")
    parser.add_argument("--index-only", action="store_true", help="Skip frame extraction, only index existing frames")
    parser.add_argument("--db", type=str, default="data/simpsons.lance", help="Path to LanceDB database")
    parser.add_argument("--use-vit", action="store_true", help="Use HuggingFace ViT model for improved character detection")
    parser.add_argument("--intro-cache", type=str, help="Path to intro/credits cache JSON (from detect_intro.py)")
    parser.add_argument("--season", type=str, help="Only process this season (e.g. s01) — useful for staging")

    args = parser.parse_args()

    if not args.index_only:
        if not args.videos:
            parser.error("--videos is required unless --index-only is specified")
        process_videos(args.videos, args.frames, args.interval, season_filter=args.season)

    index_frames(
        args.frames,
        args.db,
        args.interval,
        use_vit_detection=args.use_vit,
        intro_cache_file=args.intro_cache,
        season_filter=args.season,
    )


if __name__ == "__main__":
    main()
