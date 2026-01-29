"""
Beat Tapper Module

Detects beat timing from manual taps and calculates phase offset.
"""

import time
import numpy as np
from collections import deque
from typing import Optional, Tuple


class BeatTapper:
    """
    Manages manual beat tapping and calculates phase offset for synchronization.
    """

    def __init__(self,
                 max_taps: int = 8,
                 min_taps: int = 3,
                 timeout: float = 1.5):
        """
        Initialize beat tapper.

        Args:
            max_taps: Maximum number of taps to store
            min_taps: Minimum taps needed to calculate BPM
            timeout: Time in seconds after last tap before processing
        """
        self.max_taps = max_taps
        self.min_taps = min_taps
        self.timeout = timeout

        self.tap_times = deque(maxlen=max_taps)
        self.detected_bpm = None
        self.detected_phase = None
        self.last_tap_time = None
        self.is_active = False

    def tap(self) -> dict:
        """
        Register a beat tap.

        Returns:
            Dictionary with tap information
        """
        current_time = time.time()
        self.tap_times.append(current_time)
        self.last_tap_time = current_time
        self.is_active = True

        tap_count = len(self.tap_times)

        return {
            'tap_count': tap_count,
            'timestamp': current_time,
            'can_calculate': tap_count >= self.min_taps
        }

    def should_process(self) -> bool:
        """
        Check if enough time has passed since last tap to process.

        Returns:
            True if should process taps
        """
        if not self.is_active or self.last_tap_time is None:
            return False

        time_since_last_tap = time.time() - self.last_tap_time
        return time_since_last_tap >= self.timeout

    def calculate_bpm_and_phase(self, music_start_time: float) -> Optional[Tuple[float, float]]:
        """
        Calculate BPM and phase offset from recorded taps.

        Args:
            music_start_time: The time when the music started playing

        Returns:
            Tuple of (bpm, phase_offset) or None if insufficient data
        """
        if len(self.tap_times) < self.min_taps:
            return None

        # Calculate intervals between taps
        intervals = []
        for i in range(1, len(self.tap_times)):
            interval = self.tap_times[i] - self.tap_times[i-1]
            intervals.append(interval)

        # Calculate average interval and BPM
        avg_interval = np.mean(intervals)
        std_interval = np.std(intervals)

        # Filter out outliers (taps that are more than 1.5 std devs away)
        filtered_intervals = [
            interval for interval in intervals
            if abs(interval - avg_interval) <= 1.5 * std_interval
        ]

        if len(filtered_intervals) < self.min_taps - 1:
            return None

        # Recalculate with filtered data
        avg_interval = np.mean(filtered_intervals)
        detected_bpm = 60.0 / avg_interval

        # Calculate phase offset
        # The phase offset is how much the music is "ahead" or "behind" the taps
        # We use the first tap as reference
        first_tap_time = self.tap_times[0]
        time_since_music_start = first_tap_time - music_start_time

        # Calculate what the phase should be at the first tap
        # Assuming taps are on the beat (phase = 0)
        frequency = detected_bpm / 60.0
        current_phase = (2 * np.pi * frequency * time_since_music_start) % (2 * np.pi)

        # Phase offset needed to align beat to tap
        # We want phase = 0 at tap time, so offset = -current_phase
        phase_offset = -current_phase  # Adjusting phase to be in [-180, 180] degrees
        if phase_offset > np.pi:
            phase_offset -= 2 * np.pi
        elif phase_offset < -np.pi:
            phase_offset += 2 * np.pi

        self.detected_bpm = detected_bpm
        self.detected_phase = phase_offset

        return (detected_bpm, phase_offset)

    def reset(self):
        """Reset all tapper state."""
        self.tap_times.clear()
        self.detected_bpm = None
        self.detected_phase = None
        self.last_tap_time = None
        self.is_active = False

    def get_status(self) -> dict:
        """
        Get current tapper status.

        Returns:
            Dictionary with current status
        """
        return {
            'is_active': self.is_active,
            'tap_count': len(self.tap_times),
            'detected_bpm': self.detected_bpm,
            'detected_phase': self.detected_phase,
            'can_calculate': len(self.tap_times) >= self.min_taps,
            'time_since_last_tap': time.time() - self.last_tap_time if self.last_tap_time else None
        }


class PhaseTransitioner:
    """
    Manages smooth phase transitions to minimize jerky movement.
    """

    def __init__(self, transition_duration: float = 4.0):
        """
        Initialize phase transitioner.

        Args:
            transition_duration: Duration of phase transition in seconds
        """
        self.transition_duration = transition_duration
        self.is_transitioning = False
        self.start_phase = 0.0
        self.target_phase = 0.0
        self.transition_start_time = None

    def start_transition(self, current_phase: float, target_phase: float, current_time: float):
        """
        Start a phase transition.

        Args:
            current_phase: Current phase offset
            target_phase: Target phase offset
            current_time: Current time in seconds
        """
        self.is_transitioning = True
        self.start_phase = current_phase
        self.target_phase = target_phase
        self.transition_start_time = current_time

    def get_phase(self, current_time: float, base_phase: float) -> float:
        """
        Get the current phase during transition.

        Args:
            current_time: Current time in seconds
            base_phase: Base phase offset (if not transitioning)

        Returns:
            Current phase offset with smooth transition
        """
        if not self.is_transitioning:
            return base_phase

        elapsed = current_time - self.transition_start_time
        progress = min(elapsed / self.transition_duration, 1.0)

        # Use smooth easing function (ease-in-out cubic)
        if progress < 0.5:
            eased_progress = 4 * progress ** 3
        else:
            eased_progress = 1 - pow(-2 * progress + 2, 3) / 2

        # Interpolate between start and target phase
        current_phase = self.start_phase + (self.target_phase - self.start_phase) * eased_progress

        # End transition when complete
        if progress >= 1.0:
            self.is_transitioning = False
            return self.target_phase

        return current_phase

    def is_active(self) -> bool:
        """Check if transition is active."""
        return self.is_transitioning

    def cancel(self):
        """Cancel ongoing transition."""
        self.is_transitioning = False
