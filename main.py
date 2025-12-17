#!/usr/bin/python3
# -*- coding: UTF-8 -*-
"""
System monitoring display with tabbed UI.
Displays device information (CPU, memory, storage, network) on the LCD.
"""

import os
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

def main():
    """Main entry point for the system monitoring display.
    
    Initializes the LCD display and touch controller, creates a tabbed UI
    for displaying system statistics, and enters the main event loop.
    Handles touch input for tab navigation and updates the display with
    real-time system information.
    
    Touch Navigation:
        - Tap top of screen: switch to previous tab
        - Tap bottom of screen: switch to next tab
    
    Gracefully handles SIGTERM and SIGINT signals for clean shutdown.
    """
    
    # Initialize hardware
    disp = DisplayDriver()
    touch = TouchController()
    
    # Initialize tab manager
    tab_manager = TabManager(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    
    # Graceful shutdown handler
    def cleanup(signum, frame):
        logging.info(f"Signal {signum} received, cleaning up and exiting")
        try:
            disp.clear()
        except Exception as e:
            logging.debug(f"Error clearing display during shutdown: {e}")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    
    # Touch state tracking
    last_touch_time = 0
    touch_debounce = 0.3  # seconds
    
    logging.info("System monitoring display started")
    
    # Main loop
    while True:
        try:
            # Read touch input
            touch.read_touch_data()
            p, coords = touch.get_touch_xy()
            touched = (p != 0 and coords)
            
            if touched:
                current_time = time.time()
                # Debounce touch events to prevent rapid switching
                if current_time - last_touch_time > touch_debounce:
                    hwx = coords[0]['x']
                    hwy = coords[0]['y']
                    
                    logging.debug(f"Touch detected at hw=({hwx},{hwy})")
                    
                    # Handle touch for tab switching
                    if tab_manager.handle_touch(hwx, hwy):
                        last_touch_time = current_time
            
            # Render current tab
            frame = tab_manager.render()
            
            # Display frame
            try:
                disp.bl.value = 1.0  # Ensure backlight is on
            except Exception:
                pass
            
            disp.show_image(frame)
            
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
        
        # Update rate: ~10 FPS (system stats don't need high refresh rate)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
