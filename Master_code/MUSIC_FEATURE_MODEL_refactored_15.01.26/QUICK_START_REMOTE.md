# Quick Start Guide - Bluetooth Remote Control

## 5-Minute Setup

### 1. Install Dependencies
```bash
cd MUSIC_FEATURE_MODEL
pip install bleak
```

### 2. Power On Arduino
- Plug in your Arduino Nano BLE remote control
- Wait for the BLE service to start (LED should blink)

### 3. Start Web Interface
```bash
cd src
python web_interface.py
```
Open browser to: http://localhost:5000

### 4. Basic Operation

1. **Connect System**:
   - Check "Simulation Mode" (or connect to real ODrive)
   - Click "Connect"

2. **Connect Remote**:
   - In "Remote Control (BLE)" panel
   - Click "Connect"
   - Wait for "Connected ✅"

3. **Select Music**:
   - Choose Genre: "edm" (or your preference)
   - Choose Song: any available song

4. **Start Playing**:
   - Click "▶ Run"
   - Music starts, recording begins automatically
   - Encoder is set to baseline (1.0×)

5. **Control Amplitude**:
   - Turn encoder clockwise → amplitude increases
   - Turn encoder counter-clockwise → amplitude decreases
   - Watch "User Amplitude" display update
   - Press button → emergency stop (amplitude = 0)

6. **Stop and Analyze**:
   - Click "⏹ Stop"
   - In "Data Recording" panel:
     - Click "📈 Plot (3 Graphs)" to see all data
     - Click "💾 Export CSV" to save raw data

## Understanding the Display

### User Amplitude Colors
- 🔴 **Red (0.0×)**: Platform stopped
- 🟠 **Orange (< 0.5×)**: Low amplitude
- ⚪ **White (0.5-1.5×)**: Normal range
- 🟢 **Green (> 1.5×)**: High amplitude

### What Gets Recorded
Every control cycle (~60 Hz), the system records:
1. **User Amplitude**: Your encoder setting
2. **Original Position**: What music analysis wanted
3. **Final Position**: What actually got sent (original × user_amplitude)

## Common Actions

### Reset Encoder to 1.0×
If you want current position to be "neutral" again:
- Click "Reset Baseline" button
- Current encoder position becomes 1.0×

### Emergency Stop
Two ways:
1. Press the button on Arduino → amplitude = 0
2. Turn encoder all the way down to 0

### View Plots
After stopping:
- **3 Graphs**: Shows amplitude, original position, and final position separately
- **Combined**: Overlays all data on one plot
- Files saved to: `src/plots/motor_data_TIMESTAMP.png`

### Export Data
- Click "Export CSV"
- File saved to: `src/data/motor_data_TIMESTAMP.csv`
- Columns: Time, User Amplitude, Original Position, Final Position

## Troubleshooting

### "Device not found"
- ✅ Arduino powered on?
- ✅ Arduino running `arduino_code.ino`?
- ✅ Not connected to another device?
- Try: Power cycle the Arduino

### Encoder doesn't work
- ✅ Connected status shows "Connected ✅"?
- ✅ Check wiring: A→D6, B→D7, GND→GND
- Try: Turn encoder and watch Serial Monitor on Arduino

### No data to plot
- ✅ Did you click "Run" before trying to plot?
- ✅ Did you let it run for at least a few seconds?
- ✅ Check "Recorded Samples" counter - should be > 0

## Tips & Tricks

1. **Start at 1.0×**: Always start with encoder at baseline, then adjust up/down
2. **Small Changes**: Each click = 0.05×, so 10 clicks = ±0.5×
3. **Watch Logs**: System log shows amplitude changes for feedback
4. **Multiple Runs**: You can run, stop, plot, then run again - data clears on each run
5. **Compare Plots**: Use Combined plot to see how your input affected the output

## What's Happening Under the Hood

```
Music Analysis → Master Amplitude (from RMS)
                        ↓
Remote Control → User Amplitude (from encoder)
                        ↓
            Final Position = Music × User Amplitude
                        ↓
                  Motor Command
```

Your encoder multiplies whatever the music analysis calculated!

## Next Steps

- Read full documentation: [BLUETOOTH_REMOTE_README.md](BLUETOOTH_REMOTE_README.md)
- Try different songs and encoder patterns
- Analyze your control style with the plots
- Experiment with different amplitude ranges

Enjoy your remote-controlled music platform! 🎵🎛️
