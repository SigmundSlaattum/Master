#!/usr/bin/env python3
"""
Web Interface for Music-Synchronized Motor Control

Simplified Flask/SocketIO web interface for the refactored system.

To start audio: python -c "import sounddevice as sd; print(sd.query_devices()); print('\nDefault output:', sd.default.device[1])"

"""

import os
import sys
import json
import threading
import time
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import odrive
from odrive.enums import AXIS_STATE_IDLE, AXIS_STATE_CLOSED_LOOP_CONTROL
    
from config import SONGS_DIR, SONGS_LEGACY_DIR, CONFIG_DIR
from offline import SongManager
from core import create_playback_controller, PlaybackController, TrajectoryPlayer
from calibration import LatencyCalibrator
from odrive_controller import configure_odrive, arm, soft_reset
from bluetooth_controller import BluetoothController
from data_recorder import DataRecorder
from user_study import UserStudyManager, SongConfig, PatternType

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'music-motor-sync-secret'
socketio = SocketIO(app, cors_allowed_origins="*")


class SystemState:
    """Global system state."""

    def __init__(self):
        self.odrv0 = None
        self.controller: PlaybackController = None
        self.status = "idle"
        self.current_song_id = None
        self.initial_position = 0.0
        self.latency_offset_s = 0.035

        # Feedforward control
        self.feedforward_enabled = True  # Enabled by default when available

        # Bluetooth remote control
        self.bluetooth = BluetoothController()
        self.bluetooth_user_amplitude = 0.3  # Track amplitude from remote
        self.amplitude_locked = False  # Lock amplitude control (e.g., during no-motion trials)

        # Data recorder
        self.data_recorder = DataRecorder()

        # User study manager
        self.user_study = UserStudyManager()

        # Load calibration
        self._load_calibration()

        # Song managers for both libraries
        self.song_manager_standard = SongManager(str(SONGS_DIR))
        self.song_manager_legacy = SongManager(str(SONGS_LEGACY_DIR))

        # Current library selection ('standard' or 'legacy')
        self.current_library = 'standard'

    @property
    def song_manager(self) -> SongManager:
        """Get the currently selected song manager."""
        if self.current_library == 'legacy':
            return self.song_manager_legacy
        return self.song_manager_standard

    def _load_calibration(self):
        """Load latency calibration from config."""
        try:
            calibrator = LatencyCalibrator(config_path=str(CONFIG_DIR / "latency.json"))
            self.latency_offset_s = calibrator.get_latency_offset_seconds()
        except:
            self.latency_offset_s = 0.035


state = SystemState()


# Bluetooth callbacks
def on_bluetooth_amplitude_change(amplitude: float):
    """Callback when Bluetooth remote changes amplitude."""
    # Ignore amplitude changes when locked (e.g., during no-motion trials)
    if state.amplitude_locked:
        return
    # Clamp to [0.0, 1.0] - trajectory has motor limits baked in
    amplitude = max(0.0, min(1.0, amplitude))
    state.bluetooth_user_amplitude = amplitude
    # Update the playback controller if playing
    if state.controller is not None and state.controller.is_playing():
        state.controller.set_user_amplitude(amplitude)
    # Emit to web UI
    socketio.emit('user_amplitude_update', {'amplitude': amplitude})


def on_bluetooth_switch_press():
    """Callback when Bluetooth remote switch is pressed."""
    socketio.emit('bluetooth_switch', {})


def on_bluetooth_connection_change(connected: bool):
    """Callback when Bluetooth connection state changes."""
    socketio.emit('bluetooth_status', {
        'connected': connected,
        'status': state.bluetooth.get_status()
    })


def on_bluetooth_battery_update(voltage: float, is_low: bool):
    """Callback when battery voltage is updated."""
    socketio.emit('battery_update', {
        'voltage': voltage,
        'low_battery': is_low
    })


# Setup Bluetooth callbacks
state.bluetooth.set_amplitude_callback(on_bluetooth_amplitude_change)
state.bluetooth.set_switch_callback(on_bluetooth_switch_press)
state.bluetooth.set_connection_callback(on_bluetooth_connection_change)
state.bluetooth.set_battery_callback(on_bluetooth_battery_update)


# Routes

@app.route('/')
def index():
    """Render the main web interface."""
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    """Get current system status."""
    return jsonify({
        'success': True,
        'status': state.status,
        'connected': state.odrv0 is not None,
        'current_song_id': state.current_song_id,
        'latency_offset_ms': state.latency_offset_s * 1000,
        'feedforward_enabled': state.feedforward_enabled,
        'running': state.controller is not None and state.controller.is_playing(),
        'current_library': state.current_library
    })


@app.route('/api/library', methods=['GET', 'POST'])
def handle_library():
    """Get or set the current song library."""
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'current_library': state.current_library,
            'libraries': {
                'standard': {
                    'name': 'Standard',
                    'song_count': len(state.song_manager_standard.list_songs())
                },
                'legacy': {
                    'name': 'Legacy',
                    'song_count': len(state.song_manager_legacy.list_songs())
                }
            }
        })

    try:
        data = request.json or {}
        library = data.get('library', 'standard')

        if library not in ('standard', 'legacy'):
            return jsonify({'success': False, 'error': f'Invalid library: {library}'})

        # Don't allow switching while playing
        if state.controller is not None and state.controller.is_playing():
            return jsonify({'success': False, 'error': 'Cannot switch library while playing'})

        state.current_library = library
        state.current_song_id = None  # Clear selected song when switching

        socketio.emit('status', {
            'message': f'Switched to {library} library',
            'type': 'info'
        })

        return jsonify({
            'success': True,
            'current_library': state.current_library,
            'song_count': len(state.song_manager.list_songs())
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/songs')
def get_songs():
    """Get list of available songs."""
    try:
        songs = state.song_manager.list_songs()
        song_list = []
        for song in songs:
            song_list.append({
                'id': song.id,
                'name': song.name,
                'artist': song.artist,
                'bpm': song.bpm,
                'duration_s': song.duration_s,
                'duration_str': state.song_manager.format_duration(song.duration_s)
            })
        return jsonify({'success': True, 'songs': song_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/connect', methods=['POST'])
def connect():
    """Connect to ODrive."""
    if state.odrv0 is not None:
        return jsonify({'success': False, 'error': 'Already connected'})

    try:
        socketio.emit('status', {'message': 'Searching for ODrive...', 'type': 'info'})

        state.odrv0 = odrive.find_any(timeout=30)
        if state.odrv0 is None:
            raise Exception("ODrive not found")

        state.initial_position = state.odrv0.axis0.encoder.pos_estimate
        state.status = "connected"
        socketio.emit('status', {'message': 'ODrive connected', 'type': 'success'})

        return jsonify({'success': True})
    except Exception as e:
        socketio.emit('status', {'message': f'Error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/calibrate', methods=['POST'])
def calibrate():
    """Calibrate ODrive motor (configure, save, reboot, reconnect)."""
    if state.odrv0 is None:
        return jsonify({'success': False, 'error': 'Not connected'})

    try:
        socketio.emit('status', {'message': 'Configuring ODrive settings...', 'type': 'info'})

        # Verify we can communicate before configuring
        try:
            current_startup_motor = state.odrv0.axis0.config.startup_motor_calibration
            socketio.emit('status', {'message': f'Current startup_motor_calibration: {current_startup_motor}', 'type': 'info'})
        except Exception as e:
            socketio.emit('status', {'message': f'Warning reading config: {e}', 'type': 'warning'})

        # configure_odrive ends with reboot(), which will disconnect and raise an exception
        # This is expected behavior
        try:
            configure_odrive(state.odrv0)
        except Exception as e:
            # Expected: ODrive disconnects during reboot
            socketio.emit('status', {'message': f'Reboot triggered (expected disconnect)', 'type': 'info'})

        socketio.emit('status', {'message': 'ODrive rebooting...', 'type': 'info'})

        # ODrive is now rebooting, clear our reference
        state.odrv0 = None

        # Wait for ODrive to reboot and run startup calibration
        # Motor calibration (beep) takes ~3s, encoder offset takes ~5s
        socketio.emit('status', {'message': 'Waiting for startup calibration (motor beep + encoder)...', 'type': 'info'})
        time.sleep(12)  # Give time for full startup calibration sequence

        socketio.emit('status', {'message': 'Searching for ODrive...', 'type': 'info'})
        state.odrv0 = odrive.find_any(timeout=15)

        if state.odrv0 is None:
            socketio.emit('status', {'message': 'Failed to reconnect after reboot', 'type': 'error'})
            return jsonify({'success': False, 'error': 'Failed to reconnect after reboot'})

        # Wait for calibration to finish if still in progress
        wait_count = 0
        while state.odrv0.axis0.current_state != 1:  # 1 = IDLE
            if wait_count > 20:  # 10 second timeout
                break
            socketio.emit('status', {'message': f'Waiting for calibration to complete (state: {state.odrv0.axis0.current_state})...', 'type': 'info'})
            time.sleep(0.5)
            wait_count += 1

        # Check for errors
        axis_error = state.odrv0.axis0.error
        motor_error = state.odrv0.axis0.motor.error
        encoder_error = state.odrv0.axis0.encoder.error

        if axis_error != 0 or motor_error != 0 or encoder_error != 0:
            error_msg = f'Calibration errors - Axis: {hex(axis_error)}, Motor: {hex(motor_error)}, Encoder: {hex(encoder_error)}'
            socketio.emit('status', {'message': error_msg, 'type': 'error'})
            return jsonify({'success': False, 'error': error_msg})

        # Update initial position after reconnect
        state.initial_position = state.odrv0.axis0.encoder.pos_estimate

        socketio.emit('status', {'message': 'Calibration complete - motor ready for arming', 'type': 'success'})
        socketio.emit('status', {'message': 'Click "Arm Motor" to enable closed-loop control', 'type': 'info'})
        return jsonify({'success': True})

    except Exception as e:
        state.odrv0 = None
        socketio.emit('status', {'message': f'Calibration error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/clear_errors', methods=['POST'])
def clear_errors():
    """Clear ODrive errors."""
    if state.odrv0 is None:
        return jsonify({'success': False, 'error': 'Not connected'})

    try:
        socketio.emit('status', {'message': 'Clearing errors...', 'type': 'info'})
        state.odrv0.clear_errors()

        # Give a moment for errors to clear
        import time
        time.sleep(0.1)

        # Check if errors were successfully cleared
        axis_error = state.odrv0.axis0.error
        motor_error = state.odrv0.axis0.motor.error
        encoder_error = state.odrv0.axis0.encoder.error

        if axis_error == 0 and motor_error == 0 and encoder_error == 0:
            socketio.emit('status', {'message': 'Errors cleared successfully', 'type': 'success'})
            return jsonify({'success': True})
        else:
            error_msg = f'Errors remain - Axis: {hex(axis_error)}, Motor: {hex(motor_error)}, Encoder: {hex(encoder_error)}'
            socketio.emit('status', {'message': error_msg, 'type': 'warning'})
            return jsonify({'success': True, 'warning': error_msg})

    except Exception as e:
        socketio.emit('status', {'message': f'Clear errors failed: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/arm', methods=['POST'])
def arm_motor():
    """Arm the motor (enter closed-loop control)."""
    if state.odrv0 is None:
        return jsonify({'success': False, 'error': 'Not connected'})

    try:
        # Check current state before arming
        current_state = state.odrv0.axis0.current_state
        socketio.emit('status', {'message': f'Current state: {current_state} (1=IDLE, 8=CLOSED_LOOP)', 'type': 'info'})

        # Check for errors before arming
        if state.odrv0.axis0.error != 0:
            error_msg = f'Cannot arm - axis error: {hex(state.odrv0.axis0.error)}'
            socketio.emit('status', {'message': error_msg, 'type': 'error'})
            return jsonify({'success': False, 'error': error_msg})

        socketio.emit('status', {'message': 'Arming motor...', 'type': 'info'})
        arm(state.odrv0)

        # Wait a moment and verify state changed
        time.sleep(0.5)
        new_state = state.odrv0.axis0.current_state

        if new_state == 8:  # CLOSED_LOOP_CONTROL
            state.status = "armed"
            socketio.emit('status', {'message': 'Motor armed successfully (state: CLOSED_LOOP)', 'type': 'success'})
            return jsonify({'success': True})
        else:
            # Check for errors
            axis_error = state.odrv0.axis0.error
            motor_error = state.odrv0.axis0.motor.error
            error_msg = f'Arm failed - state: {new_state}, axis_error: {hex(axis_error)}, motor_error: {hex(motor_error)}'
            socketio.emit('status', {'message': error_msg, 'type': 'error'})
            return jsonify({'success': False, 'error': error_msg})

    except Exception as e:
        socketio.emit('status', {'message': f'Arm error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/play', methods=['POST'])
def play():
    """Start playback of a song."""
    if state.controller is not None and state.controller.is_playing():
        return jsonify({'success': False, 'error': 'Already playing'})

    try:
        data = request.json or {}
        song_id = data.get('song_id')
        tempo_mode = data.get('tempo_mode', 'fixed')  # 'fixed' or 'dynamic'
        pattern_type = data.get('pattern_type', 'complex')  # 'simple' or 'complex'

        if not song_id:
            return jsonify({'success': False, 'error': 'No song specified'})

        # Get song info
        song = state.song_manager.get_song_by_id(song_id)
        if song is None:
            return jsonify({'success': False, 'error': f'Song not found: {song_id}'})

        state.current_song_id = song_id

        # Build trajectory filename based on pattern_type and tempo_mode
        # Pattern types: 'complex' -> trajectory.npy, 'simple' -> trajectory_simple.npy
        # Tempo modes: 'fixed' -> no suffix, 'dynamic' -> _dynamic suffix
        if pattern_type == 'simple':
            if tempo_mode == 'dynamic':
                trajectory_filename = 'trajectory_simple_dynamic.npy'
            else:
                trajectory_filename = 'trajectory_simple.npy'
        else:  # complex (default)
            if tempo_mode == 'dynamic':
                trajectory_filename = 'trajectory_dynamic.npy'
            else:
                trajectory_filename = 'trajectory.npy'

        # Construct full path
        base_path = os.path.dirname(song.trajectory_path)
        trajectory_path = os.path.join(base_path, trajectory_filename)

        # Check if requested trajectory exists, fall back to default if not
        if not os.path.exists(trajectory_path):
            trajectory_path = song.trajectory_path
            socketio.emit('status', {
                'message': f'Loading: {song.metadata.name} ({trajectory_filename} not found, using default)',
                'type': 'warning'
            })
        else:
            pattern_label = 'simple' if pattern_type == 'simple' else 'complex'
            tempo_label = 'dynamic' if tempo_mode == 'dynamic' else 'fixed'
            socketio.emit('status', {
                'message': f'Loading: {song.metadata.name} ({pattern_label}, {tempo_label} tempo)',
                'type': 'info'
            })

        # Get initial position
        state.initial_position = state.odrv0.axis0.encoder.pos_estimate

        # Create playback controller
        state.controller = create_playback_controller(
            audio_path=song.audio_path,
            trajectory_path=trajectory_path,
            odrv0=state.odrv0,
            initial_offset=state.initial_position,
            latency_offset_s=state.latency_offset_s,
            feedforward_enabled=state.feedforward_enabled
        )

        # Set up status callback with data recording
        # Track last sample count update to throttle UI updates
        last_sample_update = [0]  # Use list to allow modification in closure

        def on_status(status_data):
            socketio.emit('playback_status', status_data)
            # Record data sample if recording
            if state.data_recorder.is_recording():
                user_amp = state.bluetooth_user_amplitude
                # target_position is the position after user amplitude is applied
                # We need original position (before amplitude) and final position (after)
                original_pos = status_data.get('target_position', 0) / user_amp if user_amp != 0 else 0
                final_pos = status_data.get('target_position', 0)
                actual_pos = status_data.get('actual_position', final_pos)
                state.data_recorder.record_sample(user_amp, original_pos, final_pos, actual_pos)
                # Throttle UI updates to ~2Hz (every 30 samples at 60Hz control rate)
                sample_count = state.data_recorder.get_sample_count()
                if sample_count - last_sample_update[0] >= 30:
                    last_sample_update[0] = sample_count
                    socketio.emit('recording_update', {'sample_count': sample_count})

        def on_finished():
            # Stop data recording
            if state.data_recorder.is_recording():
                state.data_recorder.stop_recording()
                socketio.emit('status', {
                    'message': f'Recording stopped: {state.data_recorder.get_sample_count()} samples',
                    'type': 'info'
                })
            state.status = "stopped"
            state.current_song_id = None
            socketio.emit('status', {'message': 'Playback finished', 'type': 'info'})
            socketio.emit('playback_finished', {})

        state.controller.set_on_status_update(on_status)
        state.controller.set_on_finished(on_finished)

        # Set initial amplitude: use saved default from metadata if available
        initial_amplitude = state.bluetooth_user_amplitude
        if not state.bluetooth.is_connected():
            # Load saved amplitude from song metadata
            if os.path.exists(song.metadata_path):
                try:
                    with open(song.metadata_path, 'r') as f:
                        metadata = json.load(f)
                        saved_amp = metadata.get('default_amplitude')
                        if saved_amp is not None:
                            initial_amplitude = float(saved_amp)
                except:
                    pass
        state.controller.set_user_amplitude(initial_amplitude)
        state.bluetooth_user_amplitude = initial_amplitude

        # Start data recording with BPM and initial motor position
        state.data_recorder.start_recording(
            bpm=song.metadata.bpm,
            initial_motor_offset=state.initial_position
        )

        # Start playback
        state.controller.start()
        state.status = "playing"

        socketio.emit('status', {
            'message': f'Playing: {song.metadata.name}',
            'type': 'success'
        })

        return jsonify({'success': True, 'user_amplitude': initial_amplitude})

    except Exception as e:
        socketio.emit('status', {'message': f'Error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/pause', methods=['POST'])
def pause():
    """Pause/resume playback."""
    if state.controller is None:
        return jsonify({'success': False, 'error': 'Not playing'})

    try:
        if state.controller.is_paused:
            state.controller.resume()
            state.status = "playing"
            socketio.emit('status', {'message': 'Resumed', 'type': 'info'})
        else:
            state.controller.pause()
            state.status = "paused"
            socketio.emit('status', {'message': 'Paused', 'type': 'info'})

        return jsonify({'success': True, 'paused': state.controller.is_paused})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


def _save_study_data_background(trial, data_recorder, user_study):
    """Save study data in background thread to avoid blocking the response."""
    try:
        # Create output directory with subfolder for this study
        base_dir = Path(__file__).parent.parent / 'user_study_data'
        folder_name = user_study.get_folder_name()
        if folder_name:
            output_dir = base_dir / folder_name
        else:
            output_dir = base_dir / 'unnamed_study'
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filenames
        base_name = user_study.get_trial_filename(trial, '')
        csv_file = output_dir / f"{base_name}data.csv"
        plot_sep_file = output_dir / f"{base_name}plot_separate.png"
        plot_comb_file = output_dir / f"{base_name}plot_combined.png"

        # Generate synchronization filenames: songName_patternType_synchronization
        song_name = trial.song_config.song_name.replace(' ', '_').replace('/', '_')
        pattern_type = trial.pattern.value  # 'simple', 'complex', or 'none'
        sync_plot_file = output_dir / f"{song_name}_{pattern_type}_synchronization.png"
        sync_csv_file = output_dir / f"{song_name}_{pattern_type}_synchronization.csv"

        # Save data and plots
        data_recorder.export_data(str(csv_file))
        data_recorder.plot_data(str(plot_sep_file))
        data_recorder.plot_combined(str(plot_comb_file))

        # Save synchronization plot and data
        data_recorder.plot_synchronization(
            save_filename=str(sync_plot_file),
            song_name=trial.song_config.song_name,
            pattern_type=pattern_type
        )
        data_recorder.export_sync_data(
            filename=str(sync_csv_file),
            song_name=trial.song_config.song_name,
            pattern_type=pattern_type
        )

        socketio.emit('status', {
            'message': f'Data saved: {base_name} + sync plots',
            'type': 'success'
        })
    except Exception as e:
        socketio.emit('status', {
            'message': f'Error saving data: {str(e)}',
            'type': 'error'
        })


def _save_study_trial_list(user_study):
    """Save the trial list to a text file in the study output folder."""
    try:
        summary = user_study.get_completed_trials_summary()
        if not summary:
            return

        # Get output directory
        base_dir = Path(__file__).parent.parent / 'user_study_data'
        folder_name = user_study.get_folder_name()
        if folder_name:
            output_dir = base_dir / folder_name
        else:
            output_dir = base_dir / 'unnamed_study'
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write trial list to file
        filepath = output_dir / 'trial_list.txt'
        with open(filepath, 'w') as f:
            f.write(f"User Study Trial List\n")
            f.write(f"{'=' * 50}\n\n")
            f.write(f"Total trials: {len(summary)}\n\n")
            f.write(f"{'#':<4} {'Song':<30} {'Pattern':<10} {'Library':<10} {'Tempo':<10}\n")
            f.write(f"{'-' * 70}\n")

            for trial in summary:
                f.write(f"{trial['trial_number']:<4} "
                       f"{trial['song_name']:<30} "
                       f"{trial['pattern']:<10} "
                       f"{trial['library']:<10} "
                       f"{trial['tempo_mode']:<10}\n")

        print(f"[UserStudy] Trial list saved to {filepath}")
    except Exception as e:
        print(f"[UserStudy] Error saving trial list: {e}")


@app.route('/api/stop', methods=['POST'])
def stop():
    """Stop playback."""
    if state.controller is None:
        return jsonify({'success': False, 'error': 'Not playing'})

    try:
        state.controller.stop()
        state.controller = None
        state.status = "stopped"
        state.current_song_id = None

        # Stop data recording and save if in user study
        if state.data_recorder.is_recording():
            state.data_recorder.stop_recording()

            # Save data if in active user study with recording enabled
            if state.user_study.is_active() and state.user_study.should_record_data():
                trial = state.user_study.get_current_trial()
                if trial:
                    # Run data saving in background thread to avoid blocking
                    save_thread = threading.Thread(
                        target=_save_study_data_background,
                        args=(trial, state.data_recorder, state.user_study),
                        daemon=True
                    )
                    save_thread.start()
                    socketio.emit('status', {'message': 'Saving data...', 'type': 'info'})
            else:
                socketio.emit('status', {
                    'message': f'Recording stopped: {state.data_recorder.get_sample_count()} samples',
                    'type': 'info'
                })

        socketio.emit('status', {'message': 'Stopped', 'type': 'info'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/amplitude', methods=['POST'])
def set_amplitude():
    """Set user amplitude multiplier."""
    if state.controller is None:
        return jsonify({'success': False, 'error': 'Not playing'})

    try:
        data = request.json or {}
        amplitude = float(data.get('amplitude', 1.0))
        # Clamp to [0.0, 1.0] - trajectory has motor limits baked in
        amplitude = max(0.0, min(1.0, amplitude))
        state.controller.set_user_amplitude(amplitude)
        return jsonify({'success': True, 'amplitude': amplitude})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/latency', methods=['GET', 'POST'])
def handle_latency():
    """Get or set latency offset."""
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'latency_offset_ms': state.latency_offset_s * 1000
        })

    try:
        data = request.json or {}
        latency_ms = float(data.get('latency_ms', state.latency_offset_s * 1000))
        state.latency_offset_s = latency_ms / 1000.0

        if state.controller is not None:
            state.controller.set_latency_offset(state.latency_offset_s)

        return jsonify({'success': True, 'latency_offset_ms': latency_ms})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/feedforward', methods=['GET', 'POST'])
def handle_feedforward():
    """Get or set velocity feedforward setting."""
    if request.method == 'GET':
        # Check if current song has feedforward available
        feedforward_available = False
        if state.current_song_id:
            song = state.song_manager.get_song_by_id(state.current_song_id)
            if song:
                try:
                    traj_player = TrajectoryPlayer(song.trajectory_path)
                    feedforward_available = traj_player.has_velocity_feedforward()
                except:
                    pass

        return jsonify({
            'success': True,
            'feedforward_enabled': state.feedforward_enabled,
            'feedforward_available': feedforward_available
        })

    try:
        data = request.json or {}
        state.feedforward_enabled = bool(data.get('enabled', True))

        socketio.emit('status', {
            'message': f'Velocity feedforward {"enabled" if state.feedforward_enabled else "disabled"}',
            'type': 'info'
        })

        return jsonify({
            'success': True,
            'feedforward_enabled': state.feedforward_enabled
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/song/<song_id>/feedforward')
def get_song_feedforward(song_id):
    """Check if a specific song has velocity feedforward available."""
    try:
        song = state.song_manager.get_song_by_id(song_id)
        if song is None:
            return jsonify({'success': False, 'error': 'Song not found'})

        traj_player = TrajectoryPlayer(song.trajectory_path)
        has_feedforward = traj_player.has_velocity_feedforward()

        return jsonify({
            'success': True,
            'song_id': song_id,
            'feedforward_available': has_feedforward
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/song/<song_id>/tempo_info')
def get_song_tempo_info(song_id):
    """Get tempo information for a specific song including dynamic tempo availability."""
    try:
        song = state.song_manager.get_song_by_id(song_id)
        if song is None:
            return jsonify({'success': False, 'error': 'Song not found'})

        # Check if dynamic tempo trajectory exists
        dynamic_path = song.trajectory_path.replace('trajectory.npy', 'trajectory_dynamic.npy')
        has_dynamic_tempo = os.path.exists(dynamic_path)

        # Read metadata.json for tempo variance info
        tempo_variance = 0.0
        local_tempo_min = song.metadata.bpm
        local_tempo_max = song.metadata.bpm
        local_tempo_avg = song.metadata.bpm

        if os.path.exists(song.metadata_path):
            try:
                with open(song.metadata_path, 'r') as f:
                    metadata = json.load(f)
                    features = metadata.get('features', {})
                    tempo_variance = features.get('tempo_variance', 0.0)
                    local_tempo_min = features.get('local_tempo_min', song.metadata.bpm)
                    local_tempo_max = features.get('local_tempo_max', song.metadata.bpm)
                    local_tempo_avg = features.get('local_tempo_avg', song.metadata.bpm)
                    # Check for has_dynamic_tempo flag in metadata
                    if not has_dynamic_tempo:
                        has_dynamic_tempo = metadata.get('trajectory', {}).get('has_dynamic_tempo', False)
            except:
                pass

        return jsonify({
            'success': True,
            'song_id': song_id,
            'has_dynamic_tempo': has_dynamic_tempo,
            'tempo_variance': tempo_variance,
            'local_tempo_min': local_tempo_min,
            'local_tempo_max': local_tempo_max,
            'local_tempo_avg': local_tempo_avg,
            'global_bpm': song.metadata.bpm
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/song/<song_id>/latency', methods=['GET', 'POST'])
def handle_song_latency(song_id):
    """Get or set song-specific latency compensation.

    Supports pattern-specific latency via 'pattern' query param or JSON field.
    Pattern can be 'simple', 'complex', or 'none'.
    If no pattern is specified, uses 'complex' as default.
    """
    song = state.song_manager.get_song_by_id(song_id)
    if song is None:
        return jsonify({'success': False, 'error': 'Song not found'})

    # Get pattern type from query param (GET) or JSON body (POST)
    if request.method == 'GET':
        pattern = request.args.get('pattern', 'complex')
    else:
        data = request.json or {}
        pattern = data.get('pattern', 'complex')

    # Normalize pattern to valid values
    if pattern not in ('simple', 'complex', 'none'):
        pattern = 'complex'

    if request.method == 'GET':
        # Read latency from song's metadata.json
        custom_latency_ms = None
        pattern_latencies = {}
        if os.path.exists(song.metadata_path):
            try:
                with open(song.metadata_path, 'r') as f:
                    metadata = json.load(f)
                    # Check for pattern-specific latency first
                    pattern_latencies = metadata.get('pattern_latencies', {})
                    if pattern in pattern_latencies:
                        custom_latency_ms = pattern_latencies[pattern]
                    else:
                        # Fall back to legacy custom_latency_ms for backwards compatibility
                        custom_latency_ms = metadata.get('custom_latency_ms')
            except:
                pass

        return jsonify({
            'success': True,
            'song_id': song_id,
            'pattern': pattern,
            'custom_latency_ms': custom_latency_ms,
            'has_custom_latency': custom_latency_ms is not None,
            'pattern_latencies': pattern_latencies
        })

    # POST - save latency to song metadata
    try:
        data = request.json or {}
        latency_ms = float(data.get('latency_ms', state.latency_offset_s * 1000))

        # Read existing metadata
        metadata = {}
        if os.path.exists(song.metadata_path):
            with open(song.metadata_path, 'r') as f:
                metadata = json.load(f)

        # Initialize pattern_latencies dict if not exists
        if 'pattern_latencies' not in metadata:
            metadata['pattern_latencies'] = {}

        # Save latency for specific pattern
        metadata['pattern_latencies'][pattern] = latency_ms

        # Also update legacy field for backwards compatibility
        metadata['custom_latency_ms'] = latency_ms

        # Save back
        with open(song.metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        pattern_name = pattern.upper() if pattern != 'none' else 'NO MOTION'
        socketio.emit('status', {
            'message': f'Saved latency {latency_ms:.0f}ms for {song.metadata.name} ({pattern_name})',
            'type': 'success'
        })

        return jsonify({
            'success': True,
            'song_id': song_id,
            'pattern': pattern,
            'custom_latency_ms': latency_ms
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/song/<song_id>/amplitude', methods=['GET', 'POST'])
def handle_song_amplitude(song_id):
    """Get or set song-specific default amplitude.

    Stores a default starting amplitude for each song in metadata.json.
    """
    song = state.song_manager.get_song_by_id(song_id)
    if song is None:
        return jsonify({'success': False, 'error': 'Song not found'})

    if request.method == 'GET':
        # Read amplitude from song's metadata.json
        default_amplitude = None
        if os.path.exists(song.metadata_path):
            try:
                with open(song.metadata_path, 'r') as f:
                    metadata = json.load(f)
                    default_amplitude = metadata.get('default_amplitude')
            except:
                pass

        return jsonify({
            'success': True,
            'song_id': song_id,
            'default_amplitude': default_amplitude,
            'has_default_amplitude': default_amplitude is not None
        })

    # POST - save amplitude to song metadata
    try:
        data = request.json or {}
        amplitude = float(data.get('amplitude', state.bluetooth_user_amplitude))

        # Read existing metadata
        metadata = {}
        if os.path.exists(song.metadata_path):
            with open(song.metadata_path, 'r') as f:
                metadata = json.load(f)

        # Save default amplitude
        metadata['default_amplitude'] = amplitude

        # Save back
        with open(song.metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        socketio.emit('status', {
            'message': f'Saved amplitude {amplitude:.2f}x for {song.metadata.name}',
            'type': 'success'
        })

        return jsonify({
            'success': True,
            'song_id': song_id,
            'default_amplitude': amplitude
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/connect', methods=['POST'])
def bluetooth_connect():
    """Connect to Bluetooth remote control."""
    try:
        if state.bluetooth.is_connected():
            return jsonify({'success': False, 'error': 'Already connected'})

        socketio.emit('status', {'message': 'Scanning for Bluetooth remote...', 'type': 'info'})

        # Start connection in background (non-blocking)
        def connect_thread():
            connected = state.bluetooth.connect(auto_reconnect=True)
            if connected:
                socketio.emit('status', {'message': 'Bluetooth remote connected', 'type': 'success'})
            else:
                socketio.emit('status', {'message': 'Bluetooth remote not found', 'type': 'warning'})

        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()

        return jsonify({'success': True, 'message': 'Connecting...'})
    except Exception as e:
        socketio.emit('status', {'message': f'Bluetooth error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/disconnect', methods=['POST'])
def bluetooth_disconnect():
    """Disconnect from Bluetooth remote control."""
    try:
        state.bluetooth.disconnect()
        socketio.emit('status', {'message': 'Bluetooth remote disconnected', 'type': 'info'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/reset_baseline', methods=['POST'])
def bluetooth_reset_baseline():
    """Reset the encoder baseline (sets amplitude to 0.3)."""
    try:
        if not state.bluetooth.is_connected():
            return jsonify({'success': False, 'error': 'Not connected'})

        state.bluetooth.reset_baseline()
        socketio.emit('status', {'message': 'Encoder baseline reset', 'type': 'info'})
        return jsonify({'success': True, 'amplitude': state.bluetooth.get_user_amplitude()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/toggle_direction', methods=['POST'])
def bluetooth_toggle_direction():
    """Toggle encoder direction (clockwise/counter-clockwise)."""
    try:
        state.bluetooth.toggle_direction()
        direction = "reversed" if state.bluetooth.encoder_direction_reversed else "normal"
        socketio.emit('status', {'message': f'Encoder direction: {direction}', 'type': 'info'})
        return jsonify({
            'success': True,
            'direction_reversed': state.bluetooth.encoder_direction_reversed
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/status')
def bluetooth_status():
    """Get Bluetooth remote control status."""
    return jsonify({
        'success': True,
        'status': state.bluetooth.get_status()
    })


@app.route('/api/data/status')
def data_status():
    """Get data recording status."""
    return jsonify({
        'success': True,
        'recording': state.data_recorder.is_recording(),
        'sample_count': state.data_recorder.get_sample_count()
    })


@app.route('/api/data/plot', methods=['POST'])
def data_plot():
    """Generate and save a plot of recorded data."""
    try:
        data = request.json or {}
        plot_type = data.get('type', 'separate')  # 'separate' or 'combined'

        if state.data_recorder.get_sample_count() == 0:
            return jsonify({'success': False, 'error': 'No data recorded'})

        # Generate filename with timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"recording_{timestamp}_{plot_type}.png"
        filepath = str(CONFIG_DIR / filename)

        if plot_type == 'combined':
            state.data_recorder.plot_combined(save_filename=filepath)
        else:
            state.data_recorder.plot_data(save_filename=filepath)

        socketio.emit('status', {'message': f'Plot saved: {filename}', 'type': 'success'})
        return jsonify({'success': True, 'filename': filename, 'filepath': filepath})
    except Exception as e:
        socketio.emit('status', {'message': f'Plot error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/data/export', methods=['POST'])
def data_export():
    """Export recorded data to CSV file."""
    try:
        if state.data_recorder.get_sample_count() == 0:
            return jsonify({'success': False, 'error': 'No data recorded'})

        # Generate filename with timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"recording_{timestamp}.csv"
        filepath = str(CONFIG_DIR / filename)

        state.data_recorder.export_data(filepath)

        socketio.emit('status', {'message': f'Data exported: {filename}', 'type': 'success'})
        return jsonify({'success': True, 'filename': filename, 'filepath': filepath})
    except Exception as e:
        socketio.emit('status', {'message': f'Export error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/data/statistics')
def data_statistics():
    """Get statistics from recorded data."""
    try:
        stats = state.data_recorder.get_statistics()
        return jsonify({'success': True, 'statistics': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/data/sync_plot', methods=['POST'])
def data_sync_plot():
    """Generate and save a synchronization plot of recorded data."""
    try:
        data = request.json or {}
        song_name = data.get('song_name', '')
        pattern_type = data.get('pattern_type', '')

        if state.data_recorder.get_sample_count() == 0:
            return jsonify({'success': False, 'error': 'No data recorded'})

        # Generate filename
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

        # Use song_name and pattern_type if provided, otherwise timestamp
        if song_name and pattern_type:
            safe_name = song_name.replace(' ', '_').replace('/', '_')
            filename = f"{safe_name}_{pattern_type}_synchronization.png"
            csv_filename = f"{safe_name}_{pattern_type}_synchronization.csv"
        else:
            filename = f"sync_{timestamp}.png"
            csv_filename = f"sync_{timestamp}.csv"

        filepath = str(CONFIG_DIR / filename)
        csv_filepath = str(CONFIG_DIR / csv_filename)

        # Generate plot and CSV in current thread (fast enough for single request)
        state.data_recorder.plot_synchronization(
            save_filename=filepath,
            song_name=song_name,
            pattern_type=pattern_type
        )
        state.data_recorder.export_sync_data(
            filename=csv_filepath,
            song_name=song_name,
            pattern_type=pattern_type
        )

        socketio.emit('status', {
            'message': f'Sync plot saved: {filename}',
            'type': 'success'
        })

        return jsonify({
            'success': True,
            'plot_filename': filename,
            'plot_filepath': filepath,
            'csv_filename': csv_filename,
            'csv_filepath': csv_filepath
        })
    except Exception as e:
        socketio.emit('status', {'message': f'Sync plot error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


# User Study API Endpoints

@app.route('/api/user_study/songs')
def user_study_songs():
    """Get list of all songs from both libraries for user study configuration."""
    try:
        songs = []
        # Standard library songs
        for song in state.song_manager_standard.list_songs():
            songs.append({
                'id': song.id,
                'name': song.name,
                'artist': song.artist,
                'bpm': song.bpm,
                'duration_s': song.duration_s,
                'duration_str': state.song_manager_standard.format_duration(song.duration_s),
                'library': 'standard'
            })
        # Legacy library songs
        for song in state.song_manager_legacy.list_songs():
            songs.append({
                'id': song.id,
                'name': song.name,
                'artist': song.artist,
                'bpm': song.bpm,
                'duration_s': song.duration_s,
                'duration_str': state.song_manager_legacy.format_duration(song.duration_s),
                'library': 'legacy'
            })
        return jsonify({'success': True, 'songs': songs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/user_study/setup', methods=['POST'])
def user_study_setup():
    """Set up a new user study with 3 songs and their configurations."""
    if state.controller is not None and state.controller.is_playing():
        return jsonify({'success': False, 'error': 'Cannot start study while playing'})

    try:
        data = request.json or {}
        songs_data = data.get('songs', [])
        record_data = data.get('record_data', True)
        folder_name = data.get('folder_name', '')

        if len(songs_data) != 3:
            return jsonify({'success': False, 'error': 'Exactly 3 songs required'})

        song_configs = []
        for song_data in songs_data:
            song_id = song_data.get('song_id')
            library = song_data.get('library', 'standard')
            tempo_mode = song_data.get('tempo_mode', 'fixed')

            # Get song manager for this library
            manager = state.song_manager_standard if library == 'standard' else state.song_manager_legacy
            song = manager.get_song_by_id(song_id)

            if song is None:
                return jsonify({'success': False, 'error': f'Song not found: {song_id}'})

            song_configs.append(SongConfig(
                song_id=song_id,
                song_name=song.metadata.name,
                library=library,
                tempo_mode=tempo_mode
            ))

        state.user_study.setup_study(song_configs, record_data=record_data, folder_name=folder_name)
        progress = state.user_study.get_study_progress()

        record_msg = f" (recording to {folder_name})" if record_data else ""
        socketio.emit('status', {'message': f'User study started{record_msg}', 'type': 'success'})
        socketio.emit('user_study_update', progress)

        return jsonify({'success': True, 'progress': progress})
    except Exception as e:
        socketio.emit('status', {'message': f'Study setup error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/user_study/status')
def user_study_status():
    """Get current user study status and progress."""
    try:
        progress = state.user_study.get_study_progress()
        return jsonify({'success': True, 'progress': progress})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/user_study/play', methods=['POST'])
def user_study_play():
    """Play the current trial in the user study."""
    if not state.user_study.is_active():
        return jsonify({'success': False, 'error': 'No active user study'})

    if state.controller is not None and state.controller.is_playing():
        return jsonify({'success': False, 'error': 'Already playing'})

    try:
        trial = state.user_study.get_current_trial()
        if trial is None:
            return jsonify({'success': False, 'error': 'Study complete - no more trials'})

        song_config = trial.song_config

        # Get song manager for this library
        manager = state.song_manager_standard if song_config.library == 'standard' else state.song_manager_legacy
        song = manager.get_song_by_id(song_config.song_id)

        if song is None:
            return jsonify({'success': False, 'error': f'Song not found: {song_config.song_id}'})

        # Get trajectory filename based on pattern and tempo mode
        trajectory_filename = state.user_study.get_trajectory_filename(trial)
        song_dir = Path(song.trajectory_path).parent
        trajectory_path = str(song_dir / trajectory_filename)

        # Check if trajectory exists
        if not os.path.exists(trajectory_path):
            # Fall back to default trajectory
            socketio.emit('status', {
                'message': f'Trajectory {trajectory_filename} not found, using default',
                'type': 'warning'
            })
            trajectory_path = song.trajectory_path

        # Get user amplitude for this pattern
        user_amplitude = state.user_study.get_user_amplitude(trial.pattern)

        # For motion patterns, override with saved amplitude from metadata if available
        if user_amplitude != 0 and os.path.exists(song.metadata_path):
            try:
                with open(song.metadata_path, 'r') as f:
                    metadata = json.load(f)
                    saved_amp = metadata.get('default_amplitude')
                    if saved_amp is not None:
                        user_amplitude = float(saved_amp)
            except:
                pass

        # Lock amplitude if this is a no-motion trial (amplitude = 0)
        state.amplitude_locked = (user_amplitude == 0)

        # Get initial position
        state.initial_position = state.odrv0.axis0.encoder.pos_estimate

        # Create playback controller
        state.controller = create_playback_controller(
            audio_path=song.audio_path,
            trajectory_path=trajectory_path,
            odrv0=state.odrv0,
            initial_offset=state.initial_position,
            latency_offset_s=state.latency_offset_s,
            feedforward_enabled=state.feedforward_enabled
        )

        # Set up status callback
        last_sample_update = [0]

        def on_status(status_data):
            socketio.emit('playback_status', status_data)
            if state.data_recorder.is_recording():
                user_amp = state.bluetooth_user_amplitude
                original_pos = status_data.get('target_position', 0) / user_amp if user_amp != 0 else 0
                final_pos = status_data.get('target_position', 0)
                actual_pos = status_data.get('actual_position', final_pos)
                state.data_recorder.record_sample(user_amp, original_pos, final_pos, actual_pos)
                sample_count = state.data_recorder.get_sample_count()
                if sample_count - last_sample_update[0] >= 30:
                    last_sample_update[0] = sample_count
                    socketio.emit('recording_update', {'sample_count': sample_count})

        def on_finished():
            if state.data_recorder.is_recording():
                state.data_recorder.stop_recording()

                # Auto-save data if recording is enabled for this study
                if state.user_study.should_record_data():
                    # Run data saving in background thread to avoid blocking
                    save_thread = threading.Thread(
                        target=_save_study_data_background,
                        args=(trial, state.data_recorder, state.user_study),
                        daemon=True
                    )
                    save_thread.start()
                    socketio.emit('status', {'message': 'Saving data...', 'type': 'info'})

            state.status = "stopped"
            state.current_song_id = None
            state.amplitude_locked = False  # Unlock amplitude control

            # Emit trial completion and study progress
            progress = state.user_study.get_study_progress()
            socketio.emit('user_study_trial_complete', {
                'trial': {
                    'song_name': trial.song_config.song_name,
                    'pattern': trial.pattern.value,
                    'trial_number': trial.trial_number
                },
                'progress': progress
            })
            socketio.emit('playback_finished', {})

        state.controller.set_on_status_update(on_status)
        state.controller.set_on_finished(on_finished)

        # Set user amplitude (0 for no motion pattern)
        state.controller.set_user_amplitude(user_amplitude)
        state.bluetooth_user_amplitude = user_amplitude

        # Start data recording if enabled for this study
        if state.user_study.should_record_data():
            state.data_recorder.start_recording(
                bpm=song.metadata.bpm,
                initial_motor_offset=state.initial_position
            )

        # Start playback
        state.controller.start()
        state.status = "playing"
        state.current_song_id = song_config.song_id

        pattern_desc = trial.pattern.value.upper()
        socketio.emit('status', {
            'message': f'Trial {trial.trial_number}/9: {song_config.song_name} - {pattern_desc}',
            'type': 'success'
        })

        return jsonify({
            'success': True,
            'trial': {
                'song_name': song_config.song_name,
                'pattern': trial.pattern.value,
                'trial_number': trial.trial_number,
                'user_amplitude': user_amplitude
            }
        })

    except Exception as e:
        socketio.emit('status', {'message': f'Error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/user_study/complete_trial', methods=['POST'])
def user_study_complete_trial():
    """Mark the current trial as complete and get the next one."""
    if not state.user_study.is_active():
        return jsonify({'success': False, 'error': 'No active user study'})

    try:
        next_trial = state.user_study.complete_current_trial()
        progress = state.user_study.get_study_progress()

        if next_trial is None:
            # Save trial list to file
            _save_study_trial_list(state.user_study)
            socketio.emit('status', {'message': 'User study complete!', 'type': 'success'})
            socketio.emit('user_study_complete', {
                'completed_trials': state.user_study.get_completed_trials_summary()
            })
        else:
            socketio.emit('user_study_update', progress)

        return jsonify({
            'success': True,
            'progress': progress,
            'study_complete': next_trial is None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/user_study/cancel', methods=['POST'])
def user_study_cancel():
    """Cancel the current user study."""
    try:
        state.user_study.cancel_study()
        socketio.emit('status', {'message': 'User study cancelled', 'type': 'info'})
        socketio.emit('user_study_update', state.user_study.get_study_progress())
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/user_study/summary')
def user_study_summary():
    """Get summary of completed trials in the user study."""
    try:
        summary = state.user_study.get_completed_trials_summary()
        return jsonify({'success': True, 'summary': summary})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    """Disconnect from ODrive."""
    if state.controller is not None:
        state.controller.stop()
        state.controller = None

    try:
        if state.odrv0 is not None:
            state.odrv0.axis0.requested_state = AXIS_STATE_IDLE

        state.odrv0 = None
        state.status = "idle"
        socketio.emit('status', {'message': 'Disconnected', 'type': 'info'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/exit', methods=['POST'])
def exit_app():
    """Gracefully shut down the application."""
    import os
    import signal

    socketio.emit('status', {'message': 'Shutting down...', 'type': 'info'})

    # Stop playback if running
    if state.controller is not None:
        try:
            state.controller.stop()
            state.controller = None
        except Exception as e:
            print(f"Error stopping controller: {e}")

    # Disconnect ODrive
    if state.odrv0 is not None:
        try:
            state.odrv0.axis0.requested_state = AXIS_STATE_IDLE
            state.odrv0 = None
        except Exception as e:
            print(f"Error disconnecting ODrive: {e}")

    state.status = "idle"

    # Schedule server shutdown after response is sent
    def shutdown():
        time.sleep(0.5)  # Give time for response to be sent
        os.kill(os.getpid(), signal.SIGTERM)

    shutdown_thread = threading.Thread(target=shutdown)
    shutdown_thread.daemon = True
    shutdown_thread.start()

    return jsonify({'success': True, 'message': 'Server shutting down'})


def main():
    """Run the web server."""
    print("\n" + "="*60)
    print("Music-Motor Sync Controller - Web Interface")
    print("="*60)
    print(f"\nSong Libraries:")
    print(f"  Standard: {SONGS_DIR} ({len(state.song_manager_standard.list_songs())} songs)")
    print(f"  Legacy:   {SONGS_LEGACY_DIR} ({len(state.song_manager_legacy.list_songs())} songs)")
    print(f"\nLatency offset: {state.latency_offset_s*1000:.1f}ms")
    print("\nOpen your browser and navigate to:")
    print("  http://localhost:5000")
    print("\nPress Ctrl+C to exit")
    print("="*60 + "\n")

    socketio.run(app, host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    main()
