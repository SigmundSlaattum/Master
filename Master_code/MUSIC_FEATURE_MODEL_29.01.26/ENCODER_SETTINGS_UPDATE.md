# Encoder Settings Update

## Changes Made

### 1. Reduced Step Size
- **Previous value**: 0.05× per encoder click
- **New value**: 0.01× per encoder click
- **Effect**: Much finer control - requires 100 clicks to go from 1.0× to 2.0× (vs 20 clicks before)

### 2. Direction Toggle Feature
Added ability to swap encoder direction for user preference.

#### Default (Normal) Direction:
- Clockwise rotation = **increase** amplitude
- Counter-clockwise rotation = **decrease** amplitude

#### Reversed Direction:
- Clockwise rotation = **decrease** amplitude
- Counter-clockwise rotation = **increase** amplitude

## User Interface

### New Elements
1. **Encoder Direction Display**
   - Shows current direction mode
   - "Normal ↻" (white) - default behavior
   - "Reversed ↺" (orange) - swapped behavior

2. **"↻ Swap Direction" Button**
   - Click to toggle between normal and reversed
   - Immediately recalculates amplitude with new direction
   - Logs direction change to system log

### Remote Control Panel Layout
```
Connection: [status]     User Amplitude: [X.XX×]
Encoder Direction: [Normal ↻ / Reversed ↺]

[Connect] [Disconnect] [Reset Baseline] [↻ Swap Direction]
```

## Technical Details

### Configuration Parameters
Both settings are stored in `BluetoothController`:
- `encoder_step_size`: 0.01 (configurable via `set_step_size()`)
- `encoder_direction_reversed`: False by default (toggles via `toggle_direction()`)

### Amplitude Calculation
```python
delta = encoder_value - initial_encoder_value
if encoder_direction_reversed:
    delta = -delta
user_amplitude = max(0.0, 1.0 + (delta * encoder_step_size))
```

### API Endpoint
- **URL**: `/api/bluetooth/toggle_direction`
- **Method**: POST
- **Returns**: `{ success: true, direction_reversed: bool }`

## Usage Examples

### Scenario 1: Fine-tuning amplitude
With 0.01 step size:
- Turn 10 clicks clockwise → 1.10×
- Turn 20 clicks clockwise → 1.20×
- Turn 50 clicks counter-clockwise from baseline → 0.50×

### Scenario 2: User prefers reversed direction
1. Connect to remote
2. Click "↻ Swap Direction" button
3. Now clockwise decreases amplitude
4. Direction preference persists until disconnect

### Scenario 3: Quickly return to baseline
1. Turn encoder back to roughly starting position
2. Click "Reset Baseline" to set current position as 1.0×
3. Continue adjusting from new baseline

## Comparison

| Feature | Before | After |
|---------|--------|-------|
| Step size | 0.05× | 0.01× |
| Clicks for +0.5× | 10 | 50 |
| Direction swap | No | Yes |
| Precision | Coarse | Fine |
| User flexibility | Low | High |

## Implementation Files Modified

1. **bluetooth_controller.py**
   - Added `encoder_step_size` parameter (0.01)
   - Added `encoder_direction_reversed` flag
   - Modified amplitude calculation to apply direction
   - Added `toggle_direction()` method
   - Added `set_step_size()` method
   - Updated `get_status()` to return direction info

2. **web_interface.py**
   - Added `/api/bluetooth/toggle_direction` endpoint

3. **templates/index.html**
   - Added "Encoder Direction" status display
   - Added "↻ Swap Direction" button
   - Added `toggleEncoderDirection()` JavaScript function
   - Added visual feedback (color change when reversed)

## Benefits

1. **Finer Control**: 0.01 steps allow precise amplitude adjustments
2. **User Preference**: Direction toggle accommodates different user expectations
3. **Live Update**: Direction toggle immediately applies to current position
4. **Visual Feedback**: Direction indicator shows current mode
5. **Persistent State**: Direction preference maintained during session

## Notes

- Direction toggle works even while motor is running
- Changing direction recalculates amplitude immediately
- Direction resets to "Normal" on disconnect/reconnect
- Step size can be programmatically changed via `set_step_size()` if needed

## Testing

To test the new features:
1. Connect remote control
2. Turn encoder 100 clicks clockwise → should reach ~2.0×
3. Click "↻ Swap Direction"
4. Turn encoder 50 clicks clockwise → should reach ~1.5×
5. Click "↻ Swap Direction" again → back to normal
6. Verify direction indicator updates correctly
