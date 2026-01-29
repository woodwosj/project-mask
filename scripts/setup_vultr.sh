#!/bin/bash
# PROJECT MASK - Vultr VPS Setup Script
# Optimized for low-memory x86_64 Ubuntu cloud instances (1GB RAM)
# Sets up lightweight X11 desktop + VNC + VS Code + Upwork

set -e

echo "=== PROJECT MASK - Vultr VPS Setup ==="
echo "Optimized for 1GB RAM x86_64 Ubuntu"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./setup_vultr.sh"
    exit 1
fi

# Create a non-root user for running the desktop
USERNAME="mask"
if ! id "$USERNAME" &>/dev/null; then
    echo "Creating user '$USERNAME'..."
    useradd -m -s /bin/bash "$USERNAME"
    echo "$USERNAME:Pr0jectM4sk!" | chpasswd
    usermod -aG sudo "$USERNAME"
fi

# Update system
echo ""
echo "Updating system packages..."
apt update && apt upgrade -y

# Install lightweight X11 desktop (Xfce is lighter than GNOME)
echo ""
echo "Installing lightweight Xfce desktop..."
DEBIAN_FRONTEND=noninteractive apt install -y \
    xfce4 \
    xfce4-terminal \
    dbus-x11 \
    x11-xserver-utils \
    xdotool \
    wmctrl \
    git \
    wget \
    curl

# Install TigerVNC server for remote access
echo ""
echo "Installing VNC server..."
apt install -y tigervnc-standalone-server tigervnc-common

# Install Python
echo ""
echo "Installing Python..."
apt install -y python3 python3-pip python3-venv

# Install VS Code (lighter alternative: use --no-sandbox for root)
echo ""
echo "Installing VS Code..."
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/packages.microsoft.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list
apt update
apt install -y code

# Install Upwork
echo ""
echo "Installing Upwork..."
wget -O /tmp/upwork.deb "https://upwork-usw2-desktopapp.upwork.com/binaries/v5_8_0_30_d2a05747676ab5a7/upwork_5.8.0.30_amd64.deb"
apt install -y /tmp/upwork.deb || apt install -y -f
rm /tmp/upwork.deb

# Clone project
echo ""
echo "Cloning PROJECT MASK..."
PROJECT_DIR="/home/$USERNAME/project-mask"
sudo -u "$USERNAME" git clone https://github.com/woodwosj/project-mask.git "$PROJECT_DIR" || true

# Setup Python environment
echo ""
echo "Setting up Python environment..."
sudo -u "$USERNAME" bash -c "cd $PROJECT_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt && pip install -e ."

# Configure VNC for the mask user
echo ""
echo "Configuring VNC server..."
VNC_DIR="/home/$USERNAME/.vnc"
mkdir -p "$VNC_DIR"

# Set VNC password (change this!)
echo "maskpass" | vncpasswd -f > "$VNC_DIR/passwd"
chmod 600 "$VNC_DIR/passwd"

# VNC startup script
cat > "$VNC_DIR/xstartup" << 'EOF'
#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export XDG_SESSION_TYPE=x11
exec startxfce4
EOF
chmod +x "$VNC_DIR/xstartup"

# VNC config for low memory
cat > "$VNC_DIR/config" << 'EOF'
geometry=1280x720
depth=16
EOF

chown -R "$USERNAME:$USERNAME" "$VNC_DIR"

# Create systemd service for VNC
echo ""
echo "Creating VNC systemd service..."
cat > /etc/systemd/system/vncserver@.service << EOF
[Unit]
Description=TigerVNC server on display %i
After=syslog.target network.target

[Service]
Type=forking
User=$USERNAME
Group=$USERNAME
WorkingDirectory=/home/$USERNAME

ExecStartPre=-/usr/bin/vncserver -kill :%i > /dev/null 2>&1
ExecStart=/usr/bin/vncserver :%i -geometry 1280x720 -depth 16 -localhost no
ExecStop=/usr/bin/vncserver -kill :%i

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vncserver@1
systemctl start vncserver@1

# Create helper script to start everything
echo ""
echo "Creating startup helper..."
cat > "/home/$USERNAME/start-mask.sh" << 'EOF'
#!/bin/bash
# Start PROJECT MASK replay session
# Run this from within the VNC desktop

cd ~/project-mask
source .venv/bin/activate

echo "Starting VS Code..."
code --no-sandbox ~/project-mask &
sleep 3

echo ""
echo "=== Ready for replay ==="
echo "1. Start Upwork and clock in"
echo "2. Run: mask-replay <session.json>"
echo "3. Clock out when done"
echo ""
echo "Available sessions:"
mask-replay --list
EOF
chmod +x "/home/$USERNAME/start-mask.sh"
chown "$USERNAME:$USERNAME" "/home/$USERNAME/start-mask.sh"

# Reduce memory usage
echo ""
echo "Optimizing for low memory..."
# Disable swap (VPS usually has limited swap)
# Enable zram for better memory compression
apt install -y zram-tools || true
echo "PERCENTAGE=50" > /etc/default/zramswap
systemctl restart zramswap || true

# Print connection info
echo ""
echo "==========================================="
echo "SETUP COMPLETE!"
echo "==========================================="
echo ""
echo "VNC Connection:"
echo "  Host: $(curl -s ifconfig.me):5901"
echo "  Password: maskpass"
echo ""
echo "SSH into server and run:"
echo "  su - mask"
echo "  ./start-mask.sh"
echo ""
echo "Or connect via VNC and:"
echo "  1. Open terminal"
echo "  2. Run: ~/start-mask.sh"
echo "  3. Start Upwork from applications menu"
echo "  4. Clock in, run mask-replay, clock out"
echo ""
echo "User credentials:"
echo "  Username: mask"
echo "  Password: maskpass123"
echo ""
echo "IMPORTANT: Change these passwords!"
echo "  passwd mask"
echo "  vncpasswd (as mask user)"
echo ""
