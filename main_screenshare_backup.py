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

# Optional alternative mouse backends: prefer pynput when available
PYNPUT_AVAILABLE = False
try:
    from pynput.mouse import Controller as PynputController, Button as PynputButton
    PYNPUT_AVAILABLE = True
except Exception:
    PYNPUT_AVAILABLE = False

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
SWAP_VIRTUAL_XY = True
# If the framebuffer X/Y appear swapped when mapping desktop coords back
# into the rotated framebuffer, set this to True to swap fx/fy.
SWAP_FRAME_XY = False

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
DIAGNOSTIC_OVERLAY = True

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
    # return floats for higher precision; callers will round as needed
    return float(vx), float(vy)


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


def calibration_targets_for_preset(preset):
    """Return a list of (vx,vy) virtual coordinates for the preset.

    Presets supported: 3, 5, 9
    - 3: top-left, bottom-right, center
    - 5: four corners + center
    - 9: 3x3 grid (margin, mid, margin)
    """
    margin = 30
    if preset == 3:
        return [(margin, margin), (VIRTUAL_W - margin, VIRTUAL_H - margin), (VIRTUAL_W // 2, VIRTUAL_H // 2)]
    if preset == 5:
        return [
            (margin, margin),
            (VIRTUAL_W - margin, margin),
            (margin, VIRTUAL_H - margin),
            (VIRTUAL_W - margin, VIRTUAL_H - margin),
            (VIRTUAL_W // 2, VIRTUAL_H // 2),
        ]
    if preset == 9:
        xs = [margin, VIRTUAL_W // 2, VIRTUAL_W - margin]
        ys = [margin, VIRTUAL_H // 2, VIRTUAL_H - margin]
        pts = []
        for yy in ys:
            for xx in xs:
                pts.append((xx, yy))
        return pts
    # default fallback
    return calibration_targets_for_preset(3)


def calibration_routine(disp, touch, preset=3):
    """Interactive calibration using a preset number of targets.

    `preset` may be 3, 5 or 9 (number of target points).
    """
    logging.info("Starting calibration. Please touch the targets as they appear.")
    targets = calibration_targets_for_preset(preset)
    raw_points = []
    for idx, (tx, ty) in enumerate(targets):
        # Draw the target at the correct rotated framebuffer location.
        fw, fh = disp.width, disp.height
        nx = float(tx) / VIRTUAL_W
        ny = float(ty) / VIRTUAL_H
        if DISPLAY_ROTATION == 0:
            fx = nx * fw
            fy = ny * fh
        elif DISPLAY_ROTATION == 90:
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
        disp_x = int(round(fx))
        disp_y = int(round(fy))

        img = Image.new('RGB', (disp.width, disp.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((disp_x - 10, disp_y - 10, disp_x + 10, disp_y + 10), fill=(255, 255, 0))
        disp.show_image(img)
        touched = False
        start = time.time()
        while time.time() - start < 12:
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

    # Solve for affine using all collected points (least-squares for N>3)
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
def virtual_to_desktop(vx, vy, desktop_size,
                       rotation=None,
                       invert_x=None,
                       invert_y=None,
                       swap_xy=None):
    """Map virtual coordinates (VIRTUAL_W x VIRTUAL_H) to desktop pixels.

    Returns (target_x, target_y) in desktop pixel coordinates (floats).
    The mapping applies rotation, optional swap, and optional inversion.
    """
    # Resolve dynamic defaults from globals at call time so runtime changes
    # (like auto-fix toggles) are honored.
    if rotation is None:
        rotation = DISPLAY_ROTATION
    if invert_x is None:
        invert_x = INVERT_VIRTUAL_X
    if invert_y is None:
        invert_y = INVERT_VIRTUAL_Y
    if swap_xy is None:
        swap_xy = SWAP_VIRTUAL_XY

    desktop_w, desktop_h = desktop_size
    nx = float(vx) / VIRTUAL_W
    ny = float(vy) / VIRTUAL_H

    if rotation == 0:
        rx, ry = nx, ny
    elif rotation == 90:
        rx, ry = ny, 1.0 - nx
    elif rotation == 180:
        rx, ry = 1.0 - nx, 1.0 - ny
    elif rotation == 270:
        rx, ry = 1.0 - ny, nx
    else:
        rx, ry = nx, ny

    if swap_xy:
        rx, ry = ry, rx
    if invert_x:
        rx = 1.0 - rx
    if invert_y:
        ry = 1.0 - ry

    return rx * desktop_w, ry * desktop_h


def desktop_to_frame(cur_dx, cur_dy, desktop_size, frame_size,
                     rotation=None, invert_x=None, invert_y=None, swap_xy=None):
    """Map desktop pixel coordinates into rotated framebuffer pixel coords.

    Steps:
    - Normalize desktop -> rx,ry
    - Invert optional swap/invert applied in virtual_to_desktop to recover
      normalized virtual coordinates nx,ny
    - Map normalized virtual nx,ny into the rotated framebuffer using
      the same DISPLAY_ROTATION logic used when rendering the virtual->frame
    Returns (fx,fy) framebuffer pixel coordinates (ints).
    """
    if rotation is None:
        rotation = DISPLAY_ROTATION
    if invert_x is None:
        invert_x = INVERT_VIRTUAL_X
    if invert_y is None:
        invert_y = INVERT_VIRTUAL_Y
    if swap_xy is None:
        swap_xy = SWAP_VIRTUAL_XY

    desktop_w, desktop_h = desktop_size
    fw, fh = frame_size
    # normalized desktop
    rx = float(cur_dx) / float(desktop_w)
    ry = float(cur_dy) / float(desktop_h)

    # invert swap/invert
    if swap_xy:
        rx, ry = ry, rx
    if invert_x:
        rx = 1.0 - rx
    if invert_y:
        ry = 1.0 - ry

    # invert rotation mapping (solve for nx,ny given rx,ry)
    if rotation == 0:
        nx, ny = rx, ry
    elif rotation == 90:
        # rx = ny ; ry = 1 - nx -> ny = rx ; nx = 1 - ry
        ny = rx
        nx = 1.0 - ry
    elif rotation == 180:
        # rx = 1 - nx ; ry = 1 - ny
        nx = 1.0 - rx
        ny = 1.0 - ry
    elif rotation == 270:
        # rx = 1 - ny ; ry = nx -> ny = 1 - rx ; nx = ry
        ny = 1.0 - rx
        nx = ry
    else:
        nx, ny = rx, ry

    # now map normalized virtual nx,ny into framebuffer (same as earlier)
    # compute pixel positions on the rotated frame
    if rotation == 0:
        fx = int(round(nx * fw))
        fy = int(round(ny * fh))
    elif rotation == 90:
        fx = int(round(ny * fw))
        fy = int(round((1.0 - nx) * fh))
    elif rotation == 180:
        fx = int(round((1.0 - nx) * fw))
        fy = int(round((1.0 - ny) * fh))
    elif rotation == 270:
        fx = int(round((1.0 - ny) * fw))
        fy = int(round(nx * fh))
    else:
        fx = int(round(nx * fw))
        fy = int(round(ny * fh))

    # clamp
    fx = max(0, min(fw - 1, fx))
    fy = max(0, min(fh - 1, fy))
    # Optional global override to swap framebuffer axes if necessary
    try:
        if SWAP_FRAME_XY:
            return fy, fx
    except NameError:
        pass
    return fx, fy

class GestureEngine:
    def __init__(self, mouse_backend=None, tap_max_time=0.25, move_threshold=2, smooth_alpha=0.6):
        self.lastx = None
        self.lasty = None
        self.start_vx = None
        self.start_vy = None
        # last visible desktop coords for cursor drawing (pixels)
        self.visible_x = None
        self.visible_y = None
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
        # xdotool geometry probe/cache
        self._probe_done = False
        self._display_geom = None
        self._invert_mouse_y = False
        # Whether the current contact is still eligible to be treated as a tap
        self.tap_eligible = False
        # pynput controller (if used)
        self._pynput = None
        if mouse_backend == 'pynput' and PYNPUT_AVAILABLE:
            try:
                self._pynput = PynputController()
            except Exception as e:
                logging.debug(f'pynput controller init failed: {e}')
                self._pynput = None
        logging.info(f'GestureEngine init: backend={self.mouse_backend} pynput_inited={self._pynput is not None}')

    def _mouse_move(self, x, y):
        logging.info(f'_mouse_move called: backend={self.mouse_backend} x={x} y={y} pynput={self._pynput is not None}')
        if self.mouse_backend == 'pynput' and self._pynput is not None:
            try:
                self._pynput.position = (int(x), int(y))
            except Exception as e:
                logging.debug(f'pynput move failed: {e}')
        elif self.mouse_backend == 'xdotool':
            try:
                # ensure we have display geometry and probe for Y inversion once
                if not self._probe_done:
                    self._probe_mouse_geom()
                tx, ty = int(x), int(y)
                if self._display_geom and self._invert_mouse_y:
                    tx = int(tx)
                    # flip Y relative to display height (use h-1 to map 0..h-1)
                    ty = int(self._display_geom[1] - 1 - ty)
                subprocess.run(['xdotool', 'mousemove', str(tx), str(ty)])
            except Exception as e:
                logging.debug(f"xdotool move failed: {e}")

    def _mouse_down(self):
        logging.info(f'_mouse_down called: backend={self.mouse_backend} pynput={self._pynput is not None} dragging={self.dragging}')
        if self.mouse_backend == 'pynput' and self._pynput is not None:
            try:
                self._pynput.press(PynputButton.left)
            except Exception as e:
                logging.debug(f'pynput mousedown failed: {e}')
            self.dragging = True
        elif self.mouse_backend == 'xdotool' and not self.dragging:
            try:
                subprocess.run(['xdotool', 'mousedown', '1'])
            except Exception as e:
                logging.debug(f"xdotool mousedown failed: {e}")
            self.dragging = True

    def _mouse_up(self):
        logging.info(f'_mouse_up called: backend={self.mouse_backend} pynput={self._pynput is not None} dragging={self.dragging}')
        if self.mouse_backend == 'pynput' and self._pynput is not None and self.dragging:
            try:
                self._pynput.release(PynputButton.left)
            except Exception as e:
                logging.debug(f'pynput mouseup failed: {e}')
            self.dragging = False
        elif self.mouse_backend == 'xdotool' and self.dragging:
            try:
                subprocess.run(['xdotool', 'mouseup', '1'])
            except Exception as e:
                logging.debug(f"xdotool mouseup failed: {e}")
            self.dragging = False

    def _mouse_click(self, x, y):
        logging.info(f'_mouse_click called: backend={self.mouse_backend} x={x} y={y} pynput={self._pynput is not None} dragging={self.dragging}')
        if self.mouse_backend == 'pynput' and self._pynput is not None:
            try:
                self._pynput.position = (int(x), int(y))
                try:
                    self._pynput.release(PynputButton.left)
                except Exception:
                    pass
                self._pynput.press(PynputButton.left)
                time.sleep(0.06)
                self._pynput.release(PynputButton.left)
            except Exception as e:
                logging.debug(f'pynput click failed: {e}')
        elif self.mouse_backend == 'xdotool':
            try:
                # Ensure probe has run so we can correct any Y inversion
                if not self._probe_done:
                    self._probe_mouse_geom()
                tx, ty = int(x), int(y)
                if self._display_geom and self._invert_mouse_y:
                    ty = int(self._display_geom[1] - 1 - ty)
                # If a drag was left active, clear it first
                if self.dragging:
                    try:
                        subprocess.run(['xdotool', 'mouseup', '1'])
                    except Exception:
                        pass
                    self.dragging = False
                # explicit press+release to avoid sticky states
                subprocess.run(['xdotool', 'mousemove', str(tx), str(ty)])
                subprocess.run(['xdotool', 'mousedown', '1'])
                time.sleep(0.06)
                subprocess.run(['xdotool', 'mouseup', '1'])
            except Exception as e:
                logging.debug(f"xdotool click failed: {e}")

    def _probe_mouse_geom(self):
        # Probe display geometry via xdotool and test whether Y is inverted
        self._probe_done = True
        try:
            out = subprocess.check_output(['xdotool', 'getdisplaygeometry'], stderr=subprocess.DEVNULL).decode().strip()
            w, h = map(int, out.split())
            self._display_geom = (w, h)
            # save original mouse pos
            loc = subprocess.check_output(['xdotool', 'getmouselocation', '--shell']).decode()
            orig = {}
            for line in loc.splitlines():
                if '=' in line:
                    k, v = line.split('=', 1)
                    try:
                        orig[k] = int(v)
                    except Exception:
                        orig[k] = 0

            # Probe top and bottom positions to detect whether reported Y
            # increases when moving down (normal) or decreases (inverted).
            top_y = 10
            bot_y = max(10, h - 11)
            mid_x = max(10, w // 2)

            # move to top and read
            subprocess.run(['xdotool', 'mousemove', str(mid_x), str(top_y)])
            loc_top = subprocess.check_output(['xdotool', 'getmouselocation', '--shell']).decode()
            p_top = {}
            for line in loc_top.splitlines():
                if '=' in line:
                    k, v = line.split('=', 1)
                    try:
                        p_top[k] = int(v)
                    except Exception:
                        p_top[k] = 0

            # move to bottom and read
            subprocess.run(['xdotool', 'mousemove', str(mid_x), str(bot_y)])
            loc_bot = subprocess.check_output(['xdotool', 'getmouselocation', '--shell']).decode()
            p_bot = {}
            for line in loc_bot.splitlines():
                if '=' in line:
                    k, v = line.split('=', 1)
                    try:
                        p_bot[k] = int(v)
                    except Exception:
                        p_bot[k] = 0

            if ('Y' in p_top) and ('Y' in p_bot):
                if p_bot['Y'] > p_top['Y']:
                    self._invert_mouse_y = False
                    logging.info('Probe: xdotool Y is normal (no flip)')
                else:
                    self._invert_mouse_y = True
                    logging.info('Probe: xdotool Y is inverted; applying Y flip for clicks')
            else:
                self._invert_mouse_y = False

            # restore original pos
            if 'X' in orig and 'Y' in orig:
                try:
                    subprocess.run(['xdotool', 'mousemove', str(orig['X']), str(orig['Y'])])
                except Exception:
                    pass
        except Exception as e:
            logging.debug(f"mouse geometry probe failed: {e}")

    def feed(self, touched, vx, vy, desktop_size):
        # desktop_size: (w, h) or None
        if desktop_size is None:
            return

        # Map virtual -> desktop coordinates (apply rotation/invert/swap)
        target_x, target_y = virtual_to_desktop(vx, vy, desktop_size)

        if not touched:
            # Touch released -> detect tap if movement stayed within threshold
            if (self.lastx is not None and self.lasty is not None):
                # compare movement from initial touch to last recorded virtual
                sx_v = self.start_vx if self.start_vx is not None else self.lastx
                sy_v = self.start_vy if self.start_vy is not None else self.lasty
                dx = self.lastx - sx_v
                dy = self.lasty - sy_v
                dist = (dx*dx + dy*dy) ** 0.5
                # If this contact remained eligible for tap, perform a click
                if self.tap_eligible and (dist <= self.move_threshold) and ((time.time() - self.down_time) <= self.tap_max_time):
                    click_x = self.visible_x if self.visible_x is not None else target_x
                    click_y = self.visible_y if self.visible_y is not None else target_y
                    # Ensure any active drag is cleared first and then send a proper click
                    try:
                        self._mouse_click(click_x, click_y)
                    finally:
                        # Make sure dragging state is cleared after a click
                        self.dragging = False
                        self.tap_eligible = False
                # clear start markers
                self.start_vx = self.start_vy = None
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
            self.start_vx, self.start_vy = vx, vy
            self.down_time = time.time()
            self.moved = False
            # allow this contact to be a tap until movement proves otherwise
            self.tap_eligible = True
            # Immediate placement for first-contact to avoid cursor lag
            self.smoothed_x = target_x
            self.smoothed_y = target_y
            self.visible_x = target_x
            self.visible_y = target_y
            self._mouse_move(target_x, target_y)
            return

        # If we're still within tap timeout and haven't moved far, prefer
        # instant movement (no smoothing) to keep clicks low-latency.
        elapsed = time.time() - self.down_time if self.down_time else 999
        if (not self.moved) and (elapsed <= self.tap_max_time):
            # instant update
            self.smoothed_x = target_x
            self.smoothed_y = target_y
            self.visible_x = target_x
            self.visible_y = target_y
            self._mouse_move(target_x, target_y)
        else:
            # Update smoothing for slower cursor movement when dragging
            self.smoothed_x = (self.smooth_alpha * target_x) + ((1 - self.smooth_alpha) * (self.smoothed_x or target_x))
            self.smoothed_y = (self.smooth_alpha * target_y) + ((1 - self.smooth_alpha) * (self.smoothed_y or target_y))
            # always keep visible cursor at last smoothed location
            self.visible_x = self.smoothed_x
            self.visible_y = self.smoothed_y

        # Movement delta in virtual coords (Euclidean)
        dx = vx - self.lastx
        dy = vy - self.lasty
        dist = (dx*dx + dy*dy) ** 0.5
        # If movement exceeds threshold, treat as drag (but only if this
        # contact is no longer tap-eligible). This prevents tiny jitters
        # from turning taps into drags.
        if dist > self.move_threshold:
            self.moved = True
            # once movement occurs, this contact is no longer a tap
            self.tap_eligible = False
            if not self.dragging:
                self._mouse_down()
            self._mouse_move(self.smoothed_x, self.smoothed_y)

        self.lastx, self.lasty = vx, vy

# ---------------------------------------------------------
# MAIN PROGRAM
# ---------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='LCD cast + touch mapper')
    parser.add_argument('--calibrate', action='store_true', help='Run calibration and save matrix then exit')
    parser.add_argument('--calibrate-preset', type=int, choices=[3,5,9], default=3,
                        help='Number of calibration points to use (3, 5, or 9)')
    parser.add_argument('--no-auto-fix', action='store_true', dest='no_auto_fix', help='Do not apply automatic swap/invert heuristics')
    parser.add_argument('--cursor-rot', type=int, default=None, help='Adjust cursor rotation (degrees) to fine-tune appearance')
    parser.add_argument('--mouse-backend', choices=['pynput','xdotool','auto','none'], default='auto',
                        help='Mouse backend to use: `auto` (default) prefers pynput then xdotool, or force `pynput`, `xdotool`, or `none`')
    parser.add_argument('--force-invert-y', action='store_true', help='Force Y inversion for xdotool clicks (use if clicks register at opposite Y)')
    parser.add_argument('--swap-frame-xy', action='store_true', help='Swap framebuffer X/Y when mapping desktop->frame (override auto behavior)')
    args = parser.parse_args()

    disp = DisplayDriver()    # 320×480 LCD
    touch = TouchController()

    # If requested, run calibration flow and exit
    if args.calibrate:
        ok = calibration_routine(disp, touch, preset=args.calibrate_preset)
        if ok:
            logging.info('Calibration successful; saved matrix. Exiting.')
            sys.exit(0)
        else:
            logging.error('Calibration failed or timed out. Exiting.')
            sys.exit(2)

    # Load calibration matrix (if present) to correct raw touch -> virtual mapping
    calib = load_calibration()
    if calib:
        logging.info("Loaded calibration matrix")
    # Auto-fix common orientation quirks for specific touch rotation mounts
    if (TOUCH_ROTATION == 90) and (not args.no_auto_fix):
        logging.info("Applying auto-fix: swap virtual X/Y and invert virtual X/Y for TOUCH_ROTATION=90 (override with INVERT_VIRTUAL_X/INVERT_VIRTUAL_Y/SWAP_VIRTUAL_XY or --no-auto-fix)")
        SWAP_VIRTUAL_XY = True
        INVERT_VIRTUAL_X = True
        INVERT_VIRTUAL_Y = True
    # Resolve mouse backend according to CLI request and availability.
    req_backend = args.mouse_backend
    mouse_backend = None
    if req_backend == 'auto' or req_backend is None:
        if PYNPUT_AVAILABLE:
            mouse_backend = 'pynput'
        elif shutil.which('xdotool'):
            mouse_backend = 'xdotool'
    elif req_backend == 'pynput':
        if PYNPUT_AVAILABLE:
            mouse_backend = 'pynput'
        else:
            logging.warning('Requested pynput but it is not available in this environment')
            if shutil.which('xdotool'):
                mouse_backend = 'xdotool'
    elif req_backend == 'xdotool':
        if shutil.which('xdotool'):
            mouse_backend = 'xdotool'
        else:
            logging.warning('Requested xdotool but it is not found on PATH')
            if PYNPUT_AVAILABLE:
                mouse_backend = 'pynput'
    elif req_backend == 'none':
        mouse_backend = None

    if mouse_backend == 'pynput':
        logging.info('Mouse backend: pynput (real cursor will be moved via Python)')
    elif mouse_backend == 'xdotool':
        logging.info('Mouse backend: xdotool (real cursor will be moved via subprocess)')
    else:
        logging.warning('No mouse backend selected: real cursor will not be moved')

    gestures = GestureEngine(mouse_backend=mouse_backend)
    if args.force_invert_y:
        gestures._invert_mouse_y = True
        gestures._probe_done = True
        logging.info('Force-enabled Y inversion for xdotool clicks')
    if args.swap_frame_xy:
        SWAP_FRAME_XY = True
        logging.info('swap-frame-xy enabled: framebuffer fx/fy will be swapped on mapping')
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
    # Counter-rotate the cursor by -DISPLAY_ROTATION and add 180° to correct
    # upside-down appearance on some panels. If this looks wrong you can set
    # `cursor_rotation_adjust` below or change DISPLAY_ROTATION.
    # cursor_rotation_adjust may be overridden via CLI for fine-tuning
    cursor_rotation_adjust = 180
    if args.cursor_rot is not None:
        cursor_rotation_adjust = args.cursor_rot % 360
    cursor_upright = cursor_img.rotate(((-DISPLAY_ROTATION) + cursor_rotation_adjust) % 360, expand=True)

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

            logging.debug(f"touch raw: hw=({hwx},{hwy})")

            # If a calibration matrix exists, use it (preferred). Otherwise
            # fall back to a simple rotation-aware mapping.
            if calib:
                try:
                    vx, vy = apply_calibration(hwx, hwy, calib)
                except Exception as e:
                    logging.debug(f"apply_calibration failed: {e}")
                    calib = None

            logging.debug(f"mapped to virtual before swap/inv: v=({vx},{vy})")

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
            # Note: mapping to desktop pixels is handled inside GestureEngine.feed
            # using virtual_to_desktop which applies DISPLAY_ROTATION and inversion/swap flags.
            logging.debug(f"mapped to virtual (post-calibration) v=({vx},{vy})")
        else:
            vx = vy = 0

        # ---- Feed gestures ----
        if desktop_size:
            gestures.feed(touched, vx, vy, desktop_size)

        # ---- Draw cursor dot accurately on the rotated framebuffer ----
        d = ImageDraw.Draw(frame)
        # Determine cursor desktop pixel coords: prefer gesture visible coords
        cur_dx = None
        cur_dy = None
        if gestures.visible_x is not None and gestures.visible_y is not None:
            cur_dx, cur_dy = gestures.visible_x, gestures.visible_y
        elif desktop_size is not None:
            # fallback: map current virtual vx,vy to desktop
            cur_dx, cur_dy = virtual_to_desktop(vx, vy, desktop_size)


        if cur_dx is not None and desktop_size is not None:
            # Map desktop pixel coords back into framebuffer coords correctly
            fw, fh = frame.size
            fx, fy = desktop_to_frame(cur_dx, cur_dy, desktop_size, frame.size)

            # draw counter-rotated upright cursor image
            cur = cursor_upright
            cx = cur.width // 2
            cy = cur.height // 2
            px = max(0, min(fw - cur.width, fx - cx))
            py = max(0, min(fh - cur.height, fy - cy))
            frame.paste(cur, (px, py), cur)

            # Diagnostic overlay: show raw hw and virtual coords if enabled
            if DIAGNOSTIC_OVERLAY:
                try:
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
                    except Exception:
                        font = ImageFont.load_default()

                    dbg = f"hw=({hwx if touched else 'N/A'},{hwy if touched else 'N/A'}) v=({vx:.1f},{vy:.1f}) f=({fx},{fy})"

                    # Wrap text to max pixel width using the chosen font
                    max_width = 250
                    def wrap_text_to_width(text, font, max_w):
                        words = text.split()
                        lines = []
                        cur = ''
                        for w in words:
                            cand = (cur + ' ' + w).strip() if cur else w
                            try:
                                w_px = font.getsize(cand)[0]
                            except Exception:
                                # Pillow compatibility: fallback to approximate width
                                w_px = len(cand) * 8
                            if w_px <= max_w:
                                cur = cand
                            else:
                                if cur:
                                    lines.append(cur)
                                cur = w
                        if cur:
                            lines.append(cur)
                        return lines

                    lines = wrap_text_to_width(dbg, font, max_width)
                    y = 4
                    line_h = font.getsize('Ay')[1] if hasattr(font, 'getsize') else 24
                    for ln in lines:
                        d.text((4, y), ln, fill=(255,255,0), font=font)
                        y += line_h + 2
                except Exception:
                    pass

        # ---- Display frame ----
        # Keep backlight asserted and protect show_image so a single
        # transient error doesn't make the screen go dark.
        try:
            try:
                disp.bl.value = 1.0
            except Exception:
                pass
            disp.show_image(frame)
        except Exception as e:
            logging.error(f"display update failed: {e}")

        time.sleep(0.03)  # ~33 FPS
