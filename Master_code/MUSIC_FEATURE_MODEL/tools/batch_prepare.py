#!/usr/bin/env python3
"""
Batch Song Preparation

Prepares all audio files in a directory for the music-synchronized motor control system.
Automatically extracts song name and artist from filename when possible.

Usage:
    python batch_prepare.py                           # Process src/songs/ folder
    python batch_prepare.py /path/to/audio/folder     # Process specific folder
    python batch_prepare.py --dry-run                 # Preview without processing
"""

import argparse
import sys
import re
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from offline import prepare_song
from offline.song_manager import SongManager
from config import SONGS_DIR


# Supported audio formats
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac'}


def parse_filename(filename: str) -> tuple[str, str]:
    """
    Extract song name and artist from filename.

    Tries common patterns:
    - "Artist - Song Title.mp3"
    - "Song Title.mp3"

    Args:
        filename: Audio filename (without path)

    Returns:
        Tuple of (name, artist)
    """
    # Remove extension
    stem = Path(filename).stem

    # Try "Artist - Title" pattern
    if ' - ' in stem:
        parts = stem.split(' - ', 1)
        artist = parts[0].strip()
        name = parts[1].strip()
        return name, artist

    # Try "Artist_ Title" pattern (underscore separator)
    if '_' in stem and not stem.replace('_', '').isalnum():
        parts = stem.split('_', 1)
        if len(parts[0]) > 2:  # Likely an artist name
            artist = parts[0].strip()
            name = parts[1].replace('_', ' ').strip()
            return name, artist

    # Fallback: use filename as name, Unknown artist
    name = stem.replace('_', ' ')
    return name, "Unknown"


def find_audio_files(folder: Path) -> list[Path]:
    """Find all audio files in a folder."""
    audio_files = []
    for ext in AUDIO_EXTENSIONS:
        audio_files.extend(folder.glob(f'*{ext}'))
        audio_files.extend(folder.glob(f'*{ext.upper()}'))
    return sorted(audio_files)


def batch_prepare(
    source_folder: str,
    dry_run: bool = False,
    max_amplitude: float = 7.5,
    gear_ratio: float = 15.0
) -> dict:
    """
    Prepare all audio files in a folder.

    Args:
        source_folder: Path to folder containing audio files
        dry_run: If True, only preview what would be done
        max_amplitude: Maximum motor amplitude in turns
        gear_ratio: Gear ratio for trajectory generation

    Returns:
        Dictionary with success/failed counts and details
    """
    source_path = Path(source_folder)

    if not source_path.exists():
        print(f"Error: Folder not found: {source_path}")
        return {'success': 0, 'failed': 0, 'skipped': 0}

    # Find audio files
    audio_files = find_audio_files(source_path)

    if not audio_files:
        print(f"No audio files found in: {source_path}")
        print(f"Supported formats: {', '.join(AUDIO_EXTENSIONS)}")
        return {'success': 0, 'failed': 0, 'skipped': 0}

    # Check existing songs to avoid duplicates
    manager = SongManager(str(SONGS_DIR))
    existing_songs = {s.name.lower() for s in manager.list_songs()}

    print(f"\n{'='*60}")
    print(f"BATCH SONG PREPARATION")
    print(f"{'='*60}")
    print(f"Source folder: {source_path}")
    print(f"Output folder: {SONGS_DIR}")
    print(f"Audio files found: {len(audio_files)}")
    print(f"Existing songs: {len(existing_songs)}")
    print(f"{'='*60}\n")

    # Preview files
    print("Files to process:")
    print("-" * 60)
    for audio_file in audio_files:
        name, artist = parse_filename(audio_file.name)
        status = "[SKIP - exists]" if name.lower() in existing_songs else "[NEW]"
        print(f"  {status} {audio_file.name}")
        print(f"           -> Name: {name}, Artist: {artist}")
    print("-" * 60)

    if dry_run:
        print("\n[DRY RUN] No files were processed.")
        return {'success': 0, 'failed': 0, 'skipped': len(audio_files)}

    # Confirm
    print(f"\nProceed with preparation? (y/n): ", end="")
    response = input().strip().lower()
    if response != 'y':
        print("Cancelled.")
        return {'success': 0, 'failed': 0, 'skipped': len(audio_files)}

    # Process files
    results = {
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'details': []
    }

    for i, audio_file in enumerate(audio_files, 1):
        name, artist = parse_filename(audio_file.name)

        # Skip if already exists
        if name.lower() in existing_songs:
            print(f"\n[{i}/{len(audio_files)}] Skipping (already exists): {name}")
            results['skipped'] += 1
            results['details'].append({
                'file': audio_file.name,
                'status': 'skipped',
                'reason': 'already exists'
            })
            continue

        print(f"\n[{i}/{len(audio_files)}] Processing: {audio_file.name}")

        try:
            song_id = prepare_song(
                audio_path=str(audio_file),
                name=name,
                artist=artist,
                max_amplitude=max_amplitude,
                gear_ratio=gear_ratio
            )
            results['success'] += 1
            results['details'].append({
                'file': audio_file.name,
                'status': 'success',
                'song_id': song_id,
                'name': name,
                'artist': artist
            })
            # Add to existing songs to prevent duplicates within batch
            existing_songs.add(name.lower())

        except Exception as e:
            print(f"  ERROR: {e}")
            results['failed'] += 1
            results['details'].append({
                'file': audio_file.name,
                'status': 'failed',
                'error': str(e)
            })

    # Summary
    print(f"\n{'='*60}")
    print("BATCH PREPARATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Successful: {results['success']}")
    print(f"  Failed: {results['failed']}")
    print(f"  Skipped: {results['skipped']}")
    print(f"{'='*60}\n")

    if results['failed'] > 0:
        print("Failed files:")
        for detail in results['details']:
            if detail['status'] == 'failed':
                print(f"  - {detail['file']}: {detail['error']}")
        print()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Prepare all audio files in a folder for motor control playback"
    )
    parser.add_argument(
        "folder",
        nargs='?',
        default=None,
        help="Folder containing audio files (default: src/songs/)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be done without processing"
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

    args = parser.parse_args()

    # Default to src/songs/ if no folder specified
    if args.folder is None:
        source_folder = Path(__file__).parent / "songs"
    else:
        source_folder = Path(args.folder)

    # Check for ffmpeg
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: ffmpeg is required for audio conversion.")
        print("Install it with: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)")
        return 1

    results = batch_prepare(
        source_folder=str(source_folder),
        dry_run=args.dry_run,
        max_amplitude=args.amplitude,
        gear_ratio=args.gear_ratio
    )

    return 0 if results['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
