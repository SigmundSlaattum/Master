# Web Interface PID Tuning Guide

## Overview

The web interface now includes a **PID Tuning** panel that allows you to adjust motor control parameters in real-time without restarting the system or calling the full configuration function.

## Location

The PID Tuning panel is located in the main interface grid, next to the Remote Control panel.

## Features

### 1. Live PID Value Display
- Shows current PID values from the ODrive
- Values are displayed next to each parameter label
- Auto-refreshes when you connect or refresh the page

### 2. Direct PID Updates
- Changes are applied **immediately** to the ODrive
- **No save/reboot required** - perfect for live tuning
- Values are validated before being sent

### 3. Parameters

#### Position Gain (P)
- **Range**: 0 to 200
- **Default**: 50 (from your config)
- **What it does**: Controls position tracking stiffness
- **Higher**: Faster response, may oscillate
- **Lower**: Smoother motion, more lag

#### Velocity Gain (D)
- **Range**: 0 to 2.0
- **Default**: ~0.16 (ODrive default)
- **What it does**: Provides damping/velocity feedback
- **Higher**: More damping, less oscillation
- **Lower**: Less damping, potentially unstable

#### Velocity Integrator Gain (I)
- **Range**: 0 to 1.0
- **Default**: ~0.5 (ODrive default)
- **What it does**: Eliminates steady-state error
- **Higher**: Faster error correction, may overshoot
- **Lower**: Slower correction, more stable

## How to Use

### Initial Setup
1. Connect to ODrive (hardware mode)
2. Arm the motor
3. The PID values will automatically load

### Tuning Workflow

#### Method 1: Quick Adjustments (Recommended)
1. Run a song to see current motor behavior
2. While running, adjust PID values in the panel
3. Click **"✓ Apply PID"** to update immediately
4. Observe the changes in motor behavior
5. Repeat until satisfied

#### Method 2: Systematic Tuning
1. Use the standalone `pid_tuning_tool.py` to find optimal values
2. Enter those values in the web interface
3. Click **"✓ Apply PID"** to use them
4. Test with various songs

### Buttons

- **✓ Apply PID**: Apply the entered values to the ODrive immediately
- **🔄 Refresh**: Reload current values from the ODrive

## Important Notes

### ⚠️ Live Tuning Safety
- PID changes are applied **immediately** without saving to ODrive memory
- Values are **not persistent** - they reset when you reboot the ODrive
- This is **intentional** for safe experimentation

### 💾 Making Changes Permanent
If you find PID values you like and want to save them:

1. Update them in [odrive_controller.py:229](odrive_controller.py#L229):
   ```python
   odrv0.axis0.controller.config.pos_gain = 50  # Your value
   odrv0.axis0.controller.config.vel_gain = 0.2  # Your value
   odrv0.axis0.controller.config.vel_integrator_gain = 0.3  # Your value
   ```

2. Or save them directly via ODrive:
   ```python
   odrv0.save_configuration()
   odrv0.reboot()
   ```

### 🚫 Limitations
- **Not available in simulation mode** - requires actual ODrive hardware
- **No history tracking** - consider noting good values manually
- **Validation ranges** are enforced to prevent obviously bad values

## Tuning Tips for Music Synchronization

### For Tight Synchronization
- Higher pos_gain (60-100)
- Moderate vel_gain (0.2-0.5)
- Low vel_integrator_gain (0.0-0.2)

### For Smooth Motion
- Moderate pos_gain (30-50)
- Low vel_gain (0.1-0.2)
- Very low vel_integrator_gain (0.0-0.1)

### For Fast Songs (>140 BPM)
- Higher pos_gain and vel_gain
- Ensure vel_gain increases with pos_gain to prevent oscillation

### For Slow Songs (<100 BPM)
- Lower pos_gain acceptable
- Lower vel_gain for smoother motion

## Monitoring Performance

Watch these indicators while tuning:

1. **Motor Statistics Panel**:
   - Position Error (lower is better)
   - Max Error (should be < 0.01 turns)
   - Phase Offset (adjust with Delay Compensation)
   - Beat Locked status

2. **System Log**:
   - Look for error messages
   - Watch for PID update confirmations

3. **Physical Motor**:
   - Listen for humming/buzzing (sign of oscillation)
   - Watch for smooth vs jerky motion
   - Feel for vibration

## Integration with PID Tuning Tool

The web interface works perfectly with the standalone tuning tool:

1. Run `pid_tuning_tool.py --auto` to find optimal values
2. Note the best PID combination from the comparison table
3. Enter those values in the web interface
4. Test with real music playback
5. Fine-tune if needed

## API Endpoints

For advanced users or custom scripts:

### Get Current PID Values
```bash
curl http://localhost:5000/api/pid/get
```

Returns:
```json
{
  "success": true,
  "pid": {
    "pos_gain": 50.0,
    "vel_gain": 0.16,
    "vel_integrator_gain": 0.5
  }
}
```

### Set PID Values
```bash
curl -X POST http://localhost:5000/api/pid/set \
  -H "Content-Type: application/json" \
  -d '{
    "pos_gain": 60,
    "vel_gain": 0.25,
    "vel_integrator_gain": 0.15
  }'
```

## Troubleshooting

### "PID tuning not available in simulation mode"
- You need to connect to actual ODrive hardware
- Uncheck "Simulation Mode" before connecting

### Values don't seem to apply
- Click the "🔄 Refresh" button to verify current values
- Check System Log for error messages
- Ensure motor is armed (not just connected)

### Motor behaves erratically after PID change
- Click "🔄 Refresh" to restore original values
- Or restart the web interface to load defaults
- Use more conservative (lower) values

### Changes reset after stopping/starting
- This is expected - values are not saved to ODrive flash
- Apply your preferred values each session
- Or update the configuration file for persistence

## Best Practices

1. **Start conservative**: Begin with lower values and increase gradually
2. **Test incrementally**: Make small changes and observe
3. **Document findings**: Note combinations that work well for different songs
4. **Use Data Recording**: Export CSV data to analyze PID performance
5. **Combine with plots**: Generate plots to visualize tracking error
