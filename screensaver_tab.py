from ui_tabs import Tab
from PIL import Image, ImageDraw, ImageFont
import random

class ScreensaverTab(Tab):
    def __init__(self):
        super().__init__("Screensaver", "🛡️")
        self.last_pos = None

    def render(self, monitor, width, height):
        img = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(img)
        # Fill the screen with random flashing colors
        block_size = 40
        for bx in range(0, width, block_size):
            for by in range(0, height, block_size):
                color = (
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255)
                )
                draw.rectangle([bx, by, bx + block_size, by + block_size], fill=color)
        return img
