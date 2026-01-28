#!/bin/bash
# PROJECT MASK - Raspberry Pi 5 Setup Script
# Sets up Ubuntu on Raspberry Pi 5 for code replay with Upwork time tracking.

set -e

echo "=== PROJECT MASK - Raspberry Pi 5 Setup ==="
echo ""

# Check if running on ARM64
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ]; then
    echo "Warning: This script is designed for ARM64 (aarch64)."
    echo "Detected architecture: $ARCH"
    echo ""
fi

# Check if running on Raspberry Pi
if [ -f /proc/device-tree/model ]; then
    MODEL=$(tr -d '\0' < /proc/device-tree/model)
    echo "Detected: $MODEL"
    echo ""
fi

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install X11 and desktop essentials
echo ""
echo "Installing X11 and desktop dependencies..."
sudo apt install -y \
    xdotool \
    wmctrl \
    x11-utils \
    x11-xserver-utils \
    firefox \
    git

# Install Python and pip
echo ""
echo "Installing Python dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv

# Create virtual environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

echo ""
echo "Creating Python virtual environment at $VENV_DIR..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# Install Python packages
echo ""
echo "Installing Python packages..."
pip install --upgrade pip
pip install -r "$PROJECT_DIR/requirements.txt"
pip install -e "$PROJECT_DIR"

# Install VS Code for ARM64
echo ""
echo "Installing VS Code for ARM64..."
if ! command -v code &> /dev/null; then
    # Download VS Code .deb for ARM64
    wget -O /tmp/vscode.deb "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-arm64"
    sudo apt install -y /tmp/vscode.deb
    rm /tmp/vscode.deb
else
    echo "VS Code already installed."
fi

# Verify installations
echo ""
echo "=== Verifying installations ==="

echo -n "xdotool: "
if command -v xdotool &> /dev/null; then
    xdotool version | head -1
else
    echo "MISSING!"
fi

echo -n "wmctrl: "
if command -v wmctrl &> /dev/null; then
    echo "OK"
else
    echo "MISSING!"
fi

echo -n "VS Code: "
if command -v code &> /dev/null; then
    code --version | head -1
else
    echo "MISSING!"
fi

echo -n "Python: "
python3 --version

echo -n "unidiff: "
python3 -c "import unidiff; print(unidiff.__version__)"

echo -n "pyyaml: "
python3 -c "import yaml; print('OK')"

# Check display server
echo ""
echo "=== Display Server ==="
if [ -n "$DISPLAY" ]; then
    echo "DISPLAY=$DISPLAY"
    echo "Session type: ${XDG_SESSION_TYPE:-unknown}"
    if [ "${XDG_SESSION_TYPE}" = "wayland" ]; then
        echo ""
        echo "WARNING: Wayland detected. xdotool requires X11."
        echo "Consider switching to an X11 session for best results."
    fi
else
    echo "Warning: No DISPLAY set. Run this script from a desktop session."
fi

# Final instructions
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Usage:"
echo "  1. Activate venv:    source $VENV_DIR/bin/activate"
echo "  2. Test input:       python scripts/test_input.py"
echo "  3. List sessions:    mask-replay --list"
echo "  4. Preview session:  mask-replay test_session_001 --dry-run"
echo "  5. Run replay:       mask-replay test_session_001"
echo ""
echo "Workflow:"
echo "  1. Start Upwork time tracker and clock in"
echo "  2. Run: mask-replay <session.json>"
echo "  3. Watch code being typed in VS Code"
echo "  4. Clock out when replay completes"
echo ""
