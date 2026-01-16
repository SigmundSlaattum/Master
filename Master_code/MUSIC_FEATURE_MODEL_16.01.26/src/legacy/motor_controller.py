"""
Motor Controller Module

Encapsulates the motor control loop logic with music synchronization.
"""

import time
import math
import numpy as np
from typing import Optional, Callable
from collections import deque


class MotorController:
    """
    Manages motor control loop with music synchronization.
    """

    def __init__(self,
                 odrv0=None,
                 sampling_rate: float = 60.0,
                 phase_correction_enabled: bool = True,
                 phase_correction_gain: float = 0.05,
                 phase_lock_threshold: float = 0.1,
                 initial_position_offset: float = 0.0):
        """
        Initialize motor controller.

        Args:
            odrv0: ODrive object (None for simulation mode)
            sampling_rate: Control loop rate in Hz
            phase_correction_enabled: Enable phase correction
            phase_correction_gain: Gain for phase correction
            phase_lock_threshold: Threshold for phase lock indicator
            initial_position_offset: Initial motor position offset (starting point)
        """
        self.odrv0 = odrv0
        self.simulation_mode = (odrv0 is None)
        self.sampling_rate = sampling_rate
        self.control_period = 1.0 / sampling_rate
        self.phase_correction_enabled = phase_correction_enabled
        self.phase_correction_gain = phase_correction_gain
        self.phase_lock_threshold = phase_lock_threshold

        # Motion parameters
        self.amplitude1 = 5.0
        self.amplitude2 = 0.0
        self.master_amplitude = 0.0
        self.user_amplitude = 1.0  # User-controlled amplitude multiplier from remote
        self.bpm = 120.0
        self.frequency = 2.0  # Hz

        # Initial position offset (starting point of motion)
        self.initial_position_offset = initial_position_offset

        # Synchronization state
        self.phase_offset = 0.0
        self.beat_locked = False
        self.beat_count = -1
        self.phase_error_history = []

        # Statistics
        self.max_position_error = 0.0
        self.avg_position_error = 0.0
        self.error_samples = []
        self.phase_velocity_estimate = 0.0

        # Simulation state
        self.simulated_encoder_pos = initial_position_offset

        # Running flag
        self.running = False

    def set_motion_parameters(self, amplitude1: float, amplitude2: float,
                             master_amplitude: float, bpm: float):
        """
        Update motion parameters from music analysis.

        Args:
            amplitude1: Primary sinusoid amplitude
            amplitude2: Secondary sinusoid amplitude
            master_amplitude: Master amplitude multiplier
            bpm: Beats per minute
        """
        self.amplitude1 = amplitude1
        self.amplitude2 = amplitude2
        self.master_amplitude = master_amplitude
        self.bpm = bpm

        # Calculate frequency with validation to prevent divide-by-zero
        self.frequency = bpm / 60.0 if bpm > 0 else 1.0  # Default to 1 Hz if bpm is 0 or negative

    def set_user_amplitude(self, user_amplitude: float):
        """
        Set user amplitude multiplier from remote control.

        Args:
            user_amplitude: User amplitude multiplier (typically 0.0 to 2.0+)
        """
        self.user_amplitude = user_amplitude

    def get_user_amplitude(self) -> float:
        """
        Get current user amplitude multiplier.

        Returns:
            float: User amplitude multiplier
        """
        return self.user_amplitude

    def calculate_expected_position(self, current_time: float) -> float:
        """
        Calculate expected motor position at given time.

        Args:
            current_time: Current time in seconds

        Returns:
            Expected position (including initial offset and user amplitude)
        """
        pos_command1 = self.amplitude1 * math.sin(
            2 * math.pi * self.frequency * current_time + self.phase_offset
        )
        pos_command2 = self.amplitude2 * math.sin(
            2 * math.pi * (self.frequency / 2) * current_time + self.phase_offset
        )
        # Add initial position offset to the calculated motion
        # Apply both master amplitude (from music) and user amplitude (from remote control)
        return (self.initial_position_offset + (pos_command1 + pos_command2) * self.master_amplitude * self.user_amplitude)

    def calculate_original_position(self, current_time: float) -> float:
        """
        Calculate original motor position (before user amplitude modification).

        Args:
            current_time: Current time in seconds

        Returns:
            Original position (with music amplitude only, no user amplitude)
        """
        pos_command1 = self.amplitude1 * math.sin(
            2 * math.pi * self.frequency * current_time + self.phase_offset
        )
        pos_command2 = self.amplitude2 * math.sin(
            2 * math.pi * (self.frequency / 2) * current_time + self.phase_offset
        )
        # Return position with music amplitude only (no user amplitude)
        return self.initial_position_offset + (pos_command1 + pos_command2) * self.master_amplitude

    def apply_beat_phase_lock(self, beat_phase: float, current_time: float):
        """
        Apply beat-based phase locking.

        Args:
            beat_phase: Current beat phase (0-1)
            current_time: Current time in seconds
        """
        if beat_phase < 0.1 and not self.beat_locked:
            self.beat_locked = True
            self.beat_count = (self.beat_count + 1) % 4

            # Calculate phase error
            expected_phase_at_beat = (
                2 * math.pi * self.frequency * current_time + self.phase_offset
            ) % (2 * math.pi)

            # Bidirectional correction
            if expected_phase_at_beat > math.pi:
                beat_phase_error = -(2 * math.pi - expected_phase_at_beat)
            else:
                beat_phase_error = -expected_phase_at_beat

            # Store error history
            self.phase_error_history.append(beat_phase_error)
            if len(self.phase_error_history) > 3:
                self.phase_error_history.pop(0)

            # Correct on downbeat
            if self.beat_count == 0 and len(self.phase_error_history) >= 2:
                mean_phase_error = np.mean(self.phase_error_history)

                if abs(mean_phase_error) > 0.05:
                    correction_gain = 0.5
                    max_beat_correction = 0.3

                    limited_correction = np.clip(
                        correction_gain * mean_phase_error,
                        -max_beat_correction,
                        max_beat_correction
                    )
                    self.phase_offset += limited_correction

                    print(f"\n[Downbeat Correction] Error: {mean_phase_error:.3f} → "
                          f"Correction: {limited_correction:.3f}")

        elif beat_phase > 0.1:
            self.beat_locked = False

    def apply_position_phase_correction(self):
        """Apply position-based phase correction."""
        if len(self.error_samples) > 20:
            avg_error = np.mean(self.error_samples[-20:])

            if abs(avg_error) > 0.02:
                phase_correction = self.phase_correction_gain * avg_error
                max_correction_per_step = 0.01
                phase_correction = np.clip(
                    phase_correction,
                    -max_correction_per_step,
                    max_correction_per_step
                )

                self.phase_offset += phase_correction
                self.phase_velocity_estimate = phase_correction * self.sampling_rate

    def get_current_encoder_position(self) -> float:
        """
        Get current encoder position (hardware or simulation).

        Returns:
            Current position
        """
        if self.simulation_mode:
            return self.simulated_encoder_pos
        else:
            try:
                return self.odrv0.axis0.encoder.pos_estimate
            except (AttributeError, OSError) as e:
                print(f"\nError reading encoder position: {e}")
                # Return last known position
                return self.simulated_encoder_pos

    def send_motor_command(self, expected_pos: float) -> float:
        """
        Send motor command and update simulation.

        Args:
            expected_pos: Expected/commanded position

        Returns:
            Updated simulated position (or current position in hardware mode)
        """
        if self.simulation_mode:
            # Simulate 90% tracking
            self.simulated_encoder_pos += 0.9 * (expected_pos - self.simulated_encoder_pos)
            return self.simulated_encoder_pos
        else:
            # Hardware mode
            try:
                self.odrv0.axis0.controller.input_pos = expected_pos
                return self.odrv0.axis0.encoder.pos_estimate
            except (AttributeError, OSError) as e:
                print(f"\nError sending motor command: {e}")
                # Return last known position on error
                return self.simulated_encoder_pos

    def update_statistics(self, position_error: float):
        """
        Update error statistics.

        Args:
            position_error: Current position error
        """
        self.error_samples.append(position_error)
        if len(self.error_samples) > 100:
            self.error_samples.pop(0)

        self.max_position_error = max(self.max_position_error, abs(position_error))
        self.avg_position_error = np.mean([abs(e) for e in self.error_samples]) if self.error_samples else 0.0

    def check_hardware_errors(self) -> bool:
        """
        Check for hardware errors (hardware mode only).

        Returns:
            True if error detected, False otherwise
        """
        if not self.simulation_mode and self.odrv0.axis0.error != 0:
            print(f"Axis error: {self.odrv0.axis0.error}")
            return True
        return False

    def print_status(self, current_time: float, position_error: float,
                    music_complexity: float = 0.0):
        """
        Print real-time status.

        Args:
            current_time: Current time
            position_error: Current position error
            music_complexity: Current music complexity
        """
        mode_str = "[SIM] " if self.simulation_mode else ""
        lock_status = "🔒" if abs(self.avg_position_error) < self.phase_lock_threshold else "🔓"
        beat_indicator = "♪" if self.beat_locked else " "

        print(f"\r{mode_str}Time: {current_time:.2f}s | BPM: {self.bpm:.1f} {beat_indicator} | "
              f"RMS: {self.master_amplitude:.2f} | Complexity: {music_complexity:.2f} | "
              f"Pos Error: {position_error:+.3f} (avg: {self.avg_position_error:.3f}, "
              f"max: {self.max_position_error:.3f}) {lock_status} | "
              f"Phase: {self.phase_offset:.2f}", end="")

    def print_final_statistics(self):
        """Print final control loop statistics."""
        print("\n\n=== Synchronization Statistics ===")
        print(f"Maximum position error: {self.max_position_error:.4f}")
        print(f"Average position error: {self.avg_position_error:.4f}")
        print(f"Final phase offset: {self.phase_offset:.4f}")
        print("==================================\n")

    def reset_statistics(self):
        """Reset all statistics counters."""
        self.max_position_error = 0.0
        self.avg_position_error = 0.0
        self.error_samples = []
        self.phase_velocity_estimate = 0.0
        self.phase_error_history = []

    def is_simulation_mode(self) -> bool:
        """Check if running in simulation mode."""
        return self.simulation_mode

    def get_statistics(self) -> dict:
        """
        Get current statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            'max_position_error': self.max_position_error,
            'avg_position_error': self.avg_position_error,
            'phase_offset': self.phase_offset,
            'beat_locked': self.beat_locked,
            'simulated_encoder_pos': self.simulated_encoder_pos
        }