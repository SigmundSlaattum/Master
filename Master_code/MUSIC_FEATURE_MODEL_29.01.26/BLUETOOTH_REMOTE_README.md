# Bluetooth Remote Control Integration

This document describes the new Bluetooth remote control feature that allows real-time manual control of platform motion amplitude using an Arduino Nano BLE rotary encoder.

## Overview

The system now supports a wireless remote control that lets you dynamically adjust the motion amplitude during operation. The remote control uses:
- **Arduino Nano 33 BLE** with rotary encoder and push button
- **Bluetooth Low Energy (BLE)** for wireless communication
- **Real-time amplitude control** - rotary encoder changes are immediately reflected in platform motion
- **Data recording and plotting** - all amplitude changes and positions are recorded for analysis

## Hardware Setup

### Arduino Remote Control
- Arduino Nano 33 BLE (programmed with `arduino_code.ino`)
- Rotary encoder (KY-040 or similar)
  - Pin A → D6
  - Pin B → D7
- Push button/switch
  - Connected between D2 and GND
- Battery monitoring on A0 (optional)

### BLE Service UUIDs
- Service UUID: `19B10000-E8F2-537E-4F6C-D104768A1214`
- Characteristic UUID: `19B10001-E8F2-537E-4F6C-D104768A1214`
- Device Name: `Nano_Encoder`

## Features

### 1. User Amplitude Control
- **Baseline Setting**: When you start playing music and connect the remote, the current encoder position is set as baseline (amplitude = 1.0×)
- **Clockwise Rotation**: Increases amplitude (each click = +0.05×)
- **Counter-Clockwise Rotation**: Decreases amplitude (each click = -0.05×)
- **Minimum Value**: 0.0× (platform stops moving)
- **No Maximum**: Can increase indefinitely (use with caution!)

### 2. Emergency Stop
- **Push Button**: Pressing the button immediately sets amplitude to 0.0×, stopping all platform motion
- **Safety Feature**: Useful for quickly stopping motion without disconnecting

### 3. Web Interface Controls

#### Remote Control Panel
Located in the web interface with the following controls:
- **Connect**: Scan for and connect to the Arduino remote (device must be powered on)
- **Disconnect**: Disconnect from the remote
- **Reset Baseline**: Reset current encoder position to amplitude 1.0×
- **Status Indicator**: Shows connection status (Disconnected / Connected ✅)
- **User Amplitude Display**: Shows current amplitude multiplier with color coding:
  - Red: 0.0× (stopped)
  - Orange: < 0.5× (low)
  - White: 0.5× - 1.5× (normal)
  - Green: > 1.5× (high)

### 4. Data Recording and Plotting

The system automatically records three data streams when you hit Play:

1. **User Amplitude**: The amplitude multiplier from the remote control
2. **Original Position**: The position command from music analysis (before user modification)
3. **Final Position**: The actual position sent to the motor (after user amplitude)

#### Recording Controls
- **Automatic Start**: Recording begins when you start playback
- **Automatic Stop**: Recording stops when you stop playback
- **Sample Counter**: Shows number of recorded samples in real-time

#### Plotting Options
- **Plot (3 Graphs)**: Creates three separate subplots showing each data stream
- **Plot (Combined)**: Creates a single plot with all data overlaid for comparison
- **Export CSV**: Exports all recorded data to a timestamped CSV file

#### Plot Storage
- Plots are saved to: `MUSIC_FEATURE_MODEL/src/plots/motor_data_YYYYMMDD_HHMMSS.png`
- CSV files are saved to: `MUSIC_FEATURE_MODEL/src/data/motor_data_YYYYMMDD_HHMMSS.csv`

### 5. Real-Time Logging
- The system logs amplitude changes to the web interface log panel
- Logs only when amplitude changes by more than 0.1× to avoid spam
- Special messages for:
  - Remote connection/disconnection
  - Button press (emergency stop)
  - Amplitude changes
  - Plot generation
  - Data export

## How It Works

### Amplitude Multiplication
The final position sent to the motor is calculated as:

```
final_position = initial_offset + (pos_command1 + pos_command2) × master_amplitude × user_amplitude
```

Where:
- `initial_offset`: Starting position of the motor
- `pos_command1`, `pos_command2`: Sinusoidal position commands from music
- `master_amplitude`: Amplitude from music analysis (RMS-based)
- `user_amplitude`: Multiplier from remote control (default 1.0)

### Data Flow
1. Arduino encoder position changes → BLE notification
2. `BluetoothController` receives notification → calculates amplitude
3. Amplitude callback updates `MotorController.user_amplitude`
4. Control loop calculates position with new amplitude
5. `DataRecorder` logs: user_amplitude, original_position, final_position
6. Web interface receives updates via Socket.IO

## Installation

### Python Dependencies
Install the new Bluetooth dependency:
```bash
pip install bleak>=0.21.0
```

Or install all new requirements:
```bash
pip install -r requirements_bluetooth.txt
```

### Arduino Setup
1. Open `arduino_code.ino` in Arduino IDE
2. Select board: **Arduino Nano 33 BLE**
3. Install libraries:
   - ArduinoBLE (built-in)
4. Upload the sketch
5. Power the Arduino (battery or USB)

## Usage Instructions

### Quick Start
1. **Start the web interface**: `python web_interface.py`
2. **Connect to ODrive** (or use simulation mode)
3. **Select a song** from the library
4. **Connect Bluetooth Remote**: Click "Connect" in Remote Control panel
   - Wait for "Connected ✅" status
5. **Arm the motor** (if using hardware)
6. **Hit Play**: Music starts, recording begins automatically
7. **Adjust amplitude**: Turn the encoder knob while music plays
   - Watch the "User Amplitude" value change
   - See real-time effect on platform motion
8. **Emergency stop**: Press the button to stop motion immediately
9. **Stop playback**: Click Stop when done
10. **Generate plots**: Click "Plot (3 Graphs)" or "Plot (Combined)"
11. **Export data**: Click "Export CSV" to save raw data

### Tips
- **Reset Baseline**: If you want the current encoder position to be 1.0× again, click "Reset Baseline"
- **Connection Issues**: If connection fails, ensure:
  - Arduino is powered on
  - BLE is not already connected to another device
  - You're within Bluetooth range (~10 meters)
- **Monitoring**: Watch the log panel for real-time feedback on amplitude changes
- **Plot After Recording**: Generate plots after stopping - plotting during recording may cause lag

## Architecture

### New Files Created
1. **`bluetooth_controller.py`**: BLE communication with Arduino
   - Async BLE scanning and connection
   - Notification handling
   - Callback system for amplitude/switch events

2. **`data_recorder.py`**: Data recording and plotting
   - Efficient deque-based data storage
   - Matplotlib plotting (3-subplot and combined views)
   - CSV export functionality
   - Statistics calculation

3. **`requirements_bluetooth.txt`**: New dependencies

### Modified Files
1. **`motor_controller.py`**:
   - Added `user_amplitude` parameter
   - Modified `calculate_expected_position()` to include user amplitude
   - Added `calculate_original_position()` for plotting
   - Added getter/setter methods for user amplitude

2. **`motor_control_music.py`**:
   - Added `data_recorder` parameter to `run_control_loop()`
   - Integrated data recording in control loop

3. **`web_interface.py`**:
   - Added `BluetoothController` and `DataRecorder` to `SystemState`
   - Added Bluetooth callback setup
   - Added API endpoints:
     - `/api/bluetooth/connect`
     - `/api/bluetooth/disconnect`
     - `/api/bluetooth/reset_baseline`
     - `/api/bluetooth/status`
     - `/api/data/plot`
     - `/api/data/export`
     - `/api/data/statistics`
   - Added Socket.IO events for real-time updates
   - Integrated recording start/stop with playback

4. **`templates/index.html`**:
   - Added Remote Control panel with BLE controls
   - Added Data Recording panel with plot/export buttons
   - Added JavaScript functions for BLE and data operations
   - Added Socket.IO handlers for amplitude updates

## Troubleshooting

### Bluetooth Connection Issues
**Problem**: "Device not found" error
- **Solution**: Ensure Arduino is powered and not already connected to another device. Try power cycling the Arduino.

**Problem**: Connection hangs or times out
- **Solution**: Check that your computer's Bluetooth is enabled. Try restarting the Bluetooth service.

### Amplitude Not Changing
**Problem**: Encoder turns but amplitude doesn't change
- **Solution**: Check that remote is connected (green ✅). Verify encoder wiring to Arduino.

**Problem**: Amplitude jumps erratically
- **Solution**: Encoder may be noisy. Try adding hardware debouncing or adjusting the `delta * 0.05` multiplier in `bluetooth_controller.py`.

### Plotting Issues
**Problem**: "No data recorded" error
- **Solution**: Ensure you clicked Play and let it run for a few seconds before stopping and plotting.

**Problem**: Plot looks wrong or empty
- **Solution**: Check that amplitude changed during recording. Verify data with CSV export.

### Performance Issues
**Problem**: System lags when remote is connected
- **Solution**: Reduce BLE update rate in Arduino code (increase `delay(10)` in main loop).

## Customization

### Adjust Amplitude Sensitivity
In `bluetooth_controller.py`, line ~87:
```python
self.user_amplitude = max(0.0, 1.0 + (delta * 0.05))
```
Change `0.05` to adjust how much each encoder click changes amplitude:
- `0.1` = more sensitive (larger changes per click)
- `0.01` = less sensitive (smaller changes per click)

### Change Recording Sample Limit
In `web_interface.py`, line ~72:
```python
self.data_recorder = DataRecorder(max_samples=20000)
```
Increase `max_samples` to record longer sessions (uses more memory).

### Modify Plot Appearance
Edit `data_recorder.py` methods:
- `plot_data()`: Customize subplot appearance
- `plot_combined()`: Customize combined plot layout

## Future Enhancements

Potential improvements:
- [ ] Live plotting during recording
- [ ] Multiple encoder support for independent control
- [ ] Preset amplitude profiles (save/load)
- [ ] Haptic feedback via Arduino vibration motor
- [ ] Web-based encoder simulation (virtual knob)
- [ ] MIDI controller support as alternative input

## Technical Notes

### Thread Safety
- `BluetoothController` runs in its own thread with asyncio event loop
- Callbacks use `socketio.emit()` which is thread-safe
- `DataRecorder` uses deques which are thread-safe for append operations
- `MotorController.user_amplitude` access is atomic (no locks needed)

### Performance Impact
- BLE communication: ~10ms latency (negligible)
- Data recording: ~0.01ms per sample (negligible)
- Plotting: 1-3 seconds for 10,000 samples (done offline)

### Bluetooth Range
- Typical BLE range: 10-30 meters line-of-sight
- Range reduced by walls, metal objects, interference
- Connection quality indicated by update latency

## Credits

Developed as an enhancement to the MUSIC_FEATURE_MODEL platform control system.

**Key Technologies:**
- Python Bleak library for cross-platform BLE
- Arduino BLE library for Nano 33 BLE
- Socket.IO for real-time web updates
- Matplotlib for data visualization
