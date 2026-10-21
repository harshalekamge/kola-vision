"""Tests for the planner and grounding (no model, screen or mouse needed).

    python -m pytest tests -q      (or: python tests/test_logic.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kola.classes import CLASSES  # noqa: E402
from kola.detector import Element  # noqa: E402
from kola.grounding import Context, ground  # noqa: E402
from kola.planner import plan  # noqa: E402


class FakeOCR:
    def __init__(self, words):
        self.words = words

    def read(self, img):
        return [Element("text", 0.9, b, text=t) for t, b in self.words]


def ctx_home():
    els = [
        Element("search_box", 0.9, (600, 15, 1200, 55)),
        Element("search_box", 0.4, (100, -40, 900, -10)),  # look-alike (e.g. browser address bar)
        Element("search_button", 0.9, (1200, 15, 1260, 55)),
        Element("watch_later", 0.88, (10, 400, 220, 440)),
        Element("history", 0.91, (10, 350, 220, 390)),
        Element("chip", 0.9, (260, 70, 320, 100)),
        Element("chip", 0.9, (330, 70, 400, 100)),
        Element("chip", 0.9, (410, 70, 490, 100)),
        Element("video_card", 0.9, (260, 120, 700, 480)),
        Element("video_card", 0.9, (720, 120, 1160, 480)),
        Element("sponsored_card", 0.8, (1180, 120, 1620, 520)),
        Element("short_card", 0.9, (500, 600, 700, 950)),
        Element("short_card", 0.9, (260, 602, 460, 950)),
    ]
    words = [
        ("All", (270, 75, 300, 95)), ("Music", (340, 75, 390, 95)), ("Gaming", (420, 75, 480, 95)),
        ("Claude code just became Free Forever...", (270, 400, 690, 420)), ("6 days ago", (270, 440, 380, 460)),
        ("Claude Code tutorial", (730, 400, 1100, 420)), ("2 weeks ago", (730, 440, 850, 460)),
        ("Build apps fast with Firebase", (1190, 400, 1600, 420)), ("Watch", (1200, 470, 1270, 500)),
        ("Sign", (1300, 470, 1340, 500)), ("up", (1345, 470, 1370, 500)),
    ]
    return Context(None, els, FakeOCR(words), known_classes=CLASSES)


def run_first(cmd, ctx):
    steps, _ = plan(cmd)
    tgt = [s for s in steps if "target" in s and s["action"] != "wait_for"][-1]["target"]
    return steps, ground(tgt, ctx)[0]


def test_scenario1_watch_later():
    steps, el = run_first("Go to the Watch Later section.", ctx_home())
    assert steps[0]["target"] == {"type": "watch_later"}
    assert el.cls == "watch_later"


def test_scenario2_search_and_play():
    ctx = ctx_home()
    steps, el = run_first("Search for Claude Code and play the video released 6 days ago.", ctx)
    assert [s["action"] for s in steps] == ["left_click", "select_all", "type", "left_click", "wait_for", "left_click"]
    assert steps[2]["text"] == "Claude Code"
    assert el.box == (260, 120, 700, 480)  # the 6-days-ago card, not the 2-weeks-ago one
    # search box: the confident one, not the look-alike
    assert ground({"type": "search_box"}, ctx)[0].conf == 0.9


def test_scenario3_chip():
    steps, el = run_first("Switch feed to Gaming videos.", ctx_home())
    assert steps[0]["target"] == {"type": "chip", "text": "Gaming"}
    assert el.box == (410, 70, 490, 100)


def test_scenario4_sponsored_button():
    steps, el = run_first("Click the Sign up button on the Firebase ad.", ctx_home())
    assert steps[0]["target"]["inside"]["type"] == "sponsored_card"
    assert el.text == "Sign up"
    assert 1300 <= el.center[0] <= 1370


def test_scenario5_first_short():
    steps, el = run_first("Play the first video on the Shorts shelf.", ctx_home())
    assert steps[0]["target"]["type"] == "short_card"
    assert el.box == (260, 602, 460, 950)  # leftmost, despite list order


def test_right_click_and_missing():
    steps, _ = plan("right click history")
    assert steps[0]["action"] == "right_click"
    el, why = ground({"type": "subscriptions"}, ctx_home())
    assert el is None and "not visible" in why


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
