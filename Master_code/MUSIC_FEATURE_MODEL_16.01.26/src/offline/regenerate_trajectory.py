#!/usr/bin/env python3
"""
Regenerate Trajectory

Regenerates a song's trajectory with a new BPM without re-converting audio.
Useful when auto-detected BPM was wrong (doubled/halved).

Usage:
    python regenerate_trajectory.py song_003 --bpm 65
"""

import argparse
import sys
import json
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import SONGS_DIR
from offline.feature_extractor import extract_features
from offline.trajectory_generator import generate_trajectory, save_trajectory


def regenerate_trajectory(song_id: str, new_bpm: float) -> None:
    """
    Regenerate trajectory for an existing song with a new BPM.

    Args:
        song_id: Song ID (e.g., "song_003")
        new_bpm: New BPM to use for trajectory generation
    """
    song_dir = SONGS_DIR / song_id

    if not song_dir.exists():
        print(f"Error: Song not found: {song_id}")
        print(f"Expected directory: {song_dir}")
        return

    audio_path = song_dir / "audio.wav"
    trajectory_path = song_dir / "trajectory.npy"
    metadata_path = song_dir / "metadata.json"

    if not audio_path.exists():
        print(f"Error: Audio file not found: {audio_path}")
        return

    print(f"\n{'='*60}")
    print(f"REGENERATING TRAJECTORY")
    print(f"{'='*60}")
    print(f"Song: {song_id}")
    print(f"New BPM: {new_bpm}")
    print()

    # Extract features from existing audio
    print("[1/3] Extracting features...")
    features = extract_features(str(audio_path), frame_duration=0.1)
    old_bpm = features.bpm
    print(f"  Auto-detected BPM: {old_bpm:.1f}")
    print(f"  Overriding to: {new_bpm:.1f}")
    features.bpm = new_bpm

    # Load existing metadata to preserve settings
    print("\n[2/3] Loading metadata...")
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)

    max_amplitude = metadata.get('trajectory', {}).get('max_amplitude', 7.5)
    gear_ratio = metadata.get('trajectory', {}).get('gear_ratio', 15.0)
    resolution_ms = metadata.get('trajectory', {}).get('resolution_ms', 10.0)

    print(f"  Max amplitude: {max_amplitude}")
    print(f"  Gear ratio: {gear_ratio}")
    print(f"  Resolution: {resolution_ms}ms")

    # Generate new trajectory
    print("\n[3/3] Generating trajectory...")
    trajectory = generate_trajectory(
        features,
        max_amplitude=max_amplitude,
        gear_ratio=gear_ratio,
        resolution_ms=resolution_ms
    )

    # Save trajectory
    save_trajectory(trajectory, str(trajectory_path))
    print(f"  Samples: {len(trajectory)}")
    print(f"  Position range: {trajectory[:, 1].min():.2f} to {trajectory[:, 1].max():.2f} turns")

    # Update metadata
    metadata['features']['bpm'] = new_bpm
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  Updated metadata.json")

    # Update index.json
    index_path = SONGS_DIR / "index.json"
    if index_path.exists():
        with open(index_path, 'r') as f:
            index = json.load(f)

        for song in index.get('songs', []):
            if song.get('id') == song_id:
                song['bpm'] = new_bpm
                break

        with open(index_path, 'w') as f:
            json.dump(index, f, indent=2)
        print(f"  Updated index.json")

    print(f"\n{'='*60}")
    print(f"Trajectory regenerated successfully!")
    print(f"  Old BPM: {old_bpm:.1f}")
    print(f"  New BPM: {new_bpm:.1f}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate a song's trajectory with a new BPM"
    )
    parser.add_argument(
        "song_id",
        help="Song ID (e.g., song_003)"
    )
    parser.add_argument(
        "--bpm",
        type=float,
        required=True,
        help="New BPM for trajectory generation"
    )

    args = parser.parse_args()

    regenerate_trajectory(args.song_id, args.bpm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
