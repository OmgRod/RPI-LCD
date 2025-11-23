#!/usr/bin/env python3
import time
import logging
from display_driver import DisplayDriver
from PIL import Image

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

if __name__ == '__main__':
    disp = DisplayDriver()
    try:
        colors = [ (255,0,0), (0,255,0), (0,0,255), (255,255,255), (0,0,0) ]
        for color in colors:
            logging.info(f"display_test: showing color={color}")
            img = Image.new('RGB', (disp.width, disp.height), color)
            try:
                disp.show_image(img)
            except Exception as e:
                logging.debug(f"display_test: show_image failed: {e}")
                # Fall back to filling via dre_rectangle using RGB565
                r, g, b = color
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                disp.dre_rectangle(0, 0, disp.width-1, disp.height-1, rgb565)
            time.sleep(2)
    finally:
        disp.clear()
        logging.info("display_test: finished and cleared")
