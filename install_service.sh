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

# If a per-user service exists, warn user about using per-user install instead
if [ -f "$PROJ_DIR/install_user_service.sh" ]; then
  echo "Note: a per-user install script is available at $PROJ_DIR/install_user_service.sh"
  echo "It is recommended to run the per-user installer from within your X/Wayland session:" \
       "\n  $HOME/lcd/Python/install_user_service.sh"
fi

systemctl daemon-reload
systemctl enable --now lcd-cast.path
systemctl enable --now lcd-cast.service

# If the per-user env file exists, inform user that system service will use it;
# otherwise advise running per-user installer from the desktop session.
if [ -f "/home/pi/.config/lcd-cast.env" ]; then
  echo "Found /home/pi/.config/lcd-cast.env — system service will load GUI env from that file."
else
  echo "Installed system service, but no per-user env found at /home/pi/.config/lcd-cast.env"
  echo "If the service shows a black screen, run the per-user installer from a terminal inside your desktop session:" 
  echo "  /home/pi/lcd/Python/install_user_service.sh"
fi

echo "Installed and started lcd-cast.service and lcd-cast.path"
echo "Check status with: sudo systemctl status lcd-cast.service"
