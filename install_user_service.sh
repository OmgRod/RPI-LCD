#!/bin/bash
set -euo pipefail

# Install and enable the lcd-cast user service for the current user.
# Run this as the user who owns the desktop session (do NOT sudo).

PROJ_DIR="$HOME/lcd/Python"
USER_SYS_DIR="$HOME/.config/systemd/user"
ENV_FILE="$HOME/.config/lcd-cast.env"
UNIT_SRC="$PROJ_DIR/lcd-cast-user.service"
UNIT_DST="$USER_SYS_DIR/lcd-cast.service"

mkdir -p "$USER_SYS_DIR"
mkdir -p "$(dirname "$ENV_FILE")"

# Write an env file capturing the current session variables if available.
# These values are essential for desktop capture (DISPLAY, XAUTHORITY, XDG_RUNTIME_DIR).
: > "$ENV_FILE"
if [ -n "${DISPLAY-}" ]; then
  echo "DISPLAY=$DISPLAY" >> "$ENV_FILE"
fi
if [ -n "${XAUTHORITY-}" ]; then
  echo "XAUTHORITY=$XAUTHORITY" >> "$ENV_FILE"
fi
if [ -n "${XDG_RUNTIME_DIR-}" ]; then
  echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" >> "$ENV_FILE"
fi

# Copy the unit into the user's systemd directory
cp "$UNIT_SRC" "$UNIT_DST"

# Reload user daemon and enable
systemctl --user daemon-reload
systemctl --user enable --now lcd-cast.service

cat <<EOF
Installed user unit at $UNIT_DST and enabled it for the current user.
If you don't see the screen updating, ensure this script was run from the same
logged-in desktop session that has access to the display (run it from a terminal
inside your X/Wayland session). You can inspect logs with:

  journalctl --user -u lcd-cast.service -f

To stop/remove the unit:
  systemctl --user disable --now lcd-cast.service
  rm "$UNIT_DST"
  rm "$ENV_FILE"
EOF
