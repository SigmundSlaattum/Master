#!/bin/bash
# Setup script for Music-Motor Sync Controller
# Installs all Python dependencies and verifies the environment.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "Music-Motor Sync Controller - Setup"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

echo "Python 3 found: $(python3 --version)"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "pip3 is not installed. Please install pip first."
    exit 1
fi

echo "pip3 found: $(pip3 --version)"

# Install all dependencies from requirements.txt
echo ""
echo "Installing dependencies from requirements.txt..."
pip3 install -r "$SCRIPT_DIR/requirements.txt"

if [ $? -eq 0 ]; then
    echo ""
    echo "All dependencies installed successfully"
else
    echo ""
    echo "Failed to install dependencies"
    exit 1
fi

# Verify key imports
echo ""
echo "Verifying key packages..."
python3 -c "import numpy; print('  numpy', numpy.__version__)" 2>/dev/null && \
python3 -c "import scipy; print('  scipy', scipy.__version__)" 2>/dev/null && \
python3 -c "import sounddevice; print('  sounddevice', sounddevice.__version__)" 2>/dev/null && \
python3 -c "import librosa; print('  librosa', librosa.__version__)" 2>/dev/null && \
python3 -c "import flask; print('  flask', flask.__version__)" 2>/dev/null && \
python3 -c "import flask_socketio; print('  flask-socketio', flask_socketio.__version__)" 2>/dev/null && \
python3 -c "import bleak; print('  bleak', bleak.__version__)" 2>/dev/null && \
python3 -c "import matplotlib; print('  matplotlib', matplotlib.__version__)" 2>/dev/null && \
python3 -c "import odrive; print('  odrive (installed)')" 2>/dev/null

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To run the system:"
echo "  1. Connect the ODrive motor controller via USB"
echo "  2. Start the web interface:"
echo "       cd $PROJECT_DIR/src && python3 web/app.py"
echo "  3. Open browser to: http://localhost:5000"
echo ""
echo "To prepare a new song:"
echo "  cd $PROJECT_DIR/src && python3 offline/prepare_song.py /path/to/song.mp3 --name \"Song Title\""
echo ""
echo "For documentation, see: $PROJECT_DIR/Readme_and_guides/"
echo ""
