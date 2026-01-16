#!/usr/bin/env python3
"""
Web Interface for ODrive Motor Control with Music Synchronization

This script provides a web-based interface to control the motor system.
"""

import os
import json
import threading
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import odrive
from odrive.enums import AXIS_STATE_IDLE

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SONGS_DIR = os.path.join(SCRIPT_DIR, 'songs')

# Import the existing modules
from music_config import MusicLibrary, get_default_song
from music_analyzer import MusicAnalyzer
from motor_controller import MotorController
from audio_synthesizer import AudioSynthesizer
from beat_tapper import BeatTapper, PhaseTransitioner
from bluetooth_controller import BluetoothController
from data_recorder import DataRecorder
from odrive_controller import *
from motor_control_music import (
    connect_to_odrive,
    read_initial_motor_position,
    run_control_loop,
    cleanup_session,
    update_from_music_features,
    setup_music_playback
)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'odrive-music-control-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
class SystemState:
    def __init__(self):
        self.odrv0 = None
        self.motor_controller = None
        self.music_analyzer = None
        self.viz_manager = None
        self.audio_synth = None
        # Initialize MusicLibrary with correct path (songs directory is in src/songs)
        self.music_library = MusicLibrary(songs_directory=SONGS_DIR)
        self.control_thread = None
        self.running = False
        self.paused = False
        self.simulation_mode = True
        self.current_song = None
        self.status = "idle"
        self.initial_position = 0.0

        # Beat tapping components
        self.beat_tapper = BeatTapper(max_taps=32, min_taps=3, timeout=1.5)
        self.phase_transitioner = PhaseTransitioner(transition_duration=4.0)
        self.music_start_time = None

        # Bluetooth remote control
        self.bluetooth_controller = BluetoothController()
        self._setup_bluetooth_callbacks()

        # Data recorder for plotting
        self.data_recorder = DataRecorder(max_samples=20000)

        # Configuration
        # Note: Visualization is disabled in web interface to avoid threading issues with PyBullet on macOS
        self.config = {
            'window_size': 2.0,
            'delay_compensation': False,
            'audio_synthesis': False,
            'play_music': True
        }

    def _setup_bluetooth_callbacks(self):
        """Setup Bluetooth controller callbacks."""
        def on_amplitude_change(amplitude: float):
            # Update motor controller if available
            if self.motor_controller:
                self.motor_controller.set_user_amplitude(amplitude)
            # Emit to web interface
            socketio.emit('user_amplitude_update', {'amplitude': amplitude})
            socketio.emit('status', {
                'message': f'Remote amplitude: {amplitude:.2f}×',
                'type': 'info'
            })

        def on_switch_press():
            # The amplitude value is already updated by bluetooth_controller
            current_amp = self.bluetooth_controller.get_user_amplitude()
            if current_amp == 0.0:
                socketio.emit('status', {
                    'message': '⏸️ Remote switch: Motion paused (amplitude = 0)',
                    'type': 'warning'
                })
            else:
                socketio.emit('status', {
                    'message': f'▶️ Remote switch: Motion resumed (amplitude = {current_amp:.2f}×)',
                    'type': 'success'
                })

        def on_connection_change(connected: bool):
            socketio.emit('bluetooth_status', {'connected': connected, 'scanning': False})
            if connected:
                socketio.emit('status', {
                    'message': '✅ Remote control connected',
                    'type': 'success'
                })
            else:
                socketio.emit('status', {
                    'message': '❌ Remote control disconnected',
                    'type': 'warning'
                })

        def on_battery_update(voltage: float, low_battery: bool):
            # Emit battery update to web interface
            socketio.emit('battery_update', {
                'voltage': voltage,
                'low_battery': low_battery
            })
            # Only show low battery as status message (normal updates are silent)
            if low_battery:
                socketio.emit('status', {
                    'message': f'⚠️ LOW BATTERY WARNING: {voltage:.2f}V - Please recharge soon!',
                    'type': 'error'
                })

        self.bluetooth_controller.set_amplitude_callback(on_amplitude_change)
        self.bluetooth_controller.set_switch_callback(on_switch_press)
        self.bluetooth_controller.set_connection_callback(on_connection_change)
        self.bluetooth_controller.set_battery_callback(on_battery_update)

state = SystemState()


@app.route('/')
def index():
    """Render the main web interface."""
    return render_template('index.html')


@app.route('/api/songs')
def get_songs():
    """Get list of available songs organized by genre."""
    try:
        library = {}
        for genre in state.music_library.get_genres():
            songs = state.music_library.get_songs_in_genre(genre)
            library[genre] = songs
        return jsonify({'success': True, 'library': library})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """Get or update configuration."""
    if request.method == 'GET':
        return jsonify({'success': True, 'config': state.config})
    else:
        try:
            data = request.json
            state.config.update(data)
            return jsonify({'success': True, 'config': state.config})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})


@app.route('/api/connect', methods=['POST'])
def connect():
    """Connect to ODrive."""
    if state.odrv0 is not None:
        return jsonify({'success': False, 'error': 'Already connected'})

    try:
        socketio.emit('status', {'message': 'Searching for ODrive...', 'type': 'info'})

        # Use simulation mode flag
        if request.json.get('simulate', False):
            state.simulation_mode = True
            state.odrv0 = None
            state.initial_position = 0.0
            socketio.emit('status', {'message': 'Running in SIMULATION mode', 'type': 'success'})
        else:
            state.simulation_mode = False
            state.odrv0 = odrive.find_any(timeout=30)

            if state.odrv0 is None:
                raise Exception("ODrive not found")

            state.initial_position = read_initial_motor_position(state.odrv0)
            socketio.emit('status', {'message': 'ODrive connected', 'type': 'success'})

        state.status = "connected"
        return jsonify({'success': True})
    except Exception as e:
        socketio.emit('status', {'message': f'Error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/calibrate', methods=['POST'])
def calibrate():
    """Calibrate ODrive."""
    if state.odrv0 is None and not state.simulation_mode:
        return jsonify({'success': False, 'error': 'Not connected to ODrive'})

    if state.simulation_mode:
        return jsonify({'success': False, 'error': 'Cannot calibrate in simulation mode'})

    try:
        socketio.emit('status', {'message': 'Calibrating...', 'type': 'info'})
        configure_odrive(state.odrv0)
        socketio.emit('status', {'message': 'Calibration complete', 'type': 'success'})
        return jsonify({'success': True})
    except Exception as e:
        socketio.emit('status', {'message': f'Calibration error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/reset', methods=['POST'])
def reset():
    """Reset ODrive (clear errors)."""
    if state.odrv0 is None and not state.simulation_mode:
        return jsonify({'success': False, 'error': 'Not connected to ODrive'})

    if state.simulation_mode:
        return jsonify({'success': False, 'error': 'Cannot reset in simulation mode'})

    try:
        socketio.emit('status', {'message': 'Resetting ODrive...', 'type': 'info'})
        soft_reset(state.odrv0)
        socketio.emit('status', {'message': 'ODrive reset complete', 'type': 'success'})
        return jsonify({'success': True})
    except Exception as e:
        socketio.emit('status', {'message': f'Reset error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/arm', methods=['POST'])
def arm_motor():
    """Arm the motor (enter closed-loop control)."""
    if state.odrv0 is None and not state.simulation_mode:
        return jsonify({'success': False, 'error': 'Not connected to ODrive'})

    if state.simulation_mode:
        return jsonify({'success': True, 'message': 'Simulation mode - no arming needed'})

    try:
        socketio.emit('status', {'message': 'Arming motor...', 'type': 'info'})
        arm(state.odrv0)
        state.status = "armed"
        socketio.emit('status', {'message': 'Motor armed', 'type': 'success'})
        return jsonify({'success': True})
    except Exception as e:
        socketio.emit('status', {'message': f'Arm error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/run', methods=['POST'])
def run():
    """Start the motor control loop."""
    if state.running:
        return jsonify({'success': False, 'error': 'Already running'})

    try:
        # Import the global variables from motor_control_music
        import motor_control_music

        data = request.json
        genre = data.get('genre', 'edm')
        song_index = data.get('song_index', -1)

        # Get song path
        audio_file = state.music_library.get_song_path(genre, song_index)
        state.current_song = state.music_library.current_song

        socketio.emit('status', {
            'message': f'Loading song: {state.current_song}',
            'type': 'info'
        })

        # Initialize music analyzer and set both local and global variables
        state.music_analyzer = MusicAnalyzer(audio_file, window_size=state.config['window_size'])
        motor_control_music.music_analyzer = state.music_analyzer  # Set global variable
        audio_duration = state.music_analyzer.get_duration()

        # Initialize motor controller
        state.motor_controller = MotorController(
            odrv0=state.odrv0,
            phase_correction_enabled=state.config['delay_compensation'],
            initial_position_offset=state.initial_position
        )

        # Initialize visualization (disabled for web interface to avoid thread issues)
        # PyBullet requires main thread on macOS, which conflicts with Flask threading
        state.viz_manager = None

        # Initialize audio synthesizer if enabled
        if state.config['audio_synthesis']:
            state.audio_synth = AudioSynthesizer()

        # Start control loop in background thread
        state.running = True
        state.status = "running"
        motor_control_music.program_running = True  # Set global flag

        # Record music start time for beat tapping
        state.music_start_time = time.time()

        # Reset beat tapper for new song
        state.beat_tapper.reset()
        state.phase_transitioner.cancel()

        # Start data recording
        state.data_recorder.start_recording()

        def control_loop_wrapper():
            try:
                run_control_loop(
                    state.motor_controller,
                    state.viz_manager,
                    audio_file,
                    audio_duration,
                    play_music=state.config['play_music'],
                    audio_synth=state.audio_synth,
                    data_recorder=state.data_recorder
                )
            except Exception as e:
                socketio.emit('status', {'message': f'Error: {str(e)}', 'type': 'error'})
            finally:
                state.running = False
                state.status = "stopped"
                motor_control_music.program_running = False  # Reset global flag
                state.music_start_time = None

                # Stop data recording
                state.data_recorder.stop_recording()

                socketio.emit('status', {'message': 'Stopped', 'type': 'info'})

        state.control_thread = threading.Thread(target=control_loop_wrapper, daemon=True)
        state.control_thread.start()

        socketio.emit('status', {'message': 'Started', 'type': 'success'})
        return jsonify({'success': True})

    except Exception as e:
        socketio.emit('status', {'message': f'Error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/pause', methods=['POST'])
def pause():
    """Pause the motor control loop."""
    if not state.running:
        return jsonify({'success': False, 'error': 'Not running'})

    state.paused = not state.paused
    status = 'paused' if state.paused else 'resumed'
    socketio.emit('status', {'message': f'Motor {status}', 'type': 'info'})
    return jsonify({'success': True, 'paused': state.paused})


@app.route('/api/stop', methods=['POST'])
def stop():
    """Stop the motor control loop."""
    if not state.running:
        return jsonify({'success': False, 'error': 'Not running'})

    try:
        import motor_control_music

        state.running = False
        motor_control_music.program_running = False  # Set global flag to stop

        # Wait for thread to finish
        if state.control_thread is not None:
            state.control_thread.join(timeout=5)

        # Cleanup
        cleanup_session(
            state.config['play_music'],
            state.viz_manager,
            state.audio_synth
        )

        state.status = "stopped"
        socketio.emit('status', {'message': 'Stopped', 'type': 'info'})
        return jsonify({'success': True})
    except Exception as e:
        socketio.emit('status', {'message': f'Error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    """Disconnect from ODrive."""
    if state.running:
        return jsonify({'success': False, 'error': 'Stop the system first'})

    try:
        if state.odrv0 is not None and not state.simulation_mode:
            state.odrv0.axis0.requested_state = AXIS_STATE_IDLE

        state.odrv0 = None
        state.status = "disconnected"
        socketio.emit('status', {'message': 'Disconnected', 'type': 'info'})
        return jsonify({'success': True})
    except Exception as e:
        socketio.emit('status', {'message': f'Error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    """Shutdown the server."""
    import motor_control_music

    try:
        # Stop any running control loops
        if state.running:
            state.running = False
            motor_control_music.program_running = False
            if state.control_thread is not None:
                state.control_thread.join(timeout=2)

        # Disconnect from ODrive
        if state.odrv0 is not None and not state.simulation_mode:
            try:
                state.odrv0.axis0.requested_state = AXIS_STATE_IDLE
            except:
                pass

        # Cleanup
        if state.music_analyzer:
            state.music_analyzer.stop()
        if state.viz_manager:
            state.viz_manager.close()
        if state.audio_synth:
            state.audio_synth.stop()

        socketio.emit('status', {'message': 'Shutting down server...', 'type': 'info'})

        # Shutdown Flask server
        def shutdown_server():
            import time
            time.sleep(1)  # Give time for response to be sent
            import os
            import signal
            os.kill(os.getpid(), signal.SIGINT)

        threading.Thread(target=shutdown_server, daemon=True).start()

        return jsonify({'success': True, 'message': 'Server shutting down'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/status')
def get_status():
    """Get current system status."""
    return jsonify({
        'success': True,
        'status': state.status,
        'running': state.running,
        'paused': state.paused,
        'simulation_mode': state.simulation_mode,
        'connected': state.odrv0 is not None or state.simulation_mode,
        'current_song': state.current_song,
        'config': state.config
    })


@app.route('/api/tap', methods=['POST'])
def tap_beat():
    """Register a beat tap."""
    if not state.running:
        return jsonify({'success': False, 'error': 'Not running'})

    if state.music_start_time is None:
        return jsonify({'success': False, 'error': 'Music start time not recorded'})

    try:
        tap_info = state.beat_tapper.tap()
        socketio.emit('tap_registered', tap_info)

        return jsonify({
            'success': True,
            'tap_count': tap_info['tap_count'],
            'can_calculate': tap_info['can_calculate']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/tap/status')
def get_tap_status():
    """Get current beat tapper status."""
    try:
        status = state.beat_tapper.get_status()
        return jsonify({'success': True, 'tapper': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/tap/reset', methods=['POST'])
def reset_taps():
    """Reset beat tapper."""
    try:
        state.beat_tapper.reset()
        state.phase_transitioner.cancel()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/connect', methods=['POST'])
def bluetooth_connect():
    """Connect to Bluetooth remote control."""
    try:
        if state.bluetooth_controller.is_connected():
            return jsonify({'success': False, 'error': 'Already connected'})

        # Connect in background (non-blocking)
        socketio.emit('status', {'message': 'Scanning for remote control...', 'type': 'info'})
        socketio.emit('bluetooth_status', {'connected': False, 'scanning': True})
        success = state.bluetooth_controller.connect()

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Connection failed - device not found'})
    except Exception as e:
        socketio.emit('status', {'message': f'Bluetooth error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/disconnect', methods=['POST'])
def bluetooth_disconnect():
    """Disconnect from Bluetooth remote control."""
    try:
        state.bluetooth_controller.disconnect()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/reset_baseline', methods=['POST'])
def bluetooth_reset_baseline():
    """Reset remote control baseline (set current encoder position to 1.0×)."""
    try:
        if not state.bluetooth_controller.is_connected():
            return jsonify({'success': False, 'error': 'Remote not connected'})

        state.bluetooth_controller.reset_baseline()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/status')
def bluetooth_status():
    """Get Bluetooth remote status."""
    try:
        status = state.bluetooth_controller.get_status()
        return jsonify({'success': True, 'bluetooth': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bluetooth/toggle_direction', methods=['POST'])
def bluetooth_toggle_direction():
    """Toggle encoder direction (swap clockwise/counter-clockwise behavior)."""
    try:
        state.bluetooth_controller.toggle_direction()
        direction = "reversed" if state.bluetooth_controller.encoder_direction_reversed else "normal"
        socketio.emit('status', {
            'message': f'Encoder direction: {direction}',
            'type': 'info'
        })
        return jsonify({
            'success': True,
            'direction_reversed': state.bluetooth_controller.encoder_direction_reversed
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/data/plot', methods=['POST'])
def plot_data():
    """Generate plot from recorded data."""
    try:
        if state.data_recorder.get_sample_count() == 0:
            return jsonify({'success': False, 'error': 'No data recorded'})

        data = request.json or {}
        plot_type = data.get('type', 'separate')  # 'separate' or 'combined'

        # Generate filename with timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'motor_data_{timestamp}.png'
        filepath = os.path.join(SCRIPT_DIR, 'plots', filename)

        # Create plots directory if it doesn't exist
        os.makedirs(os.path.join(SCRIPT_DIR, 'plots'), exist_ok=True)

        # Generate plot
        if plot_type == 'combined':
            state.data_recorder.plot_combined(save_filename=filepath)
        else:
            state.data_recorder.plot_data(save_filename=filepath)

        socketio.emit('status', {
            'message': f'Plot saved: {filename}',
            'type': 'success'
        })

        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'sample_count': state.data_recorder.get_sample_count()
        })
    except Exception as e:
        socketio.emit('status', {'message': f'Plot error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/data/export', methods=['POST'])
def export_data():
    """Export recorded data to CSV."""
    try:
        if state.data_recorder.get_sample_count() == 0:
            return jsonify({'success': False, 'error': 'No data recorded'})

        # Generate filename with timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'motor_data_{timestamp}.csv'
        filepath = os.path.join(SCRIPT_DIR, 'data', filename)

        # Create data directory if it doesn't exist
        os.makedirs(os.path.join(SCRIPT_DIR, 'data'), exist_ok=True)

        # Export data
        state.data_recorder.export_data(filepath)

        socketio.emit('status', {
            'message': f'Data exported: {filename}',
            'type': 'success'
        })

        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'sample_count': state.data_recorder.get_sample_count()
        })
    except Exception as e:
        socketio.emit('status', {'message': f'Export error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/data/statistics')
def data_statistics():
    """Get statistics from recorded data."""
    try:
        stats = state.data_recorder.get_statistics()
        if not stats:
            return jsonify({'success': False, 'error': 'No data recorded'})

        return jsonify({'success': True, 'statistics': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/pid/get', methods=['GET'])
def get_pid():
    """Get current PID values from ODrive."""
    if state.odrv0 is None and not state.simulation_mode:
        return jsonify({'success': False, 'error': 'Not connected to ODrive'})

    if state.simulation_mode:
        return jsonify({'success': False, 'error': 'PID tuning not available in simulation mode'})

    try:
        pid_values = {
            'pos_gain': state.odrv0.axis0.controller.config.pos_gain,
            'vel_gain': state.odrv0.axis0.controller.config.vel_gain,
            'vel_integrator_gain': state.odrv0.axis0.controller.config.vel_integrator_gain
        }
        return jsonify({'success': True, 'pid': pid_values})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/pid/set', methods=['POST'])
def set_pid():
    """Set PID values on ODrive (without calling full configuration)."""
    if state.odrv0 is None and not state.simulation_mode:
        return jsonify({'success': False, 'error': 'Not connected to ODrive'})

    if state.simulation_mode:
        return jsonify({'success': False, 'error': 'PID tuning not available in simulation mode'})

    try:
        data = request.json
        pos_gain = data.get('pos_gain')
        vel_gain = data.get('vel_gain')
        vel_integrator_gain = data.get('vel_integrator_gain')

        if pos_gain is None or vel_gain is None or vel_integrator_gain is None:
            return jsonify({'success': False, 'error': 'Missing PID parameters'})

        # Validate ranges
        if not (0 <= pos_gain <= 200):
            return jsonify({'success': False, 'error': 'pos_gain must be between 0 and 200'})
        if not (0 <= vel_gain <= 2):
            return jsonify({'success': False, 'error': 'vel_gain must be between 0 and 2'})
        if not (0 <= vel_integrator_gain <= 1):
            return jsonify({'success': False, 'error': 'vel_integrator_gain must be between 0 and 1'})

        # Update PID values directly (no configuration save/reboot)
        state.odrv0.axis0.controller.config.pos_gain = float(pos_gain)
        state.odrv0.axis0.controller.config.vel_gain = float(vel_gain)
        state.odrv0.axis0.controller.config.vel_integrator_gain = float(vel_integrator_gain)

        socketio.emit('status', {
            'message': f'PID updated: P={pos_gain}, D={vel_gain:.3f}, I={vel_integrator_gain:.3f}',
            'type': 'success'
        })

        return jsonify({'success': True})
    except Exception as e:
        socketio.emit('status', {'message': f'PID update error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/phase/get', methods=['GET'])
def get_phase():
    """Get current phase offset from motor controller."""
    if not state.running or state.motor_controller is None:
        return jsonify({'success': False, 'error': 'Motor not running'})

    try:
        phase_offset = state.motor_controller.phase_offset
        return jsonify({'success': True, 'phase_offset': phase_offset})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/phase/nudge', methods=['POST'])
def nudge_phase():
    """Nudge phase offset by specified amount and direction."""
    if not state.running or state.motor_controller is None:
        return jsonify({'success': False, 'error': 'Motor not running'})

    try:
        data = request.json
        direction = data.get('direction')  # 1 for lead ahead, -1 for lag behind
        amount_seconds = data.get('amount_seconds')  # Time in seconds

        if direction is None or amount_seconds is None:
            return jsonify({'success': False, 'error': 'Missing direction or amount'})

        # Convert time nudge to phase nudge
        # Phase (radians) = 2π × frequency × time
        # Leading ahead (positive direction) means adding positive phase
        # Lagging behind (negative direction) means subtracting phase
        frequency = state.motor_controller.frequency  # Hz
        phase_change = 2 * 3.14159265359 * frequency * float(amount_seconds) * int(direction)

        # Apply phase change
        state.motor_controller.phase_offset += phase_change

        socketio.emit('status', {
            'message': f'Phase nudged {abs(amount_seconds)*1000:.1f}ms {"ahead" if direction > 0 else "behind"}',
            'type': 'info'
        })

        return jsonify({
            'success': True,
            'phase_offset': state.motor_controller.phase_offset
        })
    except Exception as e:
        socketio.emit('status', {'message': f'Phase nudge error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/phase/reset', methods=['POST'])
def reset_phase():
    """Reset phase offset to zero."""
    if not state.running or state.motor_controller is None:
        return jsonify({'success': False, 'error': 'Motor not running'})

    try:
        state.motor_controller.phase_offset = 0.0
        socketio.emit('status', {
            'message': 'Phase offset reset to 0',
            'type': 'success'
        })
        return jsonify({'success': True})
    except Exception as e:
        socketio.emit('status', {'message': f'Phase reset error: {str(e)}', 'type': 'error'})
        return jsonify({'success': False, 'error': str(e)})


# Status update thread
def status_update_thread():
    """Send periodic status updates via WebSocket."""
    while True:
        time.sleep(0.1)  # Check more frequently for beat tapping

        if state.running and state.motor_controller:
            # Send motor stats every second
            if int(time.time() * 10) % 10 == 0:
                stats = state.motor_controller.get_statistics()
                stats['user_amplitude'] = state.motor_controller.get_user_amplitude()
                socketio.emit('motor_stats', stats)

                # Log user amplitude periodically
                user_amp = state.motor_controller.get_user_amplitude()
                if hasattr(status_update_thread, 'last_logged_amp'):
                    # Only log if amplitude changed significantly (>0.1)
                    if abs(user_amp - status_update_thread.last_logged_amp) > 0.1:
                        socketio.emit('status', {
                            'message': f'User amplitude: {user_amp:.2f}×',
                            'type': 'info'
                        })
                        status_update_thread.last_logged_amp = user_amp
                else:
                    status_update_thread.last_logged_amp = user_amp

            # Check if beat tapping should be processed
            if state.beat_tapper.should_process() and state.music_start_time is not None:
                result = state.beat_tapper.calculate_bpm_and_phase(state.music_start_time)

                if result is not None:
                    detected_bpm, target_phase = result

                    socketio.emit('status', {
                        'message': f'🎵 Beat detected: {detected_bpm:.1f} BPM. Starting 4-second phase transition...',
                        'type': 'success'
                    })

                    # Start smooth phase transition
                    current_time = time.time()
                    elapsed_music_time = current_time - state.music_start_time
                    current_phase = state.motor_controller.phase_offset

                    state.phase_transitioner.start_transition(
                        current_phase,
                        target_phase,
                        elapsed_music_time
                    )

                    # Mark as inactive so we don't process again
                    state.beat_tapper.is_active = False

                    # Update UI status
                    socketio.emit('tap_transition_started', {
                        'detected_bpm': detected_bpm,
                        'duration': 4.0
                    })
                else:
                    socketio.emit('status', {
                        'message': '⚠️ Could not detect beat pattern. Try tapping more consistently.',
                        'type': 'warning'
                    })
                    state.beat_tapper.is_active = False

            # Apply phase transition if active
            if state.phase_transitioner.is_transitioning and state.music_start_time is not None:
                current_time = time.time()
                elapsed_music_time = current_time - state.music_start_time

                # Check if this is the last iteration (transition just completed)
                was_transitioning = state.phase_transitioner.is_transitioning

                new_phase = state.phase_transitioner.get_phase(
                    elapsed_music_time,
                    state.motor_controller.phase_offset
                )

                state.motor_controller.phase_offset = new_phase

                # Calculate remaining time in transition
                elapsed_transition_time = elapsed_music_time - state.phase_transitioner.transition_start_time
                remaining_time = state.phase_transitioner.transition_duration - elapsed_transition_time

                # Send countdown update every 0.5 seconds
                if int(remaining_time * 2) != int((remaining_time + 0.1) * 2):
                    socketio.emit('tap_countdown', {
                        'remaining': max(0, remaining_time)
                    })

                # Check if transition just completed
                if was_transitioning and not state.phase_transitioner.is_transitioning:
                    socketio.emit('status', {
                        'message': '✅ Phase transition complete! Motion is now synchronized with your taps.',
                        'type': 'success'
                    })
                    socketio.emit('tap_transition_complete', {})


if __name__ == '__main__':
    # Start status update thread
    update_thread = threading.Thread(target=status_update_thread, daemon=True)
    update_thread.start()

    # Run Flask app
    print("\n" + "="*60)
    print("ODrive Music Control - Web Interface")
    print("="*60)
    print("\nOpen your browser and navigate to:")
    print("  http://localhost:5000")
    print("\nPress Ctrl+C to exit")
    print("="*60 + "\n")

    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
