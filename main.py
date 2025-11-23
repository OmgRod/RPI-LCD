#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import os, sys, time, logging, subprocess, shutil, tempfile, json, math, argparse
import signal
from PIL import Image, ImageDraw, ImageFont
from display_driver import DisplayDriver
from touch_controller import TouchController
import numpy as np
import io
import fcntl
import struct
from uuid import uuid4
from pathlib import Path

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------
# VIRTUAL FRAMEBUFFER = LANDSCAPE 480×320
# ---------------------------------------------------------
VIRTUAL_W = 480
VIRTUAL_H = 320
# Touch hardware resolution (common for these HATs)
TOUCH_HW_W = 320
TOUCH_HW_H = 480
# Touch rotation (degrees). Set to one of: 0, 90, 180, 270 to match how
# the display/touch panel is mounted. 90 means the screen image is rotated
# 90 degrees clockwise relative to the touch sensor coordinate system.
# If unsure, try 0/90/180/270 until touches align with on-screen elements.
TOUCH_ROTATION = 90
# Rotation applied to the virtual image when preparing the framebuffer
# This must match the rotation used in `prepare_virtual`. PIL's Image.rotate
# uses counter-clockwise angles; prepare_virtual rotates by 90 (CCW) to
# convert the landscape virtual canvas into a portrait framebuffer.
DISPLAY_ROTATION = 90

# If axes appear inverted for your mounting, toggle these to correct mapping.
INVERT_VIRTUAL_X = False
INVERT_VIRTUAL_Y = False
# If the virtual X/Y axes appear swapped on the desktop, enable this to swap
# them before feeding the OS cursor (useful for certain rotation configs).
SWAP_VIRTUAL_XY = False

# ---------------------------------------------------------
# FAST WAYLAND CAPTURE
# ---------------------------------------------------------
def capture_desktop():
    """Capture the desktop image.

    Order: grim (Wayland) if available and XDG_RUNTIME_DIR set, then scrot (X),
    then direct framebuffer read (/dev/fb0) as a last resort.
    """
    # 1) grim (fast Wayland) — only useful when running under the user's session
    if shutil.which('grim') and os.environ.get('XDG_RUNTIME_DIR'):
        try:
            tmp = os.path.join(tempfile.gettempdir(), f"wlshot_{uuid4().hex}.png")
            subprocess.run(["grim", "-t", "png", tmp], check=True)
            img = Image.open(tmp).convert("RGB")
            try:
                os.unlink(tmp)
            except Exception:
                pass
            logging.debug(f"capture_desktop: using grim, size={img.size}")
            return img
        except Exception as e:
            logging.debug(f"grim failed: {e}")

    # 2) scrot (X11) — may work when running as a service if DISPLAY/XAUTHORITY are set
    if shutil.which('scrot'):
        tmp = os.path.join(tempfile.gettempdir(), f"screencap_{uuid4().hex}.png")
        try:
            subprocess.run(['scrot', tmp], check=True)
            img = Image.open(tmp).convert('RGB')
            try:
                os.unlink(tmp)
            except Exception:
                pass
            logging.debug(f"capture_desktop: using scrot, size={img.size}")
            return img
        except Exception as e:
            logging.debug(f"scrot capture failed: {e}")

    # 3) Direct framebuffer (/dev/fb0)
    fb_dev = '/dev/fb0'
    fb_sys = '/sys/class/graphics/fb0'
    try:
        if os.path.exists(fb_dev):
            # Try to read geometry
            w = h = None
            if os.path.exists(fb_sys):
                try:
                    with open(os.path.join(fb_sys, 'virtual_size'), 'r') as f:
                        vs = f.read().strip()
                    w, h = map(int, vs.split(','))
                except Exception:
                    w = h = None

            if (w is None or h is None) and shutil.which('fbset'):
                try:
                    out = subprocess.check_output(['fbset', '-s'], stderr=subprocess.DEVNULL).decode()
                    for line in out.splitlines():
                        if line.strip().startswith('geometry'):
                            parts = line.split()
                            if len(parts) >= 3:
                                w = int(parts[1]); h = int(parts[2])
                            break
                except Exception:
                    w = h = None

            if w is None or h is None:
                # ioctl fallback
                try:
                    fb = open(fb_dev, 'rb')
                    FBIOGET_VSCREENINFO = 0x4600
                    buf = fcntl.ioctl(fb, FBIOGET_VSCREENINFO, b'\x00' * 160)
                    xres = struct.unpack_from('I', buf, 0)[0]
                    yres = struct.unpack_from('I', buf, 4)[0]
                    w, h = int(xres), int(yres)
                    fb.close()
                except Exception:
                    w = h = None

            bpp = 16
            try:
                with open(os.path.join(fb_sys, 'bits_per_pixel'), 'r') as f:
                    bpp = int(f.read().strip())
            except Exception:
                pass

            if w is None or h is None:
                raise RuntimeError('Could not determine framebuffer size')

            with open(fb_dev, 'rb') as f:
                raw = f.read(w * h * (bpp // 8))

            logging.debug(f"capture_desktop: framebuffer detected w={w} h={h} bpp={bpp}")
            if bpp == 16:
                arr = np.frombuffer(raw, dtype=np.uint16).reshape((h, w))
                r = ((arr >> 11) & 0x1F).astype(np.uint8)
                g = ((arr >> 5) & 0x3F).astype(np.uint8)
                b = (arr & 0x1F).astype(np.uint8)
                r = (r << 3) | (r >> 2)
                g = (g << 2) | (g >> 4)
                b = (b << 3) | (b >> 2)
                rgb = np.dstack((r, g, b))
                img = Image.fromarray(rgb, 'RGB')
                logging.debug('capture_desktop: using framebuffer (RGB565) backend')
                return img
            elif bpp == 24:
                arr = np.frombuffer(raw, dtype=np.uint8).reshape((h, w, 3))
                rgb = arr[..., ::-1]
                img = Image.fromarray(rgb, 'RGB')
                logging.debug('capture_desktop: using framebuffer (24bpp) backend')
                return img
            elif bpp == 32:
                arr = np.frombuffer(raw, dtype=np.uint8).reshape((h, w, 4))
                rgb = arr[..., :3][..., ::-1]
                img = Image.fromarray(rgb, 'RGB')
                logging.debug('capture_desktop: using framebuffer (32bpp) backend')
                return img
    except Exception as e:
        logging.debug(f"framebuffer capture failed: {e}")

    logging.warning("Desktop capture unavailable; returning None")
    return None


CALIB_FILE = Path(__file__).parent / 'calibration.json'
DIAGNOSTIC_OVERLAY = False


def load_calibration():
    try:
        if CALIB_FILE.exists():
            with open(CALIB_FILE, 'r') as f:
                data = json.load(f)
                return data.get('matrix')
    except Exception as e:
        logging.debug(f"load_calibration failed: {e}")
    return None


def save_calibration(matrix):
    try:
        with open(CALIB_FILE, 'w') as f:
            json.dump({'matrix': matrix}, f)
            logging.info(f"Calibration saved to {CALIB_FILE}")
    except Exception as e:
        logging.debug(f"save_calibration failed: {e}")


def apply_calibration(hx, hy, calib):
    # calib: [a,b,c,d,e,f] mapping hx,hy -> vx,vy
    a, b, c, d, e, f = calib
    vx = a * hx + b * hy + c
    vy = d * hx + e * hy + f
    return int(round(vx)), int(round(vy))


def compute_affine(raw_pts, virt_pts):
    # raw_pts and virt_pts are lists of three (x,y) pairs
    # Solve linear system for 6 params
    A = []
    B = []
    for (hx, hy), (vx, vy) in zip(raw_pts, virt_pts):
        A.append([hx, hy, 1, 0, 0, 0])
        A.append([0, 0, 0, hx, hy, 1])
        B.append(vx)
        B.append(vy)
    M = np.array(A)
    V = np.array(B)
    try:
        params, *_ = np.linalg.lstsq(M, V, rcond=None)
        return params.tolist()
    except Exception as e:
        logging.debug(f"compute_affine failed: {e}")
        return None


def calibration_routine(disp, touch):
    """Interactive 3-point calibration. Shows targets and collects raw touch points."""
    logging.info("Starting calibration. Please touch the targets as they appear.")
    margin = 40
    targets = [(margin, margin), (VIRTUAL_W - margin, VIRTUAL_H - margin), (VIRTUAL_W // 2, VIRTUAL_H // 2)]
    raw_points = []
    for idx, (tx, ty) in enumerate(targets):
        img = Image.new('RGB', (disp.width, disp.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        disp_x = int(tx * disp.width / VIRTUAL_W)
        disp_y = int(ty * disp.height / VIRTUAL_H)
        draw.ellipse((disp_x - 8, disp_y - 8, disp_x + 8, disp_y + 8), fill=(255, 255, 0))
        disp.show_image(img)
        touched = False
        start = time.time()
        while time.time() - start < 10:
            touch.read_touch_data()
            p, coords = touch.get_touch_xy()
            if p != 0 and coords:
                hx = coords[0]['x']
                hy = coords[0]['y']
                raw_points.append((hx, hy))
                logging.info(f"Calibration point {idx+1} raw=({hx},{hy})")
                touched = True
                time.sleep(0.5)
                break
            time.sleep(0.05)
        if not touched:
            logging.warning("Calibration timed out waiting for touch")
            return False
    params = compute_affine(raw_points, targets)
    if params is None:
        logging.error("Calibration computation failed")
        return False
    save_calibration(params)
    logging.info("Calibration completed successfully")
    return True


def detect_rotation_heuristic(touch, duration=2.0, sample_rate=0.02):
    logging.info("Rotation detection: please swipe across the touch panel now")
    samples = []
    start = time.time()
    while time.time() - start < duration:
        touch.read_touch_data()
        p, coords = touch.get_touch_xy()
        if p != 0 and coords:
            samples.append((coords[0]['x'], coords[0]['y']))
        time.sleep(sample_rate)
    if len(samples) < 5:
        logging.warning("Not enough samples for rotation detection")
        return None
    arr = np.array(samples)
    hx = arr[:, 0]; hy = arr[:, 1]
    candidates = {0: lambda x, y: (x, y), 90: lambda x, y: (y, 1 - x), 180: lambda x, y: (1 - x, 1 - y), 270: lambda x, y: (1 - y, x)}
    scores = {}
    for rot, fn in candidates.items():
        nx, ny = fn(hx / TOUCH_HW_W, hy / TOUCH_HW_H)
        idx = np.arange(len(nx))
        try:
            corr = abs(np.corrcoef(idx, nx)[0, 1])
        except Exception:
            corr = 0
        scores[rot] = corr
    best = max(scores, key=scores.get)
    logging.info(f"Rotation detection scores: {scores}, selected={best}")
    return best

# ---------------------------------------------------------
# DESKTOP → VIRTUAL LANDSCAPE FRAME
# ---------------------------------------------------------
def prepare_virtual(img):
    if img is None:
        return Image.new("RGB", (VIRTUAL_W, VIRTUAL_H), (0,0,0))
    img = img.resize((VIRTUAL_W, VIRTUAL_H), Image.BILINEAR)
    # rotate by DISPLAY_ROTATION (Pillow rotate is counter-clockwise)
    return img.rotate(DISPLAY_ROTATION, expand=True)

# ---------------------------------------------------------
# GESTURE ENGINE (ONE-FINGER TAP/DRAG)
# ---------------------------------------------------------
class GestureEngine:
    def __init__(self, mouse_backend=None, tap_max_time=0.25, move_threshold=2, smooth_alpha=0.6):
        self.lastx = None
        self.lasty = None
        self.dragging = False
        self.down_time = 0
        self.moved = False
        self.mouse_backend = mouse_backend
        # Smoothing and thresholds
        self.tap_max_time = tap_max_time
        self.move_threshold = move_threshold
        self.smooth_alpha = smooth_alpha
        self.smoothed_x = None
        self.smoothed_y = None

    def _mouse_move(self, x, y):
        if self.mouse_backend == 'xdotool':
            try:
                subprocess.run(['xdotool', 'mousemove', str(int(x)), str(int(y))])
            except Exception as e:
                logging.debug(f"xdotool move failed: {e}")

    def _mouse_down(self):
        if self.mouse_backend == 'xdotool' and not self.dragging:
            try:
                subprocess.run(['xdotool', 'mousedown', '1'])
            except Exception as e:
                logging.debug(f"xdotool mousedown failed: {e}")
            self.dragging = True

    def _mouse_up(self):
        if self.mouse_backend == 'xdotool' and self.dragging:
            try:
                subprocess.run(['xdotool', 'mouseup', '1'])
            except Exception as e:
                logging.debug(f"xdotool mouseup failed: {e}")
            self.dragging = False

    def _mouse_click(self, x, y):
        if self.mouse_backend == 'xdotool':
            try:
                subprocess.run(['xdotool', 'mousemove', str(int(x)), str(int(y)), 'click', '1'])
            except Exception as e:
                logging.debug(f"xdotool click failed: {e}")

    def feed(self, touched, vx, vy, desktop_size):
        # desktop_size: (w, h) or None
        if desktop_size is None:
            return

        # Map virtual -> desktop coordinates
        desktop_w, desktop_h = desktop_size
        target_x = vx * desktop_w / VIRTUAL_W
        target_y = vy * desktop_h / VIRTUAL_H

        if not touched:
            # Touch released -> detect tap if movement stayed within threshold
            if (self.lastx is not None and self.lasty is not None):
                dx = vx - self.lastx
                dy = vy - self.lasty
                dist = (dx*dx + dy*dy) ** 0.5
                if (dist <= self.move_threshold) and ((time.time() - self.down_time) <= self.tap_max_time):
                    sx = self.smoothed_x if self.smoothed_x is not None else target_x
                    sy = self.smoothed_y if self.smoothed_y is not None else target_y
                    self._mouse_click(sx, sy)
            # Release drag (if any)
            self._mouse_up()
            self.lastx = self.lasty = None
            self.moved = False
            self.smoothed_x = self.smoothed_y = None
            return

        # On touch
        if self.lastx is None:
            # first touch
            self.lastx, self.lasty = vx, vy
            self.down_time = time.time()
            self.moved = False
            self.smoothed_x = target_x
            self.smoothed_y = target_y
            self._mouse_move(self.smoothed_x, self.smoothed_y)
            return

        # Update smoothing
        self.smoothed_x = (self.smooth_alpha * target_x) + ((1 - self.smooth_alpha) * (self.smoothed_x or target_x))
        self.smoothed_y = (self.smooth_alpha * target_y) + ((1 - self.smooth_alpha) * (self.smoothed_y or target_y))

        # Movement delta in virtual coords (Euclidean)
        dx = vx - self.lastx
        dy = vy - self.lasty
        dist = (dx*dx + dy*dy) ** 0.5
        if dist > self.move_threshold:
            self.moved = True
            if not self.dragging:
                self._mouse_down()
            self._mouse_move(self.smoothed_x, self.smoothed_y)

        self.lastx, self.lasty = vx, vy

# ---------------------------------------------------------
# MAIN PROGRAM
# ---------------------------------------------------------
if __name__ == "__main__":
    disp = DisplayDriver()    # 320×480 LCD
    touch = TouchController()
    # Load calibration matrix (if present) to correct raw touch -> virtual mapping
    calib = load_calibration()
    if calib:
        logging.info("Loaded calibration matrix")
    # Auto-fix common orientation quirks for specific touch rotation mounts
    if TOUCH_ROTATION == 90:
        logging.info("Applying auto-fix: swap virtual X/Y and invert virtual X for TOUCH_ROTATION=90")
        SWAP_VIRTUAL_XY = True
        INVERT_VIRTUAL_X = True
    # Detect mouse injection backend (xdotool for X11)
    mouse_backend = None
    if shutil.which('xdotool'):
        mouse_backend = 'xdotool'
        logging.info('Mouse backend: xdotool (real cursor will be moved)')
    else:
        logging.warning('No xdotool found: real cursor will not be moved')

    gestures = GestureEngine(mouse_backend=mouse_backend)
    desktop_size = None

    # build a simple cursor image to draw on the small LCD (arrow)
    def _make_cursor():
        w, h = 16, 20
        im = Image.new('RGBA', (w, h), (0,0,0,0))
        dr = ImageDraw.Draw(im)
        # arrow polygon (tip at 1,1)
        poly = [(1,1), (1,17), (5,13), (9,19), (11,18), (7,12), (13,12)]
        dr.polygon(poly, fill=(255,255,255,255))
        dr.line([(0,0),(4,8)], fill=(0,0,0,0))
        return im

    cursor_img = _make_cursor()
    # Precompute rotated cursor images so the arrow points correctly on-screen
    # Use positive DISPLAY_ROTATION to rotate the cursor to match the framebuffer.
    cursor_variants = {
        0: cursor_img,
        90: cursor_img.rotate(DISPLAY_ROTATION, expand=True),
        180: cursor_img.rotate(DISPLAY_ROTATION * 2 % 360, expand=True),
        270: cursor_img.rotate(DISPLAY_ROTATION * 3 % 360, expand=True),
    }

    # Graceful shutdown handler for systemd (SIGTERM) and Ctrl-C (SIGINT)
    def _cleanup(signum, frame):
        logging.info(f"Signal {signum} received, cleaning up and exiting")
        try:
            disp.clear()
        except Exception as e:
            logging.debug(f"Error clearing display during shutdown: {e}")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    while True:
        # ---- Capture screen ----
        desktop = capture_desktop()
        if desktop is not None:
            desktop_size = desktop.size

        # ---- Virtual framebuffer + rotate ----
        frame = prepare_virtual(desktop)

        # ---- Touch input ----
        touch.read_touch_data()
        p, coords = touch.get_touch_xy()
        touched = (p != 0 and coords)

        if touched:
            hwx = coords[0]['x']   # 0..320
            hwy = coords[0]['y']   # 0..480

            # If a calibration matrix exists, use it (preferred). Otherwise
            # fall back to a simple rotation-aware mapping.
            if calib:
                try:
                    vx, vy = apply_calibration(hwx, hwy, calib)
                except Exception as e:
                    logging.debug(f"apply_calibration failed: {e}")
                    calib = None

            if not calib:
                # Map hardware -> virtual while accounting for panel rotation
                nx = hwx / TOUCH_HW_W
                ny = hwy / TOUCH_HW_H
                if TOUCH_ROTATION == 0:
                    vx = nx * VIRTUAL_W
                    vy = ny * VIRTUAL_H
                elif TOUCH_ROTATION == 90:
                    # rotate 90° clockwise: (x,y) -> (y, 1-x)
                    vx = ny * VIRTUAL_W
                    vy = (1.0 - nx) * VIRTUAL_H
                elif TOUCH_ROTATION == 180:
                    vx = (1.0 - nx) * VIRTUAL_W
                    vy = (1.0 - ny) * VIRTUAL_H
                elif TOUCH_ROTATION == 270:
                    # rotate 90° counter-clockwise: (x,y) -> (1-y, x)
                    vx = (1.0 - ny) * VIRTUAL_W
                    vy = nx * VIRTUAL_H
                else:
                    vx = nx * VIRTUAL_W
                    vy = ny * VIRTUAL_H
                vx, vy = int(round(vx)), int(round(vy))
            # Apply optional inversion if user reports axes swapped
            if INVERT_VIRTUAL_X:
                vx = VIRTUAL_W - vx
            if INVERT_VIRTUAL_Y:
                vy = VIRTUAL_H - vy

            # Optionally swap X/Y axes before feeding gestures (some mounts)
            if SWAP_VIRTUAL_XY:
                vx, vy = vy, vx
        else:
            vx = vy = 0

        # ---- Feed gestures ----
        if desktop_size:
            gestures.feed(touched, vx, vy, desktop_size)

        # ---- Draw cursor dot accurately on the rotated framebuffer ----
        d = ImageDraw.Draw(frame)
        if touched:
            # Map virtual coordinates (landscape VIRTUAL_W x VIRTUAL_H) to the
            # rotated framebuffer (frame.size). This accounts for the
            # DISPLAY_ROTATION applied in prepare_virtual.
            fw, fh = frame.size
            nx = vx / VIRTUAL_W
            ny = vy / VIRTUAL_H
            if DISPLAY_ROTATION == 0:
                fx = nx * fw
                fy = ny * fh
            elif DISPLAY_ROTATION == 90:
                # PIL.rotate(90) is CCW: map (x,y) -> (y, 1-x)
                fx = ny * fw
                fy = (1.0 - nx) * fh
            elif DISPLAY_ROTATION == 180:
                fx = (1.0 - nx) * fw
                fy = (1.0 - ny) * fh
            elif DISPLAY_ROTATION == 270:
                fx = (1.0 - ny) * fw
                fy = nx * fh
            else:
                fx = nx * fw
                fy = ny * fh
            fx, fy = int(round(fx)), int(round(fy))
            # choose cursor variant rotated to compensate for DISPLAY_ROTATION
            cur = cursor_variants.get(DISPLAY_ROTATION % 360, cursor_img)
            cx = cur.width // 2
            cy = cur.height // 2
            px = max(0, min(fw - cur.width, fx - cx))
            py = max(0, min(fh - cur.height, fy - cy))
            frame.paste(cur, (px, py), cur)

        # ---- Display frame ----
        disp.show_image(frame)

        time.sleep(0.015)  # ~33 FPS
