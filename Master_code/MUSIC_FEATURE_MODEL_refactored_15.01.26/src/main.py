#!/usr/bin/env python3
"""
Music-Synchronized Motor Control System

Main entry point for the floor platform control system.
Plays pre-computed motor trajectories synchronized with audio.

Usage:
    python main.py                      # Interactive song selection
    python main.py --song "Song Name"   # Play specific song
    python main.py --list               # List available songs
    python main.py --calibrate          # Run latency calibration
"""

import argparse
import sys
import time
from pathlib import Path

import odrive

from config import SONGS_DIR, CONFIG_DIR
from offline import SongManager
from core import create_playback_controller
from calibration import LatencyCalibrator


def list_songs() -> None:
    """List all available songs."""
    manager = SongManager(str(SONGS_DIR))
    songs = manager.list_songs()

    if not songs:
        print("No songs in library.")
        print(f"Add songs using: python -m offline.prepare_song <audio_file> --name 'Title'")
        return

    print("\nAvailable songs:")
    print("-" * 60)
    for song in songs:
        duration = manager.format_duration(song.duration_s)
        print(f"  {song.id}: {song.name} - {song.bpm:.0f} BPM [{duration}]")
    print("-" * 60)
    print(f"Total: {len(songs)} songs\n")


def select_song_interactive() -> str:
    """Interactive song selection. Returns song ID."""
    manager = SongManager(str(SONGS_DIR))
    songs = manager.list_songs()

    if not songs:
        print("No songs in library.")
        return None

    print("\nSelect a song:")
    for i, song in enumerate(songs):
        duration = manager.format_duration(song.duration_s)
        print(f"  [{i+1}] {song.name} - {song.bpm:.0f} BPM [{duration}]")

    while True:
        try:
            choice = input("\nEnter number (or 'q' to quit): ").strip()
            if choice.lower() == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(songs):
                return songs[idx].id
            print("Invalid selection.")
        except ValueError:
            print("Please enter a number.")


def connect_odrive(timeout: float = 30.0):
    """Connect to ODrive. Returns None if not found."""
    print("Searching for ODrive...")
    try:
        odrv0 = odrive.find_any(timeout=timeout)
        if odrv0:
            print(f"Found ODrive: {odrv0.serial_number}")
            return odrv0
    except Exception as e:
        print(f"ODrive connection failed: {e}")
    return None


def interactive_fine_tune(odrv0, result):
    """
    Interactive fine-tuning with actual song playback.

    Plays a song and asks user if motor is early/late/good.
    Returns updated CalibrationResult.
    """
    manager = SongManager(str(SONGS_DIR))
    songs = manager.list_songs()

    if not songs:
        print("No songs available for fine-tuning.")
        return result

    # Select a song for testing
    print("\nSelect a song for fine-tuning:")
    for i, song in enumerate(songs[:5]):  # Show max 5 songs
        print(f"  [{i+1}] {song.name} ({song.bpm:.0f} BPM)")

    try:
        choice = int(input("\nEnter number: ").strip()) - 1
        if choice < 0 or choice >= len(songs):
            choice = 0
    except ValueError:
        choice = 0

    song = manager.get_song_by_id(songs[choice].id)

    print("\n" + "="*50)
    print("INTERACTIVE FINE-TUNING")
    print("="*50)
    print(f"\nUsing song: {song.metadata.name}")
    print("\nInstructions:")
    print("  - A 15-second clip will play")
    print("  - Watch the motor and listen to the music")
    print("  - After each clip, answer if motor is early/late/good")
    print()

    current_offset_ms = result.total_latency_ms
    adjustment = 10.0  # Start with 10ms adjustments

    while True:
        print(f"\nCurrent offset: {current_offset_ms:.1f} ms")
        print("Playing 15-second test clip...")

        # Get initial position
        initial_offset = odrv0.axis0.encoder.pos_estimate

        # Create controller with current offset
        controller = create_playback_controller(
            audio_path=song.audio_path,
            trajectory_path=song.trajectory_path,
            odrv0=odrv0,
            initial_offset=initial_offset,
            latency_offset_s=current_offset_ms / 1000.0
        )

        # Play for 15 seconds
        controller.start()
        try:
            start = time.time()
            while time.time() - start < 15 and not controller.is_finished():
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            controller.stop()

        print("\nHow was the synchronization?")
        print("  [E] Motor moves EARLY (before the beat)")
        print("  [L] Motor moves LATE (after the beat)")
        print("  [G] GOOD - in sync!")
        print("  [R] Replay with same offset")
        print("  [Q] Quit fine-tuning")

        response = input("\nYour choice: ").strip().lower()

        if response == 'q':
            print("Keeping current offset.")
            break
        elif response == 'g':
            print("Great! Offset locked in.")
            break
        elif response == 'r':
            continue  # Replay with same offset
        elif response == 'e':
            # Motor is early -> need less lookahead
            current_offset_ms -= adjustment
            adjustment = max(adjustment * 0.7, 2.0)
            print(f"  Reducing offset by {adjustment:.1f}ms")
        elif response == 'l':
            # Motor is late -> need more lookahead
            current_offset_ms += adjustment
            adjustment = max(adjustment * 0.7, 2.0)
            print(f"  Increasing offset by {adjustment:.1f}ms")
        else:
            print("Invalid choice, replaying...")

    # Update result
    fine_tune = current_offset_ms - result.total_latency_ms
    result.fine_tune_offset_ms = fine_tune
    result.final_offset_ms = current_offset_ms

    print(f"\nFinal offset: {current_offset_ms:.1f} ms")
    print(f"  (Base: {result.total_latency_ms:.1f} ms + Fine-tune: {fine_tune:+.1f} ms)")

    return result


def run_calibration(odrv0) -> None:
    """Run latency calibration."""
    from odrive_controller import arm
    from odrive.enums import AXIS_STATE_IDLE

    # First, arm the motor (required for position commands to work)
    print("\nArming motor for calibration...")
    try:
        arm(odrv0)
        time.sleep(0.5)  # Let it stabilize
    except Exception as e:
        print(f"Failed to arm motor: {e}")
        print("Make sure the motor has been calibrated (run ODrive calibration first)")
        return

    # Verify motor is in closed-loop control
    axis_state = odrv0.axis0.current_state
    if axis_state != 8:  # AXIS_STATE_CLOSED_LOOP_CONTROL
        print(f"Motor not in closed-loop control (state={axis_state})")
        print("Please calibrate the ODrive motor first.")
        return

    print("Motor armed and ready.\n")

    calibrator = LatencyCalibrator(
        odrv0=odrv0,
        config_path=str(CONFIG_DIR / "latency.json")
    )

    result = calibrator.run_calibration()

    print("\nWould you like to do interactive fine-tuning? (y/n)")
    print("(This will play a song so you can judge if motor is early/late)")
    if input().strip().lower() == 'y':
        result = interactive_fine_tune(odrv0, result)

    calibrator.save_calibration(result)

    # Return motor to idle
    print("\nReturning motor to idle...")
    odrv0.axis0.requested_state = AXIS_STATE_IDLE

    print("\nCalibration complete!")


def play_song(song_id: str, odrv0, latency_offset_s: float = 0.035) -> None:
    """Play a song with motor synchronization."""
    manager = SongManager(str(SONGS_DIR))
    song = manager.get_song_by_id(song_id)

    if song is None:
        print(f"Song not found: {song_id}")
        return

    print(f"\n{'='*60}")
    print(f"Playing: {song.metadata.name}")
    print(f"BPM: {song.metadata.bpm:.0f}")
    print(f"Duration: {manager.format_duration(song.metadata.duration_s)}")
    print(f"Latency offset: {latency_offset_s*1000:.1f}ms")
    print(f"{'='*60}\n")

    # Get initial motor position
    initial_offset = odrv0.axis0.encoder.pos_estimate
    print(f"Initial motor position: {initial_offset:.2f}")

    # Create playback controller
    controller = create_playback_controller(
        audio_path=song.audio_path,
        trajectory_path=song.trajectory_path,
        odrv0=odrv0,
        initial_offset=initial_offset,
        latency_offset_s=latency_offset_s
    )

    # Status callback
    def on_status(status):
        pct = (status['current_time'] / status['duration']) * 100
        print(f"\r[{pct:5.1f}%] Time: {status['current_time']:.1f}s | "
              f"Pos: {status['target_position']:+.2f} | "
              f"Loop: {status['loop_time_us']:.0f}μs", end="")

    controller.set_on_status_update(on_status)

    # Start playback
    print("Starting playback... (Ctrl+C to stop)\n")
    controller.start()

    try:
        while not controller.is_finished():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        controller.stop()

        stats = controller.get_stats()
        print(f"\n\n{'='*60}")
        print("Playback Statistics:")
        print(f"  Duration: {stats.elapsed_time:.1f}s / {stats.duration:.1f}s")
        print(f"  Total commands: {stats.total_commands}")
        print(f"  Avg loop time: {stats.avg_loop_time_us:.1f} μs")
        print(f"  Max loop time: {stats.max_loop_time_us:.1f} μs")
        print(f"  Position error RMS: {stats.position_error_rms:.4f}")
        print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Music-Synchronized Motor Control System"
    )
    parser.add_argument(
        "--song", "-s",
        help="Song ID or name to play"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available songs"
    )
    parser.add_argument(
        "--calibrate", "-c",
        action="store_true",
        help="Run latency calibration"
    )
    parser.add_argument(
        "--latency",
        type=float,
        default=None,
        help="Latency offset in ms (overrides calibration)"
    )

    args = parser.parse_args()

    # List songs
    if args.list:
        list_songs()
        return 0

    # Connect to hardware
    odrv0 = connect_odrive(timeout=10.0)
    if odrv0 is None:
        print("ODrive not found. Please connect ODrive and try again.")
        return 1

    # Run calibration
    if args.calibrate:
        run_calibration(odrv0)
        return 0

    # Get latency offset
    if args.latency is not None:
        latency_offset_s = args.latency / 1000.0
    else:
        # Load from calibration
        calibrator = LatencyCalibrator(config_path=str(CONFIG_DIR / "latency.json"))
        latency_offset_s = calibrator.get_latency_offset_seconds()

    # Select song
    if args.song:
        # Try as ID first, then as name
        manager = SongManager(str(SONGS_DIR))
        song = manager.get_song_by_id(args.song)
        if song is None:
            song = manager.get_song_by_name(args.song)
        if song is None:
            print(f"Song not found: {args.song}")
            list_songs()
            return 1
        song_id = song.metadata.id
    else:
        # Interactive selection
        song_id = select_song_interactive()
        if song_id is None:
            return 0

    # Play song
    play_song(song_id, odrv0, latency_offset_s)

    return 0


if __name__ == "__main__":
    sys.exit(main())
