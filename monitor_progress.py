#!/usr/bin/env python3
"""Live progress monitor for indexing"""
import time
import re
import sys

def parse_progress(output):
    """Extract current progress from output"""
    lines = output.strip().split('\n')

    # Find the most recent episode being indexed
    current_episode = None
    current_frame = 0
    total_frames = 0
    completed_episodes = []

    for line in lines:
        # Check for "Indexing The Simpsons - s01eXX (N frames)..."
        indexing_match = re.search(r'Indexing The Simpsons - (s\d+e\d+) \((\d+) frames\)', line)
        if indexing_match:
            current_episode = indexing_match.group(1)
            total_frames = int(indexing_match.group(2))
            current_frame = 0

        # Check for progress bar "s01eXX: XX%|..."
        progress_match = re.search(r'The Simpsons - (s\d+e\d+):\s+(\d+)%.*?\|\s*(\d+)/(\d+)', line)
        if progress_match:
            episode = progress_match.group(1)
            current_frame = int(progress_match.group(3))
            total_frames = int(progress_match.group(4))
            current_episode = episode

        # Check for completed episodes "✓ The Simpsons - s01eXX indexed"
        completed_match = re.search(r'✓ The Simpsons - (s\d+e\d+) indexed', line)
        if completed_match:
            completed_episodes.append(completed_match.group(1))

    return current_episode, current_frame, total_frames, completed_episodes

def format_progress_bar(current, total, width=40):
    """Create a progress bar string"""
    if total == 0:
        return "░" * width + " 0%"

    percentage = current / total
    filled = int(width * percentage)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {int(percentage * 100)}%"

def main():
    task_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude/-Users-hughferguson-repos-bort/tasks/bfa2c8a.output"

    print("\n🎬 SIMPSONS INDEXING PROGRESS")
    print("=" * 70)

    last_output_size = 0

    try:
        while True:
            try:
                with open(task_file, 'r') as f:
                    output = f.read()

                # Only parse if file has changed
                if len(output) != last_output_size:
                    last_output_size = len(output)

                    current_episode, current_frame, total_frames, completed = parse_progress(output)

                    # Clear screen (move cursor up and clear)
                    print("\033[2J\033[H", end="")

                    print("\n🎬 SIMPSONS INDEXING PROGRESS")
                    print("=" * 70)

                    # Show completed episodes
                    if completed:
                        print(f"\n✅ Completed Episodes ({len(completed)}):")
                        for ep in completed[-5:]:  # Show last 5
                            print(f"   ✓ {ep}")
                        if len(completed) > 5:
                            print(f"   ... and {len(completed) - 5} more")

                    # Show current episode progress
                    if current_episode:
                        print(f"\n⚡ Currently Indexing: {current_episode}")
                        print(f"   Frames: {current_frame}/{total_frames}")
                        print(f"   {format_progress_bar(current_frame, total_frames)}")

                        if total_frames > 0:
                            percentage = (current_frame / total_frames) * 100
                            remaining = total_frames - current_frame
                            print(f"   {remaining} frames remaining")

                    # Calculate overall progress (13 episodes total)
                    total_episodes = 13
                    overall_progress = len(completed) + (current_frame / total_frames if total_frames > 0 else 0)
                    print(f"\n📊 Overall Progress: {overall_progress:.1f} / {total_episodes} episodes")
                    print(f"   {format_progress_bar(overall_progress, total_episodes, width=50)}")

                    print("\n" + "=" * 70)
                    print("Press Ctrl+C to exit")

                time.sleep(2)

            except FileNotFoundError:
                print(f"\n⏳ Waiting for task file to be created...")
                time.sleep(2)

    except KeyboardInterrupt:
        print("\n\n✋ Monitoring stopped")

if __name__ == "__main__":
    main()
