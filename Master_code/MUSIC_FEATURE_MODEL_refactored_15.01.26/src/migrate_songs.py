#!/usr/bin/env python3
"""
Migration Script

Migrates existing songs from the old format (MP3 files in src/songs/)
to the new format (songs/ directory with WAV, trajectory, metadata).
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from offline import prepare_song
from config import SONGS_DIR


# Mapping of old song files to metadata
SONG_METADATA = {
    "Made_Me_Like_This.mp3": {
        "name": "Made Me Like This",
        "artist": "Unknown"
    },
    "Husko - Goodnight.mp3": {
        "name": "Goodnight",
        "artist": "Husko"
    },
    "Machine Head - Davidian.mp3": {
        "name": "Davidian",
        "artist": "Machine Head"
    },
    "Machine Head - Locust.mp3": {
        "name": "Locust",
        "artist": "Machine Head"
    },
    "MACHINE HEAD - OUTSIDER.mp3": {
        "name": "Outsider",
        "artist": "Machine Head"
    },
    "For Whom The Bell Tolls (Remastered).mp3": {
        "name": "For Whom The Bell Tolls",
        "artist": "Metallica"
    },
    "Mozart - Lacrimosa.mp3": {
        "name": "Lacrimosa",
        "artist": "Mozart"
    },
    "Schubert - Serenade.mp3": {
        "name": "Serenade",
        "artist": "Schubert"
    },
    "Beethoven_ Symphony No. 7, 2nd movement  Paavo Järvi and the Deutsche Kammerphilharmonie Bremen.mp3": {
        "name": "Symphony No. 7, 2nd Movement",
        "artist": "Beethoven"
    }
}


def migrate_songs(old_songs_dir: str = None):
    """Migrate all songs from old format to new format."""
    if old_songs_dir is None:
        old_songs_dir = Path(__file__).parent / "songs"

    old_songs_dir = Path(old_songs_dir)

    if not old_songs_dir.exists():
        print(f"Old songs directory not found: {old_songs_dir}")
        return

    # Find all MP3 files
    mp3_files = list(old_songs_dir.glob("*.mp3"))

    if not mp3_files:
        print("No MP3 files found to migrate.")
        return

    print(f"\nFound {len(mp3_files)} songs to migrate:")
    for f in mp3_files:
        print(f"  - {f.name}")

    print(f"\nMigrating to: {SONGS_DIR}")
    print("="*60)

    success_count = 0
    failed = []

    for mp3_file in mp3_files:
        filename = mp3_file.name

        # Get metadata
        if filename in SONG_METADATA:
            meta = SONG_METADATA[filename]
            name = meta["name"]
            artist = meta["artist"]
        else:
            # Generate from filename
            name = mp3_file.stem.replace("_", " ").replace("-", " - ")
            artist = "Unknown"

        print(f"\n{'='*60}")
        print(f"Migrating: {filename}")
        print(f"  Name: {name}")
        print(f"  Artist: {artist}")

        try:
            song_id = prepare_song(
                audio_path=str(mp3_file),
                name=name,
                artist=artist,
                songs_dir=str(SONGS_DIR)
            )
            print(f"  SUCCESS: {song_id}")
            success_count += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append((filename, str(e)))

    print("\n" + "="*60)
    print("MIGRATION COMPLETE")
    print("="*60)
    print(f"  Successful: {success_count}")
    print(f"  Failed: {len(failed)}")

    if failed:
        print("\nFailed migrations:")
        for filename, error in failed:
            print(f"  - {filename}: {error}")

    print()


if __name__ == "__main__":
    # Check if ffmpeg is available
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: ffmpeg is required for migration.")
        print("Install it with: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)")
        sys.exit(1)

    migrate_songs()
