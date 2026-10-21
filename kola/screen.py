"""Screen capture and pixel -> mouse-coordinate mapping (handles Windows DPI scaling and Mac Retina)."""
import sys

if sys.platform.startswith("win"):
    # Make this process DPI-aware so screenshot pixels == mouse coordinates on 125%/150% displays.
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import mss  # noqa: E402
from PIL import Image  # noqa: E402


class Screen:
    def __init__(self, monitor: int = 1):
        self.monitor = monitor  # 1 = primary monitor
        self.mon = None
        self.scale = 1.0

    def grab(self) -> Image.Image:
        with mss.mss() as s:
            self.mon = s.monitors[self.monitor]
            raw = s.grab(self.mon)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        # Retina: image is 2x the monitor size reported in points -> scale 2.0
        self.scale = img.width / self.mon["width"]
        return img

    def to_screen(self, x: float, y: float):
        """Image pixel -> coordinates for pyautogui."""
        return self.mon["left"] + x / self.scale, self.mon["top"] + y / self.scale

    def center(self):
        return self.mon["left"] + self.mon["width"] / 2, self.mon["top"] + self.mon["height"] / 2
