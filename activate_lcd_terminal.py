#!/usr/bin/python3
"""Interactive bridge for feeding local keyboard input into the LCD terminal tab."""

from __future__ import annotations

import os
import signal
import socket
import sys

SOCKET_PATH = os.environ.get("LCD_TERMINAL_SOCKET", "/tmp/lcd-terminal.sock")
CTRL_SHIFT_C_SEQUENCES = (
    b"\x1b[99;6u",  # CSI-u for Ctrl+Shift+c in compatible terminals
    b"\x1b[67;6u",  # CSI-u uppercase variant
)


def _connect_socket() -> socket.socket:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCKET_PATH)
    return client


def _set_raw_mode(fd: int):
    import termios
    import tty

    original = termios.tcgetattr(fd)
    tty.setraw(fd)
    return termios, original


def main() -> int:
    if not os.path.exists(SOCKET_PATH):
        print(f"LCD terminal socket not available: {SOCKET_PATH}")
        print("Ensure lcd-cast service is running.")
        return 1

    try:
        client = _connect_socket()
    except OSError as exc:
        print(f"Failed to connect to LCD terminal socket: {exc}")
        return 1

    if not os.isatty(0):
        print("activate-lcd-terminal requires an interactive terminal.")
        client.close()
        return 1

    termios_module = None
    original_settings = None

    def _send_ctrl_c(_signum, _frame):
        try:
            client.sendall(b"\x03")
        except OSError:
            pass
        raise KeyboardInterrupt

    old_handler = signal.signal(signal.SIGINT, _send_ctrl_c)

    try:
        termios_module, original_settings = _set_raw_mode(0)
        print("LCD terminal bridge active. Ctrl+C sends interrupt to LCD shell and exits.")
        print("Press Ctrl+D to exit.")
        while True:
            data = os.read(0, 64)
            if not data:
                break
            if b"\x04" in data:
                break

            for seq in CTRL_SHIFT_C_SEQUENCES:
                if seq in data:
                    data = data.replace(seq, b"\x03")

            client.sendall(data)
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"Bridge stopped: {exc}")
    finally:
        signal.signal(signal.SIGINT, old_handler)
        if termios_module is not None and original_settings is not None:
            try:
                termios_module.tcsetattr(0, termios_module.TCSADRAIN, original_settings)
            except Exception:
                pass
        try:
            client.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
