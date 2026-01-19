#!/usr/bin/env python3
"""
delay_compensator.py

Implementation of delay estimation + PID feedback + feedforward lookup-table
synchronization as described in "Real-Time Dance Generation to Music for a Legged Robot"
(Bi et al., IROS 2018).

This module provides:
- LSE-based delay estimation between reference and actual signals
- PID + feedforward delay controller
- Dynamic lookup table for motion and tempo-specific delays
- Integration with music-synchronized motor control
"""

from __future__ import annotations
import numpy as np
import pickle
from typing import List, Tuple, Dict, Any, Optional
import argparse
import os
from collections import deque

try:
    import matplotlib.pyplot as plt
    from scipy import signal as scipy_signal
except ImportError:
    plt = None
    scipy_signal = None


# ----------------------------- DELAY ESTIMATOR -----------------------------

def estimate_delay_lse(
    reference: np.ndarray,
    actual: np.ndarray,
    fs: float,
    max_shift_s: float = 0.5
) -> Tuple[float, np.ndarray, np.ndarray]:
    """
    Estimate delay between reference and actual signals using Least Squares Error.

    The delay is found by shifting the actual signal relative to the reference
    and finding the time shift that minimizes the squared error.

    Args:
        reference: Reference (desired) signal
        actual: Actual (measured) signal
        fs: Sampling frequency in Hz
        max_shift_s: Maximum time shift to search in seconds

    Returns:
        Tuple of (delay_seconds, shift_times, lse_values)
    """
    if reference.shape != actual.shape:
        raise ValueError('reference and actual must have same shape')

    N = len(reference)
    max_shift_samples = int(round(max_shift_s * fs))
    shifts_samples = np.arange(-max_shift_samples, max_shift_samples + 1, dtype=int)
    lse_values = np.full(shifts_samples.shape, np.inf, dtype=float)

    for i, sh in enumerate(shifts_samples):
        if sh >= 0:
            if sh >= N:
                continue
            ref_seg = reference[0:N-sh]
            act_seg = actual[sh:N]
        else:
            s = -sh
            if s >= N:
                continue
            ref_seg = reference[s:N]
            act_seg = actual[0:N-s]

        lse_values[i] = np.mean((ref_seg - act_seg) ** 2)

    best_idx = int(np.argmin(lse_values))
    delay_seconds = shifts_samples[best_idx] / fs

    return delay_seconds, shifts_samples / fs, lse_values


# ----------------------------- DYNAMIC LOOKUP TABLE -----------------------------

class DynamicLookupTable:
    """
    Dynamic lookup table for motion-specific and tempo-specific feedforward delays.

    Stores successful delay corrections for each (motion, tempo) combination and
    uses a moving average to provide feedforward compensation.
    """

    def __init__(
        self,
        motions: List[str],
        bpm_min: int = 40,
        bpm_max: int = 200,
        bpm_resolution: int = 5,
        M: int = 8,
        persistence_file: Optional[str] = None
    ):
        """
        Initialize the lookup table.

        Args:
            motions: List of motion identifiers
            bpm_min: Minimum BPM value
            bpm_max: Maximum BPM value
            bpm_resolution: BPM bin resolution
            M: Number of samples to average for moving average
            persistence_file: Optional file path to save/load table state
        """
        self.motions = list(motions)
        self.motion_to_idx = {m: i for i, m in enumerate(self.motions)}
        self.bpm_min = bpm_min
        self.bpm_max = bpm_max
        self.res = bpm_resolution
        self.bins = np.arange(bpm_min, bpm_max + 1, bpm_resolution)
        self.M = M
        self.persistence_file = persistence_file

        # History stores last M successful corrections for each (motion, bpm_bin)
        self.history: Dict[Tuple[int, int], List[float]] = {
            (i, b): [] for i in range(len(motions)) for b in range(len(self.bins))
        }

        # Table stores the current feedforward value for each (motion, bpm_bin)
        self.table = np.zeros((len(motions), len(self.bins)))

        # Load from file if it exists
        if persistence_file and os.path.exists(persistence_file):
            self.load(persistence_file)

    def bpm_to_bin(self, bpm: float) -> int:
        """Convert BPM value to bin index."""
        if bpm <= self.bpm_min:
            return 0
        if bpm >= self.bpm_max:
            return len(self.bins) - 1
        idx = int((bpm - self.bpm_min) // self.res)
        return max(0, min(idx, len(self.bins) - 1))

    def read(self, motion_id: str, bpm: float) -> float:
        """
        Read feedforward delay for a given motion and BPM.

        Args:
            motion_id: Motion identifier
            bpm: Current tempo in BPM

        Returns:
            Feedforward delay in seconds
        """
        return self.table[self.motion_to_idx[motion_id], self.bpm_to_bin(bpm)]

    def update_if_success(
        self,
        motion_id: str,
        bpm: float,
        u0: float,
        delay: float,
        thresh: float = 0.075
    ) -> bool:
        """
        Update lookup table if delay is below threshold (successful sync).

        Args:
            motion_id: Motion identifier
            bpm: Current tempo in BPM
            u0: Control action that achieved this delay
            delay: Measured delay in seconds
            thresh: Threshold for "successful" synchronization

        Returns:
            True if update was performed, False otherwise
        """
        if abs(delay) > thresh:
            return False

        i = self.motion_to_idx[motion_id]
        b = self.bpm_to_bin(bpm)
        hist = self.history[(i, b)]

        hist.append(u0)
        if len(hist) > self.M:
            hist.pop(0)

        # Update table with moving average
        self.table[i, b] = np.mean(hist)

        return True

    def save(self, filepath: Optional[str] = None):
        """Save lookup table state to file."""
        filepath = filepath or self.persistence_file
        if not filepath:
            return

        state = {
            'table': self.table,
            'history': self.history,
            'motions': self.motions,
            'bpm_min': self.bpm_min,
            'bpm_max': self.bpm_max,
            'res': self.res
        }

        with open(filepath, 'wb') as f:
            pickle.dump(state, f)

    def load(self, filepath: str):
        """Load lookup table state from file."""
        if not os.path.exists(filepath):
            return

        with open(filepath, 'rb') as f:
            state = pickle.load(f)

        self.table = state['table']
        self.history = state['history']
        # Verify motions match
        if state['motions'] != self.motions:
            print(f"Warning: Loaded motions {state['motions']} don't match current {self.motions}")


# ----------------------------- DELAY COMPENSATOR -----------------------------

class DelayCompensator:
    """
    Combined PID + feedforward delay compensator for music-synchronized robot motion.

    Uses:
    - PID feedback control for reactive delay correction
    - Dynamic lookup table for proactive feedforward compensation
    - Integral windup protection
    """

    def __init__(
        self,
        motions: List[str],
        Kp: float = 2.0,
        Ki: float = 0.5,
        Kd: float = 0.1,
        integral_limit: float = 1.0,
        persistence_file: Optional[str] = None
    ):
        """
        Initialize delay compensator.

        Args:
            motions: List of motion identifiers
            Kp: Proportional gain
            Ki: Integral gain
            Kd: Derivative gain
            integral_limit: Maximum absolute value for integral term
            persistence_file: Optional file to persist lookup table
        """
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.integral_limit = integral_limit

        self.integral = 0.0
        self.prev_delay: Optional[float] = None
        self.lookup = DynamicLookupTable(motions, persistence_file=persistence_file)

        # History for diagnostics
        self.delay_history = deque(maxlen=100)
        self.control_history = deque(maxlen=100)

    def compute_control(
        self,
        motion_id: str,
        bpm: float,
        delay_est: float,
        beat_duration: float
    ) -> Tuple[float, float, float]:
        """
        Compute control action to compensate for delay.

        Args:
            motion_id: Current motion identifier
            bpm: Current tempo in BPM
            delay_est: Estimated delay in seconds (positive = robot is behind)
            beat_duration: Duration of current beat in seconds

        Returns:
            Tuple of (total_control, feedback_control, feedforward_control)
        """
        # Derivative term (rate of change of delay)
        d_err = 0.0 if self.prev_delay is None else (delay_est - self.prev_delay) / beat_duration

        # Integral term with anti-windup
        self.integral += delay_est * beat_duration
        self.integral = np.clip(self.integral, -self.integral_limit, self.integral_limit)

        # PID feedback control
        u_fb = self.Kp * delay_est + self.Ki * self.integral + self.Kd * d_err

        # Feedforward from lookup table
        u_ff = self.lookup.read(motion_id, bpm)

        # Total control action
        u_total = u_fb + u_ff

        # Update history
        self.prev_delay = delay_est
        self.delay_history.append(delay_est)
        self.control_history.append(u_total)

        return u_total, u_fb, u_ff

    def update_lookup_table(
        self,
        motion_id: str,
        bpm: float,
        control_action: float,
        resulting_delay: float
    ) -> bool:
        """
        Update lookup table if synchronization was successful.

        Args:
            motion_id: Motion identifier
            bpm: Current tempo in BPM
            control_action: Control action that was applied
            resulting_delay: Measured delay after applying control

        Returns:
            True if table was updated
        """
        # Only update with feedback component (not total control)
        # This prevents feedforward from reinforcing itself
        success = self.lookup.update_if_success(
            motion_id, bpm, control_action, resulting_delay
        )

        if success:
            # Reduce integral when we achieve good sync
            self.integral *= 0.5

        return success

    def reset(self):
        """Reset controller state (but preserve lookup table)."""
        self.integral = 0.0
        self.prev_delay = None
        self.delay_history.clear()
        self.control_history.clear()

    def save_state(self):
        """Save lookup table to persistent storage."""
        self.lookup.save()

    def get_statistics(self) -> Dict[str, float]:
        """Get diagnostic statistics."""
        if len(self.delay_history) == 0:
            return {}

        delays = np.array(self.delay_history)
        controls = np.array(self.control_history)

        return {
            'mean_delay': float(np.mean(np.abs(delays))),
            'max_delay': float(np.max(np.abs(delays))),
            'std_delay': float(np.std(delays)),
            'mean_control': float(np.mean(np.abs(controls))),
            'integral_term': self.integral
        }


# ----------------------------- SIGNAL GENERATOR FOR DEMO -----------------------------

def generate_reference_signal(
    duration: float,
    bpm: float,
    amplitude: float,
    fs: float,
    complexity: float = 0.0
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate a beat-synchronized reference signal similar to robot motion.

    Args:
        duration: Signal duration in seconds
        bpm: Tempo in beats per minute
        amplitude: Signal amplitude
        fs: Sampling frequency in Hz
        complexity: 0-1 value for adding harmonics

    Returns:
        Tuple of (time_array, signal_array)
    """
    t = np.arange(0, duration, 1/fs)
    frequency = bpm / 60.0

    # Primary sine wave at beat frequency
    signal = amplitude * np.sin(2 * np.pi * frequency * t)

    # Add complexity (harmonics)
    if complexity > 0:
        signal += complexity * amplitude * 0.5 * np.sin(2 * np.pi * frequency * 2 * t)

    return t, signal


def simulate_actual_signal(
    reference: np.ndarray,
    delay_seconds: float,
    fs: float,
    noise_level: float = 0.002,
    damping: float = 0.1
) -> np.ndarray:
    """
    Simulate actual robot response with delay, filtering, and noise.

    Args:
        reference: Reference signal
        delay_seconds: Time delay in seconds
        fs: Sampling frequency in Hz
        noise_level: Noise standard deviation
        damping: Low-pass filter strength (0-1)

    Returns:
        Simulated actual signal
    """
    delay_seconds = max(0.0, min(0.5, delay_seconds))
    delay_samples = int(round(delay_seconds * fs))
    delay_samples = max(0, min(delay_samples, len(reference) - 1))

    # Apply delay
    actual = np.zeros_like(reference)
    actual[delay_samples:] = reference[:len(reference) - delay_samples]

    # Apply low-pass filter (simulates motor dynamics)
    if scipy_signal is not None:
        b, a = scipy_signal.butter(2, 5 / (0.5 * fs))
        actual = scipy_signal.filtfilt(b, a, actual)

    # Add noise
    actual += np.random.normal(0, noise_level, len(actual))

    return actual


# ----------------------------- DEMO -----------------------------

def run_demo(duration: float = 30.0, seed: int = 1, show_plot: bool = True):
    """
    Demonstrate delay compensation with simulated music tempo changes.

    Args:
        duration: Simulation duration in seconds
        seed: Random seed for reproducibility
        show_plot: Whether to display plots
    """
    if show_plot and plt is None:
        print("Warning: matplotlib not available, disabling plots")
        show_plot = False

    if scipy_signal is None:
        print("Warning: scipy not available, using simplified signal processing")

    np.random.seed(seed)

    # Simulation parameters
    fs = 400.0  # Sampling rate in Hz
    t = np.arange(0, duration, 1/fs)

    # Create tempo sequence with changes
    bpm_sequence = np.where(t < 10, 60, np.where(t < 20, 120, 90))

    # Generate reference signal
    omega_inst = 2 * np.pi * bpm_sequence / 60
    reference = 0.03 * np.sin(np.cumsum(omega_inst / fs))

    # Initialize delay compensator
    dc = DelayCompensator(
        motions=['side_to_side'],
        Kp=1.5,
        Ki=0.3,
        Kd=0.1
    )

    # Simulation state
    true_delay = 0.2  # Initial delay in seconds
    actual = simulate_actual_signal(reference, true_delay, fs)

    # Storage for results
    delays_est = []
    controls = []
    true_delays = []
    beat_times = []

    # Simulate beat-by-beat compensation
    current_time = 0
    while current_time < duration:
        beat_times.append(current_time)

        # Get current BPM
        idx = int(current_time * fs)
        if idx >= len(bpm_sequence):
            break

        current_bpm = bpm_sequence[idx]
        beat_duration = 60.0 / current_bpm

        # Extract segment for this beat
        segment_samples = int(beat_duration * fs)
        if idx + segment_samples > len(reference):
            break

        ref_segment = reference[idx:idx + segment_samples]
        act_segment = actual[idx:idx + segment_samples]

        # Estimate delay
        delay_est, _, _ = estimate_delay_lse(ref_segment, act_segment, fs)

        # Compute control action
        u_total, u_fb, u_ff = dc.compute_control(
            'side_to_side', current_bpm, delay_est, beat_duration
        )

        # Apply control (reduce true delay)
        # In real system, this would shift the next motion's start time
        true_delay = max(0.0, min(0.5, true_delay - 0.8 * u_total))

        # Update actual signal for next beat
        actual = simulate_actual_signal(reference, true_delay, fs)

        # Update lookup table
        dc.update_lookup_table('side_to_side', current_bpm, u_total, delay_est)

        # Store results
        delays_est.append(delay_est)
        controls.append(u_total)
        true_delays.append(true_delay)

        # Move to next beat
        current_time += beat_duration

    # Print statistics
    stats = dc.get_statistics()
    print("\n=== Delay Compensation Demo Results ===")
    print(f"Mean absolute delay: {stats['mean_delay']:.4f} s")
    print(f"Max absolute delay: {stats['max_delay']:.4f} s")
    print(f"Std deviation: {stats['std_delay']:.4f} s")
    print(f"Final true delay: {true_delays[-1]:.4f} s")
    print("=" * 40)

    # Plot results
    if show_plot:
        fig, axes = plt.subplots(3, 1, figsize=(12, 8))

        # Ensure all arrays have the same length
        n_points = min(len(beat_times) - 1, len(delays_est), len(true_delays))
        plot_beat_times = beat_times[:n_points]
        plot_delays_est = delays_est[:n_points]
        plot_true_delays = true_delays[:n_points]
        plot_controls = controls[:n_points]

        # Plot delays
        axes[0].plot(plot_beat_times, plot_delays_est, 'b-', label='Estimated Delay', linewidth=2)
        axes[0].plot(plot_beat_times, plot_true_delays, 'r--', label='True Delay', linewidth=2)
        axes[0].axhline(y=0, color='k', linestyle=':', alpha=0.3)
        axes[0].axhline(y=0.075, color='g', linestyle='--', alpha=0.5, label='Sync Threshold')
        axes[0].axhline(y=-0.075, color='g', linestyle='--', alpha=0.5)
        axes[0].set_ylabel('Delay (s)')
        axes[0].set_title('Delay Estimation and True Delay')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        # Plot control actions
        axes[1].plot(plot_beat_times, plot_controls, 'g-', linewidth=2)
        axes[1].axhline(y=0, color='k', linestyle=':', alpha=0.3)
        axes[1].set_ylabel('Control Action (s)')
        axes[1].set_title('Delay Compensation Control')
        axes[1].grid(True, alpha=0.3)

        # Plot BPM
        bpm_at_beats = [bpm_sequence[int(bt * fs)] if int(bt * fs) < len(bpm_sequence) else 90
                        for bt in plot_beat_times]
        axes[2].plot(plot_beat_times, bpm_at_beats, 'm-', linewidth=2)
        axes[2].set_ylabel('BPM')
        axes[2].set_xlabel('Time (s)')
        axes[2].set_title('Music Tempo')
        axes[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()

    return delays_est, controls, true_delays


# ----------------------------- CLI -----------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delay compensator for music-synchronized robot control"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demonstration with simulated delays"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="Demo duration in seconds (default: 30.0)"
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Disable plotting in demo mode"
    )

    args = parser.parse_args()

    if args.demo:
        print("Running delay compensation demo...")
        run_demo(duration=args.duration, show_plot=not args.no_plot)
    else:
        print("Delay compensator module loaded.")
        print("Use --demo flag to run demonstration.")
        print("\nExample usage in code:")
        print("  from delay_compensator import DelayCompensator, estimate_delay_lse")
        print("  dc = DelayCompensator(motions=['motion1', 'motion2'])")
        print("  delay = estimate_delay_lse(reference, actual, sampling_rate)")
        print("  control, fb, ff = dc.compute_control('motion1', 120, delay, 0.5)")
