from ui_tabs import Tab
from screensaver_animation import RandomSquareScreensaver

class ScreensaverTab(Tab):
    def __init__(self):
        super().__init__("Screensaver", "🛡️")
        self.full_screen = True
        self._animator = RandomSquareScreensaver()

    def render(self, monitor, width, height):
        return self._animator.render(width, height)
