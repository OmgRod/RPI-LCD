#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo ./uninstall_service.sh"
  exit 1
fi

echo "Stopping and disabling units"
systemctl disable --now lcd-cast.path || true
systemctl disable --now lcd-cast.service || true

echo "Removing unit files"
rm -f /etc/systemd/system/lcd-cast.service /etc/systemd/system/lcd-cast.path
systemctl daemon-reload

echo "Uninstalled lcd-cast units"
