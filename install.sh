#!/usr/bin/env bash
set -e

if [ "$EUID" -ne 0 ]; then
    echo "Error: install.sh must be run as root (sudo ./install.sh)"
    exit 1
fi

if ! which outb > /dev/null 2>&1; then
    echo "Error: 'outb' binary not found. Install with: sudo apt install ioport"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if systemctl is-active --quiet g5ge-fancontrol 2>/dev/null; then
    echo "Stopping existing g5ge-fancontrol service..."
    systemctl stop g5ge-fancontrol
fi

echo "Installing daemon..."
cp "$SCRIPT_DIR/g5ge-fandaemon.py" /usr/local/bin/g5ge-fandaemon.py
chmod 755 /usr/local/bin/g5ge-fandaemon.py

echo "Installing fancli..."
cp "$SCRIPT_DIR/fancli" /usr/local/bin/fancli
chmod 755 /usr/local/bin/fancli

echo "Installing service unit..."
cp "$SCRIPT_DIR/g5ge-fancontrol.service" /etc/systemd/system/g5ge-fancontrol.service

mkdir -p /etc/g5ge-fan

if [ ! -f /etc/g5ge-fan/config.json ]; then
    echo "Writing default config (auto mode)..."
    echo '{"mode": "auto"}' > /etc/g5ge-fan/config.json
else
    echo "Preserving existing /etc/g5ge-fan/config.json"
fi

systemctl daemon-reload
systemctl enable --now g5ge-fancontrol

echo ""
echo "Installed. Fan control is active. Run 'fancli status' to check."
