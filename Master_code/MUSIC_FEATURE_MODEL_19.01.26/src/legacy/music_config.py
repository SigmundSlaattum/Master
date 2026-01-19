"""
Music Configuration Module

Manages audio file library and provides easy selection interface.
"""

import os
from typing import Dict, List, Optional


class MusicLibrary:
    """
    Manages the music library and provides methods for song selection.
    """

    def __init__(self, songs_directory: str = "../../songs"):
        """
        Initialize the music library.

        Args:
            songs_directory: Base directory where songs are stored (relative to src/)
        """
        self.songs_directory = songs_directory
        self.library = self._initialize_library()
        self.current_genre = None
        self.current_song = None

    def _initialize_library(self) -> Dict[str, List[str]]:
        """
        Initialize the music library with predefined songs.

        Returns:
            Dictionary mapping genres to lists of song filenames (without extension)
        """
        return {
            "metal": [
                "Machine Head - Davidian",
                "Machine Head - Locust",
                "MACHINE HEAD - OUTSIDER",
                "For Whom The Bell Tolls (Remastered)"
            ],
            "classic": [
                "Schubert - Serenade",
                "Beethoven_ Symphony No. 7, 2nd movement  Paavo Järvi and the Deutsche Kammerphilharmonie Bremen",
                "Mozart - Lacrimosa"
            ],
            "edm": [
                "Made_Me_Like_This",
                "Husko - Goodnight"
            ]
        }

    def get_genres(self) -> List[str]:
        """
        Get list of available genres.

        Returns:
            List of genre names
        """
        return list(self.library.keys())

    def get_songs_in_genre(self, genre: str) -> List[str]:
        """
        Get list of songs in a specific genre.

        Args:
            genre: Genre name (case-insensitive)

        Returns:
            List of song names in the genre

        Raises:
            KeyError: If genre doesn't exist
        """
        genre_lower = genre.lower()
        if genre_lower not in self.library:
            raise KeyError(f"Genre '{genre}' not found. Available genres: {', '.join(self.get_genres())}")
        return self.library[genre_lower]

    def get_song_path(self, genre: str, song_index: int = -1, extension: str = ".mp3") -> str:
        """
        Get the full path to a song file.

        Args:
            genre: Genre name
            song_index: Index of song in genre (-1 for last song, default)
            extension: File extension (default: .mp3)

        Returns:
            Full path to the song file

        Raises:
            KeyError: If genre doesn't exist
            IndexError: If song_index is out of range
        """
        songs = self.get_songs_in_genre(genre)
        song_name = songs[song_index]
        self.current_genre = genre
        self.current_song = song_name
        # Convert to absolute path to avoid issues with librosa
        relative_path = os.path.join(self.songs_directory, f"{song_name}{extension}")
        return os.path.abspath(relative_path)

    def get_song_path_by_name(self, genre: str, song_name: str, extension: str = ".mp3") -> str:
        """
        Get the full path to a song file by name.

        Args:
            genre: Genre name
            song_name: Exact song name (without extension)
            extension: File extension (default: .mp3)

        Returns:
            Full path to the song file

        Raises:
            KeyError: If genre doesn't exist
            ValueError: If song not found in genre
        """
        songs = self.get_songs_in_genre(genre)
        if song_name not in songs:
            raise ValueError(f"Song '{song_name}' not found in genre '{genre}'")
        self.current_genre = genre
        self.current_song = song_name
        # Convert to absolute path to avoid issues with librosa
        relative_path = os.path.join(self.songs_directory, f"{song_name}{extension}")
        return os.path.abspath(relative_path)

    def select_song_interactive(self) -> Optional[str]:
        """
        Interactive song selection via command line.

        Returns:
            Path to selected song, or None if cancelled
        """
        print("\n" + "="*60)
        print("MUSIC LIBRARY")
        print("="*60)

        # Show genres
        genres = self.get_genres()
        print("\nAvailable Genres:")
        for i, genre in enumerate(genres, 1):
            print(f"  {i}. {genre.upper()}")

        # Get genre selection
        try:
            genre_choice = input("\nSelect genre (number or name, or 'q' to use default): ").strip()
            if genre_choice.lower() == 'q':
                return None

            # Parse genre choice
            if genre_choice.isdigit():
                genre_idx = int(genre_choice) - 1
                if genre_idx < 0 or genre_idx >= len(genres):
                    print("Invalid genre number")
                    return None
                selected_genre = genres[genre_idx]
            else:
                selected_genre = genre_choice.lower()
                if selected_genre not in self.library:
                    print(f"Genre '{genre_choice}' not found")
                    return None

            # Show songs in genre
            songs = self.get_songs_in_genre(selected_genre)
            print(f"\nSongs in {selected_genre.upper()}:")
            for i, song in enumerate(songs, 1):
                print(f"  {i}. {song}")

            # Get song selection
            song_choice = input("\nSelect song (number, or press Enter for last song): ").strip()

            if song_choice == "":
                song_idx = -1
            elif song_choice.isdigit():
                song_idx = int(song_choice) - 1
                if song_idx < 0 or song_idx >= len(songs):
                    print("Invalid song number")
                    return None
            else:
                print("Invalid input")
                return None

            path = self.get_song_path(selected_genre, song_idx)
            print(f"\nSelected: {self.current_song}")
            print("="*60 + "\n")
            return path

        except Exception as e:
            print(f"Error during selection: {e}")
            return None

    def add_song(self, genre: str, song_name: str):
        """
        Add a song to the library.

        Args:
            genre: Genre name (case-insensitive)
            song_name: Song name without extension
        """
        genre_lower = genre.lower()
        if genre_lower not in self.library:
            self.library[genre_lower] = []
        if song_name not in self.library[genre_lower]:
            self.library[genre_lower].append(song_name)

    def remove_song(self, genre: str, song_name: str):
        """
        Remove a song from the library.

        Args:
            genre: Genre name
            song_name: Song name to remove

        Raises:
            KeyError: If genre doesn't exist
            ValueError: If song not found
        """
        genre_lower = genre.lower()
        songs = self.get_songs_in_genre(genre_lower)
        if song_name not in songs:
            raise ValueError(f"Song '{song_name}' not found in genre '{genre}'")
        self.library[genre_lower].remove(song_name)

    def __str__(self) -> str:
        """String representation of the library."""
        lines = ["Music Library:"]
        for genre, songs in self.library.items():
            lines.append(f"\n{genre.upper()}:")
            for song in songs:
                lines.append(f"  - {song}")
        return "\n".join(lines)


# Default library instance for quick access
default_library = MusicLibrary()


def get_default_song() -> str:
    """
    Get the default song path (EDM - last song).

    Returns:
        Path to default song
    """
    return default_library.get_song_path("edm", -1)


def get_song(genre: str = "edm", song_index: int = -1) -> str:
    """
    Quick function to get a song path.

    Args:
        genre: Genre name (default: edm)
        song_index: Song index (default: -1, last song)

    Returns:
        Path to the song file
    """
    return default_library.get_song_path(genre, song_index)


if __name__ == "__main__":
    # Demo/test mode
    library = MusicLibrary()
    print(library)
    print("\n" + "="*60)
    print("Testing song selection:")
    print(f"Default song: {get_default_song()}")
    print(f"Metal song #1: {get_song('metal', 0)}")
    print(f"Classic last song: {get_song('classic', -1)}")