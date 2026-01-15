#!/usr/bin/env python3
"""
Song Preparation CLI

Prepares a song for the music-synchronized motor control system.
This script:
1. Converts audio to WAV format (44100 Hz)
2. Extracts music features (BPM, RMS, complexity)
3. Generates pre-computed motor trajectory
4. Creates metadata and registers in song library

Usage:
    python prepare_song.py path/to/song.mp3 --name "Song Title" --artist "Artist"
"""

import argparse
import subprocess
import sys
import shutil
from pathlib import Path

import numpy as np

from .feature_extractor import extract_features
from .trajectory_generator import generate_trajectory, save_trajectory, TrajectoryConfig
from .song_manager import SongManager


def convert_to_wav(input_path: str, output_path: str, sample_rate: int = 44100) -> bool:
    """
    Convert audio file to WAV format using ffmpeg.

    Args:
        input_path: Path to input audio file
        output_path: Path to output WAV file
        sample_rate: Target sample rate

    Returns:
        True if successful, False otherwise
    """
    try:
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-ar', str(sample_rate),  # Sample rate
            '-ac', '2',               # Stereo
            '-y',                     # Overwrite output
            output_path
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"ffmpeg error: {result.stderr}")
            return False
        return True
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please install ffmpeg.")
        return False


def prepare_song(
    audio_path: str,
    name: str,
    artist: str = "Unknown",
    max_amplitude: float = 7.5,
    gear_ratio: float = 15.0,
    resolution_ms: float = 10.0,
    songs_dir: str = None,
    bpm_override: float = None
) -> str:
    """
    Prepare a song for the motor control system.

    Args:
        audio_path: Path to the audio file
        name: Song name
        artist: Artist name
        max_amplitude: Maximum motor amplitude in turns
        gear_ratio: Gear ratio (motor:output)
        resolution_ms: Trajectory time resolution in ms
        songs_dir: Songs directory path (uses default if None)
        bpm_override: Manual BPM override (None to use auto-detection)

    Returns:
        Song ID if successful
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print(f"\n{'='*60}")
    print(f"Preparing song: {name}")
    print(f"{'='*60}\n")

    # Initialize song manager
    manager = SongManager(songs_dir)

    # Create song directory
    song_id = manager._generate_song_id()
    song_dir = manager.create_song_directory(song_id)
    print(f"Created song directory: {song_dir}")

    # Define output paths
    wav_path = song_dir / "audio.wav"
    trajectory_path = song_dir / "trajectory.npy"
    metadata_path = song_dir / "metadata.json"

    try:
        # Step 1: Convert to WAV
        print(f"\n[1/4] Converting to WAV...")
        if audio_path.suffix.lower() == '.wav':
            # Already WAV, just copy
            shutil.copy(audio_path, wav_path)
            print(f"  Copied WAV file")
        else:
            if not convert_to_wav(str(audio_path), str(wav_path)):
                raise RuntimeError("Failed to convert audio to WAV")
            print(f"  Converted to: {wav_path.name}")

        # Step 2: Extract features
        print(f"\n[2/4] Extracting features...")
        features = extract_features(str(wav_path), frame_duration=0.1)

        # Apply BPM override if specified
        if bpm_override is not None:
            print(f"  Auto-detected BPM: {features.bpm:.1f} (overriding to {bpm_override:.1f})")
            features.bpm = bpm_override
        else:
            print(f"  BPM: {features.bpm:.1f}")
        print(f"  Duration: {features.duration:.2f}s")
        print(f"  Beats detected: {len(features.beat_times)}")

        # Step 3: Generate trajectory
        print(f"\n[3/4] Generating trajectory...")
        trajectory = generate_trajectory(
            features,
            max_amplitude=max_amplitude,
            gear_ratio=gear_ratio,
            resolution_ms=resolution_ms
        )
        save_trajectory(trajectory, str(trajectory_path))
        print(f"  Samples: {len(trajectory)}")
        print(f"  Position range: {trajectory[:, 1].min():.2f} to {trajectory[:, 1].max():.2f} turns")

        # Step 4: Register in index and save metadata
        print(f"\n[4/4] Registering song...")
        manager.add_song(
            name=name,
            artist=artist,
            duration_s=features.duration,
            bpm=features.bpm,
            original_file=audio_path.name,
            song_dir=song_id
        )

        # Save detailed metadata
        extra_data = {
            'audio': {
                'sample_rate': features.sample_rate,
                'channels': 2,
                'duration_seconds': features.duration
            },
            'features': {
                'bpm': features.bpm,
                'num_beats': len(features.beat_times),
                'avg_rms': float(np.mean(features.rms)),
                'avg_complexity': float(np.mean(features.complexity))
            },
            'trajectory': {
                'resolution_ms': resolution_ms,
                'num_samples': len(trajectory),
                'gear_ratio': gear_ratio,
                'max_amplitude': max_amplitude
            }
        }
        manager.save_song_metadata(song_id, extra_data)

        print(f"\n{'='*60}")
        print(f"Song prepared successfully!")
        print(f"  ID: {song_id}")
        print(f"  Name: {name}")
        print(f"  Artist: {artist}")
        print(f"  Duration: {manager.format_duration(features.duration)}")
        print(f"  BPM: {features.bpm:.1f}")
        print(f"{'='*60}\n")

        return song_id

    except Exception as e:
        # Cleanup on failure
        print(f"\nError: {e}")
        if song_dir.exists():
            shutil.rmtree(song_dir)
            print(f"Cleaned up: {song_dir}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a song for the music-synchronized motor control system"
    )
    parser.add_argument(
        "audio_file",
        help="Path to the audio file (MP3, WAV, etc.)"
    )
    parser.add_argument(
        "--name", "-n",
        required=True,
        help="Song name"
    )
    parser.add_argument(
        "--artist", "-a",
        default="Unknown",
        help="Artist name (default: Unknown)"
    )
    parser.add_argument(
        "--amplitude",
        type=float,
        default=7.5,
        help="Maximum motor amplitude in turns (default: 7.5)"
    )
    parser.add_argument(
        "--gear-ratio",
        type=float,
        default=15.0,
        help="Gear ratio motor:output (default: 15.0)"
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=10.0,
        help="Trajectory resolution in ms (default: 10.0)"
    )
    parser.add_argument(
        "--songs-dir",
        help="Songs directory path (uses default if not specified)"
    )
    parser.add_argument(
        "--bpm",
        type=float,
        default=None,
        help="Manual BPM override (auto-detect if not specified)"
    )

    args = parser.parse_args()

    try:
        song_id = prepare_song(
            audio_path=args.audio_file,
            name=args.name,
            artist=args.artist,
            max_amplitude=args.amplitude,
            gear_ratio=args.gear_ratio,
            resolution_ms=args.resolution,
            songs_dir=args.songs_dir,
            bpm_override=args.bpm
        )
        print(f"Song ID: {song_id}")
        return 0
    except Exception as e:
        print(f"Failed to prepare song: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
