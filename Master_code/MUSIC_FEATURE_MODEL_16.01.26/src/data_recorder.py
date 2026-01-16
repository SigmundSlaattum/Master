#!/usr/bin/env python3
"""
Data Recorder Module

Records position and amplitude data during motor control operation for later analysis.
"""

import time
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Optional
from collections import deque


class DataRecorder:
    """
    Records motor position and amplitude data for analysis and plotting.
    """

    def __init__(self, max_samples: int = 10000):
        """
        Initialize data recorder.

        Args:
            max_samples: Maximum number of samples to store (to prevent memory issues)
        """
        self.max_samples = max_samples
        self.recording = False
        self.start_time: Optional[float] = None

        # Data storage using deques for efficient append operations
        self.timestamps: deque = deque(maxlen=max_samples)
        self.user_amplitudes: deque = deque(maxlen=max_samples)
        self.original_positions: deque = deque(maxlen=max_samples)
        self.final_positions: deque = deque(maxlen=max_samples)

    def start_recording(self):
        """Start recording data."""
        self.recording = True
        self.start_time = time.time()
        self.clear()
        print("[Recorder] Started recording position and amplitude data")

    def stop_recording(self):
        """Stop recording data."""
        self.recording = False
        print(f"[Recorder] Stopped recording. Total samples: {len(self.timestamps)}")

    def clear(self):
        """Clear all recorded data."""
        self.timestamps.clear()
        self.user_amplitudes.clear()
        self.original_positions.clear()
        self.final_positions.clear()

    def record_sample(self, user_amplitude: float, original_position: float,
                      final_position: float):
        """
        Record a single data sample.

        Args:
            user_amplitude: User amplitude multiplier from remote control
            original_position: Original position before user amplitude modification
            final_position: Final position sent to motor
        """
        if not self.recording or self.start_time is None:
            return

        elapsed_time = time.time() - self.start_time

        self.timestamps.append(elapsed_time)
        self.user_amplitudes.append(user_amplitude)
        self.original_positions.append(original_position)
        self.final_positions.append(final_position)

    def get_sample_count(self) -> int:
        """
        Get number of recorded samples.

        Returns:
            int: Number of samples
        """
        return len(self.timestamps)

    def is_recording(self) -> bool:
        """
        Check if currently recording.

        Returns:
            bool: True if recording
        """
        return self.recording

    def export_data(self, filename: str):
        """
        Export recorded data to CSV file.

        Args:
            filename: Output filename
        """
        if len(self.timestamps) == 0:
            print("[Recorder] No data to export")
            return

        try:
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Time (s)', 'User Amplitude', 'Original Position', 'Final Position'])

                for i in range(len(self.timestamps)):
                    writer.writerow([
                        self.timestamps[i],
                        self.user_amplitudes[i],
                        self.original_positions[i],
                        self.final_positions[i]
                    ])

            print(f"[Recorder] Data exported to {filename}")
        except Exception as e:
            print(f"[Recorder] Error exporting data: {e}")

    def plot_data(self, save_filename: Optional[str] = None):
        """
        Plot recorded data with three subplots.

        Args:
            save_filename: Optional filename to save plot (if None, displays interactively)
        """
        if len(self.timestamps) == 0:
            print("[Recorder] No data to plot")
            return

        try:
            # Convert deques to numpy arrays for plotting
            times = np.array(self.timestamps)
            user_amps = np.array(self.user_amplitudes)
            orig_pos = np.array(self.original_positions)
            final_pos = np.array(self.final_positions)

            # Create figure with three subplots
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
            fig.suptitle('Motor Control Data Recording', fontsize=16, fontweight='bold')

            # Plot 1: User Amplitude
            ax1.plot(times, user_amps, 'b-', linewidth=1.5, label='User Amplitude')
            ax1.axhline(y=1.0, color='r', linestyle='--', linewidth=1, alpha=0.5, label='Baseline (1.0)')
            ax1.set_ylabel('User Amplitude', fontsize=12, fontweight='bold')
            ax1.grid(True, alpha=0.3)
            ax1.legend(loc='upper right')
            ax1.set_title('Remote Control Amplitude Multiplier', fontsize=11)

            # Plot 2: Original Position (before user modification)
            ax2.plot(times, orig_pos, 'g-', linewidth=1.5, label='Original Position')
            ax2.set_ylabel('Position (turns)', fontsize=12, fontweight='bold')
            ax2.grid(True, alpha=0.3)
            ax2.legend(loc='upper right')
            ax2.set_title('Original Position (Music-Based)', fontsize=11)

            # Plot 3: Final Position (after user modification)
            ax3.plot(times, final_pos, 'r-', linewidth=1.5, label='Final Position')
            ax3.set_ylabel('Position (turns)', fontsize=12, fontweight='bold')
            ax3.set_xlabel('Time (seconds)', fontsize=12, fontweight='bold')
            ax3.grid(True, alpha=0.3)
            ax3.legend(loc='upper right')
            ax3.set_title('Final Position Sent to Motor', fontsize=11)

            plt.tight_layout()

            if save_filename:
                plt.savefig(save_filename, dpi=300, bbox_inches='tight')
                print(f"[Recorder] Plot saved to {save_filename}")
            else:
                plt.show()

        except Exception as e:
            print(f"[Recorder] Error plotting data: {e}")

    def plot_combined(self, save_filename: Optional[str] = None):
        """
        Plot all data in a single plot for comparison.

        Args:
            save_filename: Optional filename to save plot (if None, displays interactively)
        """
        if len(self.timestamps) == 0:
            print("[Recorder] No data to plot")
            return

        try:
            # Convert deques to numpy arrays
            times = np.array(self.timestamps)
            user_amps = np.array(self.user_amplitudes)
            orig_pos = np.array(self.original_positions)
            final_pos = np.array(self.final_positions)

            # Create figure
            fig, ax = plt.subplots(figsize=(14, 8))
            fig.suptitle('Motor Control Data - Combined View', fontsize=16, fontweight='bold')

            # Create twin axis for amplitude
            ax2 = ax.twinx()

            # Plot positions on primary axis
            line1 = ax.plot(times, orig_pos, 'g-', linewidth=2, alpha=0.7, label='Original Position')
            line2 = ax.plot(times, final_pos, 'r-', linewidth=2, alpha=0.7, label='Final Position')

            # Plot amplitude on secondary axis
            line3 = ax2.plot(times, user_amps, 'b-', linewidth=2, label='User Amplitude')
            ax2.axhline(y=1.0, color='b', linestyle='--', linewidth=1, alpha=0.3)

            # Labels
            ax.set_xlabel('Time (seconds)', fontsize=12, fontweight='bold')
            ax.set_ylabel('Position (turns)', fontsize=12, fontweight='bold', color='black')
            ax2.set_ylabel('User Amplitude', fontsize=12, fontweight='bold', color='blue')

            # Combine legends
            lines = line1 + line2 + line3
            labels = [l.get_label() for l in lines]
            ax.legend(lines, labels, loc='upper left', fontsize=10)

            ax.grid(True, alpha=0.3)
            plt.tight_layout()

            if save_filename:
                plt.savefig(save_filename, dpi=300, bbox_inches='tight')
                print(f"[Recorder] Combined plot saved to {save_filename}")
            else:
                plt.show()

        except Exception as e:
            print(f"[Recorder] Error plotting combined data: {e}")

    def get_statistics(self) -> dict:
        """
        Calculate statistics from recorded data.

        Returns:
            dict: Statistics including min/max/mean values
        """
        if len(self.timestamps) == 0:
            return {}

        user_amps = np.array(self.user_amplitudes)
        orig_pos = np.array(self.original_positions)
        final_pos = np.array(self.final_positions)

        return {
            'sample_count': len(self.timestamps),
            'duration': self.timestamps[-1] - self.timestamps[0] if len(self.timestamps) > 1 else 0,
            'user_amplitude': {
                'min': float(np.min(user_amps)),
                'max': float(np.max(user_amps)),
                'mean': float(np.mean(user_amps)),
                'std': float(np.std(user_amps))
            },
            'original_position': {
                'min': float(np.min(orig_pos)),
                'max': float(np.max(orig_pos)),
                'mean': float(np.mean(orig_pos)),
                'std': float(np.std(orig_pos))
            },
            'final_position': {
                'min': float(np.min(final_pos)),
                'max': float(np.max(final_pos)),
                'mean': float(np.mean(final_pos)),
                'std': float(np.std(final_pos))
            }
        }
