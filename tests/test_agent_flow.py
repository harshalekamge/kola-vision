"""End-to-end test of the agent loop with a simulated screen, model and mouse.

Runs the real planner, grounding and Kola.run() step logic; only the screenshot,
YOLO model and pyautogui are replaced by fakes.

    python tests/test_agent_flow.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from kola.agent import Kola  # noqa: E402
from kola.classes import CLASSES  # noqa: E402
from kola.detector import Element  # noqa: E402
from kola.planner import plan  # noqa: E402

HOME = [
    ("search_box", (600, 15, 1200, 55)), ("search_button", (1200, 15, 1260, 55)),
    ("menu_button", (10, 15, 50, 55)), ("watch_later", (10, 400, 220, 440)),
]
RESULTS = HOME[:3] + [("video_card", (300, 300, 1500, 500)), ("video_card", (300, 520, 1500, 720))]


class FakeWorld:
    """Pretends to be the browser: the page changes when the search button is clicked or Enter pressed."""

    def __init__(self, show_search_button=True):
        self.page = "home"
        self.show_search_button = show_search_button
        self.typed = ""
        self.actions = []

    def elements(self):
        els = RESULTS if self.page == "results" else HOME
        return [Element(c, 0.95, b) for c, b in els if c != "search_button" or self.show_search_button]


class FakeScreen:
    def __init__(self, world):
        self.world, self.mon, self.scale = world, {"left": 0, "top": 0, "width": 1920, "height": 1080}, 1.0

    def grab(self):
        # a different image per page, so "screen changed" can be detected
        return Image.new("RGB", (1920, 1080), "white" if self.world.page == "home" else "gray")

    def to_screen(self, x, y):
        return x, y

    def center(self):
        return 960, 540


class FakeDetector:
    classes = CLASSES

    def __init__(self, world):
        self.world = world

    def detect(self, img):
        return self.world.elements()


class FakeHands:
    speed = 1.0

    def __init__(self, world):
        self.world = world

    def pointer(self, action, x, y):
        self.world.actions.append((action, round(x), round(y)))
        if (1200 <= x <= 1260) and (15 <= y <= 55):  # search button
            self.world.page = "results"

    def type_text(self, text):
        self.world.typed += text
        self.world.actions.append(("type", text))

    def select_all(self):
        self.world.typed = ""
        self.world.actions.append(("select_all",))

    def press(self, key):
        self.world.actions.append(("press", key))
        if key == "enter" and self.world.typed:
            self.world.page = "results"

    def scroll(self, x, y, clicks):
        self.world.actions.append(("scroll", clicks))


def make_kola(world):
    k = Kola.__new__(Kola)
    k.log = lambda m: None
    k.on_frame = lambda img: None
    k.screen = FakeScreen(world)
    k.detector = FakeDetector(world)
    k.ocr = None
    k.hands = FakeHands(world)
    return k


def run(command, world):
    import kola.agent as agent
    agent.time.sleep = lambda s: None  # don't actually wait
    steps, _ = plan(command)
    return make_kola(world).run(steps)


def test_search_chanux_bro():
    w = FakeWorld()
    assert run("Search for chanux bro", w)
    assert w.typed == "chanux bro"
    assert w.page == "results"
    assert w.actions[0] == ("left_click", 900, 35)  # clicked the search box first
    assert ("left_click", 1230, 35) in w.actions  # then the search button


def test_search_and_play_first_video():
    w = FakeWorld()
    assert run("Search for chanux bro and play the first video", w)
    assert w.actions[-1] == ("left_click", 900, 400)  # first video card


def test_search_button_not_detected_falls_back_to_enter():
    w = FakeWorld(show_search_button=False)
    assert run("Search for chanux bro", w)
    assert ("press", "enter") in w.actions
    assert w.page == "results"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
