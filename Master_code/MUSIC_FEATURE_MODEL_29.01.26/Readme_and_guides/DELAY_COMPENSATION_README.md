# Delay Compensation for Music-Synchronized Robot Control

Implementation of the delay compensation method from:
**"Real-Time Dance Generation to Music for a Legged Robot"** (Bi et al., IROS 2018)

## Overview

This module provides beat-synchronized delay compensation for robotic motion control. It addresses the fundamental problem that robot motion lags behind commanded motion due to:
- Motor dynamics and inertia
- Communication delays
- Control loop timing
- Hardware response time

The system learns optimal time shifts for different motions and tempos, providing both reactive (PID) and proactive (feedforward) compensation.

## Files

### Core Module
- **[delay_compensator.py](delay_compensator.py)** - Main implementation
  - `estimate_delay_lse()` - Least Squares Error delay estimation
  - `DelayCompensator` - PID + feedforward controller
  - `DynamicLookupTable` - Motion/tempo-specific delay storage
  - Demo mode with visualization

### Documentation
- **[DELAY_COMPENSATION_GUIDE.md](DELAY_COMPENSATION_GUIDE.md)** - Detailed integration guide
  - Step-by-step integration instructions
  - Tuning guidelines
  - Troubleshooting tips
  - Comparison with current system

### Examples
- **[motor_control_music_with_delay_comp.py](motor_control_music_with_delay_comp.py)** - Integration example
  - `MotionSignalRecorder` - Helper class for signal recording
  - `integrate_delay_compensation_example()` - Complete working example
  - `integration_checklist()` - Step-by-step checklist

## Quick Start

### 1. Test the Demo

```bash
# With visualization
python3 delay_compensator.py --demo

# Without plots (faster)
python3 delay_compensator.py --demo --no-plot

# Longer simulation
python3 delay_compensator.py --demo --duration 60
```

Expected output:
```
=== Delay Compensation Demo Results ===
Mean absolute delay: 0.0215 s
Max absolute delay: 0.1234 s
Std deviation: 0.0312 s
Final true delay: 0.0003 s
```

### 2. Run the Integration Example

```bash
python3 motor_control_music_with_delay_comp.py
```

This simulates a full beat-by-beat control loop with delay compensation.

### 3. View Integration Checklist

```bash
python3 motor_control_music_with_delay_comp.py --checklist
```

## How It Works

### The Paper's Method

1. **At each beat boundary:**
   - Record reference signal (commanded positions)
   - Record actual signal (encoder feedback)
   - Compare using time-shifting to find delay

2. **Compute compensation:**
   - PID feedback based on current delay
   - Feedforward from learned delays
   - Combine for total time shift

3. **Apply to next motion:**
   - Shift start time: `next_start = beat_time - compensation`
   - Execute motion
   - Repeat

### Key Insight

Instead of trying to speed up/slow down during motion (which distorts it), the system **shifts the entire motion in time** by starting it earlier or later.

## Integration with Your System

### Current System (motor_control_music.py)

Your system already has excellent synchronization using:
- **Beat phase locking** on downbeats
- **Position error correction** within beats
- **Phase offset adjustments**

### Adding Delay Compensation

The paper's method complements your system:

```python
# Your existing approach (continuous, during motion):
phase_offset += continuous_correction(position_error)

# Paper's approach (discrete, between motions):
next_beat_start = beat_time - delay_compensation
```

**Recommendation:** Start with your existing system. Add delay compensation if you notice:
- Consistent lag at certain tempos
- Difficulty converging after tempo changes
- Different delays for different motion types

## Basic Integration

### Minimal Changes to motor_control_music.py

```python
# 1. Import at top
from delay_compensator import DelayCompensator, estimate_delay_lse
import numpy as np

# 2. Initialize in main()
delay_comp = DelayCompensator(
    motions=['sine_wave'],
    persistence_file='delays.pkl'
)
ref_history = []
act_history = []

# 3. In control loop, record signals
ref_history.append(expected_pos)
act_history.append(current_encoder_pos)

# 4. At beat boundary, estimate and compensate
if beat_just_occurred:
    ref = np.array(ref_history[-30:])  # Last 30 samples
    act = np.array(act_history[-30:])

    if len(ref) > 10:
        delay, _, _ = estimate_delay_lse(ref, act, sampling_rate)
        compensation, _, _ = delay_comp.compute_control(
            'sine_wave', bpm, delay, 60.0/bpm
        )

        # Apply compensation to phase offset
        phase_offset -= compensation * (2 * math.pi * bpm / 60)

        # Update lookup table
        delay_comp.update_lookup_table(
            'sine_wave', bpm, compensation, delay
        )
```

## Configuration

### Motion Types

Define different motions if they have different delays:

```python
motions = [
    'sine_wave',
    'complex_wave',
    'step_response',
    'fast_oscillation'
]
```

### PID Tuning

Adjust based on your system's response:

```python
dc = DelayCompensator(
    motions=motions,
    Kp=1.5,    # ↑ faster response, may overshoot
    Ki=0.3,    # ↑ eliminates steady error, may oscillate
    Kd=0.1,    # ↑ reduces overshoot, smoother
    integral_limit=1.0  # Prevents wind-up
)
```

### Lookup Table

The table automatically learns optimal delays:
- Stores last 8 successful attempts per (motion, tempo)
- Updates when delay < 75ms
- Persists to disk for next session

## Testing Workflow

### 1. Simulation Mode

```bash
# Test without hardware
python3 motor_control_music.py -sim --enable-delay-compensation
```

Verify:
- [ ] Delay estimates are reasonable (< 200ms)
- [ ] Compensation converges
- [ ] No oscillations

### 2. Hardware Mode (No Music)

```bash
# Test with motor, no music
python3 motor_control_music.py -wm --enable-delay-compensation
```

Verify:
- [ ] Motor moves smoothly
- [ ] Encoder feedback is clean
- [ ] Reference signal is correct

### 3. Hardware Mode (With Music)

```bash
# Full integration test
python3 motor_control_music.py --enable-delay-compensation
```

Verify:
- [ ] Synchronization improves over time
- [ ] Lookup table updates
- [ ] Statistics look good

## Monitoring

### Real-Time

During operation, check:
- Estimated delay (should be < 100ms when synced)
- Control action (should stabilize)
- Lookup table updates (should occur frequently)

### Post-Run

```python
stats = delay_comp.get_statistics()
print(f"Mean delay: {stats['mean_delay']*1000:.1f} ms")
print(f"Max delay: {stats['max_delay']*1000:.1f} ms")
print(f"Std: {stats['std_delay']*1000:.1f} ms")
```

Good results:
- Mean < 50ms
- Max < 150ms
- Std < 30ms

## Troubleshooting

### High Delays (> 200ms)

**Cause:** Motor PID not tuned, or control loop too slow

**Fix:**
```python
# Increase motor controller gains
odrv0.axis0.controller.config.pos_gain = 200
odrv0.axis0.controller.config.vel_gain = 0.8

# Increase control loop rate
sampling_rate = 60  # Hz minimum
```

### Oscillations

**Cause:** Delay compensation gains too high

**Fix:**
```python
dc = DelayCompensator(
    motions=motions,
    Kp=1.0,   # Reduced from 1.5
    Ki=0.2,   # Reduced from 0.3
    Kd=0.05   # Reduced from 0.1
)
```

### Not Converging

**Cause:** Reference signal doesn't match actual motion

**Fix:**
```python
# Verify signals are aligned
import matplotlib.pyplot as plt
plt.plot(ref_history, label='Reference')
plt.plot(act_history, label='Actual')
plt.legend()
plt.show()
```

They should have the same shape, just shifted in time.

### Lookup Table Not Helping

**Cause:** Need more training data

**Fix:**
- Run for longer (several minutes)
- Stay at consistent tempo
- Ensure BPM detection is stable

## Performance Expectations

Based on paper's results with ANYmal quadruped:

| Metric | Paper's Results | Your System Should Achieve |
|--------|----------------|---------------------------|
| Convergence time | 3-7 seconds | 5-10 seconds |
| Steady-state delay | < 75ms | < 100ms |
| Max delay | < 200ms | < 250ms |
| Sync threshold | 75ms | 75-100ms |

Human perception threshold: **±75ms** for audio-visual sync

## Advanced Features

### Multiple Motions

```python
# Define multiple motion types
motions = ['slow', 'medium', 'fast']

# Use appropriate motion_id
if bpm < 80:
    motion_id = 'slow'
elif bpm < 120:
    motion_id = 'medium'
else:
    motion_id = 'fast'

delay_comp.compute_control(motion_id, bpm, delay, duration)
```

### Adaptive Gains

```python
# Adjust gains based on tempo
if bpm > 140:  # Fast tempo
    delay_comp.Kp = 1.0  # Lower gains
elif bpm < 80:  # Slow tempo
    delay_comp.Kp = 2.0  # Higher gains
```

### Save/Load State

```python
# Save learned delays
delay_comp.save_state()

# Automatically loads on next run if persistence_file is set
dc = DelayCompensator(
    motions=motions,
    persistence_file='learned_delays.pkl'  # Auto-loads this file
)
```

## Theory vs. Practice

### What the Paper Does (Legged Robot)

- Multiple dance motions (stomping, twerking, side-to-side)
- Complex dynamics with foot contacts
- Beat-synchronized dance choreography
- Markov chain motion selection

### What Your System Does (Single Motor)

- Continuous sinusoidal motion
- Simpler dynamics (rotational inertia)
- Music feature-driven amplitude/complexity
- Phase-locked control

### Adaptation for Your System

The core delay compensation works the same:
1. Measure delay between command and feedback
2. Compute correction using PID + feedforward
3. Apply time shift to maintain sync

The difference is **what you're synchronizing:**
- Paper: Discrete dance moves starting at beats
- You: Continuous waveform phase-locked to beats

## References

- **Paper:** Bi, T., et al. "Real-Time Dance Generation to Music for a Legged Robot." IROS 2018.
  DOI: 10.1109/IROS.2018.8593983

- **Beat Tracking:** madmom library (used in your music_analyzer.py)

- **Your Implementation:**
  - [motor_control_music.py](motor_control_music.py) - Phase-locking approach
  - [music_analyzer.py](music_analyzer.py) - Beat detection and music features

## Support

For questions or issues:

1. Check [DELAY_COMPENSATION_GUIDE.md](DELAY_COMPENSATION_GUIDE.md) for detailed explanations
2. Run `python3 delay_compensator.py --demo` to verify installation
3. Review [motor_control_music_with_delay_comp.py](motor_control_music_with_delay_comp.py) for integration examples

## License

This implementation is based on the publicly available research paper.
Adapt freely for your project.
