#!/bin/bash
# Installation script for Bluetooth Remote Control feature

echo "=========================================="
echo "Bluetooth Remote Control Setup"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

echo "✅ Python 3 found"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip first."
    exit 1
fi

echo "✅ pip3 found"

# Install bleak
echo ""
echo "Installing Bluetooth dependencies..."
pip3 install bleak>=0.21.0

if [ $? -eq 0 ]; then
    echo "✅ Bluetooth dependencies installed successfully"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Create directories
echo ""
echo "Creating directories..."
mkdir -p src/plots
mkdir -p src/data

echo "✅ Directories created"

# Summary
echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Power on your Arduino Nano BLE remote"
echo "2. Run: cd src && python web_interface.py"
echo "3. Open browser to: http://localhost:5000"
echo "4. Click 'Connect' in Remote Control panel"
echo ""
echo "For detailed instructions, see:"
echo "  - QUICK_START_REMOTE.md (quick guide)"
echo "  - BLUETOOTH_REMOTE_README.md (full docs)"
echo ""
echo "Happy controlling! 🎛️🎵"
