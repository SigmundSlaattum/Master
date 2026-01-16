# Auto-Reconnect & Max Amplitude Update

## Changes Made

### 1. Automatic Reconnection
The Bluetooth connection now automatically attempts to reconnect when the connection is lost.

#### Features
- **Auto-enabled by default**: Reconnection starts automatically when you click "Connect"
- **Retry interval**: 5 seconds between reconnection attempts
- **Continuous monitoring**: Detects connection loss and attempts to restore it
- **Non-blocking**: Runs in background without affecting motor control
- **Clean state preservation**: Maintains encoder baseline and settings during reconnection

#### How It Works
```
Connect button clicked
  ↓
Initial connection attempt
  ↓
Connected! → Monitor connection
  ↓
Connection lost detected
  ↓
Wait 5 seconds
  ↓
Automatic reconnection attempt
  ↓
Back to "Connected!" (cycle repeats on disconnect)
```

### 2. Maximum Amplitude Limit
Added a configurable maximum amplitude to prevent excessive motion.

#### Features
- **Default max**: 2.0× (double the baseline)
- **Hard limit**: Encoder cannot increase amplitude beyond this value
- **Configurable**: Can be changed via `set_max_amplitude()` method
- **Safe clamping**: Automatically limits amplitude if it would exceed max

## Usage

### Automatic Reconnection
**No user action needed!** The system automatically:
1. Connects when you click "Connect"
2. Monitors the connection continuously
3. Attempts to reconnect every 5 seconds if connection drops
4. Continues this until you click "Disconnect"

### Console Output Examples

#### Initial Connection
```
[BLE] Scanning for devices: Nano_Encoder, Arduino...
[BLE] Found 3 devices:
  - Arduino (AA:BB:CC:DD:EE:FF)
  - iPhone (12:34:56:78:90:AB)
  - None (CD:EF:01:23:45:67)
[BLE] Matched device: Arduino
[BLE] Connecting to: Arduino (AA:BB:CC:DD:EE:FF)
[BLE] Connected successfully
[BLE] Initial encoder position: 42 (amplitude = 1.0)
```

#### Connection Lost & Reconnecting
```
[BLE] Connection lost. Attempting to reconnect in 5.0s...
[BLE] Scanning for devices: Nano_Encoder, Arduino...
[BLE] Found 2 devices:
  - Arduino (AA:BB:CC:DD:EE:FF)
  - iPhone (12:34:56:78:90:AB)
[BLE] Matched device: Arduino
[BLE] Connecting to: Arduino (AA:BB:CC:DD:EE:FF)
[BLE] Connected successfully
[BLE] Initial encoder position: 78 (amplitude = 1.0)
```

#### Max Amplitude Reached
```
[BLE] User amplitude: 1.99×
[BLE] User amplitude: 2.00× (MAX)
(Encoder continues to turn but amplitude stays at 2.00×)
```

## Technical Details

### Auto-Reconnect Implementation

#### Configuration
```python
self.auto_reconnect_enabled: bool = False  # Set to True on connect()
self.reconnect_interval: float = 5.0  # Seconds between attempts
```

#### Connection Loop
```python
while not stopped:
    try:
        connect_to_device()
        while connected:
            monitor_connection()

        if auto_reconnect_enabled:
            wait(5 seconds)
            retry_connection()
        else:
            break
    except error:
        if auto_reconnect_enabled:
            retry()
```

#### State Preservation
- **Encoder baseline**: Reset on reconnection (new connection = new baseline)
- **Direction setting**: Preserved (persists across reconnections)
- **Max amplitude**: Preserved
- **Step size**: Preserved

### Max Amplitude Implementation

#### Clamping Logic
```python
# Calculate raw amplitude
raw_amplitude = 1.0 + (delta * step_size)

# Clamp to range [0.0, max_amplitude]
user_amplitude = max(0.0, min(max_amplitude, raw_amplitude))
```

#### Applied Everywhere
- Encoder position changes
- Direction toggle
- All amplitude calculations

## Behavior Examples

### Example 1: Connection Drops During Performance
```
Timeline:
00:00 - Connect to remote (auto-reconnect: ON)
00:05 - Adjust amplitude to 1.5×
00:10 - Connection drops (Arduino loses power/goes out of range)
00:11 - System logs: "Connection lost. Attempting to reconnect..."
00:16 - First reconnect attempt fails (Arduino still off)
00:21 - Second reconnect attempt fails
00:25 - Arduino powered back on
00:26 - Third reconnect attempt succeeds!
00:27 - Baseline reset (amplitude back to 1.0×)
00:28 - User turns encoder to restore ~1.5×
```

### Example 2: Hitting Max Amplitude
```
Initial: amplitude = 1.0×
Turn +50 clicks: 1.0 + (50 × 0.01) = 1.5×
Turn +50 clicks: 1.5 + (50 × 0.01) = 2.0× (MAX)
Turn +10 clicks: still 2.0× (clamped)
Turn -20 clicks: 2.0 - (20 × 0.01) = 1.8× (below max, changes again)
```

### Example 3: Graceful Disconnect
```
User clicks "Disconnect" button
  ↓
auto_reconnect_enabled = False
  ↓
Connection closes cleanly
  ↓
No reconnection attempts
  ↓
Thread exits
```

## Web Interface Integration

The web interface automatically works with these features:

1. **Auto-reconnect is transparent**: User just sees connection status updates
2. **Max amplitude shows in limits**: Encoder stops increasing at 2.0×
3. **No new UI needed**: Everything works through existing controls

## Benefits

### Auto-Reconnect Benefits
1. ✅ **Robust connection**: Handles intermittent Bluetooth issues
2. ✅ **Hands-free recovery**: No manual reconnection needed
3. ✅ **Performance continuity**: Motion continues even if remote temporarily disconnects
4. ✅ **Range flexibility**: Can move further from Arduino briefly
5. ✅ **Power management**: Survives Arduino power cycles

### Max Amplitude Benefits
1. ✅ **Safety**: Prevents excessive motion that could damage equipment
2. ✅ **Predictable range**: User knows upper limit (0× to 2×)
3. ✅ **Fine control maintained**: Can still use full resolution up to max
4. ✅ **Clear feedback**: Amplitude stops increasing at limit
5. ✅ **Configurable**: Can adjust max if needed

## Configuration Options

### Change Reconnect Interval
```python
bluetooth_controller.reconnect_interval = 10.0  # 10 seconds between attempts
```

### Change Max Amplitude
```python
bluetooth_controller.set_max_amplitude(3.0)  # Allow up to 3.0×
```

### Disable Auto-Reconnect
```python
bluetooth_controller.connect(auto_reconnect=False)  # Manual reconnection only
```

## Comparison: Before vs After

| Feature | Before | After |
|---------|--------|-------|
| Connection drops | Must manually reconnect | Automatic reconnection |
| Max amplitude | Unlimited | 2.0× limit |
| Reconnect interval | N/A | 5 seconds |
| State on reconnect | Lost | Baseline resets |
| Range flexibility | Low (must stay connected) | High (tolerates drops) |
| Safety | User-controlled | Built-in limits |

## Testing Recommendations

### Test Auto-Reconnect
1. Connect to remote
2. Power off Arduino
3. Wait 10 seconds
4. Power on Arduino
5. Verify automatic reconnection
6. Check that baseline resets

### Test Max Amplitude
1. Connect to remote
2. Turn encoder clockwise continuously
3. Verify amplitude stops at 2.00×
4. Turn counter-clockwise
5. Verify amplitude decreases normally

### Test Connection Stability
1. Connect to remote
2. Move Arduino to edge of Bluetooth range
3. Observe connection drops and reconnects
4. Verify motor control continues smoothly

## Notes

- Auto-reconnect is **enabled by default** for better user experience
- Baseline **always resets** on reconnection (by design, for safety)
- Max amplitude can be changed if 2.0× is too restrictive
- Connection monitoring runs every 0.5 seconds (minimal overhead)
- All settings persist across reconnections except baseline

## Troubleshooting

### Issue: Continuous reconnection attempts
**Cause**: Arduino is off or out of range
**Solution**: Move Arduino closer or power it on. The system will auto-connect.

### Issue: Amplitude won't go above 2.0×
**Cause**: Max amplitude limit reached
**Solution**: This is intentional. To increase limit, call `set_max_amplitude(3.0)` or higher.

### Issue: Baseline keeps resetting
**Cause**: Connection is unstable, causing frequent reconnections
**Solution**: Move Arduino closer to computer or check for interference.

## Future Enhancements

Possible improvements:
- [ ] Configurable reconnect interval via UI
- [ ] Visual indicator for "reconnecting" state
- [ ] Option to preserve baseline across reconnections
- [ ] Exponential backoff for reconnection attempts
- [ ] Max amplitude configurable via UI
- [ ] Warning when approaching max amplitude
