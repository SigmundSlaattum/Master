# PID Tuning Tool for Music-Synchronized Motor Control

## Overview

This tool helps you tune the PID constants for optimal motor synchronization with music features. It runs systematic tests and provides performance metrics to find the best PID settings.

## What Gets Tuned

The ODrive position controller uses three main parameters:

1. **pos_gain** (P term): Controls position tracking stiffness
   - Higher = faster response, but can cause oscillation
   - Lower = smoother motion, but more lag

2. **vel_gain** (D term): Damping/velocity feedback
   - Higher = more damping, reduces oscillation
   - Lower = less damping, faster but potentially unstable

3. **vel_integrator_gain** (I term): Eliminates steady-state error
   - Higher = faster error correction, but can cause overshoot
   - Lower = slower correction, more stable

## Usage

### 1. Single Test (Current PID Values)

Test your current PID settings with a sine wave:

```bash
python pid_tuning_tool.py -a 5.0 -f 2.0 -d 10.0
```

Arguments:
- `-a, --amplitude`: Sine wave amplitude in turns (default: 5.0)
- `-f, --frequency`: Sine wave frequency in Hz (default: 2.0)
- `-d, --duration`: Test duration in seconds (default: 5.0)

### 2. Step Response Test

Test transient response to step changes:

```bash
python pid_tuning_tool.py --step --step_size 10.0 -d 5.0
```

This is useful for evaluating:
- Rise time (how fast it responds)
- Settling time (how long until stable)
- Overshoot (how much it overshoots target)

### 3. Auto-Tuning Mode (Recommended)

Automatically test multiple PID combinations and find the best one:

```bash
python pid_tuning_tool.py --auto -a 5.0 -f 2.0 -d 5.0
```

This will:
- Test 48 different PID combinations
- Compare all results
- Recommend the best settings
- Generate comparison plots

The auto-tune tests these ranges:
- `pos_gain`: [20, 30, 40, 50]
- `vel_gain`: [0.05, 0.1, 0.15, 0.2]
- `vel_integrator_gain`: [0.0, 0.1, 0.2]

## Performance Metrics

The tool evaluates:

1. **RMS Error**: Root-mean-square tracking error (primary metric)
2. **Max Error**: Maximum absolute error during test
3. **MAE**: Mean absolute error
4. **Phase Lag**: Delay between command and actual position
5. **Settling Time**: Time to reach steady-state
6. **Overshoot**: How much the motor overshoots target

## Understanding Results

### For Music Synchronization

You want:
- **Low RMS error** (< 0.01 turns ideal)
- **Low phase lag** (< 20ms for good sync)
- **Minimal overshoot** (< 5%)
- **Fast settling** (< 0.5s)

### Trade-offs

- **Too much P (pos_gain)**: Oscillation, ringing
- **Too little P**: Sluggish, high error
- **Too much D (vel_gain)**: Over-damped, slow
- **Too little D**: Under-damped, oscillatory
- **Too much I (vel_integrator_gain)**: Overshoot, instability
- **Too little I**: Steady-state error

## Example Output

```
================================ BEST RESULT ================================
  pos_gain = 40
  vel_gain = 0.15
  vel_integrator_gain = 0.1
  RMS Error = 0.00234 turns
=============================================================================
```

## Applying Results

After finding optimal values, update them in [odrive_controller.py:229](odrive_controller.py#L229):

```python
odrv0.axis0.controller.config.pos_gain = 40  # Update this
odrv0.axis0.controller.config.vel_gain = 0.15  # And this
odrv0.axis0.controller.config.vel_integrator_gain = 0.1  # And this
```

Or apply them dynamically at runtime.

## Tips

1. **Start with auto-tuning** to get a baseline
2. **Test at music BPM frequencies** (e.g., 120 BPM = 2 Hz)
3. **Use realistic amplitudes** matching your application
4. **Check plots** for oscillations and phase lag
5. **Verify stability** across different songs/BPMs

## Troubleshooting

### Motor oscillates during test
- Reduce `pos_gain`
- Increase `vel_gain`

### Motor is sluggish/laggy
- Increase `pos_gain`
- Reduce `vel_gain`

### Steady-state error (doesn't reach target)
- Increase `vel_integrator_gain`
- But be careful - too much causes instability

### ODrive errors during test
- Reduce amplitude or frequency
- Check vel_limit is high enough
- Verify brake resistor configuration

## Safety

- Motor will return to initial position between tests
- Press Ctrl+C to abort any test
- Motor returns to IDLE state at end
- All results are logged and plotted

## Output Files

Results saved to `plots/` directory:
- `pid_tuning_comparison.png`: Visual comparison of all tests
