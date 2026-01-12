#!/usr/bin/env python3
"""
This is the main control script that coordinates:
- ODrive motor control
- Music analysis and synchronization
- Visualization (simulation or hardware plotting)
- Optional audio synthesis
"""

import time
import subprocess
import threading
import argparse
import odrive
from pynput import keyboard

# Import refactored modules
from music_config import MusicLibrary, get_default_song
from music_analyzer import MusicAnalyzer
from motor_controller import MotorController
from visualization import VisualizationManager
from audio_synthesizer import AudioSynthesizer
from odrive_controller import *
from odrive.enums import AXIS_STATE_IDLE


# Global state
program_running = True
music_analyzer = None
audio_start_time = None
audio_process = None
current_motor_position = 0.0


def get_real_audio_time():
    """
    Get the real playback time of the audio using system time.

    Returns:
        float: Elapsed time since audio started
    """
    if audio_start_time is None:
        return 0.0
    return time.time() - audio_start_time


def play_audio_thread(file_path):
    """
    Launch audio playback subprocess.

    Args:
        file_path: Path to audio file

    Returns:
        subprocess.Popen: Audio playback process
    """
    process = subprocess.Popen(
        ['ffplay', '-nodisp', '-autoexit', file_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return process


def terminate_subprocess(process):
    """
    Gracefully terminate a subprocess.

    Args:
        process: subprocess.Popen object
    """
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def connect_to_odrive():
    """
    Search for and connect to an ODrive in a separate thread.
    Allows cancellation while searching via the global program_running flag.

    Returns:
        ODrive object if found, None if cancelled or not found
    """
    global program_running

    search_thread = threading.Thread(
        target=lambda: setattr(search_thread, 'result', odrive.find_any()),
        daemon=True
    )
    search_thread.result = None
    search_thread.start()

    while search_thread.is_alive() and program_running:
        time.sleep(0.1)

    return search_thread.result if program_running else None


def read_initial_motor_position(odrv0):
    """
    Read the current motor position before arming.

    Args:
        odrv0: ODrive object

    Returns:
        float: Current encoder position, or 0.0 if unable to read
    """
    try:
        initial_pos = odrv0.axis0.encoder.pos_estimate
        print(f"Initial motor position: {initial_pos:.3f} turns")
        return initial_pos
    except (AttributeError, OSError) as e:
        print(f"Warning: Could not read initial motor position: {e}")
        print("Using default initial position: 0.0")
        return 0.0


def calculate_amplitude_ratio(complexity):
    """
    Calculate amplitude1 and amplitude2 based on complexity.

    Args:
        complexity: Value between 0 and 1
            0 = simple (amplitude2 = 0)
            1 = complex (amplitude1 ≈ amplitude2)

    Returns:
        tuple: (amplitude1, amplitude2)
    """
    base_amplitude = 10.0
    gear_ratio = 2.0
    motor_amplitude = base_amplitude * gear_ratio
    amplitude1 = motor_amplitude * (1.0 - complexity * 0.5)
    amplitude2 = motor_amplitude * complexity
    return amplitude1, amplitude2


def update_from_music_features(motor_controller: MotorController):
    """
    Update motor control parameters based on music features.
    Runs continuously in the background.

    Args:
        motor_controller: MotorController instance to update
    """
    global music_analyzer, program_running

    while program_running and music_analyzer is not None:
        current_time = get_real_audio_time()

        if current_time >= music_analyzer.duration:
            time.sleep(0.1)
            continue

        features = music_analyzer.get_features(current_time)

        # Update BPM
        bpm = features['bpm']

        # Update master amplitude from RMS
        master_amplitude = min(features['rms'] * 3.0, 1.0)

        # Update amplitude ratio based on complexity
        amplitude1, amplitude2 = calculate_amplitude_ratio(features['complexity'])

        # Update motor controller
        motor_controller.set_motion_parameters(amplitude1, amplitude2, master_amplitude, bpm)

        time.sleep(0.05)  # Update at 20 Hz


def setup_music_playback(audio_file: str, play_music: bool):
    """
    Start music playback and analysis.

    Args:
        audio_file: Path to audio file
        play_music: Whether to play audio

    Returns:
        threading.Thread: Feature update thread (or None if not playing music)
    """
    global audio_start_time, audio_process, music_analyzer

    if not play_music:
        return None

    # Start music analysis
    music_analyzer.start_continuous_analysis(get_real_audio_time)

    # Start audio playback with precise timing
    time.sleep(0.35)  # Buffer time
    audio_process = play_audio_thread(audio_file)
    audio_start_time = time.time()  # Record exact start time

    return None  # Feature thread created separately


def cleanup_session(play_music: bool, viz_manager: VisualizationManager,
                   audio_synth: AudioSynthesizer = None):
    """
    Clean up resources after control loop finishes.

    Args:
        play_music: Whether music was playing
        viz_manager: VisualizationManager to close
        audio_synth: Optional AudioSynthesizer to stop
    """
    global music_analyzer, audio_process, audio_start_time

    if play_music and music_analyzer:
        music_analyzer.stop()
        if audio_process:
            terminate_subprocess(audio_process)
        audio_start_time = None

    if viz_manager:
        viz_manager.close()

    if audio_synth and audio_synth.is_running():
        audio_synth.stop()


def run_control_loop(motor_controller: MotorController,
                    viz_manager: VisualizationManager,
                    audio_file: str,
                    duration: float,
                    play_music: bool = True,
                    audio_synth: AudioSynthesizer = None,
                    data_recorder = None):
    """
    Main motor control loop with music synchronization.

    Args:
        motor_controller: MotorController instance
        viz_manager: VisualizationManager instance
        audio_file: Path to audio file
        duration: Duration to run in seconds
        play_music: Whether to play audio
        audio_synth: Optional audio synthesizer
        data_recorder: Optional DataRecorder for logging position/amplitude data
    """
    global program_running, current_motor_position, music_analyzer

    # Setup music playback
    setup_music_playback(audio_file, play_music)

    # Start background thread to update parameters from music
    if play_music:
        feature_thread = threading.Thread(
            target=update_from_music_features,
            args=(motor_controller,),
            daemon=True
        )
        feature_thread.start()

    # Start audio synthesis if enabled
    if audio_synth:
        audio_synth.set_position_callback(lambda: current_motor_position)
        audio_synth.start()

    # Timing setup
    start_time = time.time()
    next_control_time = start_time + motor_controller.control_period

    # Reset statistics
    motor_controller.reset_statistics()

    print("\n=== Synchronization Active ===")
    print(f"Mode: {'SIMULATION' if motor_controller.is_simulation_mode() else 'HARDWARE'}")
    print(f"Delay Compensation: {'ENABLED' if motor_controller.phase_correction_enabled else 'DISABLED'}")
    print(f"Audio Synthesis: {'ENABLED' if (audio_synth and audio_synth.is_running()) else 'DISABLED'}")
    print(f"Visualization: {'ENABLED' if viz_manager else 'DISABLED'}")
    print("==============================\n")

    iteration = 0
    while program_running:
        # Check for hardware errors
        if motor_controller.check_hardware_errors():
            break

        # Get current time
        current_time = get_real_audio_time() if play_music else (time.time() - start_time)

        if current_time >= duration:
            break

        # Get current encoder position
        current_encoder_pos = motor_controller.get_current_encoder_position()
        current_motor_position = current_encoder_pos  # Update for audio synthesis

        # Apply beat phase locking if music is playing and delay compensation is enabled
        if play_music and music_analyzer is not None:
            beat_phase = music_analyzer.current_beat_phase

            # Apply beat phase lock only if delay compensation is enabled
            if motor_controller.phase_correction_enabled:
                motor_controller.apply_beat_phase_lock(beat_phase, current_time)

            # Update visualization with beat data
            if viz_manager:
                viz_manager.update_beat_rms(beat_phase, motor_controller.bpm)

        # Calculate expected position
        expected_pos = motor_controller.calculate_expected_position(current_time)

        # Record data if recorder is active
        if data_recorder and data_recorder.is_recording():
            original_pos = motor_controller.calculate_original_position(current_time)
            user_amp = motor_controller.get_user_amplitude()
            data_recorder.record_sample(user_amp, original_pos, expected_pos)

        # Calculate position error
        position_error = expected_pos - current_encoder_pos

        # Update statistics
        motor_controller.update_statistics(position_error)

        # Apply position-based phase correction only if delay compensation is enabled
        if motor_controller.phase_correction_enabled:
            motor_controller.apply_position_phase_correction()

        # Send motor command
        motor_controller.send_motor_command(expected_pos)

        # Update visualization
        if viz_manager:
            # Get feedback position (might be different from command in simulation)
            feedback_pos = motor_controller.get_current_encoder_position()
            viz_manager.update_position(expected_pos, feedback_pos)

        # Display status every 30 iterations (~0.5 seconds at 60Hz)
        if iteration % 250 == 0:
            complexity = music_analyzer.current_complexity if music_analyzer else 0.0
            motor_controller.print_status(current_time, position_error, complexity)

        # Wait until next control interval
        current_wall_time = time.time()
        sleep_time = next_control_time - current_wall_time
        if sleep_time > 0:
            time.sleep(sleep_time)

        next_control_time += motor_controller.control_period

        # If we've fallen behind, reset
        if next_control_time < time.time():
            next_control_time = time.time() + motor_controller.control_period

        iteration += 1

    motor_controller.print_final_statistics()
    cleanup_session(play_music, viz_manager, audio_synth)


def keyboard_listener():
    """Listen for keyboard input to control the program."""
    global program_running

    def on_press(key):
        global program_running
        try:
            if key == keyboard.Key.esc:
                print("\nExit command received (ESC key)")
                program_running = False
                return False  # Stop listener
        except Exception as e:
            print(f"Keyboard error: {e}")

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


def main():
    """Main function with argparse for command-line options."""
    global program_running, music_analyzer

    parser = argparse.ArgumentParser(
        description="ODrive motor control synchronized with music analysis."
    )
    parser.add_argument('-c', '--calibrate', action='store_true',
                       help="Calibrate ODrive")
    parser.add_argument('-r', '--reset', action='store_true',
                       help="Reset ODrive (clear errors) before starting")
    parser.add_argument('-wm', '--without_music', action='store_true',
                       help="Run without music")
    parser.add_argument('-w', '--window_size', type=float, default=2.0,
                       help="Music analysis window size in seconds (default: 2.0)")
    parser.add_argument('-dc', '--delay_compensation', action='store_true',
                       help="Enable delay compensation / phase correction")
    parser.add_argument('-sim', '--simulate', action='store_true',
                       help="Simulation mode - run without ODrive hardware")
    parser.add_argument('-a', '--audio', action='store_true',
                       help="Enable audio synthesis from motor position")
    parser.add_argument('-plot', '--plot', action='store_true',
                       help="Enable real-time sine wave plot (hardware mode)")
    parser.add_argument('-g', '--genre', type=str, default='edm',
                       help="Music genre (metal/classic/edm, default: edm)")
    parser.add_argument('-s', '--song_index', type=int, default=-1,
                       help="Song index in genre (-1 for last, default: -1)")
    parser.add_argument('-i', '--interactive', action='store_true',
                       help="Interactive song selection")

    args = parser.parse_args()

    # Select music file
    music_library = MusicLibrary()

    if args.interactive:
        audio_file = music_library.select_song_interactive()
        if audio_file is None:
            audio_file = get_default_song()
            print(f"Using default song: {audio_file}")
    else:
        try:
            audio_file = music_library.get_song_path(args.genre, args.song_index)
            print(f"Selected: {music_library.current_song}")
        except (KeyError, IndexError) as e:
            print(f"Error: {e}")
            print("Using default song")
            audio_file = get_default_song()

    # Initialize music analyzer
    print("Initializing music analyzer...")
    music_analyzer = MusicAnalyzer(audio_file, window_size=args.window_size)
    audio_duration = music_analyzer.get_duration()
    print(f"Audio duration: {audio_duration:.2f} seconds")

    # Connect to ODrive (skip in simulation mode)
    odrv0 = None
    initial_position = 0.0
    if not args.simulate:
        print("Looking for ODrive... (Press ESC to cancel)")

        # Start keyboard listener early
        keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True)
        keyboard_thread.start()

        # Search for ODrive
        odrv0 = connect_to_odrive()

        if not program_running:
            print("ODrive search cancelled by user")
            return
        print("ODrive found")

        # Reset if requested
        if args.reset:
            soft_reset(odrv0)

        # Read initial motor position BEFORE arming
        initial_position = read_initial_motor_position(odrv0)

        # Calibrate if requested
        if args.calibrate:
            configure_odrive(odrv0)
            odrv0.connect_to_odrive()
            arm(odrv0)
        else:
            arm(odrv0)
    else:
        print("Running in SIMULATION mode (no ODrive connection)")
        # Start keyboard listener for simulation mode
        keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True)
        keyboard_thread.start()

    # Initialize motor controller with initial position offset
    motor_controller = MotorController(
        odrv0=odrv0,
        phase_correction_enabled=args.delay_compensation,
        initial_position_offset=initial_position
    )

    # Initialize visualization
    viz_manager = VisualizationManager(
        simulation_mode=args.simulate,
        plot_enabled=args.plot
    )

    # Initialize audio synthesizer (optional)
    audio_synth = None
    if args.audio:
        audio_synth = AudioSynthesizer()

    print("\n=== Controls ===")
    print("Press 'ESC' to exit")
    print("================\n")

    input("Press Enter to start...\n")

    try:
        while program_running:
            run_control_loop(
                motor_controller,
                viz_manager,
                audio_file,
                audio_duration,
                play_music=not args.without_music,
                audio_synth=audio_synth
            )

            if not args.without_music:
                # If music finished, ask to replay
                response = input("\nReplay? (y/n): ")
                if response.lower() != 'y':
                    break
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        time.sleep(1)
        if odrv0 is not None:
            odrv0.axis0.requested_state = AXIS_STATE_IDLE
        if music_analyzer:
            music_analyzer.stop()
        if viz_manager:
            viz_manager.close()
        if audio_synth:
            audio_synth.stop()

    print("Session finished")


if __name__ == "__main__":
    main()