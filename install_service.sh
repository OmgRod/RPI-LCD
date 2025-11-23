#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo ./install_service.sh"
  exit 1
fi

PROJ_DIR="/home/pi/lcd/Python"
SYSTEMD_DIR="/etc/systemd/system"

echo "Installing systemd units from $PROJ_DIR to $SYSTEMD_DIR"
cp "$PROJ_DIR/lcd-cast.service" "$SYSTEMD_DIR/"
cp "$PROJ_DIR/lcd-cast.path" "$SYSTEMD_DIR/"

systemctl daemon-reload
systemctl enable --now lcd-cast.path
systemctl enable --now lcd-cast.service

echo "Installed and started lcd-cast.service and lcd-cast.path"
echo "Check status with: sudo systemctl status lcd-cast.service"
