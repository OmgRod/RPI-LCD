import time
import smbus
import logging
from gpiozero import DigitalOutputDevice, Button


FT6336U_ADDRESS = 0x38

FT6336U_LCD_TOUCH_MAX_POINTS = 2

TP_INT   = 4
TP_RST   = 17


class TouchController():
    """Simple wrapper for the FT6336U touch controller.
    Provides `read_touch_data()` and `get_touch_xy()` returning the
    number of touch points and coordinates list similar to the original.
    """
    def __init__(self):
        try:
            # Initialize I2C
            self.I2C = smbus.SMBus(1)
        except Exception as e:
            logging.error("Failed to initialize I2C: %s", e)
            logging.error("Ensure I2C is enabled: sudo raspi-config -> Interface Options -> I2C")
            raise

        try:
            # Initialize GPIO using gpiozero (no root needed if user is in gpio group)
            self.tp_rst = DigitalOutputDevice(TP_RST, active_high=True, initial_value=True)
            self.tp_int = Button(TP_INT)
        except Exception as e:
            logging.error("Failed to initialize GPIO pins for touch controller: %s", e)
            logging.error("Possible causes: insufficient permissions or pins already in use.")
            logging.error("Try running as root or add your user to the gpio group:")
            logging.error("  sudo usermod -aG gpio $USER")
            raise
        
        self.coordinates = [{"x": 0, "y": 0} for _ in range(FT6336U_LCD_TOUCH_MAX_POINTS)]
        self.point_count = 0
        self.touch_rst()
    
    def Int_Callback(self):
        self.read_touch_data()
    
    def touch_rst(self):
        """Hardware reset for the touch controller."""
        self.tp_rst.off()
        time.sleep(1 / 1000.0)
        self.tp_rst.on()
        time.sleep(50 / 1000.0)
        
    def write_cmd(self, cmd):
        """Write a single byte command over I2C."""
        self.I2C.write_byte(FT6336U_ADDRESS, cmd)

    def read_bytes(self, reg_addr, length):
        # send register address and read multiple bytes
        data = self.I2C.read_i2c_block_data(FT6336U_ADDRESS, reg_addr, length)
        return data
    
    def read_touch_data(self):
        TOUCH_NUM_REG = 0x02
        TOUCH_XY_REG = 0x03
        
        buf = self.read_bytes(TOUCH_NUM_REG, 1)
        
        if buf and buf[0] != 0:
            self.point_count = buf[0]
            buf = self.read_bytes(TOUCH_XY_REG, 6 * self.point_count)
            for i in range(2):
                self.coordinates[i]["x"] = 0
                self.coordinates[i]["y"] = 0
            
            if buf:
                for i in range(self.point_count):
                    # convert returned data to screen coordinates
                    self.coordinates[i]["x"] = ((buf[(i * 6) + 0] & 0x0f) << 8) + buf[(i * 6) + 1]
                    self.coordinates[i]["y"] = ((buf[(i * 6) + 2] & 0x0f) << 8) + buf[(i * 6) + 3]
    
    def get_touch_xy(self):
        point = self.point_count
        # reset count after read
        self.point_count = 0

        if point != 0:
            return point, self.coordinates
        else:
            return 0 , []
