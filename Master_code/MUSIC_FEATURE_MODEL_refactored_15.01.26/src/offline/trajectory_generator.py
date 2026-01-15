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

    def generate(self) -> np.ndarray:
        """
        Generate the complete motor trajectory.

        Returns:
            numpy array of shape (N, 2) where:
            - Column 0: timestamp in seconds
            - Column 1: motor position in turns (at motor shaft)
        """
        duration = self.features.duration
        resolution_s = self.config.resolution_ms / 1000.0

        # Create timestamps at specified resolution
        num_samples = int(duration / resolution_s) + 1
        timestamps = np.linspace(0, duration, num_samples)

        # Pre-allocate position array
        positions = np.zeros(num_samples)

        # Calculate frequency from BPM
        frequency = self.features.bpm / 60.0 if self.features.bpm > 0 else 1.0

        print(f"Generating trajectory: {num_samples} samples at {self.config.resolution_ms}ms resolution")
        print(f"  BPM: {self.features.bpm:.1f}, Frequency: {frequency:.3f} Hz")

        for i, t in enumerate(timestamps):
            # Interpolate features at time t
            rms = self._interpolate_feature(t, self.features.timestamps, self.features.rms)
            complexity = self._interpolate_feature(t, self.features.timestamps, self.features.complexity)

            # Calculate master amplitude from RMS (0-1 range, capped)
            master_amplitude = min(rms * 3.0, 1.0)

            # Calculate amplitude distribution based on complexity
            amplitude1, amplitude2 = self._calculate_amplitudes(complexity)

            # Calculate position using dual-sinusoid formula
            # Note: phase_offset is 0 for pre-computed trajectories
            # (sync is handled by latency calibration)
            pos1 = amplitude1 * math.sin(2 * math.pi * frequency * t)
            pos2 = amplitude2 * math.sin(2 * math.pi * (frequency / 2) * t)

            positions[i] = self.config.initial_offset + (pos1 + pos2) * master_amplitude

        # Stack into (N, 2) array
        trajectory = np.column_stack([timestamps, positions])

        print(f"  Position range: {positions.min():.2f} to {positions.max():.2f} turns")

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
    resolution_ms: float = 10.0
) -> np.ndarray:
    """
    Convenience function to generate a trajectory from features.

    Args:
        features: Extracted audio features
        max_amplitude: Maximum amplitude in motor turns
        gear_ratio: Gear ratio (motor:output)
        resolution_ms: Time resolution in milliseconds

    Returns:
        Trajectory array of shape (N, 2)
    """
    config = TrajectoryConfig(
        max_amplitude=max_amplitude,
        gear_ratio=gear_ratio,
        resolution_ms=resolution_ms
    )
    generator = TrajectoryGenerator(features, config)
    return generator.generate()


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
