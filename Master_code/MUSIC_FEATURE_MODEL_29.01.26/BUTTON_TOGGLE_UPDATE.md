# Button Toggle Update

## New Behavior: Pause/Resume Instead of Just Stop

The push button on the Arduino remote now acts as a **toggle** between pause and resume, preserving your amplitude setting.

## How It Works

### First Press (Pause)
- **Current state**: Amplitude is active (e.g., 1.5×)
- **Button pressed**:
  - Saves current amplitude (1.5×)
  - Sets amplitude to 0 (platform stops)
  - Log: "⏸️ Remote switch: Motion paused"

### Second Press (Resume)
- **Current state**: Amplitude is 0 (paused)
- **Button pressed**:
  - Restores previous amplitude (1.5×)
  - Platform resumes motion at previous level
  - Log: "▶️ Remote switch: Motion resumed (amplitude = 1.5×)"

## Use Cases

### Quick Pause During Performance
```
User: Turns encoder to 1.8× for high energy section
User: Presses button → Motion pauses (saves 1.8×)
User: Waits for quiet section...
User: Presses button → Motion resumes at 1.8×
```

### Emergency Stop and Continue
```
User: Something unexpected happens
User: Presses button → Immediate stop
User: Checks everything is okay
User: Presses button → Resumes exactly where they left off
```

### Comparing With/Without Motion
```
User: Adjusts to 1.3×
User: Presses button → See platform without motion
User: Presses button → See platform with same 1.3× motion
```

## Edge Cases

1. **No previous amplitude saved**
   - If you press button when amplitude is 0 and nothing was saved
   - Defaults to 1.0× (baseline)

2. **Multiple presses while at 0**
   - Pressing button multiple times while paused
   - Always restores the same saved value

3. **Encoder changes during pause**
   - Turning encoder while paused (amplitude = 0)
   - Resume still restores the saved value
   - After resume, encoder position determines new amplitude

## Technical Implementation

### State Variables
```python
self.user_amplitude: float = 1.0  # Current amplitude
self.amplitude_before_stop: Optional[float] = None  # Saved amplitude
```

### Toggle Logic
```python
if user_amplitude != 0.0:
    # Pause: Save and set to 0
    amplitude_before_stop = user_amplitude
    user_amplitude = 0.0
else:
    # Resume: Restore saved value
    user_amplitude = amplitude_before_stop or 1.0
```

### Visual Feedback
- **Pause**: User Amplitude display shows 0.00× (red)
- **Resume**: User Amplitude display shows restored value (color coded)
- **Log messages**: Different icons and messages for pause vs resume
  - ⏸️ = Pause
  - ▶️ = Resume

## Comparison: Old vs New Behavior

| Aspect | Old Behavior | New Behavior |
|--------|--------------|--------------|
| First press | Set to 0 | Set to 0 (save value) |
| Second press | Set to 0 again | Restore saved value |
| Third press | Set to 0 again | Set to 0 (save again) |
| Use case | Emergency stop only | Pause/resume workflow |
| Flexibility | Low | High |

## Examples

### Example 1: Simple Pause/Resume
```
Initial: amplitude = 1.2×
Press 1: amplitude = 0.0× (saved: 1.2×) → PAUSED
Press 2: amplitude = 1.2× → RESUMED
Press 3: amplitude = 0.0× (saved: 1.2×) → PAUSED AGAIN
Press 4: amplitude = 1.2× → RESUMED AGAIN
```

### Example 2: Pause with Encoder Movement
```
Initial: amplitude = 1.5×
Press 1: amplitude = 0.0× (saved: 1.5×) → PAUSED
Turn encoder +50 clicks: still 0.0× (encoder ignored while paused)
Press 2: amplitude = 1.5× (not affected by encoder turns) → RESUMED
Now encoder position matters: turning changes from 1.5× baseline
```

### Example 3: Multiple Amplitude Levels
```
Adjust to 2.0×
Press: 0.0× (saved: 2.0×)
Press: 2.0× (resumed)
Adjust to 0.8×
Press: 0.0× (saved: 0.8×)
Press: 0.8× (resumed)
```

## Benefits

1. ✅ **Preserve settings** - Don't lose your carefully adjusted amplitude
2. ✅ **Quick A/B comparison** - Toggle motion on/off to see difference
3. ✅ **Performance workflow** - Pause during transitions, resume for action
4. ✅ **Safety** - Still works as emergency stop on first press
5. ✅ **Intuitive** - Pause/resume behavior matches common expectations
6. ✅ **Flexible** - Can pause and resume as many times as needed

## User Feedback

The system provides clear feedback at each step:

1. **First press (pause)**:
   - Amplitude display: 1.5× → 0.00× (turns red)
   - Log: "⏸️ Remote switch: Motion paused (amplitude = 0)"
   - Platform: Stops moving

2. **Second press (resume)**:
   - Amplitude display: 0.00× → 1.5× (color coded)
   - Log: "▶️ Remote switch: Motion resumed (amplitude = 1.5×)"
   - Platform: Resumes motion at 1.5×

## Implementation Note

The saved amplitude (`amplitude_before_stop`) persists throughout the connection session but resets on disconnect. This ensures clean state management and predictable behavior.
