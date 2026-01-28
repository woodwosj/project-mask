#!/bin/bash
# PROJECT MASK - Dependency Installation Script
# This script installs system and Python dependencies for the code replay system.

set -e

echo "=== PROJECT MASK Dependency Installation ==="
echo ""

# Check if running on Ubuntu/Debian
if ! command -v apt &> /dev/null; then
    echo "Warning: apt not found. This script is designed for Ubuntu/Debian systems."
    echo "Please install the following packages manually:"
    echo "  - xdotool"
    echo "  - wmctrl"
    echo ""
fi

# Install system dependencies
echo "Installing system dependencies..."
if command -v apt &> /dev/null; then
    sudo apt update
    sudo apt install -y xdotool wmctrl

    # Optional: install xdpyinfo for screen resolution detection
    sudo apt install -y x11-utils || true
fi

echo ""
echo "Verifying xdotool installation..."
if command -v xdotool &> /dev/null; then
    xdotool version
    echo "xdotool: OK"
else
    echo "Error: xdotool not found!"
    exit 1
fi

echo ""
echo "Verifying wmctrl installation..."
if command -v wmctrl &> /dev/null; then
    echo "wmctrl: OK"
else
    echo "Warning: wmctrl not found. Some window management features may not work."
fi

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."

# Determine the script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip install -r "$PROJECT_DIR/requirements.txt"
else
    echo "Warning: requirements.txt not found at $PROJECT_DIR/requirements.txt"
    echo "Installing dependencies directly..."
    pip install unidiff pyyaml python-xlib
fi

# Verify Python packages
echo ""
echo "Verifying Python packages..."

python3 -c "import unidiff; print(f'unidiff: {unidiff.__version__}')"
python3 -c "import yaml; print(f'pyyaml: OK')"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. Install PROJECT MASK package: pip install -e $PROJECT_DIR"
echo "2. Run input test: python $SCRIPT_DIR/test_input.py"
echo "3. Calibrate Upwork: python $SCRIPT_DIR/calibrate_upwork.py"
echo ""
