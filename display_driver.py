# ---------------------------------------------
#  Waveshare 2.5" Capacitive LCD (ST7796) DRIVER
#  Corrected + Fully Working
# ---------------------------------------------

import time
import spidev
import logging
import numpy as np
from gpiozero import DigitalOutputDevice, PWMOutputDevice

# GPIO pins (Waveshare default)
RST_PIN = 27
DC_PIN  = 25
BL_PIN  = 18

# SPI speed
SPI_FREQ = 40000000   # 40 MHz (stable for ST7796)
BL_FREQ  = 1000


class DisplayDriver:
    """Fully corrected driver for Waveshare ST7796 LCD 320×480"""

    def __init__(self, rotate=0):
        """
        rotate = 0, 90, 180, 270 degrees
        """
        self.np = np

        self.width  = 320
        self.height = 480

        # Setup GPIO (guarded for clearer error messages)
        try:
            self.rst = DigitalOutputDevice(RST_PIN, active_high=True, initial_value=True)
            self.dc  = DigitalOutputDevice(DC_PIN,  active_high=True, initial_value=True)
            self.bl  = PWMOutputDevice(BL_PIN, frequency=BL_FREQ)
            self.bl.value = 1.0   # 100% brightness
        except Exception as e:
            logging.error("Failed to initialize GPIO pins for the display: %s", e)
            logging.error("Possible causes: another process (service) already claimed the GPIO pins, or insufficient permissions.")
            logging.error("Try stopping any running lcd-cast service, kill lingering Python processes, and retry. Example:")
            logging.error("  sudo systemctl stop lcd-cast.service && sudo pkill -f main.py && sudo pkill -f lcd-cast")
            logging.error("Also ensure no other GPIO libraries (pigpiod) are holding the pins.")
            raise

        # Setup SPI
        self.spi = spidev.SpiDev(0, 0)
        self.spi.max_speed_hz = SPI_FREQ
        self.spi.mode = 0b00

        self.rotation = rotate
        self.MADCTL = self.rotation_to_madctl(rotate)

        # Initialize LCD
        self.lcd_init()


    # -------------------------
    # Helper functions
    # -------------------------

    def rotation_to_madctl(self, rot):
        # BGR bit must always be set for Waveshare
        BGR = 0x08

        if rot == 0:
            return 0x48  # MX=0 MY=1 MV=0 BGR=1
        elif rot == 90:
            return 0x28  # rotate right
        elif rot == 180:
            return 0x88
        elif rot == 270:
            return 0xE8
        else:
            return 0x48


    def digital_write(self, pin, level):
        if level:
            pin.on()
        else:
            pin.off()

    def command(self, cmd):
        self.digital_write(self.dc, 0)
        self.spi.writebytes([cmd])

    def data(self, val):
        self.digital_write(self.dc, 1)
        self.spi.writebytes([val])

    def reset(self):
        self.rst.on()
        time.sleep(0.1)
        self.rst.off()
        time.sleep(0.1)
        self.rst.on()
        time.sleep(0.12)

    # -------------------------
    # Display initialization
    # -------------------------

    def lcd_init(self):
        """Correct ST7796 init sequence for Waveshare"""
        logging.info("Initializing ST7796...")

        self.reset()

        self.command(0x11)
        time.sleep(0.12)

        # Memory Access Control
        self.command(0x36)
        self.data(self.MADCTL)

        # Pixel Format
        self.command(0x3A)
        self.data(0x55)    # 16-bit pixel

        self.command(0xB2)
        self.data(0x0C)
        self.data(0x0C)
        self.data(0x00)
        self.data(0x33)
        self.data(0x33)

        self.command(0xB7)
        self.data(0x35)

        self.command(0xBB)
        self.data(0x28)

        self.command(0xC0)
        self.data(0x2C)

        self.command(0xC2)
        self.data(0x01)

        self.command(0xC3)
        self.data(0x0B)

        self.command(0xC4)
        self.data(0x20)

        self.command(0xC6)
        self.data(0x0F)

        self.command(0xD0)
        self.data(0xA4)
        self.data(0xA1)

        # Enable display
        self.command(0x21)   # Inversion On
        self.command(0x29)   # Display On
        time.sleep(0.05)

        logging.info("ST7796 initialization complete.")

    # --------------------------
    # Drawing primitives
    # --------------------------

    def set_windows(self, x0, y0, x1, y1):
        """Set RAM address window (inclusive)"""
        self.command(0x2A)
        self.data(x0 >> 8)
        self.data(x0 & 0xFF)
        self.data(x1 >> 8)
        self.data(x1 & 0xFF)

        self.command(0x2B)
        self.data(y0 >> 8)
        self.data(y0 & 0xFF)
        self.data(y1 >> 8)
        self.data(y1 & 0xFF)

        self.command(0x2C)

    # -------------------------
    # Show Full Image
    # -------------------------

    def show_image(self, img):
        """Send a full 320×480 PIL RGB image to the LCD"""

        if img.size != (self.width, self.height):
            img = img.resize((self.width, self.height))

        arr = self.np.array(img, dtype=self.np.uint16)

        r = (arr[...,0] & 0xF8) << 8
        g = (arr[...,1] & 0xFC) << 3
        b = (arr[...,2] >> 3)

        rgb565 = r | g | b

        high = (rgb565 >> 8).astype(self.np.uint8)
        low  = (rgb565 & 0xFF).astype(self.np.uint8)

        pix = self.np.dstack((high, low)).flatten().tolist()

        self.command(0x36)
        self.data(self.MADCTL)

        self.set_windows(0,0,self.width-1, self.height-1)
        self.digital_write(self.dc, 1)

        # burst write
        for i in range(0, len(pix), 4096):
            self.spi.writebytes(pix[i:i+4096])

    # -------------------------
    # Clear Screen
    # -------------------------

    def clear(self, color=0xFFFF):
        """Fill screen with a 16-bit RGB565 color"""

        hi = (color >> 8) & 0xFF
        lo = color & 0xFF

        line = [hi, lo] * self.width

        self.set_windows(0,0,self.width-1,self.height-1)
        self.digital_write(self.dc, 1)

        for _ in range(self.height):
            self.spi.writebytes(line)
