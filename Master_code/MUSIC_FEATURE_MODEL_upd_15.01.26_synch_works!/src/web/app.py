#!/usr/bin/env python3
"""
Web Interface for Music-Synchronized Motor Control

Simplified Flask/SocketIO web interface for the refactored system.
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

from config import SONGS_DIR, CONFIG_DIR
from offline import SongManager
from core import create_playback_controller, PlaybackController, TrajectoryPlayer
from calibration import LatencyCalibrator
from odrive_controller import configure_odrive, arm, soft_reset

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

        # Load calibration
        self._load_calibration()

        # Song manager
        self.song_manager = SongManager(str(SONGS_DIR))

    def _load_calibration(self):
        """Load latency calibration from config."""
        try:
            calibrator = LatencyCalibrator(config_path=str(CONFIG_DIR / "latency.json"))
            self.latency_offset_s = calibrator.get_latency_offset_seconds()
        except:
            self.latency_offset_s = 0.035


state = SystemState()


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
        'running': state.controller is not None and state.controller.is_playing()
    })


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

        if not song_id:
            return jsonify({'success': False, 'error': 'No song specified'})

        # Get song info
        song = state.song_manager.get_song_by_id(song_id)
        if song is None:
            return jsonify({'success': False, 'error': f'Song not found: {song_id}'})

        state.current_song_id = song_id

        # Select trajectory based on tempo mode
        if tempo_mode == 'dynamic':
            # Use dynamic tempo trajectory if available
            dynamic_path = song.trajectory_path.replace('trajectory.npy', 'trajectory_dynamic.npy')
            if os.path.exists(dynamic_path):
                trajectory_path = dynamic_path
                socketio.emit('status', {
                    'message': f'Loading: {song.metadata.name} (dynamic tempo)',
                    'type': 'info'
                })
            else:
                trajectory_path = song.trajectory_path
                socketio.emit('status', {
                    'message': f'Loading: {song.metadata.name} (dynamic tempo not available, using fixed)',
                    'type': 'warning'
                })
        else:
            trajectory_path = song.trajectory_path
            socketio.emit('status', {
                'message': f'Loading: {song.metadata.name} (fixed tempo)',
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

        # Set up status callback
        def on_status(status_data):
            socketio.emit('playback_status', status_data)

        def on_finished():
            state.status = "stopped"
            state.current_song_id = None
            socketio.emit('status', {'message': 'Playback finished', 'type': 'info'})
            socketio.emit('playback_finished', {})

        state.controller.set_on_status_update(on_status)
        state.controller.set_on_finished(on_finished)

        # Start playback
        state.controller.start()
        state.status = "playing"

        socketio.emit('status', {
            'message': f'Playing: {song.metadata.name}',
            'type': 'success'
        })

        return jsonify({'success': True})

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
    print(f"\nSongs directory: {SONGS_DIR}")
    print(f"Songs available: {len(state.song_manager.list_songs())}")
    print(f"Latency offset: {state.latency_offset_s*1000:.1f}ms")
    print("\nOpen your browser and navigate to:")
    print("  http://localhost:5000")
    print("\nPress Ctrl+C to exit")
    print("="*60 + "\n")

    socketio.run(app, host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    main()
