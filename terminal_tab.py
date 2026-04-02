"""A small live shell tab rendered into the LCD UI."""

from __future__ import annotations

import os
import re
import select
import socket
import subprocess
import threading
from collections import deque

from PIL import Image, ImageDraw, ImageFont

from tab_base import Tab


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
INPUT_SOCKET_PATH = os.environ.get("LCD_TERMINAL_SOCKET", "/tmp/lcd-terminal.sock")


class _ShellSession:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._output = deque(maxlen=16000)
        self._process = None
        self._master_fd = None
        self._stdin_restore = None
        self._reader_thread = None
        self._stdin_thread = None
        self._socket_thread = None
        self._socket_server = None
        self._start_shell()

    def _start_shell(self):
        import pty

        shell = os.environ.get("SHELL", "/bin/bash")
        if not os.path.exists(shell):
            shell = "/bin/sh"

        master_fd, slave_fd = pty.openpty()
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("PS1", r"[\u@\h \W]$ ")

        try:
            self._process = subprocess.Popen(
                [shell, "-i"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            os.close(slave_fd)

        self._master_fd = master_fd
        os.set_blocking(self._master_fd, False)

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._start_keyboard_reader()
        self._start_socket_bridge()

    def _start_socket_bridge(self):
        socket_dir = os.path.dirname(INPUT_SOCKET_PATH)
        if socket_dir:
            os.makedirs(socket_dir, exist_ok=True)

        try:
            if os.path.exists(INPUT_SOCKET_PATH):
                os.unlink(INPUT_SOCKET_PATH)
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(INPUT_SOCKET_PATH)
            os.chmod(INPUT_SOCKET_PATH, 0o666)
            server.listen(4)
            server.settimeout(0.5)
            self._socket_server = server
        except Exception:
            self._socket_server = None
            return

        self._socket_thread = threading.Thread(target=self._socket_loop, daemon=True)
        self._socket_thread.start()

    def _socket_loop(self):
        while not self._stop_event.is_set() and self._socket_server is not None:
            try:
                conn, _ = self._socket_server.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with conn:
                while not self._stop_event.is_set():
                    try:
                        data = conn.recv(4096)
                    except OSError:
                        break
                    if not data:
                        break
                    self.send_bytes(data)

    def _start_keyboard_reader(self):
        if not os.isatty(0):
            return

        try:
            import termios
            import tty
        except Exception:
            return

        stdin_fd = 0
        original_settings = termios.tcgetattr(stdin_fd)
        tty.setcbreak(stdin_fd)
        self._stdin_restore = (termios, original_settings)

        def _read_stdin():
            try:
                while not self._stop_event.is_set():
                    ready, _, _ = select.select([stdin_fd], [], [], 0.1)
                    if not ready:
                        continue
                    data = os.read(stdin_fd, 1)
                    if not data:
                        break
                    self.send_bytes(data)
            finally:
                if self._stdin_restore is not None:
                    termios_module, settings = self._stdin_restore
                    termios_module.tcsetattr(stdin_fd, termios_module.TCSADRAIN, settings)

        self._stdin_thread = threading.Thread(target=_read_stdin, daemon=True)
        self._stdin_thread.start()

    def _read_loop(self):
        while not self._stop_event.is_set():
            if self._process is not None and self._process.poll() is not None:
                break

            try:
                ready, _, _ = select.select([self._master_fd], [], [], 0.1)
                if not ready:
                    continue
                data = os.read(self._master_fd, 4096)
                if not data:
                    break
                self._append_output(data.decode("utf-8", errors="ignore"))
            except (BlockingIOError, InterruptedError):
                continue
            except OSError:
                break

    def _append_output(self, text: str):
        with self._lock:
            self._output.extend(text)

    def get_output(self) -> str:
        with self._lock:
            return "".join(self._output)

    def send_bytes(self, data: bytes):
        if self._master_fd is None:
            return
        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    def close(self):
        self._stop_event.set()
        if self._socket_server is not None:
            try:
                self._socket_server.close()
            except OSError:
                pass
            self._socket_server = None
        if os.path.exists(INPUT_SOCKET_PATH):
            try:
                os.unlink(INPUT_SOCKET_PATH)
            except OSError:
                pass
        if self._stdin_restore is not None:
            try:
                termios_module, settings = self._stdin_restore
                termios_module.tcsetattr(0, termios_module.TCSADRAIN, settings)
            except Exception:
                pass
            self._stdin_restore = None
        if self._process is not None and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None


class TerminalTab(Tab):
    def __init__(self):
        super().__init__("Terminal", "⌘")
        self._session = _ShellSession()
        self._font = None
        self._is_service_mode = not os.isatty(0)
        self._service_message = "Service mode: run activate-lcd-terminal to type"

    def close(self):
        self._session.close()

    def render(self, monitor, width, height):
        image = Image.new("RGB", (width, height), (12, 14, 18))
        draw = ImageDraw.Draw(image)

        font = self._load_font()

        char_bbox = font.getbbox("M")
        char_width = max(8, char_bbox[2] - char_bbox[0])
        line_height = max(16, char_bbox[3] - char_bbox[1] + 3)

        left_padding = 8
        top_padding = 6
        usable_width = max(1, width - left_padding * 2)
        usable_height = max(1, height - top_padding * 2)
        columns = max(20, usable_width // char_width)
        visible_rows = max(6, usable_height // line_height)

        raw_output = self._session.get_output()
        visible_lines = self._wrap_terminal_text(raw_output, columns)

        if len(visible_lines) > visible_rows:
            visible_lines = visible_lines[-visible_rows:]

        y = top_padding
        for line in visible_lines:
            draw.text((left_padding, y), line, fill=(225, 230, 235), font=font)
            y += line_height

        if not visible_lines:
            draw.text((left_padding, y), "Launching shell...", fill=(180, 190, 200), font=font)

        if self._is_service_mode:
            draw.text((left_padding, 2), self._service_message, fill=(170, 140, 120), font=font)

        return image

    def _load_font(self):
        if self._font is not None:
            return self._font

        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]

        for path in font_paths:
            if os.path.exists(path):
                try:
                    self._font = ImageFont.truetype(path, 17)
                    return self._font
                except Exception:
                    continue

        self._font = ImageFont.load_default()
        return self._font

    def _wrap_terminal_text(self, text, columns):
        text = ANSI_ESCAPE_RE.sub("", text)
        lines = [""]

        for character in text:
            if character == "\r":
                lines[-1] = ""
            elif character == "\n":
                lines.append("")
            elif character in ("\b", "\x7f"):
                if lines[-1]:
                    lines[-1] = lines[-1][:-1]
                elif len(lines) > 1:
                    lines.pop()
            elif character == "\t":
                spaces = 4 - (len(lines[-1]) % 4)
                lines[-1] += " " * spaces
            else:
                lines[-1] += character
                while len(lines[-1]) > columns:
                    overflow = lines[-1][columns:]
                    lines[-1] = lines[-1][:columns]
                    lines.append(overflow)

        while len(lines) > 1 and lines[-1] == "":
            lines.pop()

        return lines