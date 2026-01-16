"""
Trajectory Player

Provides O(1) lookup of pre-computed motor positions and velocities with linear interpolation.
This is the CPU-light component that runs in the real-time control loop.

Supports both legacy (N, 2) and new (N, 3) trajectory formats:
- Legacy: [timestamp, position]
- New: [timestamp, position, velocity] for feedforward control
"""

import numpy as np
from pathlib import Path
from typing import Optional, Tuple


class TrajectoryPlayer:
    """
    Fast trajectory lookup with linear interpolation.

    Loads a pre-computed trajectory and provides efficient position and
    velocity lookup at any timestamp. Designed for minimal CPU overhead
    in the real-time control loop.

    Supports velocity feedforward when trajectory includes velocity data.
    """

    def __init__(self, trajectory_path: str):
        """
        Initialize the trajectory player.

        Args:
            trajectory_path: Path to the trajectory .npy file
        """
        self.trajectory_path = Path(trajectory_path)

        if not self.trajectory_path.exists():
            raise FileNotFoundError(f"Trajectory not found: {trajectory_path}")

        # Load trajectory
        self.trajectory = np.load(str(self.trajectory_path))

        # Validate shape - support both (N, 2) legacy and (N, 3) with velocity
        if len(self.trajectory.shape) != 2:
            raise ValueError(f"Invalid trajectory shape: {self.trajectory.shape}")
        if self.trajectory.shape[1] < 2:
            raise ValueError(f"Trajectory must have at least 2 columns, got {self.trajectory.shape[1]}")

        # Extract timestamps and positions for fast lookup
        self.timestamps = self.trajectory[:, 0]
        self.positions = self.trajectory[:, 1]

        # Check for velocity data (new format with 3 columns)
        self.has_velocity = self.trajectory.shape[1] >= 3
        if self.has_velocity:
            self.velocities = self.trajectory[:, 2]
        else:
            self.velocities = None

        # Pre-compute time step for O(1) index calculation
        if len(self.timestamps) > 1:
            self.time_step = self.timestamps[1] - self.timestamps[0]
        else:
            self.time_step = 0.01  # Default 10ms

        self.duration = self.timestamps[-1]
        self.num_samples = len(self.timestamps)

        # Cache for last lookup (helps with interpolation)
        self._last_index = 0

    def get_position(self, timestamp: float, latency_offset: float = 0.0) -> float:
        """
        Get motor position at a given timestamp.

        This is the hot path called at 60Hz - optimized for speed.

        Args:
            timestamp: Current audio timestamp in seconds
            latency_offset: Additional offset for latency compensation (added to timestamp)

        Returns:
            Motor position in turns
        """
        # Apply latency offset (look ahead in time)
        t = timestamp + latency_offset

        # Boundary checks
        if t <= 0:
            return float(self.positions[0])
        if t >= self.duration:
            return float(self.positions[-1])

        # O(1) index calculation using known time step
        # This is faster than binary search for uniform spacing
        index_float = t / self.time_step
        index = int(index_float)

        # Clamp index
        if index >= self.num_samples - 1:
            return float(self.positions[-1])

        # Linear interpolation
        t0 = self.timestamps[index]
        t1 = self.timestamps[index + 1]
        p0 = self.positions[index]
        p1 = self.positions[index + 1]

        # Interpolation factor
        alpha = (t - t0) / (t1 - t0) if t1 != t0 else 0.0

        return float(p0 + alpha * (p1 - p0))

    def get_velocity(self, timestamp: float, latency_offset: float = 0.0) -> float:
        """
        Get motor velocity at a given timestamp (for feedforward control).

        This is the hot path called at 60Hz - optimized for speed.

        Args:
            timestamp: Current audio timestamp in seconds
            latency_offset: Additional offset for latency compensation

        Returns:
            Motor velocity in turns/second, or 0.0 if velocity data not available
        """
        if not self.has_velocity:
            return 0.0

        # Apply latency offset (look ahead in time)
        t = timestamp + latency_offset

        # Boundary checks
        if t <= 0:
            return float(self.velocities[0])
        if t >= self.duration:
            return float(self.velocities[-1])

        # O(1) index calculation using known time step
        index_float = t / self.time_step
        index = int(index_float)

        # Clamp index
        if index >= self.num_samples - 1:
            return float(self.velocities[-1])

        # Linear interpolation
        t0 = self.timestamps[index]
        t1 = self.timestamps[index + 1]
        v0 = self.velocities[index]
        v1 = self.velocities[index + 1]

        # Interpolation factor
        alpha = (t - t0) / (t1 - t0) if t1 != t0 else 0.0

        return float(v0 + alpha * (v1 - v0))

    def get_position_with_amplitude(
        self,
        timestamp: float,
        user_amplitude: float = 1.0,
        initial_offset: float = 0.0,
        latency_offset: float = 0.0
    ) -> float:
        """
        Get motor position with user amplitude applied.

        Args:
            timestamp: Current audio timestamp in seconds
            user_amplitude: User amplitude multiplier (typically 0-2)
            initial_offset: Motor's starting position (oscillation center)
            latency_offset: Latency compensation offset

        Returns:
            Motor position in turns
        """
        base_position = self.get_position(timestamp, latency_offset)

        # Trajectory stores positions relative to 0 (oscillating around 0)
        # Apply user amplitude to motion, then offset to motor's start position
        return initial_offset + base_position * user_amplitude

    def get_position_and_velocity(
        self,
        timestamp: float,
        user_amplitude: float = 1.0,
        initial_offset: float = 0.0,
        latency_offset: float = 0.0
    ) -> Tuple[float, float]:
        """
        Get motor position and velocity with user amplitude applied.

        This is the primary method for feedforward control - returns both
        position and velocity in a single call for efficiency.

        Args:
            timestamp: Current audio timestamp in seconds
            user_amplitude: User amplitude multiplier (typically 0-2)
            initial_offset: Motor's starting position (oscillation center)
            latency_offset: Latency compensation offset

        Returns:
            Tuple of (position, velocity) in turns and turns/second
        """
        base_position = self.get_position(timestamp, latency_offset)
        base_velocity = self.get_velocity(timestamp, latency_offset)

        # Apply user amplitude to both position and velocity
        # Position is offset to motor's start position
        # Velocity is scaled by amplitude (derivative scales linearly)
        position = initial_offset + base_position * user_amplitude
        velocity = base_velocity * user_amplitude

        return position, velocity

    def get_duration(self) -> float:
        """Get trajectory duration in seconds."""
        return self.duration

    def get_time_step(self) -> float:
        """Get time step between samples in seconds."""
        return self.time_step

    def get_position_range(self) -> tuple[float, float]:
        """Get (min, max) position range."""
        return float(self.positions.min()), float(self.positions.max())

    def get_sample_count(self) -> int:
        """Get total number of samples."""
        return self.num_samples

    def has_velocity_feedforward(self) -> bool:
        """Check if velocity feedforward data is available."""
        return self.has_velocity

    def get_velocity_range(self) -> tuple[float, float]:
        """Get (min, max) velocity range, or (0, 0) if no velocity data."""
        if not self.has_velocity:
            return 0.0, 0.0
        return float(self.velocities.min()), float(self.velocities.max())


def load_trajectory_player(trajectory_path: str) -> TrajectoryPlayer:
    """Create a TrajectoryPlayer instance."""
    return TrajectoryPlayer(trajectory_path)


if __name__ == "__main__":
    import sys
    import time

    if len(sys.argv) < 2:
        print("Usage: python trajectory_player.py <trajectory.npy>")
        sys.exit(1)

    trajectory_path = sys.argv[1]
    player = TrajectoryPlayer(trajectory_path)

    print(f"Trajectory: {trajectory_path}")
    print(f"Duration: {player.get_duration():.2f}s")
    print(f"Samples: {player.get_sample_count()}")
    print(f"Time step: {player.get_time_step()*1000:.1f}ms")
    print(f"Position range: {player.get_position_range()}")
    print(f"Velocity feedforward: {'enabled' if player.has_velocity_feedforward() else 'not available'}")
    if player.has_velocity_feedforward():
        print(f"Velocity range: {player.get_velocity_range()} turns/s")

    # Benchmark lookup speed
    print("\nBenchmarking 10000 lookups...")
    timestamps = np.random.uniform(0, player.get_duration(), 10000)

    start = time.perf_counter()
    for t in timestamps:
        _ = player.get_position(t)
    elapsed = time.perf_counter() - start

    avg_us = (elapsed / 10000) * 1_000_000
    print(f"Average position lookup time: {avg_us:.2f} μs")

    if player.has_velocity_feedforward():
        start = time.perf_counter()
        for t in timestamps:
            _ = player.get_position_and_velocity(t)
        elapsed = time.perf_counter() - start

        avg_us = (elapsed / 10000) * 1_000_000
        print(f"Average position+velocity lookup time: {avg_us:.2f} μs")
