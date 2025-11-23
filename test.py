from display_driver import DisplayDriver
from PIL import Image

disp = DisplayDriver()
img = Image.new("RGB", (320,480), (255,0,0))  # red test
disp.show_image(img)
