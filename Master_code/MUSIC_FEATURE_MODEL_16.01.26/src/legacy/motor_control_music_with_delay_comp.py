#!/usr/bin/env python3
"""
Example integration of delay compensation with motor_control_music.py

This demonstrates how to add LSE-based delay compensation to the existing
music-synchronized motor control system.

Key additions:
1. DelayCompensator instance
2. Signal recording during motion
3. Delay estimation at beat boundaries
4. Time-shifted motion start based on compensation
"""

import numpy as np
import time
from collections import deque

# Import the delay compensator
from delay_compensator import DelayCompensator, estimate_delay_lse


class MotionSignalRecorder:
    """
    Records reference and actual signals for delay estimation.

    Call add_sample() at each control loop iteration during a motion.
    Call get_signals() at the end of the motion to retrieve arrays for LSE.
    """

    def __init__(self, max_samples=1000):
        self.reference = deque(maxlen=max_samples)
        self.actual = deque(maxlen=max_samples)
        self.timestamps = deque(maxlen=max_samples)
        self.recording = False
        self.start_time = None

    def start_recording(self):
        """Start a new recording session."""
        self.reference.clear()
        self.actual.clear()
        self.timestamps.clear()
        self.recording = True
        self.start_time = time.time()

    def add_sample(self, reference_pos: float, actual_pos: float):
        """
        Add a sample to the recording.

        Args:
            reference_pos: Commanded/expected position
            actual_pos: Actual encoder position
        """
        if not self.recording:
            return

        self.reference.append(reference_pos)
        self.actual.append(actual_pos)
        self.timestamps.append(time.time() - self.start_time)

    def stop_recording(self):
        """Stop recording and return signals."""
        self.recording = False
        return self.get_signals()

    def get_signals(self):
        """
        Get recorded signals as numpy arrays.

        Returns:
            Tuple of (reference_array, actual_array, duration)
        """
        if len(self.reference) == 0:
            return None, None, 0.0

        ref_array = np.array(self.reference)
        act_array = np.array(self.actual)
        duration = self.timestamps[-1] if len(self.timestamps) > 0 else 0.0

        return ref_array, act_array, duration


def integrate_delay_compensation_example():
    """
    Example showing how to integrate delay compensation into your control loop.

    This is a template - adapt it to your actual motor_control_music.py structure.
    """

    print("=== Delay Compensation Integration Example ===\n")

    # ============================================================================
    # SETUP PHASE
    # ============================================================================

    # 1. Initialize delay compensator
    motions = ['sine_wave_motion']  # Add more as needed
    delay_compensator = DelayCompensator(
        motions=motions,
        Kp=1.5,
        Ki=0.3,
        Kd=0.1,
        persistence_file='delay_lookup.pkl'
    )

    # 2. Initialize signal recorder
    signal_recorder = MotionSignalRecorder()

    # 3. Control parameters
    sampling_rate = 60  # Hz
    control_period = 1.0 / sampling_rate

    # Example parameters (normally from music analyzer)
    bpm = 120
    beat_duration = 60.0 / bpm
    motion_id = 'sine_wave_motion'

    # Time shift accumulator (compensation from delay controller)
    time_shift_compensation = 0.0

    print(f"Initialized delay compensator for motions: {motions}")
    print(f"Control rate: {sampling_rate} Hz")
    print(f"Tempo: {bpm} BPM ({beat_duration:.3f}s per beat)\n")

    # ============================================================================
    # MAIN CONTROL LOOP (simplified example)
    # ============================================================================

    print("Starting control loop simulation...\n")

    beat_count = 0
    max_beats = 10

    while beat_count < max_beats:
        print(f"--- Beat {beat_count + 1}/{max_beats} ---")

        # ========================================================================
        # A. WAIT FOR COMPENSATED START TIME
        # ========================================================================

        # In real system, this would be:
        # next_beat_time = music_analyzer.beat_times[beat_index + 1]
        # compensated_start = next_beat_time - time_shift_compensation

        # For this example, we just apply the shift
        beat_start_time = time.time() + time_shift_compensation

        # Wait until start time
        while time.time() < beat_start_time:
            time.sleep(0.001)

        if abs(time_shift_compensation) > 0.001:
            print(f"  Applied time shift: {time_shift_compensation*1000:+.1f} ms")

        # ========================================================================
        # B. EXECUTE MOTION WITH SIGNAL RECORDING
        # ========================================================================

        signal_recorder.start_recording()

        motion_start = time.time()
        iteration = 0

        # Execute motion for one beat duration
        while (time.time() - motion_start) < beat_duration:
            current_time = time.time() - motion_start

            # Calculate reference position (what we WANT the motor to do)
            # This is your calculate_expected_position() function
            frequency = bpm / 60.0
            amplitude = 5.0  # Example amplitude
            reference_pos = amplitude * np.sin(2 * np.pi * frequency * current_time)

            # In real system, this would be:
            # odrv0.axis0.controller.input_pos = reference_pos

            # Simulate actual position (with realistic delay and noise)
            # In real system, this would be:
            # actual_pos = odrv0.axis0.encoder.pos_estimate
            simulated_delay = 0.05  # 50ms simulated delay
            actual_pos = amplitude * np.sin(2 * np.pi * frequency * (current_time - simulated_delay))
            actual_pos += np.random.normal(0, 0.01)  # Add noise

            # Record both signals
            signal_recorder.add_sample(reference_pos, actual_pos)

            # Sleep until next control iteration
            time.sleep(control_period)
            iteration += 1

        print(f"  Executed motion: {iteration} samples recorded")

        # ========================================================================
        # C. ESTIMATE DELAY AFTER MOTION COMPLETES
        # ========================================================================

        ref_signal, act_signal, duration = signal_recorder.stop_recording()

        if ref_signal is not None and len(ref_signal) > 10:
            # Estimate delay using LSE method
            delay_est, _, _ = estimate_delay_lse(
                reference=ref_signal,
                actual=act_signal,
                fs=sampling_rate,
                max_shift_s=0.5
            )

            print(f"  Estimated delay: {delay_est*1000:+.1f} ms")

            # ====================================================================
            # D. COMPUTE COMPENSATION FOR NEXT BEAT
            # ====================================================================

            u_total, u_fb, u_ff = delay_compensator.compute_control(
                motion_id=motion_id,
                bpm=bpm,
                delay_est=delay_est,
                beat_duration=beat_duration
            )

            print(f"  Compensation: {u_total*1000:+.1f} ms (FB: {u_fb*1000:+.1f}, FF: {u_ff*1000:+.1f})")

            # Store for next iteration
            time_shift_compensation = u_total

            # ====================================================================
            # E. UPDATE LOOKUP TABLE IF SYNC IS GOOD
            # ====================================================================

            success = delay_compensator.update_lookup_table(
                motion_id=motion_id,
                bpm=bpm,
                control_action=u_total,
                resulting_delay=delay_est
            )

            if success:
                print(f"  ✓ Lookup table updated")

        beat_count += 1
        print()

    # ============================================================================
    # CLEANUP
    # ============================================================================

    print("=== Final Statistics ===")
    stats = delay_compensator.get_statistics()
    print(f"Mean absolute delay: {stats.get('mean_delay', 0)*1000:.1f} ms")
    print(f"Max absolute delay: {stats.get('max_delay', 0)*1000:.1f} ms")
    print(f"Std deviation: {stats.get('std_delay', 0)*1000:.1f} ms")

    # Save learned delays
    delay_compensator.save_state()
    print("\n✓ Delay lookup table saved to delay_lookup.pkl")


def integration_checklist():
    """Print integration checklist for adding to motor_control_music.py"""

    print("\n" + "="*60)
    print("INTEGRATION CHECKLIST FOR motor_control_music.py")
    print("="*60)
    print("""
1. [ ] Import delay compensator at top of file:
       from delay_compensator import DelayCompensator, estimate_delay_lse

2. [ ] Add MotionSignalRecorder class (copy from this file)

3. [ ] In main() function, add initialization:
       delay_compensator = DelayCompensator(
           motions=['sine_wave_motion'],
           persistence_file='delay_lookup.pkl'
       )
       signal_recorder = MotionSignalRecorder()

4. [ ] In run_control_loop(), before main loop:
       time_shift_compensation = 0.0

5. [ ] In run_control_loop(), modify loop start:
       # Apply compensation to beat timing
       if play_music:
           next_beat = music_analyzer.beat_times[beat_index]
           compensated_start = next_beat - time_shift_compensation
           # Wait until compensated start time
           while time.time() < compensated_start:
               time.sleep(0.001)

6. [ ] In run_control_loop(), start recording at beat boundary:
       if music_analyzer.current_beat_phase < 0.1 and not recording:
           signal_recorder.start_recording()
           recording = True

7. [ ] In run_control_loop(), record samples each iteration:
       if signal_recorder.recording:
           signal_recorder.add_sample(expected_pos, current_encoder_pos)

8. [ ] In run_control_loop(), at next beat boundary:
       if music_analyzer.current_beat_phase < 0.1 and recording:
           # Stop recording
           ref, act, dur = signal_recorder.stop_recording()
           recording = False

           # Estimate delay
           if ref is not None:
               delay_est, _, _ = estimate_delay_lse(ref, act, sampling_rate)

               # Compute compensation
               u_total, _, _ = delay_compensator.compute_control(
                   'sine_wave_motion', bpm, delay_est, 60.0/bpm
               )

               # Apply to next beat
               time_shift_compensation = u_total

               # Update lookup
               delay_compensator.update_lookup_table(
                   'sine_wave_motion', bpm, u_total, delay_est
               )

9. [ ] Add command-line flag:
       parser.add_argument('--enable-delay-compensation',
                          action='store_true',
                          help='Enable LSE-based delay compensation')

10. [ ] Test in simulation mode first:
        python3 motor_control_music.py -sim --enable-delay-compensation

11. [ ] Test in hardware mode:
        python3 motor_control_music.py --enable-delay-compensation

12. [ ] Monitor statistics and tune PID gains as needed

""")
    print("="*60)


if __name__ == "__main__":
    import sys

    if '--checklist' in sys.argv:
        integration_checklist()
    else:
        integrate_delay_compensation_example()
