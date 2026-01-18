#!/usr/bin/env python3
"""
Audio-based intro and credits detection for The Simpsons episodes.

Uses ffmpeg to analyze audio patterns and detect intros/credits.
The Simpsons intro has a distinctive audio signature that can be detected.

Requirements:
    ffmpeg must be installed and in PATH
"""

import argparse
import json
import subprocess
import struct
from pathlib import Path
from typing import Optional


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def get_audio_volume_profile(video_path: str, start: float = 0, duration: float = 150, step: float = 0.5) -> list[float]:
    """
    Get volume profile of audio at regular intervals.

    Returns list of mean volume values at each step.
    """
    volumes = []
    current = start

    while current < duration:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(current),
            "-t", str(step),
            "-i", video_path,
            "-af", "volumedetect",
            "-f", "null", "-",
            "-loglevel", "info"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        stderr = result.stderr

        # Parse mean volume from ffmpeg output
        mean_vol = -50.0  # Default to very quiet
        for line in stderr.split('\n'):
            if 'mean_volume' in line:
                try:
                    mean_vol = float(line.split(':')[1].strip().split()[0])
                except (IndexError, ValueError):
                    pass

        volumes.append(mean_vol)
        current += step

    return volumes


def detect_intro_by_audio(video_path: str) -> float:
    """
    Detect intro end time by analyzing audio patterns.

    The Simpsons intro typically:
    - Starts with the theme song
    - Has a couch gag
    - Ends around 60-90 seconds

    Returns estimated intro end time in seconds.
    """
    # Get volume profile for first 2.5 minutes
    volumes = get_audio_volume_profile(video_path, start=0, duration=150, step=1.0)

    if not volumes:
        return 90  # Default

    # Look for the transition from intro to episode
    # The intro music is typically louder and more consistent
    # Episode dialogue tends to have more variation

    # Calculate rolling variance (high variance = dialogue, low = music)
    window = 5
    variances = []
    for i in range(len(volumes) - window):
        segment = volumes[i:i + window]
        mean = sum(segment) / len(segment)
        variance = sum((v - mean) ** 2 for v in segment) / len(segment)
        variances.append(variance)

    # Find the first significant increase in variance after 30 seconds
    # This usually indicates transition from intro music to dialogue
    threshold = 20  # dB variance threshold
    for i, var in enumerate(variances):
        time_sec = i + window
        if time_sec > 30 and var > threshold:
            return min(time_sec + 5, 120)  # Add buffer, cap at 2 min

    # Default to 90 seconds if no clear transition found
    return 90


def detect_credits_by_audio(video_path: str, duration: float) -> float:
    """
    Detect credits start time by analyzing audio at the end.

    Credits typically have:
    - Consistent background music
    - No dialogue

    Returns estimated credits start time in seconds.
    """
    # Analyze last 2 minutes
    start_time = max(0, duration - 120)
    volumes = get_audio_volume_profile(video_path, start=start_time, duration=120, step=1.0)

    if not volumes:
        return duration - 40  # Default

    # Look for the transition to credits
    # Credits typically have lower variance (just music)
    window = 5
    variances = []
    for i in range(len(volumes) - window):
        segment = volumes[i:i + window]
        mean = sum(segment) / len(segment)
        variance = sum((v - mean) ** 2 for v in segment) / len(segment)
        variances.append(variance)

    # Find the last significant drop in variance
    threshold = 10  # Lower threshold for credits detection
    last_high_variance = len(variances) - 1

    for i in range(len(variances) - 1, -1, -1):
        if variances[i] > threshold:
            last_high_variance = i
            break

    credits_start = start_time + last_high_variance + window
    return min(credits_start, duration - 20)  # At least 20s of credits


def detect_with_silence(video_path: str) -> tuple[float, float]:
    """
    Alternative: detect intro/credits by finding silence gaps.

    Many episodes have brief silence between intro and main content.
    """
    duration = get_video_duration(video_path)

    # Use ffmpeg silencedetect
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", "silencedetect=noise=-30dB:d=0.5",
        "-f", "null", "-",
        "-loglevel", "info"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    stderr = result.stderr

    # Parse silence periods
    silences = []
    current_start = None
    for line in stderr.split('\n'):
        if 'silence_start' in line:
            try:
                current_start = float(line.split('silence_start:')[1].strip())
            except (IndexError, ValueError):
                pass
        elif 'silence_end' in line and current_start is not None:
            try:
                end = float(line.split('silence_end:')[1].split()[0].strip())
                silences.append((current_start, end))
                current_start = None
            except (IndexError, ValueError):
                pass

    # Find intro end: first significant silence after 60 seconds
    intro_end = 90
    for start, end in silences:
        if 60 < start < 120 and (end - start) > 0.3:
            intro_end = end
            break

    # Find credits start: last significant silence before end
    credits_start = duration - 40
    for start, end in reversed(silences):
        if duration - 120 < start < duration - 20 and (end - start) > 0.3:
            credits_start = start
            break

    return intro_end, credits_start


def detect_intros_credits(videos_dir: str, output_file: str = "intro_credits.json", method: str = "audio") -> dict:
    """
    Detect intro and credits timestamps for all episodes in a directory.

    Args:
        videos_dir: Directory containing video files for a season
        output_file: Path to save detection results
        method: Detection method - "audio" (volume analysis) or "silence" (gap detection)

    Returns:
        Dictionary mapping episode filenames to intro/credits timestamps
    """
    videos_path = Path(videos_dir)

    # Get all video files
    video_files = []
    for ext in ['*.mp4', '*.mkv', '*.avi', '*.mov']:
        video_files.extend(videos_path.glob(ext))

    if not video_files:
        print(f"No video files found in {videos_dir}")
        return {}

    print(f"Detecting intros/credits in {len(video_files)} episodes using {method} method...")

    parsed = {}
    for video_path in sorted(video_files):
        print(f"  Analyzing {video_path.name}...", end=" ", flush=True)

        try:
            duration = get_video_duration(str(video_path))

            if method == "silence":
                intro_end, credits_start = detect_with_silence(str(video_path))
            else:
                intro_end = detect_intro_by_audio(str(video_path))
                credits_start = detect_credits_by_audio(str(video_path), duration)

            parsed[video_path.name] = {
                "intro_end": round(intro_end, 1),
                "credits_start": round(credits_start, 1),
                "duration": round(duration, 1)
            }

            print(f"intro={intro_end:.0f}s, credits={credits_start:.0f}s")

        except Exception as e:
            print(f"error: {e}")
            # Use defaults
            parsed[video_path.name] = {
                "intro_end": 90,
                "credits_start": get_video_duration(str(video_path)) - 40,
                "duration": get_video_duration(str(video_path)),
                "error": str(e)
            }

    # Save results
    output_path = Path(output_file)
    with open(output_path, 'w') as f:
        json.dump(parsed, f, indent=2)

    print(f"\n✓ Saved detection results to {output_file}")
    return parsed


def load_intro_credits(cache_file: str = "intro_credits.json") -> dict:
    """
    Load cached intro/credits timestamps.

    Returns empty dict if cache doesn't exist.
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    return {}


def get_timestamps_for_episode(filename: str, cache: dict, fallback_intro: int = 90, fallback_credits: int = 40) -> tuple[int, int]:
    """
    Get intro end and credits start timestamps for an episode.

    Args:
        filename: Video filename
        cache: Loaded cache from detect_intros_credits
        fallback_intro: Default intro duration in seconds
        fallback_credits: Default credits duration in seconds

    Returns:
        Tuple of (intro_end_seconds, credits_start_seconds)
    """
    if filename in cache:
        data = cache[filename]
        return (int(data["intro_end"]), int(data["credits_start"]))

    # Try to match by episode pattern
    for cached_name, data in cache.items():
        if filename.split(".")[0] in cached_name or cached_name.split(".")[0] in filename:
            return (int(data["intro_end"]), int(data["credits_start"]))

    # Return defaults
    return (fallback_intro, -fallback_credits)  # Negative means "from end"


def main():
    parser = argparse.ArgumentParser(description="Detect intros and credits in Simpsons episodes")
    parser.add_argument("videos_dir", help="Directory containing video files")
    parser.add_argument("--output", "-o", default="intro_credits.json", help="Output JSON file")
    parser.add_argument("--method", choices=["audio", "silence"], default="audio",
                       help="Detection method: 'audio' (volume analysis) or 'silence' (gap detection)")

    args = parser.parse_args()

    detect_intros_credits(args.videos_dir, args.output, args.method)


if __name__ == "__main__":
    main()
