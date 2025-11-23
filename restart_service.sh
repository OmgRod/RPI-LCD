#!/bin/bash
set -euo pipefail

echo "Restarting lcd-cast.service and lcd-cast.path"
sudo systemctl restart lcd-cast.service || true
sudo systemctl restart lcd-cast.path || true
echo "Done. Check status: sudo systemctl status lcd-cast.service"
