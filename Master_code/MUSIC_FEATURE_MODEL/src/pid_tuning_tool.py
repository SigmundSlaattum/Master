#!/usr/bin/env python3
"""
PID Tuning Tool for ODrive Motor Control with Music Synchronization

This standalone script helps tune the PID constants for optimal music synchronization.
It tests different PID values and provides performance metrics to find the best settings.
"""

import time
import math
import argparse
import odrive
from odrive.enums import AXIS_STATE_IDLE, AXIS_STATE_CLOSED_LOOP_CONTROL
import numpy as np
import matplotlib.pyplot as plt
from collections import deque


class PIDTuner:
    """Class to manage PID tuning experiments."""

    def __init__(self, odrv0, initial_position=0.0):
        """
        Initialize PID tuner.

        Args:
            odrv0: ODrive object
            initial_position: Starting motor position
        """
        self.odrv0 = odrv0
        self.initial_position = initial_position
        self.results = []

    def get_current_pid_values(self):
        """Get current PID values from ODrive."""
        return {
            'pos_gain': self.odrv0.axis0.controller.config.pos_gain,
            'vel_gain': self.odrv0.axis0.controller.config.vel_gain,
            'vel_integrator_gain': self.odrv0.axis0.controller.config.vel_integrator_gain,
            'vel_limit': self.odrv0.axis0.controller.config.vel_limit
        }

    def set_pid_values(self, pos_gain, vel_gain, vel_integrator_gain):
        """
        Set PID values on ODrive.

        Args:
            pos_gain: Position gain (P term)
            vel_gain: Velocity gain (D term)
            vel_integrator_gain: Velocity integrator gain (I term)
        """
        self.odrv0.axis0.controller.config.pos_gain = pos_gain
        self.odrv0.axis0.controller.config.vel_gain = vel_gain
        self.odrv0.axis0.controller.config.vel_integrator_gain = vel_integrator_gain
        time.sleep(0.1)  # Let settings take effect

    def run_sine_wave_test(self, amplitude, frequency, duration, pos_gain, vel_gain, vel_integrator_gain):
        """
        Run a sine wave tracking test with given PID parameters.

        Args:
            amplitude: Sine wave amplitude in motor turns
            frequency: Sine wave frequency in Hz
            duration: Test duration in seconds
            pos_gain: Position gain to test
            vel_gain: Velocity gain to test
            vel_integrator_gain: Velocity integrator gain to test

        Returns:
            dict: Test results with performance metrics
        """
        print(f"\n{'='*60}")
        print(f"Testing PID: pos_gain={pos_gain}, vel_gain={vel_gain}, vel_integrator_gain={vel_integrator_gain}")
        print(f"Test parameters: amp={amplitude} turns, freq={frequency} Hz, duration={duration}s")
        print(f"{'='*60}")

        # Set PID values
        self.set_pid_values(pos_gain, vel_gain, vel_integrator_gain)

        # Data collection
        time_data = []
        command_data = []
        actual_data = []
        error_data = []
        velocity_data = []

        # Control loop parameters
        sampling_rate = 100.0  # Hz (higher for PID tuning)
        control_period = 1.0 / sampling_rate

        # Start test
        start_time = time.time()
        next_control_time = start_time + control_period

        print("Starting test...")
        iteration = 0
        max_error = 0.0

        while True:
            current_time = time.time() - start_time

            if current_time >= duration:
                break

            # Generate sinusoidal reference
            pos_command = self.initial_position + amplitude * math.sin(2 * math.pi * frequency * current_time)

            # Get actual position
            try:
                actual_pos = self.odrv0.axis0.encoder.pos_estimate
                actual_vel = self.odrv0.axis0.encoder.vel_estimate
            except (AttributeError, OSError) as e:
                print(f"\nError reading encoder: {e}")
                break

            # Calculate error
            error = pos_command - actual_pos
            max_error = max(max_error, abs(error))

            # Send command
            try:
                self.odrv0.axis0.controller.input_pos = pos_command
            except (AttributeError, OSError) as e:
                print(f"\nError sending command: {e}")
                break

            # Record data
            time_data.append(current_time)
            command_data.append(pos_command)
            actual_data.append(actual_pos)
            error_data.append(error)
            velocity_data.append(actual_vel)

            # Check for errors
            if self.odrv0.axis0.error != 0:
                print(f"\nAxis error detected: {self.odrv0.axis0.error}")
                break

            # Print status every 50 iterations
            if iteration % 50 == 0:
                rms_error = np.sqrt(np.mean(np.array(error_data[-50:])**2)) if len(error_data) >= 50 else 0
                print(f"\rTime: {current_time:.2f}s | Error: {error:+.4f} | Max: {max_error:.4f} | RMS: {rms_error:.4f}", end="")

            # Wait for next control cycle
            current_wall_time = time.time()
            sleep_time = next_control_time - current_wall_time
            if sleep_time > 0:
                time.sleep(sleep_time)

            next_control_time += control_period

            # If we've fallen behind, reset timing
            if next_control_time < time.time():
                next_control_time = time.time() + control_period

            iteration += 1

        print("\n")

        # Calculate performance metrics
        time_array = np.array(time_data)
        error_array = np.array(error_data)
        command_array = np.array(command_data)
        actual_array = np.array(actual_data)
        velocity_array = np.array(velocity_data)

        # RMS error
        rms_error = np.sqrt(np.mean(error_array**2))

        # Maximum absolute error
        max_abs_error = np.max(np.abs(error_array))

        # Mean absolute error
        mae = np.mean(np.abs(error_array))

        # Settling time (time to get within 2% of steady-state)
        settling_threshold = 0.02 * amplitude
        settled_indices = np.where(np.abs(error_array) < settling_threshold)[0]
        settling_time = time_array[settled_indices[0]] if len(settled_indices) > 0 else duration

        # Overshoot
        if len(command_array) > 0:
            peak_error = np.max(error_array)
            overshoot_pct = (peak_error / amplitude) * 100 if amplitude > 0 else 0
        else:
            overshoot_pct = 0

        # Velocity characteristics
        max_velocity = np.max(np.abs(velocity_array))
        avg_velocity = np.mean(np.abs(velocity_array))

        # Phase lag estimation (using cross-correlation)
        if len(command_array) > 100:
            correlation = np.correlate(command_array - np.mean(command_array),
                                       actual_array - np.mean(actual_array),
                                       mode='same')
            phase_lag_samples = np.argmax(correlation) - len(correlation) // 2
            phase_lag_time = phase_lag_samples * control_period
        else:
            phase_lag_time = 0

        # Compile results
        results = {
            'pos_gain': pos_gain,
            'vel_gain': vel_gain,
            'vel_integrator_gain': vel_integrator_gain,
            'rms_error': rms_error,
            'max_error': max_abs_error,
            'mae': mae,
            'settling_time': settling_time,
            'overshoot_pct': overshoot_pct,
            'max_velocity': max_velocity,
            'avg_velocity': avg_velocity,
            'phase_lag_time': phase_lag_time,
            'time_data': time_data,
            'command_data': command_data,
            'actual_data': actual_data,
            'error_data': error_data,
            'velocity_data': velocity_data
        }

        # Print summary
        print("Test Results:")
        print(f"  RMS Error: {rms_error:.5f} turns")
        print(f"  Max Error: {max_abs_error:.5f} turns")
        print(f"  MAE: {mae:.5f} turns")
        print(f"  Settling Time: {settling_time:.3f}s")
        print(f"  Overshoot: {overshoot_pct:.2f}%")
        print(f"  Phase Lag: {phase_lag_time*1000:.2f}ms")
        print(f"  Max Velocity: {max_velocity:.2f} turns/s")

        self.results.append(results)
        return results

    def run_step_response_test(self, step_size, duration, pos_gain, vel_gain, vel_integrator_gain):
        """
        Run a step response test with given PID parameters.

        Args:
            step_size: Step size in motor turns
            duration: Test duration in seconds
            pos_gain: Position gain to test
            vel_gain: Velocity gain to test
            vel_integrator_gain: Velocity integrator gain to test

        Returns:
            dict: Test results with performance metrics
        """
        print(f"\n{'='*60}")
        print(f"Step Response Test: pos_gain={pos_gain}, vel_gain={vel_gain}, vel_integrator_gain={vel_integrator_gain}")
        print(f"Step size: {step_size} turns")
        print(f"{'='*60}")

        # Set PID values
        self.set_pid_values(pos_gain, vel_gain, vel_integrator_gain)

        # Data collection
        time_data = []
        command_data = []
        actual_data = []
        error_data = []

        # Control loop parameters
        sampling_rate = 100.0  # Hz
        control_period = 1.0 / sampling_rate

        # Command step
        target_position = self.initial_position + step_size

        # Start test
        start_time = time.time()
        next_control_time = start_time + control_period

        print("Starting step response test...")
        iteration = 0

        while True:
            current_time = time.time() - start_time

            if current_time >= duration:
                break

            # Get actual position
            try:
                actual_pos = self.odrv0.axis0.encoder.pos_estimate
            except (AttributeError, OSError) as e:
                print(f"\nError reading encoder: {e}")
                break

            # Calculate error
            error = target_position - actual_pos

            # Send command
            try:
                self.odrv0.axis0.controller.input_pos = target_position
            except (AttributeError, OSError) as e:
                print(f"\nError sending command: {e}")
                break

            # Record data
            time_data.append(current_time)
            command_data.append(target_position)
            actual_data.append(actual_pos)
            error_data.append(error)

            # Check for errors
            if self.odrv0.axis0.error != 0:
                print(f"\nAxis error detected: {self.odrv0.axis0.error}")
                break

            # Print status
            if iteration % 50 == 0:
                print(f"\rTime: {current_time:.2f}s | Error: {error:+.4f} | Position: {actual_pos:.4f}", end="")

            # Wait for next control cycle
            current_wall_time = time.time()
            sleep_time = next_control_time - current_wall_time
            if sleep_time > 0:
                time.sleep(sleep_time)

            next_control_time += control_period
            iteration += 1

        print("\n")

        # Calculate step response metrics
        time_array = np.array(time_data)
        actual_array = np.array(actual_data)
        error_array = np.array(error_data)

        # Rise time (10% to 90%)
        rise_10_pct = self.initial_position + 0.1 * step_size
        rise_90_pct = self.initial_position + 0.9 * step_size

        rise_10_idx = np.where(actual_array >= rise_10_pct)[0]
        rise_90_idx = np.where(actual_array >= rise_90_pct)[0]

        rise_time = 0
        if len(rise_10_idx) > 0 and len(rise_90_idx) > 0:
            rise_time = time_array[rise_90_idx[0]] - time_array[rise_10_idx[0]]

        # Settling time (within 2% of final value)
        settling_threshold = 0.02 * abs(step_size)
        settled_indices = np.where(np.abs(error_array) < settling_threshold)[0]
        settling_time = time_array[settled_indices[0]] if len(settled_indices) > 0 else duration

        # Overshoot
        max_pos = np.max(actual_array)
        overshoot = max_pos - target_position
        overshoot_pct = (overshoot / abs(step_size)) * 100 if step_size != 0 else 0

        # Steady state error
        steady_state_error = np.mean(error_array[-50:]) if len(error_array) >= 50 else error_array[-1]

        results = {
            'pos_gain': pos_gain,
            'vel_gain': vel_gain,
            'vel_integrator_gain': vel_integrator_gain,
            'rise_time': rise_time,
            'settling_time': settling_time,
            'overshoot': overshoot,
            'overshoot_pct': overshoot_pct,
            'steady_state_error': steady_state_error,
            'time_data': time_data,
            'command_data': command_data,
            'actual_data': actual_data,
            'error_data': error_data
        }

        print("Step Response Results:")
        print(f"  Rise Time (10-90%): {rise_time:.3f}s")
        print(f"  Settling Time (2%): {settling_time:.3f}s")
        print(f"  Overshoot: {overshoot:.5f} turns ({overshoot_pct:.2f}%)")
        print(f"  Steady State Error: {steady_state_error:.5f} turns")

        return results

    def compare_results(self):
        """Print comparison table of all test results."""
        if not self.results:
            print("No results to compare")
            return

        print(f"\n{'='*80}")
        print("PID TUNING RESULTS COMPARISON")
        print(f"{'='*80}")
        print(f"{'Pos Gain':>10} {'Vel Gain':>10} {'Vel Int':>10} {'RMS Error':>12} {'Max Error':>12} {'Phase Lag':>12}")
        print(f"{'-'*80}")

        for result in self.results:
            print(f"{result['pos_gain']:>10.1f} {result['vel_gain']:>10.3f} {result['vel_integrator_gain']:>10.3f} "
                  f"{result['rms_error']:>12.5f} {result['max_error']:>12.5f} {result.get('phase_lag_time', 0)*1000:>11.2f}ms")

        # Find best result (minimum RMS error)
        best_result = min(self.results, key=lambda x: x['rms_error'])

        print(f"{'-'*80}")
        print(f"BEST RESULT (Minimum RMS Error):")
        print(f"  pos_gain = {best_result['pos_gain']}")
        print(f"  vel_gain = {best_result['vel_gain']}")
        print(f"  vel_integrator_gain = {best_result['vel_integrator_gain']}")
        print(f"  RMS Error = {best_result['rms_error']:.5f} turns")
        print(f"{'='*80}\n")

        return best_result

    def plot_comparison(self, indices=None):
        """
        Plot comparison of test results.

        Args:
            indices: List of result indices to plot (None = plot all)
        """
        if not self.results:
            print("No results to plot")
            return

        if indices is None:
            indices = range(len(self.results))

        fig, axes = plt.subplots(3, 1, figsize=(12, 10))

        colors = plt.cm.viridis(np.linspace(0, 1, len(indices)))

        for idx, color in zip(indices, colors):
            if idx >= len(self.results):
                continue

            result = self.results[idx]
            label = f"P={result['pos_gain']}, D={result['vel_gain']:.2f}, I={result['vel_integrator_gain']:.3f}"

            # Position tracking
            axes[0].plot(result['time_data'], result['command_data'], '--', color=color, alpha=0.5, linewidth=1)
            axes[0].plot(result['time_data'], result['actual_data'], '-', color=color, label=label, linewidth=2)

            # Tracking error
            axes[1].plot(result['time_data'], result['error_data'], '-', color=color, label=label, linewidth=2)

            # Velocity
            axes[2].plot(result['time_data'], result['velocity_data'], '-', color=color, label=label, linewidth=2)

        axes[0].set_ylabel('Position (turns)')
        axes[0].set_title('Position Tracking')
        axes[0].legend(loc='upper right', fontsize=8)
        axes[0].grid(True, alpha=0.3)

        axes[1].set_ylabel('Error (turns)')
        axes[1].set_title('Tracking Error')
        axes[1].axhline(y=0, color='k', linestyle='--', alpha=0.3)
        axes[1].grid(True, alpha=0.3)

        axes[2].set_xlabel('Time (s)')
        axes[2].set_ylabel('Velocity (turns/s)')
        axes[2].set_title('Velocity')
        axes[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig('/Users/sigmund/Documents/master/Master_code/MUSIC_FEATURE_MODEL/src/plots/pid_tuning_comparison.png', dpi=150)
        print("Plot saved to: plots/pid_tuning_comparison.png")
        plt.show()


def main():
    """Main function for PID tuning."""
    parser = argparse.ArgumentParser(
        description="PID Tuning Tool for ODrive Motor Control"
    )
    parser.add_argument('-a', '--amplitude', type=float, default=5.0,
                       help='Sine wave amplitude in turns (default: 5.0)')
    parser.add_argument('-f', '--frequency', type=float, default=2.0,
                       help='Sine wave frequency in Hz (default: 2.0)')
    parser.add_argument('-d', '--duration', type=float, default=5.0,
                       help='Test duration in seconds (default: 5.0)')
    parser.add_argument('--step', action='store_true',
                       help='Run step response test instead of sine wave')
    parser.add_argument('--step_size', type=float, default=10.0,
                       help='Step size in turns (default: 10.0)')
    parser.add_argument('--auto', action='store_true',
                       help='Auto-tune using multiple PID values')

    args = parser.parse_args()

    print("\n" + "="*60)
    print("PID TUNING TOOL FOR ODRIVE MOTOR CONTROL")
    print("="*60 + "\n")

    # Connect to ODrive
    print("Looking for ODrive...")
    odrv0 = odrive.find_any(timeout=30)

    if odrv0 is None:
        print("ODrive not found!")
        return

    print("ODrive found")

    # Get initial position
    try:
        initial_position = odrv0.axis0.encoder.pos_estimate
        print(f"Initial motor position: {initial_position:.3f} turns")
    except (AttributeError, OSError) as e:
        print(f"Error reading initial position: {e}")
        initial_position = 0.0

    # Make sure motor is in closed-loop control
    print("\nStarting closed-loop control...")
    odrv0.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
    time.sleep(0.5)

    # Check for errors
    if odrv0.axis0.error != 0:
        print(f"Axis error: {odrv0.axis0.error}")
        print("Please clear errors and try again")
        return

    print("Motor ready")

    # Get current PID values
    tuner = PIDTuner(odrv0, initial_position)
    current_pid = tuner.get_current_pid_values()

    print("\nCurrent PID values:")
    print(f"  pos_gain: {current_pid['pos_gain']}")
    print(f"  vel_gain: {current_pid['vel_gain']}")
    print(f"  vel_integrator_gain: {current_pid['vel_integrator_gain']}")
    print(f"  vel_limit: {current_pid['vel_limit']}")

    input("\nPress Enter to start tuning tests...\n")

    # Create plots directory
    import os
    os.makedirs('/Users/sigmund/Documents/master/Master_code/MUSIC_FEATURE_MODEL/src/plots', exist_ok=True)

    if args.auto:
        print("\n" + "="*60)
        print("AUTO-TUNING MODE: Testing multiple PID combinations")
        print("="*60 + "\n")

        # Define PID test ranges for music synchronization application
        # pos_gain: Controls position tracking stiffness
        pos_gains = [40, 50, 80, 100]

        # vel_gain: Damping (typical range 0.1 to 1.0 for ODrive)
        # Higher values = more damping but slower response
        # Increased to match higher pos_gains (80-100 need more damping)
        vel_gains = [0.15, 0.2, 0.3, 0.5]

        # vel_integrator_gain: Eliminates steady-state error
        # Start with low values to avoid instability
        vel_integrator_gains = [0.0, 0.15, 0.3]

        total_tests = len(pos_gains) * len(vel_gains) * len(vel_integrator_gains)
        test_num = 0

        for pos_gain in pos_gains:
            for vel_gain in vel_gains:
                for vel_integrator_gain in vel_integrator_gains:
                    test_num += 1
                    print(f"\n[Test {test_num}/{total_tests}]")

                    try:
                        if args.step:
                            tuner.run_step_response_test(
                                step_size=args.step_size,
                                duration=args.duration,
                                pos_gain=pos_gain,
                                vel_gain=vel_gain,
                                vel_integrator_gain=vel_integrator_gain
                            )
                        else:
                            tuner.run_sine_wave_test(
                                amplitude=args.amplitude,
                                frequency=args.frequency,
                                duration=args.duration,
                                pos_gain=pos_gain,
                                vel_gain=vel_gain,
                                vel_integrator_gain=vel_integrator_gain
                            )

                        # Return to initial position
                        print("Returning to initial position...")
                        odrv0.axis0.controller.input_pos = initial_position
                        time.sleep(2.0)

                    except KeyboardInterrupt:
                        print("\n\nTuning interrupted by user")
                        break
                    except Exception as e:
                        print(f"\nError during test: {e}")
                        continue

        # Compare all results
        best_result = tuner.compare_results()

        # Plot comparison
        print("\nGenerating comparison plots...")
        tuner.plot_comparison()

    else:
        # Single test with current or specified PID values
        pos_gain = current_pid['pos_gain']
        vel_gain = current_pid['vel_gain']
        vel_integrator_gain = current_pid['vel_integrator_gain']

        try:
            if args.step:
                result = tuner.run_step_response_test(
                    step_size=args.step_size,
                    duration=args.duration,
                    pos_gain=pos_gain,
                    vel_gain=vel_gain,
                    vel_integrator_gain=vel_integrator_gain
                )
            else:
                result = tuner.run_sine_wave_test(
                    amplitude=args.amplitude,
                    frequency=args.frequency,
                    duration=args.duration,
                    pos_gain=pos_gain,
                    vel_gain=vel_gain,
                    vel_integrator_gain=vel_integrator_gain
                )

            # Plot single test result
            print("\nGenerating plot...")
            tuner.plot_comparison([0])

        except KeyboardInterrupt:
            print("\n\nTest interrupted by user")
        except Exception as e:
            print(f"\nError during test: {e}")

    # Return motor to idle
    print("\nReturning motor to idle state...")
    odrv0.axis0.requested_state = AXIS_STATE_IDLE

    print("\nPID tuning session complete!")


if __name__ == "__main__":
    main()
