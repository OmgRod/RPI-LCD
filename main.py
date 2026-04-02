#!/usr/bin/python3
# -*- coding: UTF-8 -*-
"""
System monitoring display with tabbed UI.
Displays device information (CPU, memory, storage, network) on the LCD.
"""

import sys
import time
import logging
import signal
from display_driver import DisplayDriver
from touch_controller import TouchController
from ui_tabs import TabManager

logging.basicConfig(level=logging.INFO)

# Display is 320×480 in portrait orientation
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 480
TARGET_FPS = 45
FRAME_INTERVAL = 1.0 / TARGET_FPS
TAB_HOLD_SECONDS = 0.12
SCREENSAVER_EXIT_HOLD_SECONDS = 3.0


def _read_touch(touch):
    """Return the touch state and first touch point if present."""
    touch.read_touch_data()
    pressure, coordinates = touch.get_touch_xy()
    if pressure == 0 or not coordinates:
        return False, None
    return True, coordinates[0]


def _safe_enable_backlight(display):
    try:
        display.bl.value = 1.0
    except Exception:
        pass


def _reset_touch_state():
    return {
        "active_dot": None,
        "active_since": None,
        "latched": False,
    }


def _reset_screensaver_touch_state():
    return {
        "touched_at": None,
    }

def main():
    """Main entry point for the system monitoring display.
    
    Initializes the LCD display and touch controller, creates a tabbed UI
    for displaying system statistics, and enters the main event loop.
    Handles touch input for tab navigation and updates the display with
    real-time system information.
    
    Touch Navigation:
        - Tap and hold the bottom tab dots to switch tabs
        - Touches outside the dots do not change tabs
        - Any touch exits the screensaver back to the first tab
    
    Gracefully handles SIGTERM and SIGINT signals for clean shutdown.
    """
    
    # Initialize hardware
    disp = DisplayDriver()
    touch = TouchController()
    
    # Initialize tab manager
    tab_manager = TabManager(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    screensaver_tab_index = tab_manager.get_tab_index("Screensaver")
    terminal_tab_index = tab_manager.get_tab_index("Terminal")
    touch_state = _reset_touch_state()
    screensaver_touch_state = _reset_screensaver_touch_state()
    
    # Graceful shutdown handler
    def cleanup(signum, frame):
        logging.info(f"Signal {signum} received, cleaning up and exiting")
        try:
            tab_manager.shutdown()
            disp.clear()
        except Exception as e:
            logging.debug(f"Error clearing display during shutdown: {e}")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    
    # Touch state tracking
    last_touch_time = time.monotonic()
    touch_debounce = 0.08  # seconds
    screensaver_timeout = 60  # seconds of inactivity before screensaver
    
    logging.info("System monitoring display started")
    
    # Main loop
    while True:
        loop_start = time.monotonic()
        try:
            touched, touch_point = _read_touch(touch)
            current_time = time.monotonic()

            if tab_manager.current_tab == screensaver_tab_index:
                if touched:
                    # Require a 3-second hold to exit screensaver
                    if screensaver_touch_state["touched_at"] is None:
                        screensaver_touch_state["touched_at"] = current_time
                    
                    hold_duration = current_time - screensaver_touch_state["touched_at"]
                    if hold_duration >= SCREENSAVER_EXIT_HOLD_SECONDS:
                        tab_manager.current_tab = 0
                        last_touch_time = current_time
                        touch_state = _reset_touch_state()
                        screensaver_touch_state = _reset_screensaver_touch_state()
                else:
                    screensaver_touch_state = _reset_screensaver_touch_state()
            else:
                if touched:
                    if current_time - last_touch_time > touch_debounce:
                        hwx = touch_point['x']
                        hwy = touch_point['y']
                        dot_index = tab_manager.hit_test_dot(hwx, hwy)

                        if dot_index is None:
                            touch_state = _reset_touch_state()
                        else:
                            if touch_state["active_dot"] != dot_index:
                                touch_state["active_dot"] = dot_index
                                touch_state["active_since"] = current_time
                                touch_state["latched"] = False
                            elif not touch_state["latched"] and current_time - touch_state["active_since"] >= TAB_HOLD_SECONDS:
                                if tab_manager.select_tab(dot_index):
                                    last_touch_time = current_time
                                touch_state["latched"] = True
                else:
                    touch_state = _reset_touch_state()
                if (
                    tab_manager.current_tab != terminal_tab_index
                    and current_time - last_touch_time > screensaver_timeout
                ):
                    tab_manager.current_tab = screensaver_tab_index
                    touch_state = _reset_touch_state()

            frame = tab_manager.render()
            _safe_enable_backlight(disp)
            disp.show_image(frame)
        except Exception as e:
            logging.error(f"Error in main loop: {e}")

        elapsed = time.monotonic() - loop_start
        if elapsed < FRAME_INTERVAL:
            time.sleep(FRAME_INTERVAL - elapsed)


if __name__ == "__main__":
    main()
