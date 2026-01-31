from ui_tabs import Tab
from PIL import Image, ImageDraw, ImageFont
import random

class ScreensaverTab(Tab):
    def __init__(self):
        super().__init__("Screensaver", "🛡️")
        self.last_pos = None

    def render(self, monitor, width, height):
        img = Image.new('RGB', (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Draw moving shapes/text to prevent burn-in
        if self.last_pos is None:
            self.last_pos = (random.randint(40, width-40), random.randint(40, height-40))
        else:
            # Move to a new random position
            self.last_pos = (random.randint(40, width-40), random.randint(40, height-40))
        x, y = self.last_pos
        # Draw a circle
        draw.ellipse([x-20, y-20, x+20, y+20], fill=(random.randint(50,255), random.randint(50,255), random.randint(50,255)))
        # Draw text
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except Exception:
            font = ImageFont.load_default()
        draw.text((x, y), "Screensaver", fill=(255,255,255), font=font, anchor="mm")
        return img
