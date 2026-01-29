#!/usr/bin/env python3
"""
Data Recorder Module

Records position and amplitude data during motor control operation for later analysis.
"""

import time
import numpy as np

# Use non-interactive backend for server compatibility
import matplotlib
matplotlib.use('Agg')
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
        self.actual_positions: deque = deque(maxlen=max_samples)  # Encoder feedback

        # Music metadata for synchronization analysis
        self.bpm: float = 120.0  # Default BPM
        self.initial_motor_offset: float = 0.0  # Motor position at start

    def start_recording(self, bpm: float = 120.0, initial_motor_offset: float = 0.0):
        """
        Start recording data.

        Args:
            bpm: Song BPM for music frequency reference
            initial_motor_offset: Motor position at recording start (for centering)
        """
        self.recording = True
        self.start_time = time.time()
        self.bpm = bpm
        self.initial_motor_offset = initial_motor_offset
        self.clear()
        print(f"[Recorder] Started recording (BPM: {bpm:.1f})")

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
        self.actual_positions.clear()

    def record_sample(self, user_amplitude: float, original_position: float,
                      final_position: float, actual_position: float = None):
        """
        Record a single data sample.

        Args:
            user_amplitude: User amplitude multiplier from remote control
            original_position: Original position before user amplitude modification
            final_position: Final position sent to motor (target)
            actual_position: Actual position from encoder feedback (optional)
        """
        if not self.recording or self.start_time is None:
            return

        elapsed_time = time.time() - self.start_time

        self.timestamps.append(elapsed_time)
        self.user_amplitudes.append(user_amplitude)
        self.original_positions.append(original_position)
        self.final_positions.append(final_position)
        # Use target position as fallback if actual not provided
        self.actual_positions.append(actual_position if actual_position is not None else final_position)

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
                writer.writerow(['Time (s)', 'User Amplitude', 'Original Position', 'Final Position', 'Actual Position'])

                for i in range(len(self.timestamps)):
                    writer.writerow([
                        self.timestamps[i],
                        self.user_amplitudes[i],
                        self.original_positions[i],
                        self.final_positions[i],
                        self.actual_positions[i] if i < len(self.actual_positions) else self.final_positions[i]
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
                plt.close(fig)  # Close figure to free memory
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
                plt.close(fig)  # Close figure to free memory
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
        actual_pos = np.array(self.actual_positions) if len(self.actual_positions) > 0 else final_pos

        # Calculate position error (target - actual)
        position_error = final_pos - actual_pos[:len(final_pos)]

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
            },
            'actual_position': {
                'min': float(np.min(actual_pos)),
                'max': float(np.max(actual_pos)),
                'mean': float(np.mean(actual_pos)),
                'std': float(np.std(actual_pos))
            },
            'position_error': {
                'min': float(np.min(position_error)),
                'max': float(np.max(position_error)),
                'mean': float(np.mean(position_error)),
                'rms': float(np.sqrt(np.mean(position_error**2)))
            }
        }

    def plot_synchronization(self, save_filename: Optional[str] = None,
                             song_name: str = "", pattern_type: str = ""):
        """
        Plot synchronization between music frequency (as sinusoid) and actual motor position.

        Creates a plot showing:
        - Music frequency as a sinusoid derived from BPM
        - Actual motor position from encoder feedback
        - Phase difference and synchronization quality metrics

        Args:
            save_filename: Optional filename to save plot (if None, displays interactively)
            song_name: Song name for the plot title
            pattern_type: Pattern type (simple/complex) for the plot title
        """
        if len(self.timestamps) == 0:
            print("[Recorder] No data to plot")
            return

        try:
            # Convert deques to numpy arrays
            times = np.array(self.timestamps)
            actual_pos = np.array(self.actual_positions) if len(self.actual_positions) > 0 else np.array(self.final_positions)

            # Ensure arrays are same length
            min_len = min(len(times), len(actual_pos))
            times = times[:min_len]
            actual_pos = actual_pos[:min_len]

            # Center the actual position around zero (remove initial offset)
            actual_centered = actual_pos - self.initial_motor_offset

            # Generate music frequency sinusoid from BPM
            # frequency = BPM / 60 (beats per second)
            music_freq = self.bpm / 60.0
            omega = 2 * np.pi * music_freq  # angular frequency

            # Scale the music sinusoid to match the amplitude of actual movement
            actual_amplitude = (np.max(actual_centered) - np.min(actual_centered)) / 2
            if actual_amplitude < 0.01:
                actual_amplitude = 1.0  # Fallback if no movement

            # Generate music reference sinusoid (centered at 0)
            music_sinusoid = actual_amplitude * np.sin(omega * times)

            # Calculate phase offset using cross-correlation (find best alignment)
            # This tells us how much the motor lags/leads the music
            correlation_full = np.correlate(actual_centered - np.mean(actual_centered),
                                           music_sinusoid - np.mean(music_sinusoid), mode='full')
            # Find the lag that maximizes correlation
            lag_samples = np.argmax(correlation_full) - (len(actual_centered) - 1)
            if len(times) > 1:
                dt = times[1] - times[0]
                phase_lag_ms = lag_samples * dt * 1000  # Convert to milliseconds
            else:
                phase_lag_ms = 0

            # Calculate synchronization metrics
            # Correlation coefficient (shape similarity, phase-independent)
            if np.std(music_sinusoid) > 0 and np.std(actual_centered) > 0:
                correlation = np.corrcoef(music_sinusoid, actual_centered)[0, 1]
            else:
                correlation = 0.0

            # RMS difference (amplitude and phase dependent)
            rms_diff = np.sqrt(np.mean((music_sinusoid - actual_centered)**2))

            # Amplitude ratio
            music_amplitude = actual_amplitude  # We scaled to match, so ratio is based on original
            amplitude_ratio = actual_amplitude / music_amplitude if music_amplitude > 0 else 1.0

            # Create figure with 2 subplots
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10),
                                           gridspec_kw={'height_ratios': [3, 1]})

            # Title with song info
            title = 'Music-Motor Synchronization Analysis'
            if song_name:
                title = f'{song_name}'
                if pattern_type:
                    title += f' - {pattern_type.upper()}'
            fig.suptitle(title, fontsize=16, fontweight='bold')

            # Plot 1: Music Sinusoid vs Actual Position
            ax1.plot(times, music_sinusoid, 'b-', linewidth=2, label=f'Music Beat ({self.bpm:.0f} BPM)', alpha=0.7)
            ax1.plot(times, actual_centered, 'r-', linewidth=1.5, label='Actual Motor Position', alpha=0.8)
            ax1.axhline(y=0, color='k', linestyle='-', linewidth=0.5, alpha=0.3)
            ax1.set_ylabel('Position (turns, centered)', fontsize=12, fontweight='bold')
            ax1.set_title('Music Frequency vs Actual Motor Movement', fontsize=11)
            ax1.grid(True, alpha=0.3)
            ax1.legend(loc='upper right', fontsize=10)

            # Add metrics text box
            metrics_text = (f'BPM: {self.bpm:.1f} ({music_freq:.2f} Hz)\n'
                          f'Phase Lag: {phase_lag_ms:.1f} ms\n'
                          f'Correlation: {correlation:.4f}\n'
                          f'RMS Diff: {rms_diff:.4f} turns')
            props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
            ax1.text(0.02, 0.98, metrics_text, transform=ax1.transAxes, fontsize=10,
                    verticalalignment='top', bbox=props, family='monospace')

            # Plot 2: Instantaneous difference
            difference = music_sinusoid - actual_centered
            ax2.plot(times, difference, 'g-', linewidth=1.0, label='Difference (Music - Actual)')
            ax2.axhline(y=0, color='k', linestyle='-', linewidth=0.5, alpha=0.5)
            ax2.axhline(y=rms_diff, color='r', linestyle='--', linewidth=1, alpha=0.5, label=f'RMS ({rms_diff:.4f})')
            ax2.axhline(y=-rms_diff, color='r', linestyle='--', linewidth=1, alpha=0.5)
            ax2.fill_between(times, -rms_diff, rms_diff, alpha=0.1, color='red')
            ax2.set_ylabel('Difference (turns)', fontsize=12, fontweight='bold')
            ax2.set_xlabel('Time (seconds)', fontsize=12, fontweight='bold')
            ax2.set_title('Instantaneous Difference (Music - Motor)', fontsize=11)
            ax2.grid(True, alpha=0.3)
            ax2.legend(loc='upper right', fontsize=10)

            plt.tight_layout()

            if save_filename:
                plt.savefig(save_filename, dpi=300, bbox_inches='tight')
                plt.close(fig)  # Close figure to free memory
                print(f"[Recorder] Synchronization plot saved to {save_filename}")
            else:
                plt.show()

        except Exception as e:
            print(f"[Recorder] Error plotting synchronization data: {e}")

    def export_sync_data(self, filename: str, song_name: str = "", pattern_type: str = ""):
        """
        Export synchronization data to CSV file with music sinusoid and metrics.

        Args:
            filename: Output filename
            song_name: Song name for metadata
            pattern_type: Pattern type for metadata
        """
        if len(self.timestamps) == 0:
            print("[Recorder] No data to export")
            return

        try:
            import csv

            # Convert to arrays for calculations
            times = np.array(self.timestamps)
            actual_pos = np.array(self.actual_positions) if len(self.actual_positions) > 0 else np.array(self.final_positions)

            # Ensure same length
            min_len = min(len(times), len(actual_pos))
            times = times[:min_len]
            actual_pos = actual_pos[:min_len]

            # Center the actual position
            actual_centered = actual_pos - self.initial_motor_offset

            # Generate music sinusoid
            music_freq = self.bpm / 60.0
            omega = 2 * np.pi * music_freq
            actual_amplitude = (np.max(actual_centered) - np.min(actual_centered)) / 2
            if actual_amplitude < 0.01:
                actual_amplitude = 1.0
            music_sinusoid = actual_amplitude * np.sin(omega * times)

            # Calculate metrics
            difference = music_sinusoid - actual_centered
            rms_diff = np.sqrt(np.mean(difference**2))

            if np.std(music_sinusoid) > 0 and np.std(actual_centered) > 0:
                correlation = np.corrcoef(music_sinusoid, actual_centered)[0, 1]
            else:
                correlation = 0.0

            # Calculate phase lag
            correlation_full = np.correlate(actual_centered - np.mean(actual_centered),
                                           music_sinusoid - np.mean(music_sinusoid), mode='full')
            lag_samples = np.argmax(correlation_full) - (len(actual_centered) - 1)
            dt = times[1] - times[0] if len(times) > 1 else 0.01
            phase_lag_ms = lag_samples * dt * 1000

            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)

                # Write metadata header
                writer.writerow(['# Music-Motor Synchronization Data'])
                if song_name:
                    writer.writerow([f'# Song: {song_name}'])
                if pattern_type:
                    writer.writerow([f'# Pattern: {pattern_type}'])
                writer.writerow([f'# BPM: {self.bpm:.1f}'])
                writer.writerow([f'# Music Frequency: {music_freq:.3f} Hz'])
                writer.writerow([f'# Phase Lag: {phase_lag_ms:.2f} ms'])
                writer.writerow([f'# Correlation: {correlation:.6f}'])
                writer.writerow([f'# RMS Difference: {rms_diff:.6f}'])
                writer.writerow([])

                # Write data header
                writer.writerow(['Time (s)', 'Music Sinusoid', 'Actual Position (centered)', 'Difference'])

                for i in range(min_len):
                    writer.writerow([
                        times[i],
                        music_sinusoid[i],
                        actual_centered[i],
                        difference[i]
                    ])

            print(f"[Recorder] Sync data exported to {filename}")
        except Exception as e:
            print(f"[Recorder] Error exporting sync data: {e}")
