import time
import math
import subprocess
import threading
import os
import csv
import argparse
from pynput import keyboard
from music_analyzer import MusicAnalyzer
import numpy as np
from floor_simulator import FloorPlatformSimulator, SineWavePlotter
import pyaudio
import queue
import matplotlib.pyplot as plt
from collections import deque
from odrive_controller import (ODriveController, configure_odrive, start_and_skip_config_legacy,
                               soft_reset, print_errors)
from odrive.enums import AXIS_STATE_IDLE
import odrive

### Favorites: 
## Metal: Machine Head - Locust
## classical: 2nd movement  Paavo Järvi and the Deutsche Kammerphilharmonie Bremen
## EDM: 

# Audio file configuration
audio_files = {"metal": ["Machine Head - Davidian", "Machine Head - Locust", "MACHINE HEAD - OUTSIDER", "For Whom The Bell Tolls (Remastered)"], 
               "classic": ["Schubert - Serenade", "Beethoven_ Symphony No. 7, 2nd movement  Paavo Järvi and the Deutsche Kammerphilharmonie Bremen", "Mozart - Lacrimosa"], 
               "EDM": ["Made_Me_Like_This", "Husko - Goodnight"]}
audio_file = "songs" + "/" + audio_files["EDM"][-1] + ".mp3"
csv_filename = 'stored_patterns.csv'

# Control parameters (will be driven by music features)
amplitude1 = 5.0  # Initial value for sin1
amplitude2 = 0.0  # Initial value for sin2 (controlled by complexity)
master_amplitude = 0.0  # Controlled by RMS
bpm = 120  # Will be extracted from music
phase = 0  # Initial phase
program_running = True

# Music analyzer instance
music_analyzer = None

# Real playback time tracking
audio_start_time = None
audio_process = None

# Synchronization parameters
phase_correction_enabled = True
phase_correction_gain = 0.05  # How aggressively to correct phase drift (lower = smoother)
phase_lock_threshold = 0.1  # Position error threshold for considering "locked"

# Audio synthesis parameters
audio_synthesis_enabled = False  # Controlled by -a flag
plot_enabled = False  # Controlled by -plot flag
current_motor_position = 0.0
position_queue = queue.Queue(maxsize=100)
position_history = deque(maxlen=200)  # Store last 200 samples for plotting
time_history = deque(maxlen=200)


def get_audio_duration(file_path):
    """Get audio file duration using ffprobe."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )

    if result.returncode != 0:
        raise RuntimeError(f"Error getting audio duration: {result.stderr.decode()}")

    return float(result.stdout)


def get_real_audio_time():
    """
    Get the real playback time of the audio using system time.
    This provides more accurate synchronization than software time.
    """
    if audio_start_time is None:
        return 0.0
    return time.time() - audio_start_time


def store_current_values(csv_filename):
    """Store current amplitude, BPM, and phase values to CSV file."""
    global amplitude1, amplitude2, master_amplitude, bpm, phase

    stored_values = {
        'amplitude1': amplitude1,
        'amplitude2': amplitude2,
        'master_amplitude': master_amplitude,
        'bpm': bpm,
        'phase': phase
    }

    # Determine a unique identifier
    unique_id = 1

    # Check if the CSV file exists
    if os.path.exists(csv_filename):
        with open(csv_filename, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            existing_ids = [int(row['id']) for row in reader if 'id' in row]
            if existing_ids:
                unique_id = max(existing_ids) + 1

    # Prepare the stored entry by adding the ID
    stored_entry = {'id': unique_id}
    stored_entry.update(stored_values)

    # Write the new row to the CSV file
    file_existed = os.path.exists(csv_filename)
    with open(csv_filename, 'a', newline='') as csvfile:
        fieldnames = ['id', 'amplitude1', 'amplitude2', 'master_amplitude', 'bpm', 'phase']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_existed:
            writer.writeheader()

        writer.writerow(stored_entry)

    print(f"\nStored settings with ID {unique_id} in {csv_filename}")


def read_patterns(csv_filename):
    """Read stored patterns from CSV file."""
    patterns = []

    if os.path.exists(csv_filename):
        with open(csv_filename, newline='') as csvfile:
            reader = csv.DictReader(csvfile)

            try:
                fieldnames = reader.fieldnames
                for row in reader:
                    try:
                        pattern = {key: float(value) for key, value in row.items() if key != 'id'}
                        patterns.append(pattern)
                    except ValueError as e:
                        print(f"Skipping row due to conversion error: {row} -> {e}")

            except csv.Error as e:
                print(f"CSV Error: {e}")
    else:
        print(f"CSV file not found: {csv_filename}")

    print(f"{len(patterns)} patterns loaded from CSV file")
    return patterns


def play_audio_thread(file_path):
    """Launch audio playback subprocess."""
    process = subprocess.Popen(
        ['ffplay', '-nodisp', '-autoexit', file_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return process


def terminate_subprocess(process):
    """Gracefully terminate a subprocess."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


# Legacy functions for backwards compatibility - now using odrive_controller module
configure_odrive = configure_odrive
start_and_skip_config = start_and_skip_config_legacy


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
    # Base amplitude - adjust this to control overall movement range
    base_amplitude = 10.0

    # Low complexity: mainly amplitude1, amplitude2 = 0
    # High complexity: amplitude1 and amplitude2 are similar
    amplitude1 = base_amplitude * (1.0 - complexity * 0.5)  # Scales from base to 0.5*base
    amplitude2 = base_amplitude * complexity  # Scales from 0 to base

    return amplitude1, amplitude2


def audio_synthesis_thread():
    """
    Generate real-time sine wave audio based on motor position.
    Runs in a separate thread.
    """
    global program_running, current_motor_position, audio_synthesis_enabled

    # Audio parameters
    sample_rate = 44100
    chunk_size = 1024

    # Initialize PyAudio
    p = pyaudio.PyAudio()

    try:
        stream = p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=sample_rate,
            output=True,
            frames_per_buffer=chunk_size
        )

        print("Audio synthesis started")

        # Phase accumulator for smooth frequency transitions
        phase = 0.0

        while program_running and audio_synthesis_enabled:
            # Map motor position to frequency
            # Assuming motor position ranges roughly -10 to +10
            # Map to frequency range 200Hz to 800Hz
            base_freq = 440.0  # A4
            position = current_motor_position

            # Scale position to frequency deviation
            # ±10 position -> ±200Hz deviation
            freq = base_freq + (position * 20.0)
            freq = np.clip(freq, 100, 2000)  # Limit frequency range

            # Generate audio samples
            samples = np.zeros(chunk_size, dtype=np.float32)

            for i in range(chunk_size):
                samples[i] = 0.2 * np.sin(phase)  # 0.2 amplitude to avoid clipping
                phase += 2.0 * np.pi * freq / sample_rate

                # Keep phase wrapped to prevent overflow
                if phase > 2.0 * np.pi:
                    phase -= 2.0 * np.pi

            # Write to audio stream
            stream.write(samples.tobytes())

        stream.stop_stream()
        stream.close()

    except Exception as e:
        print(f"Audio synthesis error: {e}")
    finally:
        p.terminate()
        print("Audio synthesis stopped")


def setup_plot():
    """
    Set up the plot window. Must be called from main thread on macOS.
    Returns fig, ax, line objects for updating.
    """
    print("Starting position plot window...")

    # Use non-GUI backend that can be updated from main thread
    plt.ion()  # Interactive mode
    fig, ax = plt.subplots(figsize=(10, 6))
    line, = ax.plot([], [], 'b-', linewidth=2)

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Motor Position', fontsize=12)
    ax.set_title('Real-Time Motor Position', fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(-15, 15)

    plt.show(block=False)
    plt.pause(0.001)  # Allow window to render

    return fig, ax, line


def update_plot(fig, ax, line):
    """
    Update the plot with current position data.
    Should be called periodically from the main control loop.
    """
    global position_history, time_history

    try:
        if len(position_history) > 0 and len(time_history) > 0:
            # Convert deques to lists for plotting
            times = list(time_history)
            positions = list(position_history)

            # Update plot data
            line.set_data(times, positions)

            # Auto-scale x-axis to show last 5 seconds
            if len(times) > 1:
                ax.set_xlim(max(0, times[-1] - 5), times[-1] + 0.5)

            # Redraw
            fig.canvas.draw()
            fig.canvas.flush_events()
            plt.pause(0.001)  # Allow GUI events to process

    except Exception as e:
        print(f"Plot update error: {e}")


def update_from_music_features():
    """
    Update motor control parameters based on music features.
    This runs continuously in the background.
    """
    global amplitude1, amplitude2, master_amplitude, bpm, music_analyzer

    while program_running and music_analyzer is not None:
        # Get current music features
        current_time = get_real_audio_time()

        if current_time >= music_analyzer.duration:
            time.sleep(0.1)
            continue

        features = music_analyzer.get_features(current_time)

        # Update BPM
        bpm = features['bpm']

        # Update master amplitude from RMS (scale appropriately)
        # RMS typically ranges from 0 to ~0.3, scale to 0-1 range for master_amplitude
        master_amplitude = min(features['rms'] * 3.0, 1.0)

        # Update amplitude ratio based on complexity
        amplitude1, amplitude2 = calculate_amplitude_ratio(features['complexity'])

        time.sleep(0.05)  # Update at 20 Hz


def setup_music_playback(play_music):
    """
    Start music playback and analysis.

    Args:
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

    # Start background thread to update parameters from music
    feature_thread = threading.Thread(target=update_from_music_features, daemon=True)
    feature_thread.start()

    return feature_thread


def setup_visualization(simulation_mode, plot_enabled):
    """
    Initialize visualization (simulator or standalone plotter).

    Args:
        simulation_mode: Whether running in simulation mode
        plot_enabled: Whether plotting is enabled

    Returns:
        tuple: (simulator, standalone_plotter)
    """
    simulator = None
    standalone_plotter = None

    if simulation_mode:
        # Always enable the PyBullet built-in plot visualization
        simulator = FloorPlatformSimulator(enable_gui=True, show_plot=True)
    elif plot_enabled:
        # In hardware mode with -plot flag, create standalone plotter
        standalone_plotter = SineWavePlotter(window_duration=4.0, update_rate=60)
        standalone_plotter.start()

    return simulator, standalone_plotter


def apply_beat_phase_lock(beat_phase, beat_locked, current_time, frequency, phase_offset,
                          beat_count, phase_error_history):
    """
    Apply bidirectional phase locking based on strong beat detection (beat 1 of bar).

    Only corrects on the downbeat (first beat of each bar in 4/4 time) and uses
    the mean of the last 3 corrections for smoother, more responsive adjustment.

    Args:
        beat_phase: Current beat phase from music analyzer
        beat_locked: Whether currently locked to a beat
        current_time: Current time in seconds
        frequency: Frequency in Hz
        phase_offset: Current phase offset
        beat_count: Counter for beats (0-3 for 4/4 time)
        phase_error_history: List of recent phase errors from last beats

    Returns:
        tuple: (new_phase_offset, new_beat_locked, new_beat_count, updated_history)
    """
    if beat_phase < 0.1 and not beat_locked:
        beat_locked = True
        beat_count = (beat_count + 1) % 4  # Cycle through 0-3 for 4/4 time

        # Calculate phase error at this beat
        expected_phase_at_beat = (2 * math.pi * frequency * current_time + phase_offset) % (2 * math.pi)

        # Find shortest rotation to get to 0 (bidirectional correction)
        if expected_phase_at_beat > math.pi:
            beat_phase_error = -(2 * math.pi - expected_phase_at_beat)
        else:
            beat_phase_error = -expected_phase_at_beat

        # Store this beat's error in history
        phase_error_history.append(beat_phase_error)
        if len(phase_error_history) > 3:
            phase_error_history.pop(0)  # Keep only last 3

        # Only correct on beat 1 (downbeat) of each bar
        if beat_count == 0 and len(phase_error_history) >= 2:
            # Use mean of last 3 beats for smoother, more reliable correction
            mean_phase_error = np.mean(phase_error_history)

            # Apply correction if significant
            if abs(mean_phase_error) > 0.05:  # Lower threshold for more responsiveness
                # More aggressive correction since we only correct once per bar
                correction_gain = 0.5  # Higher gain since correcting less frequently
                max_beat_correction = 0.3  # Allow larger correction on downbeat

                limited_correction = np.clip(
                    correction_gain * mean_phase_error,
                    -max_beat_correction,
                    max_beat_correction
                )
                phase_offset += limited_correction

                print(f"\n[Downbeat Correction] Error: {mean_phase_error:.3f} → Correction: {limited_correction:.3f}")

    elif beat_phase > 0.1:
        beat_locked = False

    return phase_offset, beat_locked, beat_count, phase_error_history


def apply_position_phase_correction(error_samples, phase_offset, phase_correction_gain, sampling_rate):
    """
    Apply bidirectional phase correction based on position error.

    Corrects both leading (ahead) and lagging (behind) phase errors.

    Args:
        error_samples: List of recent position errors
        phase_offset: Current phase offset
        phase_correction_gain: Gain for phase correction
        sampling_rate: Control loop sampling rate

    Returns:
        tuple: (new_phase_offset, phase_velocity_estimate)
    """
    phase_velocity_estimate = 0.0

    if len(error_samples) > 20:
        # Calculate average error over recent samples
        avg_error = np.mean(error_samples[-20:])

        # Bidirectional proportional correction with damping
        # Positive error: control signal is ahead (leading) → reduce phase
        # Negative error: control signal is behind (lagging) → increase phase
        if abs(avg_error) > 0.02:  # Only correct if error is significant
            # Phase correction is proportional to position error
            # The sign of avg_error determines direction:
            # - Positive error (expected > actual) → need to slow down → subtract from phase
            # - Negative error (expected < actual) → need to speed up → add to phase
            phase_correction = phase_correction_gain * avg_error

            # Apply correction with limiting to prevent overcorrection
            max_correction_per_step = 0.01  # Limit correction rate
            phase_correction = np.clip(phase_correction, -max_correction_per_step, max_correction_per_step)

            phase_offset += phase_correction

            # Track phase drift for diagnostics
            phase_velocity_estimate = phase_correction * sampling_rate

    return phase_offset, phase_velocity_estimate


def send_motor_command(expected_pos, simulation_mode, odrv0, simulator, standalone_plotter,
                       simulated_encoder_pos, current_encoder_pos):
    """
    Send motor command and update visualizations.

    Args:
        expected_pos: Expected/commanded position
        simulation_mode: Whether in simulation mode
        odrv0: ODrive object (or None)
        simulator: FloorPlatformSimulator (or None)
        standalone_plotter: SineWavePlotter (or None)
        simulated_encoder_pos: Current simulated position
        current_encoder_pos: Current encoder position

    Returns:
        float: Updated simulated_encoder_pos
    """
    if simulation_mode:
        # In simulation mode, simulate motor response with 90% tracking
        simulated_encoder_pos += 0.9 * (expected_pos - simulated_encoder_pos)
        # Update PyBullet visualization with both command and feedback
        if simulator is not None:
            simulator.update_position(expected_pos, feedback_position=simulated_encoder_pos)
            simulator.step_simulation()
    else:
        # Hardware mode: send command to ODrive
        odrv0.axis0.controller.input_pos = expected_pos

        # Update standalone plotter if enabled
        if standalone_plotter is not None:
            standalone_plotter.add_point(expected_pos, feedback_position=current_encoder_pos)
            standalone_plotter.update()

    return simulated_encoder_pos


def cleanup_session(play_music, simulator, standalone_plotter):
    """
    Clean up resources after control loop finishes.

    Args:
        play_music: Whether music was playing
        simulator: FloorPlatformSimulator to close (or None)
        standalone_plotter: SineWavePlotter to close (or None)
    """
    global music_analyzer, audio_process, audio_start_time

    if play_music:
        music_analyzer.stop()
        terminate_subprocess(audio_process)
        audio_start_time = None

    # Clean up simulator
    if simulator is not None:
        simulator.close()

    # Clean up standalone plotter
    if standalone_plotter is not None:
        standalone_plotter.close()


def calculate_expected_position(current_time, frequency, phase_offset):
    """
    Calculate the expected motor position based on time and music parameters.

    Args:
        current_time: Current time in seconds
        frequency: Frequency in Hz (derived from BPM)
        phase_offset: Phase offset in radians

    Returns:
        float: Expected position
    """
    global amplitude1, amplitude2, master_amplitude

    # Calculate position commands with beat-locked phase
    pos_command1 = amplitude1 * math.sin(2 * math.pi * frequency * current_time + phase_offset)
    pos_command2 = amplitude2 * math.sin(2 * math.pi * (frequency / 2) * current_time + phase_offset)

    # Combine sinusoids and apply master amplitude
    return (pos_command1 + pos_command2) * master_amplitude


def run_control_loop(odrv0, duration, play_music=True):
    """
    Main motor control loop with music synchronization.

    Args:
        odrv0: ODrive object (or None for simulation mode)
        duration: Duration to run in seconds
        play_music: Whether to play audio
    """
    global amplitude1, amplitude2, master_amplitude, phase, bpm, program_running
    global audio_start_time, audio_process, music_analyzer, phase_correction_enabled
    global current_motor_position, audio_synthesis_enabled, plot_enabled
    global position_history, time_history

    # Check if running in simulation mode
    simulation_mode = (odrv0 is None)

    # Setup music playback
    feature_thread = setup_music_playback(play_music)

    # Timing setup
    sampling_rate = 60  # 60Hz motor control rate for better synchronization
    control_period = 1.0 / sampling_rate  # Time between control updates
    start_time = time.time()
    next_control_time = start_time + control_period  # Absolute time for next iteration

    # Synchronization variables
    phase_offset = phase  # Initial phase offset
    beat_locked = False
    beat_count = -1  # Beat counter for 4/4 time (will increment to 0 on first beat)
    phase_error_history = []  # Store last 3 beat phase errors

    # Statistics tracking
    max_position_error = 0.0
    avg_position_error = 0.0
    error_samples = []
    phase_velocity_estimate = 0.0

    # Simulated encoder position for simulation mode
    simulated_encoder_pos = 0.0

    # Setup visualization
    simulator, standalone_plotter = setup_visualization(simulation_mode, plot_enabled)

    # Start audio synthesis thread
    audio_thread = None
    if audio_synthesis_enabled:
        audio_thread = threading.Thread(target=audio_synthesis_thread, daemon=True)
        audio_thread.start()

    print("\n=== Synchronization Active ===")
    if simulation_mode:
        print("Mode: SIMULATION (no hardware, PyBullet plot enabled)")
    else:
        print("Mode: HARDWARE")
    print("Phase Correction:", "ENABLED" if phase_correction_enabled else "DISABLED")
    print("Audio Synthesis:", "ENABLED" if audio_synthesis_enabled else "DISABLED")
    print("Sine Wave Plot:", "ENABLED" if (plot_enabled or simulation_mode) else "DISABLED")
    print("==============================\n")

    while True:
        if not simulation_mode and odrv0.axis0.error != 0:
            print(f"Axis error: {odrv0.axis0.error}")
            break

        # Use real audio time for synchronization
        current_time = get_real_audio_time() if play_music else (time.time() - start_time)

        if current_time >= duration:
            break

        # Get current encoder position (actual motor position or simulated)
        if simulation_mode:
            # In simulation mode, get actual position from PyBullet physics
            current_encoder_pos = simulator.get_actual_platform_position() if simulator else simulated_encoder_pos
        else:
            current_encoder_pos = odrv0.axis0.encoder.pos_estimate

        # Calculate frequency from BPM
        frequency = bpm / 60  # Convert BPM to Hz

        # Apply beat phase locking if music is playing
        if play_music and music_analyzer is not None:
            beat_phase = music_analyzer.current_beat_phase
            phase_offset, beat_locked, beat_count, phase_error_history = apply_beat_phase_lock(
                beat_phase, beat_locked, current_time, frequency, phase_offset,
                beat_count, phase_error_history
            )

            # Update plotter with beat and BPM data
            if standalone_plotter is not None:
                standalone_plotter.update_beat_rms(beat_phase, bpm)

        # Calculate expected position
        expected_pos = calculate_expected_position(current_time, frequency, phase_offset)

        # Calculate position error (difference between expected and actual)
        position_error = expected_pos - current_encoder_pos

        # Track error statistics
        error_samples.append(position_error)
        if len(error_samples) > 100:
            error_samples.pop(0)

        # Apply position-based phase correction
        if phase_correction_enabled:
            phase_offset, phase_velocity_estimate = apply_position_phase_correction(
                error_samples, phase_offset, phase_correction_gain, sampling_rate
            )

        # Send motor command and update visualizations
        simulated_encoder_pos = send_motor_command(
            expected_pos, simulation_mode, odrv0, simulator, standalone_plotter,
            simulated_encoder_pos, current_encoder_pos
        )

        # Update beat reference wave in simulator's plotter (if simulation mode with music)
        if simulation_mode and play_music and simulator is not None and music_analyzer is not None:
            if simulator.plotter is not None:
                simulator.plotter.update_beat_rms(music_analyzer.current_beat_phase, bpm)

        # Update current motor position for audio synthesis and plotting
        current_motor_position = current_encoder_pos

        # Position history and plotting is now handled by PyBullet's built-in visualization
        # (updated automatically in simulator.update_position())

        # Update statistics
        max_position_error = max(max_position_error, abs(position_error))
        avg_position_error = np.mean([abs(e) for e in error_samples]) if error_samples else 0.0

        # Display real-time status every 30 iterations (~0.5 seconds at 60Hz)
        if int(current_time * sampling_rate) % 30 == 0:
            mode_str = "[SIM] " if simulation_mode else ""
            lock_status = "🔒" if abs(avg_position_error) < phase_lock_threshold else "🔓"
            beat_indicator = "♪" if beat_locked else " "
            print(f"\r{mode_str}Time: {current_time:.2f}s | BPM: {bpm:.1f} {beat_indicator} | "
                  f"RMS: {master_amplitude:.2f} | Complexity: {music_analyzer.current_complexity:.2f} | "
                  f"Pos Error: {position_error:+.3f} (avg: {avg_position_error:.3f}, max: {max_position_error:.3f}) {lock_status} | "
                  f"Phase: {phase_offset:.2f}", end="")

        # Wait until next control interval using absolute timestamps
        # This prevents drift accumulation from software timing
        current_wall_time = time.time()
        sleep_time = next_control_time - current_wall_time
        if sleep_time > 0:
            time.sleep(sleep_time)

        # Schedule next control update at absolute time
        next_control_time += control_period

        # If we've fallen behind, reset to avoid playing catch-up
        if next_control_time < time.time():
            next_control_time = time.time() + control_period

        if not program_running:
            break

    print("\n\n=== Synchronization Statistics ===")
    print(f"Maximum position error: {max_position_error:.4f}")
    print(f"Average position error: {avg_position_error:.4f}")
    print(f"Final phase offset: {phase_offset:.4f}")
    print("==================================\n")

    # Cleanup resources
    cleanup_session(play_music, simulator, standalone_plotter)


def keyboard_listener():
    """Listen for keyboard input to store patterns."""
    global program_running, phase_correction_enabled

    def on_press(key):
        global phase_correction_enabled, program_running
        try:
            if hasattr(key, 'char') and key.char == 's':
                store_current_values(csv_filename)
            elif hasattr(key, 'char') and key.char == 'p':
                phase_correction_enabled = not phase_correction_enabled
                status = "ENABLED" if phase_correction_enabled else "DISABLED"
                print(f"\nPhase correction {status}")
            elif key == keyboard.Key.esc:
                print("\nExit command received (ESC key)")
                program_running = False
                return False  # Stop listener
        except Exception as e:
            print(f"Keyboard error: {e}")

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


def main():
    """Main function with argparse for command-line options."""
    global program_running, music_analyzer, phase_correction_enabled
    global audio_synthesis_enabled, plot_enabled

    parser = argparse.ArgumentParser(description="ODrive motor control synchronized with music analysis.")
    parser.add_argument('-c', '--calibrate', action='store_true', help="Calibrate ODrive")
    parser.add_argument('-r', '--reset', action='store_true', help="Reset ODrive (clear errors) before starting")
    parser.add_argument('-wm', '--without_music', action='store_true', help="Run without music")
    parser.add_argument('-w', '--window_size', type=float, default=5.0,
                        help="Music analysis window size in seconds (default: 2.0)")
    parser.add_argument('-npc', '--no_phase_correction', action='store_true',
                        help="Disable phase correction")
    parser.add_argument('-sim', '--simulate', action='store_true',
                        help="Simulation mode - run without ODrive hardware")
    parser.add_argument('-a', '--audio', action='store_true',
                        help="Enable audio synthesis from motor position")
    parser.add_argument('-plot', '--plot', action='store_true',
                        help="Enable real-time sine wave plot (hardware mode only; always on in -sim mode)")

    args = parser.parse_args()

    if args.no_phase_correction:
        phase_correction_enabled = False

    if args.audio:
        audio_synthesis_enabled = True

    if args.plot:
        plot_enabled = True

    # Initialize music analyzer
    print("Initializing music analyzer...")
    music_analyzer = MusicAnalyzer(audio_file, window_size=args.window_size)
    audio_duration = music_analyzer.get_duration()
    print(f"Audio duration: {audio_duration:.2f} seconds")

    # Connect to ODrive (skip in simulation mode)
    odrv0 = None
    if args.simulate:
        print("Running in SIMULATION mode (no ODrive connection)")
        odrv0 = None
    else:
        print("Looking for ODrive... (Press ESC to cancel)")

        # Start keyboard listener early to allow ESC during ODrive search
        keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True)
        keyboard_thread.start()

        # Search for ODrive with periodic checks for exit request
        odrv0 = None
        search_thread = threading.Thread(target=lambda: setattr(search_thread, 'result', odrive.find_any()), daemon=True)
        search_thread.result = None
        search_thread.start()

        while search_thread.is_alive() and program_running:
            time.sleep(0.1)

        if not program_running:
            print("ODrive search cancelled by user")
            return

        odrv0 = search_thread.result
        print("ODrive found")

        # Reset if requested
        if args.reset:
            soft_reset(odrv0)

        # Calibrate if requested
        if args.calibrate:
            configure_odrive(odrv0)
        else:
            start_and_skip_config(odrv0)

    # Start keyboard listener in background thread (if not already started in normal mode)
    if args.simulate:
        keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True)
        keyboard_thread.start()

    print("\n=== Controls ===")
    print("Press 's' to store current pattern")
    print("Press 'p' to toggle phase correction")
    print("Press 'ESC' to exit")
    print("================\n")

    input("Press Enter to start...\n")

    try:
        while program_running:
            run_control_loop(odrv0, audio_duration, play_music=not args.without_music)

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

    print("Session finished")


if __name__ == "__main__":
    main()
