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
    Interactive mode: python prepare_song.py
    Direct mode: python prepare_song.py path/to/song.mp3 --name "Song Title" --artist "Artist"
"""

import argparse
import subprocess
import sys
import shutil
import librosa
from pathlib import Path

import numpy as np

# Support both direct script execution and module import
if __name__ == "__main__":
    # Running as script - add parent to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from offline.feature_extractor import extract_features
    from offline.trajectory_generator import generate_trajectory, save_trajectory, TrajectoryConfig
    from offline.song_manager import SongManager
else:
    # Running as module
    from .feature_extractor import extract_features
    from .trajectory_generator import generate_trajectory, save_trajectory, TrajectoryConfig
    from .song_manager import SongManager


# Supported audio formats
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma'}


def get_source_songs_dir() -> Path:
    """Get the path to the source songs directory (src/songs)."""
    return Path(__file__).parent.parent / "songs"


def list_available_songs(songs_dir: Path = None) -> list[Path]:
    """
    List all audio files in the source songs directory.

    Args:
        songs_dir: Directory to scan (defaults to src/songs)

    Returns:
        List of Path objects for audio files
    """
    if songs_dir is None:
        songs_dir = get_source_songs_dir()

    if not songs_dir.exists():
        return []

    audio_files = []
    for ext in AUDIO_EXTENSIONS:
        audio_files.extend(songs_dir.glob(f"*{ext}"))
        audio_files.extend(songs_dir.glob(f"*{ext.upper()}"))

    return sorted(audio_files, key=lambda p: p.name.lower())


def detect_bpm(audio_path: str) -> float:
    """
    Quick BPM detection from audio file.

    Args:
        audio_path: Path to audio file

    Returns:
        Detected BPM value
    """
    try:
        # Load just enough audio for BPM detection (first 60 seconds)
        y, sr = librosa.load(audio_path, sr=22050, duration=60)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo) if np.isscalar(tempo) else float(tempo[0])
        return bpm
    except Exception as e:
        print(f"  Warning: BPM detection failed: {e}")
        return 120.0  # Default fallback


def prompt_choice(prompt: str, options: list[str], allow_multiple: bool = False) -> list[int]:
    """
    Display a numbered list and prompt user to select option(s).

    Args:
        prompt: Header text to display
        options: List of option strings
        allow_multiple: If True, allow comma-separated selections

    Returns:
        List of selected indices (0-based)
    """
    print(f"\n{prompt}")
    print("-" * 50)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    print("-" * 50)

    if allow_multiple:
        print("Enter number(s) separated by commas, or 'all' for all, or 'q' to quit:")
    else:
        print("Enter number or 'q' to quit:")

    while True:
        response = input("> ").strip().lower()

        if response == 'q':
            return []

        if allow_multiple and response == 'all':
            return list(range(len(options)))

        try:
            if allow_multiple and ',' in response:
                indices = [int(x.strip()) - 1 for x in response.split(',')]
            else:
                indices = [int(response) - 1]

            # Validate all indices
            if all(0 <= idx < len(options) for idx in indices):
                return indices
            else:
                print(f"Please enter number(s) between 1 and {len(options)}")
        except ValueError:
            print("Invalid input. Enter a number or 'q' to quit.")


def prompt_text(prompt: str, default: str = "") -> str:
    """
    Prompt user for text input with optional default.

    Args:
        prompt: Prompt text
        default: Default value if user presses Enter

    Returns:
        User input or default
    """
    if default:
        response = input(f"{prompt} [{default}]: ").strip()
        return response if response else default
    else:
        while True:
            response = input(f"{prompt}: ").strip()
            if response:
                return response
            print("This field is required.")


def prompt_bpm(detected_bpm: float) -> float:
    """
    Prompt user to confirm or override BPM.

    Args:
        detected_bpm: Auto-detected BPM value

    Returns:
        Final BPM value (detected or user-specified)
    """
    current_bpm = detected_bpm
    print(f"  Detected BPM: {current_bpm:.1f}")
    print(f"  Options: Enter=accept, h=halve ({current_bpm/2:.0f}), d=double ({current_bpm*2:.0f}), or type a number")

    while True:
        response = input(f"  BPM [{current_bpm:.0f}]: ").strip().lower()

        if response == "":
            return current_bpm

        if response == "h":
            current_bpm = current_bpm / 2
            print(f"  Halved to: {current_bpm:.1f} BPM")
            print(f"  Options: Enter=accept, h=halve ({current_bpm/2:.0f}), d=double ({current_bpm*2:.0f}), or type a number")
            continue

        if response == "d":
            current_bpm = current_bpm * 2
            print(f"  Doubled to: {current_bpm:.1f} BPM")
            print(f"  Options: Enter=accept, h=halve ({current_bpm/2:.0f}), d=double ({current_bpm*2:.0f}), or type a number")
            continue

        try:
            bpm = float(response)
            if 20 <= bpm <= 300:
                return bpm
            else:
                print("  Please enter a BPM between 20 and 300.")
        except ValueError:
            print("  Invalid input. Enter a number, 'h' to halve, 'd' to double, or Enter to accept.")


def prompt_float(prompt: str, default: float, min_val: float = None, max_val: float = None) -> float:
    """
    Prompt user for a float value with default.

    Args:
        prompt: Prompt text
        default: Default value
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        User input or default
    """
    while True:
        response = input(f"{prompt} [{default}]: ").strip()

        if response == "":
            return default

        try:
            value = float(response)
            if min_val is not None and value < min_val:
                print(f"  Value must be at least {min_val}")
                continue
            if max_val is not None and value > max_val:
                print(f"  Value must be at most {max_val}")
                continue
            return value
        except ValueError:
            print("  Invalid input. Enter a number or press Enter for default.")


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    """
    Prompt user for yes/no input.

    Args:
        prompt: Prompt text
        default: Default value if user presses Enter

    Returns:
        True for yes, False for no
    """
    default_str = "Y/n" if default else "y/N"
    while True:
        response = input(f"{prompt} [{default_str}]: ").strip().lower()

        if response == "":
            return default
        if response in ('y', 'yes'):
            return True
        if response in ('n', 'no'):
            return False
        print("  Please enter 'y' or 'n'.")


def guess_song_metadata(filename: str) -> tuple[str, str]:
    """
    Try to guess song name and artist from filename.

    Args:
        filename: The audio filename (without path)

    Returns:
        (name, artist) tuple
    """
    stem = Path(filename).stem

    # Common patterns: "Artist - Song", "Artist_-_Song", "Song"
    separators = [' - ', ' _ ', '_-_', '-']

    for sep in separators:
        if sep in stem:
            parts = stem.split(sep, 1)
            if len(parts) == 2:
                artist = parts[0].strip().replace('_', ' ')
                name = parts[1].strip().replace('_', ' ')
                return name, artist

    # No separator found, use filename as song name
    name = stem.replace('_', ' ').replace('-', ' ')
    return name, "Unknown"


def interactive_prepare():
    """
    Interactive mode for preparing songs.
    Lists available songs and prompts user for all options.
    """
    print("\n" + "=" * 60)
    print("  INTERACTIVE SONG PREPARATION")
    print("=" * 60)

    # Check for ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\nERROR: ffmpeg is required for song preparation.")
        print("Install it with: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)")
        return 1

    # Find source songs
    source_dir = get_source_songs_dir()
    audio_files = list_available_songs(source_dir)

    if not audio_files:
        print(f"\nNo audio files found in: {source_dir}")
        print("Supported formats:", ', '.join(AUDIO_EXTENSIONS))
        return 1

    # Display songs and let user select
    song_names = [f.name for f in audio_files]
    selected_indices = prompt_choice(
        f"Available songs in {source_dir}:",
        song_names,
        allow_multiple=True
    )

    if not selected_indices:
        print("\nNo songs selected. Exiting.")
        return 0

    selected_files = [audio_files[i] for i in selected_indices]
    print(f"\nSelected {len(selected_files)} song(s) for preparation.")

    # Ask for common settings
    print("\n" + "-" * 50)
    print("Configuration (press Enter for defaults)")
    print("-" * 50)

    max_amplitude = prompt_float("Max amplitude (motor turns)", 7.5, 0.1, 20.0)
    gear_ratio = prompt_float("Gear ratio", 15.0, 1.0, 100.0)
    resolution_ms = prompt_float("Trajectory resolution (ms)", 10.0, 1.0, 100.0)

    # Frequency halving options
    print("\nFrequency options (halving = slower oscillation):")
    half_freq_simple = prompt_yes_no("  Half frequency for SIMPLE pattern", False)
    half_freq_complex = prompt_yes_no("  Half frequency for COMPLEX pattern", False)

    # Process each selected song
    success_count = 0
    failed = []

    for audio_file in selected_files:
        print("\n" + "=" * 60)
        print(f"Preparing: {audio_file.name}")
        print("=" * 60)

        # Guess metadata from filename
        guessed_name, guessed_artist = guess_song_metadata(audio_file.name)

        # Prompt for metadata
        print("\nSong Metadata:")
        name = prompt_text("  Song name", guessed_name)
        artist = prompt_text("  Artist", guessed_artist)

        # Detect and confirm BPM
        print("\n  Analyzing BPM...")
        detected_bpm = detect_bpm(str(audio_file))
        final_bpm = prompt_bpm(detected_bpm)

        # Confirm before processing
        print(f"\n  Summary:")
        print(f"    Name: {name}")
        print(f"    Artist: {artist}")
        print(f"    BPM: {final_bpm:.0f}")
        print(f"    Amplitude: {max_amplitude}")
        if half_freq_simple or half_freq_complex:
            freq_info = []
            if half_freq_simple:
                freq_info.append("simple")
            if half_freq_complex:
                freq_info.append("complex")
            print(f"    Half frequency: {', '.join(freq_info)}")

        confirm = input("\n  Proceed with preparation? [Y/n]: ").strip().lower()
        if confirm == 'n':
            print("  Skipped.")
            continue

        # Prepare the song
        try:
            song_id = prepare_song(
                audio_path=str(audio_file),
                name=name,
                artist=artist,
                max_amplitude=max_amplitude,
                gear_ratio=gear_ratio,
                resolution_ms=resolution_ms,
                bpm_override=final_bpm,
                half_freq_simple=half_freq_simple,
                half_freq_complex=half_freq_complex
            )
            print(f"  SUCCESS: {song_id}")
            success_count += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed.append((audio_file.name, str(e)))

    # Summary
    print("\n" + "=" * 60)
    print("PREPARATION COMPLETE")
    print("=" * 60)
    print(f"  Successful: {success_count}")
    print(f"  Failed: {len(failed)}")

    if failed:
        print("\nFailed preparations:")
        for filename, error in failed:
            print(f"  - {filename}: {error}")

    return 0 if not failed else 1


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
    bpm_override: float = None,
    half_freq_simple: bool = False,
    half_freq_complex: bool = False
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
        half_freq_simple: If True, halve the frequency for simple pattern
        half_freq_complex: If True, halve the frequency for complex pattern

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
    trajectory_path = song_dir / "trajectory.npy"           # Fixed tempo, complex pattern
    trajectory_dynamic_path = song_dir / "trajectory_dynamic.npy"  # Dynamic tempo, complex pattern
    trajectory_simple_path = song_dir / "trajectory_simple.npy"    # Fixed tempo, simple pattern
    trajectory_simple_dynamic_path = song_dir / "trajectory_simple_dynamic.npy"  # Dynamic tempo, simple
    metadata_path = song_dir / "metadata.json"

    try:
        # Step 1: Convert to WAV
        print(f"\n[1/7] Converting to WAV...")
        if audio_path.suffix.lower() == '.wav':
            # Already WAV, just copy
            shutil.copy(audio_path, wav_path)
            print(f"  Copied WAV file")
        else:
            if not convert_to_wav(str(audio_path), str(wav_path)):
                raise RuntimeError("Failed to convert audio to WAV")
            print(f"  Converted to: {wav_path.name}")

        # Step 2: Extract features
        print(f"\n[2/7] Extracting features...")
        features = extract_features(str(wav_path), frame_duration=0.1)

        # Apply BPM override if specified
        if bpm_override is not None:
            print(f"  Auto-detected BPM: {features.bpm:.1f} (overriding to {bpm_override:.1f})")
            # Scale local_tempo array proportionally to the BPM override
            # This ensures dynamic tempo trajectory uses correct baseline
            scale_factor = bpm_override / features.bpm
            features.local_tempo = features.local_tempo * scale_factor
            print(f"  Local tempo scaled by {scale_factor:.2f}x (range: {features.local_tempo.min():.1f} - {features.local_tempo.max():.1f})")
            features.bpm = bpm_override
        else:
            print(f"  BPM: {features.bpm:.1f}")
        print(f"  Duration: {features.duration:.2f}s")
        print(f"  Beats detected: {len(features.beat_times)}")

        # Frequency divisors
        complex_freq_div = 2.0 if half_freq_complex else 1.0
        simple_freq_div = 2.0 if half_freq_simple else 1.0

        # Step 3: Generate complex trajectories (dual sinusoid based on features)
        freq_note = " (HALF FREQ)" if half_freq_complex else ""
        print(f"\n[3/7] Generating fixed tempo COMPLEX trajectory{freq_note}...")
        trajectory_fixed = generate_trajectory(
            features,
            max_amplitude=max_amplitude,
            gear_ratio=gear_ratio,
            resolution_ms=resolution_ms,
            dynamic_tempo=False,
            pattern_type='complex',
            frequency_divisor=complex_freq_div
        )
        save_trajectory(trajectory_fixed, str(trajectory_path))
        print(f"  Samples: {len(trajectory_fixed)}")
        print(f"  Position range: {trajectory_fixed[:, 1].min():.2f} to {trajectory_fixed[:, 1].max():.2f} turns")

        print(f"\n[4/7] Generating dynamic tempo COMPLEX trajectory{freq_note}...")
        trajectory_dynamic = generate_trajectory(
            features,
            max_amplitude=max_amplitude,
            gear_ratio=gear_ratio,
            resolution_ms=resolution_ms,
            dynamic_tempo=True,
            pattern_type='complex',
            frequency_divisor=complex_freq_div
        )
        save_trajectory(trajectory_dynamic, str(trajectory_dynamic_path))
        print(f"  Samples: {len(trajectory_dynamic)}")
        print(f"  Position range: {trajectory_dynamic[:, 1].min():.2f} to {trajectory_dynamic[:, 1].max():.2f} turns")

        # Step 5: Generate simple trajectories (single sinusoid)
        freq_note = " (HALF FREQ)" if half_freq_simple else ""
        print(f"\n[5/7] Generating fixed tempo SIMPLE trajectory{freq_note}...")
        trajectory_simple = generate_trajectory(
            features,
            max_amplitude=max_amplitude,
            gear_ratio=gear_ratio,
            resolution_ms=resolution_ms,
            dynamic_tempo=False,
            pattern_type='simple',
            frequency_divisor=simple_freq_div
        )
        save_trajectory(trajectory_simple, str(trajectory_simple_path))
        print(f"  Samples: {len(trajectory_simple)}")
        print(f"  Position range: {trajectory_simple[:, 1].min():.2f} to {trajectory_simple[:, 1].max():.2f} turns")

        print(f"\n[6/7] Generating dynamic tempo SIMPLE trajectory{freq_note}...")
        trajectory_simple_dynamic = generate_trajectory(
            features,
            max_amplitude=max_amplitude,
            gear_ratio=gear_ratio,
            resolution_ms=resolution_ms,
            dynamic_tempo=True,
            pattern_type='simple',
            frequency_divisor=simple_freq_div
        )
        save_trajectory(trajectory_simple_dynamic, str(trajectory_simple_dynamic_path))
        print(f"  Samples: {len(trajectory_simple_dynamic)}")
        print(f"  Position range: {trajectory_simple_dynamic[:, 1].min():.2f} to {trajectory_simple_dynamic[:, 1].max():.2f} turns")

        # Step 7: Register in index and save metadata
        print(f"\n[7/7] Registering song...")
        manager.add_song(
            name=name,
            artist=artist,
            duration_s=features.duration,
            bpm=features.bpm,
            original_file=audio_path.name,
            song_dir=song_id
        )

        # Save detailed metadata
        tempo_range = features.local_tempo.max() - features.local_tempo.min()
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
                'avg_complexity': float(np.mean(features.complexity)),
                'local_tempo_min': float(features.local_tempo.min()),
                'local_tempo_max': float(features.local_tempo.max()),
                'local_tempo_avg': float(np.mean(features.local_tempo)),
                'tempo_variance': float(tempo_range)
            },
            'trajectory': {
                'resolution_ms': resolution_ms,
                'num_samples': len(trajectory_fixed),
                'gear_ratio': gear_ratio,
                'max_amplitude': max_amplitude,
                'has_dynamic_tempo': True,
                'has_simple_pattern': True,
                'half_freq_simple': half_freq_simple,
                'half_freq_complex': half_freq_complex
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
    # If no arguments, run interactive mode
    if len(sys.argv) == 1:
        return interactive_prepare()

    # Otherwise, use argument-based mode
    parser = argparse.ArgumentParser(
        description="Prepare a song for the music-synchronized motor control system",
        epilog="Run without arguments for interactive mode."
    )
    parser.add_argument(
        "audio_file",
        nargs='?',
        help="Path to the audio file (MP3, WAV, etc.). Omit for interactive mode."
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode"
    )
    parser.add_argument(
        "--name", "-n",
        help="Song name (required in direct mode)"
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
    parser.add_argument(
        "--half-freq-simple",
        action="store_true",
        help="Halve the frequency for simple pattern (slower oscillation)"
    )
    parser.add_argument(
        "--half-freq-complex",
        action="store_true",
        help="Halve the frequency for complex pattern (slower oscillation)"
    )

    args = parser.parse_args()

    # Interactive mode via flag
    if args.interactive:
        return interactive_prepare()

    # Direct mode requires audio_file and name
    if not args.audio_file:
        print("Error: audio_file is required in direct mode.")
        print("Run with --interactive or without arguments for interactive mode.")
        return 1

    if not args.name:
        print("Error: --name is required in direct mode.")
        print("Run with --interactive or without arguments for interactive mode.")
        return 1

    try:
        song_id = prepare_song(
            audio_path=args.audio_file,
            name=args.name,
            artist=args.artist,
            max_amplitude=args.amplitude,
            gear_ratio=args.gear_ratio,
            resolution_ms=args.resolution,
            songs_dir=args.songs_dir,
            bpm_override=args.bpm,
            half_freq_simple=args.half_freq_simple,
            half_freq_complex=args.half_freq_complex
        )
        print(f"Song ID: {song_id}")
        return 0
    except Exception as e:
        print(f"Failed to prepare song: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
