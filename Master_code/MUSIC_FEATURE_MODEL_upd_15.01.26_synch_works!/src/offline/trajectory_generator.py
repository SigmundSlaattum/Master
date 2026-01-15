"""
Trajectory Generator

Generates pre-computed motor trajectories from extracted audio features.
The trajectory is a time-indexed array of motor positions that can be
looked up during playback with minimal CPU overhead.
"""

import numpy as np
import math
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from .feature_extractor import FeatureData


@dataclass
class TrajectoryConfig:
    """Configuration for trajectory generation."""
    # Motor parameters
    max_amplitude: float = 7.5      # Maximum amplitude in motor turns (at motor shaft)
    gear_ratio: float = 15.0        # Gear ratio (motor turns : output turns)
    initial_offset: float = 0.0     # Initial position offset

    # Trajectory parameters
    resolution_ms: float = 10.0     # Time resolution in milliseconds


class TrajectoryGenerator:
    """
    Generates motor trajectory from audio features.

    The trajectory uses a dual-sinusoid formula:
    - Primary sinusoid at BPM frequency
    - Secondary sinusoid at BPM/2 frequency (harmonic)

    Amplitude distribution is controlled by music complexity:
    - Simple music (low complexity): primarily single sinusoid
    - Complex music (high complexity): both sinusoids active
    """

    def __init__(self, features: FeatureData, config: Optional[TrajectoryConfig] = None):
        """
        Initialize the trajectory generator.

        Args:
            features: Extracted audio features
            config: Trajectory configuration (uses defaults if None)
        """
        self.features = features
        self.config = config or TrajectoryConfig()

    def generate(self, dynamic_tempo: bool = False) -> np.ndarray:
        """
        Generate the complete motor trajectory with analytical velocity.

        Args:
            dynamic_tempo: If True, use time-varying local tempo instead of fixed BPM

        Returns:
            numpy array of shape (N, 3) where:
            - Column 0: timestamp in seconds
            - Column 1: motor position in turns (at motor shaft)
            - Column 2: motor velocity in turns/second (analytical feedforward)
        """
        if dynamic_tempo:
            return self._generate_dynamic()
        else:
            return self._generate_fixed()

    def _generate_fixed(self) -> np.ndarray:
        """Generate trajectory using fixed global BPM."""
        duration = self.features.duration
        resolution_s = self.config.resolution_ms / 1000.0

        # Create timestamps at specified resolution
        num_samples = int(duration / resolution_s) + 1
        timestamps = np.linspace(0, duration, num_samples)

        # Pre-allocate position and velocity arrays
        positions = np.zeros(num_samples)
        velocities = np.zeros(num_samples)

        # Calculate frequency from BPM
        frequency = self.features.bpm / 60.0 if self.features.bpm > 0 else 1.0

        # Angular frequencies for velocity calculation
        omega1 = 2 * math.pi * frequency        # Primary frequency (rad/s)
        omega2 = 2 * math.pi * (frequency / 2)  # Secondary frequency (rad/s)

        print(f"Generating FIXED tempo trajectory: {num_samples} samples at {self.config.resolution_ms}ms resolution")
        print(f"  BPM: {self.features.bpm:.1f}, Frequency: {frequency:.3f} Hz")
        print(f"  Velocity feedforward: enabled (analytical)")

        for i, t in enumerate(timestamps):
            # Interpolate features at time t
            rms = self._interpolate_feature(t, self.features.timestamps, self.features.rms)
            complexity = self._interpolate_feature(t, self.features.timestamps, self.features.complexity)

            # Calculate master amplitude from RMS (0-1 range, capped)
            master_amplitude = min(rms * 3.0, 1.0)

            # Calculate amplitude distribution based on complexity
            amplitude1, amplitude2 = self._calculate_amplitudes(complexity)

            # Calculate position using dual-sinusoid formula
            # position(t) = A1*sin(ω1*t) + A2*sin(ω2*t)
            pos1 = amplitude1 * math.sin(omega1 * t)
            pos2 = amplitude2 * math.sin(omega2 * t)
            positions[i] = self.config.initial_offset + (pos1 + pos2) * master_amplitude

            # Calculate analytical velocity (derivative of position)
            # velocity(t) = d/dt[position(t)]
            #             = A1*ω1*cos(ω1*t) + A2*ω2*cos(ω2*t)
            # Note: master_amplitude changes slowly, so we treat it as constant for derivative
            vel1 = amplitude1 * omega1 * math.cos(omega1 * t)
            vel2 = amplitude2 * omega2 * math.cos(omega2 * t)
            velocities[i] = (vel1 + vel2) * master_amplitude

        # Stack into (N, 3) array: [time, position, velocity]
        trajectory = np.column_stack([timestamps, positions, velocities])

        print(f"  Position range: {positions.min():.2f} to {positions.max():.2f} turns")
        print(f"  Velocity range: {velocities.min():.2f} to {velocities.max():.2f} turns/s")

        return trajectory

    def _generate_dynamic(self) -> np.ndarray:
        """
        Generate trajectory using time-varying local tempo.

        Uses cumulative phase integration to smoothly track tempo changes:
        - φ(t) = ∫₀ᵗ ω(τ) dτ  where ω(τ) = 2π × local_tempo(τ)/60
        - position(t) = A₁·sin(φ₁(t)) + A₂·sin(φ₂(t))
        - velocity(t) = A₁·ω₁(t)·cos(φ₁(t)) + A₂·ω₂(t)·cos(φ₂(t))
        """
        duration = self.features.duration
        resolution_s = self.config.resolution_ms / 1000.0

        # Create timestamps at specified resolution
        num_samples = int(duration / resolution_s) + 1
        timestamps = np.linspace(0, duration, num_samples)

        # Pre-allocate arrays
        positions = np.zeros(num_samples)
        velocities = np.zeros(num_samples)
        phase1 = np.zeros(num_samples)  # Cumulative phase for primary frequency
        phase2 = np.zeros(num_samples)  # Cumulative phase for harmonic frequency

        # Get local tempo at trajectory timestamps (interpolate from feature timestamps)
        local_tempo = np.interp(timestamps, self.features.timestamps, self.features.local_tempo)

        # Convert local tempo to instantaneous angular frequencies
        # ω(t) = 2π × BPM(t) / 60
        omega1_array = 2 * math.pi * local_tempo / 60.0        # Primary frequency
        omega2_array = omega1_array / 2.0                       # Harmonic at half frequency

        # Compute cumulative phase using trapezoidal integration
        # φ(t) = ∫₀ᵗ ω(τ) dτ
        for i in range(1, num_samples):
            dt = timestamps[i] - timestamps[i-1]
            # Trapezoidal rule: (ω[i-1] + ω[i]) / 2 × dt
            phase1[i] = phase1[i-1] + (omega1_array[i-1] + omega1_array[i]) / 2.0 * dt
            phase2[i] = phase2[i-1] + (omega2_array[i-1] + omega2_array[i]) / 2.0 * dt

        avg_bpm = np.mean(local_tempo)
        tempo_range = local_tempo.max() - local_tempo.min()
        print(f"Generating DYNAMIC tempo trajectory: {num_samples} samples at {self.config.resolution_ms}ms resolution")
        print(f"  Local tempo range: {local_tempo.min():.1f} - {local_tempo.max():.1f} BPM (avg: {avg_bpm:.1f})")
        print(f"  Tempo variance: {tempo_range:.1f} BPM")
        print(f"  Velocity feedforward: enabled (analytical with local ω)")

        for i, t in enumerate(timestamps):
            # Interpolate features at time t
            rms = self._interpolate_feature(t, self.features.timestamps, self.features.rms)
            complexity = self._interpolate_feature(t, self.features.timestamps, self.features.complexity)

            # Calculate master amplitude from RMS (0-1 range, capped)
            master_amplitude = min(rms * 3.0, 1.0)

            # Calculate amplitude distribution based on complexity
            amplitude1, amplitude2 = self._calculate_amplitudes(complexity)

            # Calculate position using dual-sinusoid formula with cumulative phase
            # position(t) = A1*sin(φ1(t)) + A2*sin(φ2(t))
            pos1 = amplitude1 * math.sin(phase1[i])
            pos2 = amplitude2 * math.sin(phase2[i])
            positions[i] = self.config.initial_offset + (pos1 + pos2) * master_amplitude

            # Calculate analytical velocity with instantaneous frequency
            # velocity(t) = A1*ω1(t)*cos(φ1(t)) + A2*ω2(t)*cos(φ2(t))
            vel1 = amplitude1 * omega1_array[i] * math.cos(phase1[i])
            vel2 = amplitude2 * omega2_array[i] * math.cos(phase2[i])
            velocities[i] = (vel1 + vel2) * master_amplitude

        # Stack into (N, 3) array: [time, position, velocity]
        trajectory = np.column_stack([timestamps, positions, velocities])

        print(f"  Position range: {positions.min():.2f} to {positions.max():.2f} turns")
        print(f"  Velocity range: {velocities.min():.2f} to {velocities.max():.2f} turns/s")

        return trajectory

    def _calculate_amplitudes(self, complexity: float) -> tuple[float, float]:
        """
        Calculate amplitude1 and amplitude2 based on complexity.

        Args:
            complexity: Music complexity (0-1)
                0 = simple (single sinusoid dominates)
                1 = complex (both sinusoids active)

        Returns:
            (amplitude1, amplitude2) tuple
        """
        # Clamp complexity to valid range
        complexity = max(0.0, min(1.0, complexity))

        # amplitude1 decreases with complexity (primary frequency)
        # amplitude2 increases with complexity (harmonic frequency)
        amplitude1 = self.config.max_amplitude * (1.0 - complexity * 0.5)
        amplitude2 = self.config.max_amplitude * complexity

        return amplitude1, amplitude2

    def _interpolate_feature(self, t: float, timestamps: np.ndarray, values: np.ndarray) -> float:
        """
        Interpolate a feature value at time t.

        Args:
            t: Time in seconds
            timestamps: Feature timestamps
            values: Feature values

        Returns:
            Interpolated value at time t
        """
        if len(timestamps) == 0:
            return 0.0

        # Handle boundary cases
        if t <= timestamps[0]:
            return float(values[0])
        if t >= timestamps[-1]:
            return float(values[-1])

        # Linear interpolation
        return float(np.interp(t, timestamps, values))


def generate_trajectory(
    features: FeatureData,
    max_amplitude: float = 7.5,
    gear_ratio: float = 15.0,
    resolution_ms: float = 10.0,
    dynamic_tempo: bool = False
) -> np.ndarray:
    """
    Convenience function to generate a trajectory from features.

    Args:
        features: Extracted audio features
        max_amplitude: Maximum amplitude in motor turns
        gear_ratio: Gear ratio (motor:output)
        resolution_ms: Time resolution in milliseconds
        dynamic_tempo: If True, use time-varying local tempo instead of fixed BPM

    Returns:
        Trajectory array of shape (N, 3) with [time, position, velocity]
    """
    config = TrajectoryConfig(
        max_amplitude=max_amplitude,
        gear_ratio=gear_ratio,
        resolution_ms=resolution_ms
    )
    generator = TrajectoryGenerator(features, config)
    return generator.generate(dynamic_tempo=dynamic_tempo)


def save_trajectory(trajectory: np.ndarray, path: str) -> None:
    """Save trajectory to a numpy file."""
    np.save(path, trajectory)
    print(f"Saved trajectory to: {path}")


def load_trajectory(path: str) -> np.ndarray:
    """Load trajectory from a numpy file."""
    return np.load(path)


if __name__ == "__main__":
    import sys
    from .feature_extractor import extract_features

    if len(sys.argv) < 2:
        print("Usage: python trajectory_generator.py <audio_file> [output.npy]")
        sys.exit(1)

    audio_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "trajectory.npy"

    # Extract features
    features = extract_features(audio_path)

    # Generate trajectory
    trajectory = generate_trajectory(features)

    # Save
    save_trajectory(trajectory, output_path)

    print(f"\nTrajectory generated:")
    print(f"  Samples: {len(trajectory)}")
    print(f"  Duration: {trajectory[-1, 0]:.2f}s")
    print(f"  Position range: {trajectory[:, 1].min():.2f} to {trajectory[:, 1].max():.2f}")
    if trajectory.shape[1] >= 3:
        print(f"  Velocity range: {trajectory[:, 2].min():.2f} to {trajectory[:, 2].max():.2f} turns/s")
