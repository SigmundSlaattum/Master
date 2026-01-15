# Phase Nudging Guide

## Overview

The **Phase Nudging** feature allows you to fine-tune the synchronization between motor motion and music by making small real-time adjustments to the phase offset while the motor is running.

## What is Phase Nudging?

Phase nudging lets you incrementally shift the motor's motion timing relative to the music:
- **Lead Ahead (→)**: Motor moves slightly ahead of the beat
- **Lag Behind (←)**: Motor moves slightly behind the beat

This is useful when:
- The motor is mostly synchronized but slightly off
- You want to fine-tune the "feel" of the synchronization
- The automatic phase correction is close but not perfect

## Location

The Phase Nudging panel is located in the main interface grid, below the PID Tuning panel.

## Features

### 1. Current Phase Offset Display
- Shows the current phase offset in radians
- Updates in real-time as you nudge or as the system adjusts
- Synced with the Motor Statistics panel

### 2. Nudge Amount Selector
Three precision levels for different tuning needs:
- **1.0 ms** - Larger adjustments, noticeable changes
- **0.5 ms** - Medium adjustments (default)
- **0.1 ms** - Fine adjustments, subtle changes

### 3. Directional Nudging
- **← Lag Behind**: Delays the motion relative to music (negative phase shift)
- **→ Lead Ahead**: Advances the motion relative to music (positive phase shift)

### 4. Reset Function
- **↺ Reset Phase**: Returns phase offset to 0

## How to Use

### Quick Tuning Workflow

1. **Start playing music** with motor running
2. **Listen and observe** - Is the motor ahead or behind the beat?
3. **Select nudge amount** (start with 0.5ms)
4. **Nudge in the correct direction**:
   - If motor is **ahead** of beat → Click "← Lag Behind"
   - If motor is **behind** beat → Click "→ Lead Ahead"
5. **Repeat** until synchronized
6. **Use finer adjustments** (0.1ms) for final tuning

### Understanding the Math

The phase nudge converts time delay to phase offset:

```
Phase Change (radians) = 2π × frequency × time × direction
```

For example, at 120 BPM (2 Hz):
- 1.0 ms nudge = 2π × 2 × 0.001 = 0.0126 radians
- 0.5 ms nudge = 2π × 2 × 0.0005 = 0.0063 radians
- 0.1 ms nudge = 2π × 2 × 0.0001 = 0.0013 radians

The phase change is **frequency-dependent**, so the same time nudge has different effects at different BPMs.

## When to Use Phase Nudging vs Delay Compensation

### Use Phase Nudging When:
- ✅ Motor is running and you want real-time adjustment
- ✅ You need small, incremental changes
- ✅ Automatic phase correction is close but not perfect
- ✅ You want to experiment with the "feel" of synchronization
- ✅ Fine-tuning during performance

### Use Delay Compensation When:
- ✅ You want automatic continuous correction
- ✅ There's consistent system latency to account for
- ✅ You want the system to self-correct over time
- ✅ You're setting up the system initially

**Best Practice**: Enable Delay Compensation for automatic correction, then use Phase Nudging for final fine-tuning.

## Typical Values

### Small Nudges (0.1 ms)
- For final precision tuning
- When motor is very close to sync
- Subtle feel adjustments

### Medium Nudges (0.5 ms)
- Default and most common
- Good balance of precision and speed
- Noticeable but not jarring changes

### Large Nudges (1.0 ms)
- For larger corrections
- When motor is noticeably off
- Faster coarse tuning

## Phase Offset Interpretation

The phase offset value shows cumulative adjustment:
- **0.000**: No phase adjustment (default)
- **Positive values**: Motion is leading ahead
- **Negative values**: Motion is lagging behind

Note: The automatic phase correction system may also adjust this value continuously if Delay Compensation is enabled.

## Integration with Other Features

### Works With:
- ✅ **Beat Tapping**: Use phase nudging after beat tapping to fine-tune
- ✅ **Delay Compensation**: Both can work together for best results
- ✅ **Motor Statistics**: Monitor phase offset in real-time
- ✅ **Data Recording**: Phase changes are recorded in CSV exports

### Complementary Workflow:
1. Enable Delay Compensation for automatic correction
2. Use Beat Tapping to get initial sync
3. Let system stabilize for a few seconds
4. Use Phase Nudging for final fine-tuning
5. Monitor Motor Statistics to verify improvement

## Limitations

### ⚠️ Important Notes:
- **Requires running motor**: Phase nudging only works while motor is running
- **Not persistent**: Phase adjustments reset when you stop/restart
- **Frequency dependent**: Same time nudge has different effects at different BPMs
- **No effect in simulation mode**: Requires motor controller to be active

### Won't Help If:
- ❌ Motor is grossly out of sync (use calibration/PID tuning first)
- ❌ PID values are way off (tune PID first)
- ❌ System has high jitter/instability (fix root cause first)

## Tips for Best Results

### 1. Start with Automatic Systems
- Enable Delay Compensation
- Use Beat Tapping if available
- Let system stabilize before manual nudging

### 2. Use Appropriate Nudge Amounts
- Start with 0.5ms (default)
- Switch to 0.1ms for final precision
- Use 1.0ms only for larger corrections

### 3. Make Small Incremental Changes
- Don't over-nudge - small changes add up
- Wait a moment between nudges to observe effect
- Listen to both the music and motor sound

### 4. Visual Feedback
- Watch the Beat Locked indicator (✅/❌)
- Monitor Position Error values
- Check if Phase Offset is growing or stable

### 5. Compare Before/After
- Note the phase offset before nudging
- Make adjustment
- Observe if position error improves

## Keyboard Shortcuts

Currently, phase nudging requires clicking buttons in the web interface. For rapid adjustments, you can:
- Click buttons repeatedly for multiple nudges
- Change nudge amount dropdown between clicks
- Use Beat Tapping with 'P' key for coarser phase adjustment

## Troubleshooting

### "Motor not running" Error
- You must start the motor before using phase nudging
- Select a song and click "▶ Run"

### Phase keeps drifting back
- Delay Compensation is actively correcting
- This is normal if enabled
- Your nudge and auto-correction are competing

### Large phase offsets accumulate
- Multiple nudges add up
- Use "↺ Reset Phase" to start fresh
- Check if you're nudging in the wrong direction

### Nudging has no visible effect
- Try larger nudge amount (1.0ms)
- Verify motor is actually running
- Check if position error is improving slightly

### Phase offset jumps suddenly
- Beat Tapping or automatic correction activated
- This is normal system behavior
- Nudge again if needed after it stabilizes

## API Endpoints

For advanced users or automation:

### Get Current Phase
```bash
curl http://localhost:5000/api/phase/get
```

Returns:
```json
{
  "success": true,
  "phase_offset": 0.1234
}
```

### Nudge Phase
```bash
curl -X POST http://localhost:5000/api/phase/nudge \
  -H "Content-Type: application/json" \
  -d '{
    "direction": 1,
    "amount_seconds": 0.0005
  }'
```

Parameters:
- `direction`: 1 for lead ahead, -1 for lag behind
- `amount_seconds`: Time nudge in seconds (0.0001, 0.0005, or 0.001)

### Reset Phase
```bash
curl -X POST http://localhost:5000/api/phase/reset
```

## Best Practices Summary

1. ✅ Use Delay Compensation as baseline
2. ✅ Start with 0.5ms nudges
3. ✅ Make small incremental changes
4. ✅ Wait between nudges to observe
5. ✅ Switch to 0.1ms for final precision
6. ✅ Reset if you over-nudge
7. ✅ Monitor position error for improvement
8. ✅ Combine with beat tapping for best results

## Technical Details

### Phase Calculation
The conversion from time to phase considers the current motion frequency:

```python
frequency = motor_controller.frequency  # Hz (from BPM)
phase_change = 2π × frequency × time_seconds × direction
motor_controller.phase_offset += phase_change
```

This ensures that:
- Nudges are consistent relative to beat timing
- Higher BPM songs require proportionally more phase change
- Time-based interface is intuitive for users

### Update Rate
- Phase offset is applied immediately on each control loop iteration
- Changes take effect within ~16ms (60 Hz control rate)
- Visual feedback updates at 10 Hz via WebSocket
