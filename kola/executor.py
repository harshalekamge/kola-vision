"""The hands: smooth, visible mouse movement, hover, clicks and typing."""
import math
import sys
import time

import pyautogui

pyautogui.FAILSAFE = True  # slam the mouse into a screen corner to abort
pyautogui.PAUSE = 0.03


class Executor:
    def __init__(self, speed: float = 1.0, hover_pause: float = 0.45):
        self.speed = speed            # >1 slower and easier to follow, <1 faster
        self.hover_pause = hover_pause

    def move(self, x, y):
        cx, cy = pyautogui.position()
        dist = math.hypot(x - cx, y - cy)
        duration = min(1.1, max(0.3, dist / 1400)) * self.speed
        pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)

    def pointer(self, action, x, y):
        self.move(x, y)
        time.sleep(self.hover_pause)  # lets YouTube show its hover effect, and the audience see the target
        if action == "left_click":
            pyautogui.click()
        elif action == "right_click":
            pyautogui.rightClick()
        elif action == "double_click":
            pyautogui.doubleClick()
        elif action == "hover":
            time.sleep(0.8)
        else:
            raise ValueError(f"Unknown pointer action {action}")

    def type_text(self, text):
        pyautogui.write(text, interval=0.06)

    def press(self, key):
        pyautogui.press(key)

    def select_all(self):
        pyautogui.hotkey("command" if sys.platform == "darwin" else "ctrl", "a")

    def scroll(self, x, y, clicks):
        self.move(x, y)
        pyautogui.scroll(clicks)
