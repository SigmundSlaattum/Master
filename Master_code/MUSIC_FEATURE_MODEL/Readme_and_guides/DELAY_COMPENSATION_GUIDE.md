# Delay Compensation Integration Guide

## Overview

This guide explains how to integrate the delay compensation system (based on the paper "Real-Time Dance Generation to Music for a Legged Robot" by Bi et al., IROS 2018) with your motor control system.

## How It Works

### 1. **Delay Estimation (LSE Method)**
At each beat, the system:
- Records the **reference signal** (what the motor should do)
- Records the **actual signal** (what the motor actually did, from encoder feedback)
- Compares them by time-shifting and finding minimum squared error
- Outputs the delay in seconds

### 2. **PID Feedback Controller**
Uses the estimated delay to compute correction:
- **P term**: Proportional to current delay error
- **I term**: Accumulates past delays (with anti-windup)
- **D term**: Responds to rate of change of delay

### 3. **Feedforward Lookup Table**
- Stores successful corrections for each (motion, tempo) pair
- Uses moving average of last 8 successful attempts
- Provides proactive compensation before delay is even measured

### 4. **Time Shifting**
The control output shifts the **start time** of the next motion:
```python
next_motion_start_time = next_beat_time - control_action
```

## Integration Steps

### Step 1: Initialize the Delay Compensator

```python
from delay_compensator import DelayCompensator, estimate_delay_lse
import numpy as np

# Define your motion types (one for now, but can expand)
motions = ['sine_wave_motion']

# Create compensator with persistence
dc = DelayCompensator(
    motions=motions,
    Kp=1.5,          # Tune these based on your system
    Ki=0.3,
    Kd=0.1,
    persistence_file='delay_lookup.pkl'  # Saves learned delays
)
```

### Step 2: Collect Signals During Motion

During each beat/motion cycle, record both reference and actual positions:

```python
# At each control loop iteration
sampling_rate = 60  # Hz (your control loop rate)
beat_duration = 60.0 / bpm  # seconds per beat

# Storage for one beat cycle
reference_positions = []
actual_positions = []
timestamps = []

start_time = time.time()

# Execute motion for one beat duration
while (time.time() - start_time) < beat_duration:
    # Calculate reference position (what you WANT)
    expected_pos = calculate_expected_position(time.time() - start_time, bpm, ...)
    reference_positions.append(expected_pos)

    # Get actual position (what you GOT from encoder)
    actual_pos = odrv0.axis0.encoder.pos_estimate  # or simulator position
    actual_positions.append(actual_pos)

    timestamps.append(time.time() - start_time)

    # Send command to motor
    odrv0.axis0.controller.input_pos = expected_pos

    time.sleep(1.0 / sampling_rate)
```

### Step 3: Estimate Delay After Each Beat

```python
# Convert to numpy arrays
ref_signal = np.array(reference_positions)
act_signal = np.array(actual_positions)

# Estimate delay
delay_est, _, _ = estimate_delay_lse(
    reference=ref_signal,
    actual=act_signal,
    fs=sampling_rate,
    max_shift_s=0.5  # Don't search beyond 500ms
)

print(f"Estimated delay: {delay_est*1000:.1f} ms")
```

### Step 4: Compute Control Action

```python
# Compute how much to shift the next motion
motion_id = 'sine_wave_motion'
u_total, u_fb, u_ff = dc.compute_control(
    motion_id=motion_id,
    bpm=bpm,
    delay_est=delay_est,
    beat_duration=beat_duration
)

print(f"Control: {u_total*1000:.1f} ms (FB: {u_fb*1000:.1f}, FF: {u_ff*1000:.1f})")
```

### Step 5: Apply Time Shift to Next Motion

```python
# Calculate when next beat should occur
next_beat_time = music_analyzer.beat_times[beat_index + 1]

# Apply delay compensation by shifting start time
compensated_start_time = next_beat_time - u_total

# Wait until compensated start time
while time.time() < compensated_start_time:
    time.sleep(0.001)

# Now start the next motion
# ... (back to Step 2)
```

### Step 6: Update Lookup Table

```python
# After executing with compensation, measure the result
# (This would be done at the NEXT beat after applying compensation)
success = dc.update_lookup_table(
    motion_id=motion_id,
    bpm=bpm,
    control_action=u_total,
    resulting_delay=delay_est  # From next beat's measurement
)

if success:
    print("✓ Lookup table updated")
```

## Key Differences from Current System

### Current System (motor_control_music.py)
- Uses **beat phase locking** on downbeat
- Uses **position error** for continuous correction
- Corrects phase offset during motion

### Paper's Method (delay_compensator.py)
- Uses **LSE delay estimation** per beat
- Uses **PID + feedforward** for discrete corrections
- Shifts **start time** of next motion (not continuous)

## Recommended Hybrid Approach

Combine both methods:

1. **Use delay compensation for beat-to-beat timing** (discrete)
2. **Use phase correction for within-beat tracking** (continuous)

```python
# At each beat boundary:
delay_est = estimate_delay_lse(ref_signal, act_signal, sampling_rate)
time_shift = dc.compute_control(motion_id, bpm, delay_est, beat_duration)[0]
next_start_time = next_beat_time - time_shift

# During beat execution:
phase_offset += continuous_phase_correction(position_error)
```

## Tuning Guidelines

### PID Gains
- **Kp (1.0-2.0)**: Higher = faster response, but may overshoot
- **Ki (0.1-0.5)**: Eliminates steady-state error, but too high causes oscillation
- **Kd (0.05-0.2)**: Reduces overshoot, smooths response

### When to Use
- **Slow tempos (< 80 BPM)**: Higher gains work well
- **Fast tempos (> 140 BPM)**: Lower gains prevent oscillation
- **Complex motions**: Start with lower gains

### Debugging
```python
# Get statistics
stats = dc.get_statistics()
print(f"Mean delay: {stats['mean_delay']*1000:.1f} ms")
print(f"Max delay: {stats['max_delay']*1000:.1f} ms")
print(f"Integral term: {stats['integral_term']:.3f}")

# Save learned delays for next session
dc.save_state()
```

## Demo Mode

Test the system without hardware:

```bash
# Run demo with visualization
python3 delay_compensator.py --demo

# Run demo without plots (faster)
python3 delay_compensator.py --demo --no-plot

# Custom duration
python3 delay_compensator.py --demo --duration 60
```

## Simulation Mode Integration

Test with your simulator:

```bash
# Run motor control in simulation mode with delay compensation
python3 motor_control_music.py -sim --enable-delay-compensation
```

## Hardware Mode Integration

With real ODrive motor:

```bash
# Run with delay compensation enabled
python3 motor_control_music.py --enable-delay-compensation

# With calibration
python3 motor_control_music.py -c --enable-delay-compensation
```

## Expected Results

Based on the paper's results:
- **Convergence time**: 3-7 seconds after tempo change
- **Steady-state delay**: < 75ms (within human perception threshold)
- **Synchronization accuracy**: Typically < 50ms for simple motions

Your system should show:
- Immediate improvement with feedforward (if table is trained)
- Gradual convergence of feedback controller
- Better tracking at consistent tempos vs. changing tempos

## Troubleshooting

### Problem: Delays don't converge
- Check that reference signal matches commanded motion
- Verify sampling rate is consistent (60 Hz)
- Ensure beat duration is accurate

### Problem: Oscillations in timing
- Reduce Kp and Kd gains
- Check for quantization in encoder readings
- Verify control loop timing is stable

### Problem: Lookup table not helping
- Need more training data at each tempo
- Check that BPM detection is accurate
- Verify motion_id matches between training and use

### Problem: Large delays (> 200ms)
- Motor may not be tuned properly (check PID gains)
- Control loop may be too slow (increase to 60 Hz+)
- Check for communication delays with ODrive

## Further Improvements

1. **Multiple motion types**: Add different motions to the lookup table
2. **Adaptive gains**: Adjust PID gains based on tempo
3. **Predictive compensation**: Use beat tracker's tempo prediction
4. **Cross-modal sync**: Combine audio beat detection with motion timing

## References

- Paper: "Real-Time Dance Generation to Music for a Legged Robot" (Bi et al., IROS 2018)
- Your current phase-locking implementation: [motor_control_music.py:431-492](motor_control_music.py#L431-L492)
