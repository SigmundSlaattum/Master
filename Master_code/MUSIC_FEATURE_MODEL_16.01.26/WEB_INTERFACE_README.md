# ODrive Music Control - Web Interface

A modern web-based interface for controlling the ODrive motor synchronized with music.

## Features

- **Song Selection**: Browse and select songs from your music library organized by genre
- **Motor Control**: Full control over ODrive motor operations
  - Connect/Disconnect
  - Calibrate
  - Reset
  - Arm
  - Run/Pause/Stop
- **Configuration**: Adjust all parameters from the web interface
  - Analysis window size
  - Delay compensation toggle
  - Audio synthesis toggle
  - Plotting toggle
  - Music playback toggle
- **Real-time Monitoring**: Live statistics and status updates
  - Position error
  - Maximum error
  - Phase offset
  - Beat lock status
- **System Log**: Real-time logging of all operations
- **Simulation Mode**: Test without hardware

## Installation

1. Install the required dependencies:
```bash
cd /Users/sigmund/Documents/master/Master_code/MUSIC_FEATURE_MODEL
pip install -r requirements_web.txt
```

## Usage

1. Start the web server:
```bash
cd src
python web_interface.py
```

2. Open your web browser and navigate to:
```
http://localhost:5000
```

3. Use the web interface:
   - **Connect**: Click "Connect" to find and connect to your ODrive (or check "Simulation Mode" first)
   - **Select Song**: Choose a genre and song from the dropdowns
   - **Configure**: Adjust settings as needed and click "Update Config"
   - **Arm**: Click "Arm" to prepare the motor
   - **Run**: Click "Run" to start the synchronized motion
   - **Control**: Use Pause/Stop to control execution

## Interface Sections

### Connection Panel
- Simulation Mode checkbox
- Connect/Disconnect buttons
- Reset, Calibrate, and Arm buttons

### Song Selection Panel
- Genre dropdown (Metal, Classic, EDM)
- Song dropdown (populated based on selected genre)

### Configuration Panel
- Analysis Window Size (seconds)
- Delay Compensation toggle
- Audio Synthesis toggle
- Enable Plotting toggle
- Play Music toggle

### Motor Control Panel
- Run button (▶)
- Pause button (⏸)
- Stop button (⏹)
- Exit button (🔄)

### Motor Statistics Panel
Real-time display of:
- Average Position Error
- Maximum Error
- Phase Offset
- Beat Lock Status

### System Log Panel
Displays all system messages with timestamps and color-coding:
- Info messages (blue)
- Success messages (green)
- Warning messages (yellow)
- Error messages (red)

## API Endpoints

The web interface exposes the following REST API endpoints:

- `GET /` - Main web interface
- `GET /api/songs` - Get available songs
- `GET /api/config` - Get current configuration
- `POST /api/config` - Update configuration
- `POST /api/connect` - Connect to ODrive
- `POST /api/calibrate` - Calibrate ODrive
- `POST /api/reset` - Reset ODrive
- `POST /api/arm` - Arm motor
- `POST /api/run` - Start motor control loop
- `POST /api/pause` - Pause/resume motor
- `POST /api/stop` - Stop motor control loop
- `POST /api/disconnect` - Disconnect from ODrive
- `GET /api/status` - Get system status

## WebSocket Events

Real-time updates via Socket.IO:
- `status` - Status messages
- `motor_stats` - Motor statistics updates (every second)

## Network Access

By default, the server binds to `0.0.0.0:5000`, making it accessible from:
- Local machine: `http://localhost:5000`
- Network: `http://<your-ip>:5000`

To restrict to local access only, modify `web_interface.py`:
```python
socketio.run(app, host='127.0.0.1', port=5000, debug=False)
```

## Troubleshooting

### Port Already in Use
If port 5000 is already in use, change it in `web_interface.py`:
```python
socketio.run(app, host='0.0.0.0', port=5001, debug=False)
```

### ODrive Not Found
- Make sure ODrive is connected via USB
- Check that you have permissions to access USB devices
- Try using Simulation Mode for testing

### Music Files Not Loading
- Verify songs are in the `songs/` directory
- Check that file names match those in `music_config.py`

## Security Note

This web interface is intended for local network use only. Do not expose it to the public internet without proper authentication and security measures.

## Comparison with Command Line

### Command Line:
```bash
python motor_control_music.py -sim -dc -w 2.0 -g edm -s 0
```

### Web Interface:
1. Check "Simulation Mode"
2. Select Genre: "EDM"
3. Select Song: First song
4. Set Window Size: 2.0
5. Check "Delay Compensation"
6. Click "Connect" → "Run"

The web interface provides the same functionality with a more intuitive visual interface!
