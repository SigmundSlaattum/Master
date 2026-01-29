# Quick Start: Delay Compensation

## ✅ Installation Verified

Your delay compensation system is now working! Here's how to use it:

## Test the Demo

```bash
cd music_feature_controlled

# Basic demo (no plots)
python3 delay_compensator.py --demo --no-plot

# With plots (requires matplotlib)
python3 delay_compensator.py --demo

# Custom duration
python3 delay_compensator.py --demo --no-plot --duration 60
```

**Expected output:**
```
=== Delay Compensation Demo Results ===
Mean absolute delay: 0.0205 s
Max absolute delay: 0.2000 s
Std deviation: 0.0598 s
Final true delay: 0.0000 s
```

Good results show:
- Mean delay < 0.05s (50ms)
- Final delay near 0.0s
- Std deviation < 0.1s

## Run Integration Example

```bash
python3 motor_control_music_with_delay_comp.py
```

This shows a complete beat-by-beat control loop with delay compensation.

## View Integration Checklist

```bash
python3 motor_control_music_with_delay_comp.py --checklist
```

## File Guide

- **[delay_compensator.py](delay_compensator.py)** - Main module (use this in your code)
- **[DELAY_COMPENSATION_README.md](DELAY_COMPENSATION_README.md)** - Full documentation
- **[DELAY_COMPENSATION_GUIDE.md](DELAY_COMPENSATION_GUIDE.md)** - Integration guide
- **[motor_control_music_with_delay_comp.py](motor_control_music_with_delay_comp.py)** - Example code

## Basic Usage

```python
from delay_compensator import DelayCompensator, estimate_delay_lse
import numpy as np

# 1. Initialize
dc = DelayCompensator(
    motions=['sine_wave'],
    Kp=1.5, Ki=0.3, Kd=0.1
)

# 2. Record signals during motion
reference_positions = []  # What you commanded
actual_positions = []      # What motor did

# ... collect samples ...

# 3. Estimate delay
ref = np.array(reference_positions)
act = np.array(actual_positions)
delay, _, _ = estimate_delay_lse(ref, act, sampling_rate=60)

# 4. Compute compensation
control, fb, ff = dc.compute_control(
    'sine_wave', bpm=120, delay_est=delay, beat_duration=0.5
)

# 5. Apply to next motion
next_start_time = next_beat_time - control
```

## What It Does

1. **Measures** how much your motor lags behind commands
2. **Learns** optimal timing for different tempos
3. **Compensates** by shifting motion start times
4. **Improves** synchronization over time

## Key Features

✅ **LSE delay estimation** - Accurate time-shift detection
✅ **PID feedback** - Reactive correction
✅ **Feedforward lookup** - Proactive compensation
✅ **Persistent learning** - Saves/loads learned delays
✅ **Demo mode** - Test without hardware
✅ **Integration example** - Shows full implementation

## Next Steps

1. **Read** [DELAY_COMPENSATION_README.md](DELAY_COMPENSATION_README.md)
2. **Study** [motor_control_music_with_delay_comp.py](motor_control_music_with_delay_comp.py)
3. **Integrate** into your motor_control_music.py
4. **Test** in simulation mode first
5. **Tune** PID gains for your system

## Troubleshooting

### scipy not available warning
This is OK! The demo will work with simplified signal processing. To get full functionality:
```bash
pip install scipy
```

### matplotlib not available warning
Plots will be disabled. To enable visualization:
```bash
pip install matplotlib
```

### Array length mismatch (FIXED)
The demo had a plotting bug - this is now fixed!

## Performance

Expected results based on paper:
- **Convergence**: 5-10 seconds
- **Accuracy**: < 100ms delay
- **Human perception threshold**: 75ms

Your system should achieve these metrics after tuning.

## Questions?

Check the detailed guides:
- [DELAY_COMPENSATION_README.md](DELAY_COMPENSATION_README.md) - Overview
- [DELAY_COMPENSATION_GUIDE.md](DELAY_COMPENSATION_GUIDE.md) - Technical details

## Status: ✅ Ready to Use

The delay compensation system is fully functional and tested!
