"""
Song Manager

Manages the song library index and provides methods for adding,
removing, and querying songs.
"""

import json
import os
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional
from datetime import datetime


@dataclass
class SongMetadata:
    """Metadata for a single song."""
    id: str
    name: str
    artist: str
    duration_s: float
    bpm: float
    path: str  # Relative path within songs directory
    original_file: str
    created_at: str


@dataclass
class SongInfo:
    """Full information about a song including file paths."""
    metadata: SongMetadata
    audio_path: str       # Full path to audio.wav
    trajectory_path: str  # Full path to trajectory.npy
    metadata_path: str    # Full path to metadata.json


class SongManager:
    """
    Manages the song library.

    Song library structure:
    songs/
    ├── index.json
    ├── song_001/
    │   ├── audio.wav
    │   ├── trajectory.npy
    │   └── metadata.json
    └── song_002/
        └── ...
    """

    def __init__(self, songs_dir: str = None):
        """
        Initialize the song manager.

        Args:
            songs_dir: Path to the songs directory. If None, uses default location.
        """
        if songs_dir is None:
            # Default to project_root/songs
            src_dir = Path(__file__).parent.parent
            songs_dir = src_dir.parent / "songs"

        self.songs_dir = Path(songs_dir)
        self.index_path = self.songs_dir / "index.json"

        # Create songs directory if it doesn't exist
        self.songs_dir.mkdir(parents=True, exist_ok=True)

        # Load or create index
        self._load_index()

    def _load_index(self) -> None:
        """Load the song index from disk."""
        if self.index_path.exists():
            with open(self.index_path, 'r') as f:
                data = json.load(f)
                self.songs = [SongMetadata(**s) for s in data.get('songs', [])]
        else:
            self.songs = []
            self._save_index()

    def _save_index(self) -> None:
        """Save the song index to disk."""
        data = {
            'version': 1,
            'songs': [asdict(s) for s in self.songs]
        }
        with open(self.index_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _generate_song_id(self) -> str:
        """Generate a unique song ID."""
        existing_ids = {s.id for s in self.songs}
        counter = 1
        while True:
            song_id = f"song_{counter:03d}"
            if song_id not in existing_ids:
                return song_id
            counter += 1

    def add_song(
        self,
        name: str,
        artist: str,
        duration_s: float,
        bpm: float,
        original_file: str,
        song_dir: str = None
    ) -> str:
        """
        Register a new song in the index.

        Args:
            name: Song name
            artist: Artist name
            duration_s: Duration in seconds
            bpm: Beats per minute
            original_file: Original filename
            song_dir: Song directory name (auto-generated if None)

        Returns:
            The generated song ID
        """
        song_id = self._generate_song_id()

        if song_dir is None:
            song_dir = song_id

        metadata = SongMetadata(
            id=song_id,
            name=name,
            artist=artist,
            duration_s=duration_s,
            bpm=bpm,
            path=song_dir,
            original_file=original_file,
            created_at=datetime.now().isoformat()
        )

        self.songs.append(metadata)
        self._save_index()

        return song_id

    def remove_song(self, song_id: str, delete_files: bool = False) -> bool:
        """
        Remove a song from the index.

        Args:
            song_id: ID of the song to remove
            delete_files: If True, also delete the song directory

        Returns:
            True if song was removed, False if not found
        """
        song = self.get_song_by_id(song_id)
        if song is None:
            return False

        if delete_files:
            song_dir = self.songs_dir / song.metadata.path
            if song_dir.exists():
                shutil.rmtree(song_dir)

        self.songs = [s for s in self.songs if s.id != song_id]
        self._save_index()

        return True

    def list_songs(self) -> List[SongMetadata]:
        """
        List all songs in the library.

        Returns:
            List of SongMetadata objects
        """
        return self.songs.copy()

    def get_song_by_id(self, song_id: str) -> Optional[SongInfo]:
        """
        Get full song information by ID.

        Args:
            song_id: Song ID

        Returns:
            SongInfo or None if not found
        """
        for song in self.songs:
            if song.id == song_id:
                return self._build_song_info(song)
        return None

    def get_song_by_name(self, name: str) -> Optional[SongInfo]:
        """
        Get song information by name (case-insensitive).

        Args:
            name: Song name

        Returns:
            SongInfo or None if not found
        """
        name_lower = name.lower()
        for song in self.songs:
            if song.name.lower() == name_lower:
                return self._build_song_info(song)
        return None

    def _build_song_info(self, metadata: SongMetadata) -> SongInfo:
        """Build full SongInfo from metadata."""
        song_dir = self.songs_dir / metadata.path
        return SongInfo(
            metadata=metadata,
            audio_path=str(song_dir / "audio.wav"),
            trajectory_path=str(song_dir / "trajectory.npy"),
            metadata_path=str(song_dir / "metadata.json")
        )

    def create_song_directory(self, song_id: str) -> Path:
        """
        Create the directory for a song.

        Args:
            song_id: Song ID

        Returns:
            Path to the created directory
        """
        song_dir = self.songs_dir / song_id
        song_dir.mkdir(parents=True, exist_ok=True)
        return song_dir

    def save_song_metadata(self, song_id: str, extra_data: dict = None) -> None:
        """
        Save detailed metadata for a song.

        Args:
            song_id: Song ID
            extra_data: Additional data to include in metadata.json
        """
        song = self.get_song_by_id(song_id)
        if song is None:
            raise ValueError(f"Song not found: {song_id}")

        data = asdict(song.metadata)
        if extra_data:
            data.update(extra_data)

        with open(song.metadata_path, 'w') as f:
            json.dump(data, f, indent=2)

    def get_songs_directory(self) -> Path:
        """Get the path to the songs directory."""
        return self.songs_dir

    def format_duration(self, seconds: float) -> str:
        """Format duration as MM:SS."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}:{secs:02d}"


def get_song_manager(songs_dir: str = None) -> SongManager:
    """Get a SongManager instance."""
    return SongManager(songs_dir)


if __name__ == "__main__":
    # Test the song manager
    manager = SongManager()

    print(f"Songs directory: {manager.songs_dir}")
    print(f"Index path: {manager.index_path}")
    print(f"\nSongs in library: {len(manager.list_songs())}")

    for song in manager.list_songs():
        duration = manager.format_duration(song.duration_s)
        print(f"  {song.id}: {song.name} - {song.bpm:.0f} BPM [{duration}]")
