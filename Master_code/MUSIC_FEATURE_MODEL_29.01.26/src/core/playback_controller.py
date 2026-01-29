"""
Playback Controller

Main orchestrator for synchronized audio-motor playback.
Coordinates audio playback, trajectory lookup, and motor control
in a CPU-light real-time loop.
"""

import time
import threading
from typing import Optional, Callable
from dataclasses import dataclass

from .audio_player import AudioPlayer
from .trajectory_player import TrajectoryPlayer
from .motor_driver import MotorDriver


@dataclass
class PlaybackStats:
    """Statistics from playback session."""
    duration: float
    elapsed_time: float
    total_commands: int
    avg_loop_time_us: float
    max_loop_time_us: float
    position_error_rms: float


class PlaybackController:
    """
    Main playback controller.

    Coordinates:
    - Audio playback (master clock via sample count)
    - Trajectory lookup (pre-computed positions)
    - Motor control (60Hz position commands)

    The control loop is designed to be CPU-light (<1ms per iteration).
    """

    def __init__(
        self,
        audio_player: AudioPlayer,
        trajectory_player: TrajectoryPlayer,
        motor_driver: MotorDriver,
        control_rate_hz: float = 60.0,
        latency_offset_s: float = 0.0,
        feedforward_enabled: bool = True
    ):
        """
        Initialize the playback controller.

        Args:
            audio_player: AudioPlayer instance
            trajectory_player: TrajectoryPlayer instance
            motor_driver: MotorDriver instance
            control_rate_hz: Motor control loop rate in Hz
            latency_offset_s: Latency compensation offset in seconds
            feedforward_enabled: Whether to use velocity feedforward (if available)
        """
        self.audio_player = audio_player
        self.trajectory_player = trajectory_player
        self.motor_driver = motor_driver

        self.control_rate = control_rate_hz
        self.control_period = 1.0 / control_rate_hz
        self.latency_offset = latency_offset_s

        # Velocity feedforward control
        self._feedforward_enabled = feedforward_enabled
        self._feedforward_lock = threading.Lock()

        # User-controlled amplitude (applied at runtime)
        self._user_amplitude = 0.3
        self._user_amplitude_lock = threading.Lock()

        # Latency offset lock for thread-safe updates
        self._latency_offset_lock = threading.Lock()

        # Initial motor offset
        self._initial_offset = motor_driver.initial_offset

        # Control state
        self._running = False
        self._paused = False
        self._control_thread: Optional[threading.Thread] = None

        # Statistics
        self._loop_times = []
        self._position_errors = []

        # Callbacks
        self._on_status_update: Optional[Callable[[dict], None]] = None
        self._on_finished: Optional[Callable[[], None]] = None

    def start(self) -> None:
        """Start synchronized playback."""
        if self._running:
            return

        self._running = True
        self._paused = False
        self._loop_times = []
        self._position_errors = []

        # Start audio playback
        self.audio_player.set_on_finished(self._on_audio_finished)
        self.audio_player.start()

        # Start control loop in separate thread
        self._control_thread = threading.Thread(
            target=self._control_loop,
            daemon=True
        )
        self._control_thread.start()

    def stop(self) -> None:
        """Stop playback."""
        self._running = False

        # Stop audio
        self.audio_player.stop()

        # Wait for control thread
        if self._control_thread is not None:
            self._control_thread.join(timeout=2.0)
            self._control_thread = None

    def pause(self) -> None:
        """Pause playback."""
        self._paused = True
        self.audio_player.pause()

    def resume(self) -> None:
        """Resume playback."""
        self._paused = False
        self.audio_player.resume()

    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self._running and not self._paused

    def is_finished(self) -> bool:
        """Check if playback finished."""
        return self.audio_player.is_finished

    @property
    def is_paused(self) -> bool:
        """Check if playback is paused."""
        return self._paused

    def get_current_time(self) -> float:
        """Get current playback time in seconds."""
        return self.audio_player.current_time_seconds

    def get_duration(self) -> float:
        """Get total duration in seconds."""
        return self.audio_player.get_duration()

    def set_user_amplitude(self, amplitude: float) -> None:
        """
        Set user amplitude multiplier.

        Args:
            amplitude: Amplitude multiplier (typically 0-2)
        """
        with self._user_amplitude_lock:
            self._user_amplitude = max(0.0, amplitude)

    def get_user_amplitude(self) -> float:
        """Get current user amplitude multiplier."""
        with self._user_amplitude_lock:
            return self._user_amplitude

    def set_latency_offset(self, offset_s: float) -> None:
        """Set latency compensation offset in seconds (thread-safe)."""
        with self._latency_offset_lock:
            self.latency_offset = offset_s

    def get_latency_offset(self) -> float:
        """Get current latency offset in seconds."""
        with self._latency_offset_lock:
            return self.latency_offset

    def set_feedforward_enabled(self, enabled: bool) -> None:
        """Enable or disable velocity feedforward (thread-safe)."""
        with self._feedforward_lock:
            self._feedforward_enabled = enabled

    def is_feedforward_enabled(self) -> bool:
        """Check if feedforward is enabled."""
        with self._feedforward_lock:
            return self._feedforward_enabled

    def set_on_status_update(self, callback: Callable[[dict], None]) -> None:
        """Set callback for status updates (called ~10Hz)."""
        self._on_status_update = callback

    def set_on_finished(self, callback: Callable[[], None]) -> None:
        """Set callback for playback finished."""
        self._on_finished = callback

    def _control_loop(self) -> None:
        """
        Main control loop.

        Runs at control_rate_hz (default 60Hz).
        Target: <1ms per iteration.
        """
        next_time = time.perf_counter()
        status_update_counter = 0

        while self._running:
            loop_start = time.perf_counter()

            # Skip if paused
            if self._paused:
                time.sleep(self.control_period)
                next_time = time.perf_counter() + self.control_period
                continue

            # Check if audio finished
            if self.audio_player.is_finished:
                break

            # Get current audio time (the master clock)
            current_time = self.audio_player.current_time_seconds

            # Get user amplitude (thread-safe)
            with self._user_amplitude_lock:
                user_amp = self._user_amplitude

            # Get latency offset (thread-safe)
            with self._latency_offset_lock:
                latency_off = self.latency_offset

            # Get feedforward setting (thread-safe)
            with self._feedforward_lock:
                use_feedforward = self._feedforward_enabled

            # Lookup trajectory position and velocity with latency offset
            # Uses velocity feedforward if available AND enabled
            if use_feedforward and self.trajectory_player.has_velocity_feedforward():
                target_pos, target_vel = self.trajectory_player.get_position_and_velocity(
                    timestamp=current_time,
                    user_amplitude=user_amp,
                    initial_offset=self._initial_offset,
                    latency_offset=latency_off
                )
                # Send position with velocity feedforward
                self.motor_driver.set_position_with_velocity(target_pos, target_vel)
            else:
                # Position-only mode (feedforward disabled or not available)
                target_pos = self.trajectory_player.get_position_with_amplitude(
                    timestamp=current_time,
                    user_amplitude=user_amp,
                    initial_offset=self._initial_offset,
                    latency_offset=latency_off
                )
                self.motor_driver.set_position(target_pos)

            # Record loop time
            loop_time = time.perf_counter() - loop_start
            self._loop_times.append(loop_time)

            # Record position error (for statistics)
            actual_pos = self.motor_driver.get_position()
            self._position_errors.append(target_pos - actual_pos)

            # Status update every ~10 iterations (6Hz with 60Hz loop)
            status_update_counter += 1
            if status_update_counter >= 10 and self._on_status_update:
                status_update_counter = 0
                self._emit_status(current_time, target_pos, actual_pos, loop_time)

            # Timing control - wait for next period
            next_time += self.control_period
            sleep_time = next_time - time.perf_counter()

            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # We're behind - catch up
                next_time = time.perf_counter() + self.control_period

        self._running = False

    def _emit_status(
        self,
        current_time: float,
        target_pos: float,
        actual_pos: float,
        loop_time: float
    ) -> None:
        """Emit status update to callback."""
        if self._on_status_update is None:
            return

        # Feedforward is active only if enabled AND available
        ff_available = self.trajectory_player.has_velocity_feedforward()
        ff_enabled = self.is_feedforward_enabled()
        ff_active = ff_available and ff_enabled

        status = {
            'current_time': current_time,
            'duration': self.get_duration(),
            'target_position': target_pos,
            'actual_position': actual_pos,
            'position_error': target_pos - actual_pos,
            'loop_time_us': loop_time * 1_000_000,
            'user_amplitude': self.get_user_amplitude(),
            'latency_offset_ms': self.get_latency_offset() * 1000,
            'feedforward_available': ff_available,
            'feedforward_enabled': ff_enabled,
            'feedforward_active': ff_active,
            'target_velocity': self.motor_driver.get_last_velocity_command()
        }
        self._on_status_update(status)

    def _on_audio_finished(self) -> None:
        """Called when audio playback finishes."""
        self._running = False
        if self._on_finished:
            self._on_finished()

    def get_stats(self) -> PlaybackStats:
        """Get playback statistics."""
        import numpy as np

        loop_times_us = [t * 1_000_000 for t in self._loop_times]

        return PlaybackStats(
            duration=self.get_duration(),
            elapsed_time=self.get_current_time(),
            total_commands=self.motor_driver.get_command_count(),
            avg_loop_time_us=np.mean(loop_times_us) if loop_times_us else 0,
            max_loop_time_us=max(loop_times_us) if loop_times_us else 0,
            position_error_rms=np.sqrt(np.mean(np.array(self._position_errors)**2)) if self._position_errors else 0
        )


def create_playback_controller(
    audio_path: str,
    trajectory_path: str,
    odrv0,
    initial_offset: float = 0.0,
    control_rate_hz: float = 60.0,
    latency_offset_s: float = 0.0,
    feedforward_enabled: bool = True
) -> PlaybackController:
    """
    Create a complete playback controller.

    Args:
        audio_path: Path to audio.wav
        trajectory_path: Path to trajectory.npy
        odrv0: ODrive object (required)
        initial_offset: Initial motor position
        control_rate_hz: Control loop rate
        latency_offset_s: Latency compensation
        feedforward_enabled: Whether to use velocity feedforward (if available)

    Returns:
        Configured PlaybackController

    Raises:
        ValueError: If odrv0 is None
    """
    if odrv0 is None:
        raise ValueError("ODrive object is required")

    audio_player = AudioPlayer(audio_path)
    trajectory_player = TrajectoryPlayer(trajectory_path)
    motor_driver = MotorDriver(odrv0, initial_offset)

    return PlaybackController(
        audio_player=audio_player,
        trajectory_player=trajectory_player,
        motor_driver=motor_driver,
        control_rate_hz=control_rate_hz,
        latency_offset_s=latency_offset_s,
        feedforward_enabled=feedforward_enabled
    )


if __name__ == "__main__":
    import sys
    import odrive

    if len(sys.argv) < 3:
        print("Usage: python playback_controller.py <audio.wav> <trajectory.npy>")
        sys.exit(1)

    audio_path = sys.argv[1]
    trajectory_path = sys.argv[2]

    print("Searching for ODrive...")
    odrv0 = odrive.find_any(timeout=10)
    if odrv0 is None:
        print("ODrive not found. Please connect ODrive and try again.")
        sys.exit(1)

    print(f"Found ODrive: {odrv0.serial_number}")
    initial_offset = odrv0.axis0.encoder.pos_estimate

    print("Creating playback controller...")
    controller = create_playback_controller(
        audio_path=audio_path,
        trajectory_path=trajectory_path,
        odrv0=odrv0,
        initial_offset=initial_offset,
        latency_offset_s=0.035  # Example: 35ms total latency
    )

    def on_status(status):
        print(f"\rTime: {status['current_time']:.1f}s | "
              f"Pos: {status['target_position']:.2f} | "
              f"Loop: {status['loop_time_us']:.0f}μs", end="")

    controller.set_on_status_update(on_status)

    print(f"Duration: {controller.get_duration():.1f}s")
    print("Starting playback... (Ctrl+C to stop)")

    controller.start()

    try:
        while not controller.is_finished():
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()

        stats = controller.get_stats()
        print(f"\n\nPlayback Statistics:")
        print(f"  Total commands: {stats.total_commands}")
        print(f"  Avg loop time: {stats.avg_loop_time_us:.1f} μs")
        print(f"  Max loop time: {stats.max_loop_time_us:.1f} μs")
        print(f"  Position error RMS: {stats.position_error_rms:.4f}")
