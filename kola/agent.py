"""Kola agent: look -> understand -> act -> verify, step by step."""
import time

from PIL import ImageChops, ImageDraw

from .classes import CLASSES, FEED_CLASSES, SIDEBAR_CLASSES
from .grounding import Context, describe, ground

POINTER_ACTIONS = {"left_click", "right_click", "double_click", "hover"}
PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0",
           "#f032e6", "#bcf60c", "#fabebe", "#008080", "#9a6324", "#800000"]


def annotate(img, elements, target=None, max_w=1100):
    """Screenshot with every detected element boxed and the chosen target highlighted."""
    im = img.copy()
    d = ImageDraw.Draw(im)
    lw = max(2, im.width // 700)
    for e in elements:
        col = PALETTE[CLASSES.index(e.cls) % len(PALETTE)] if e.cls in CLASSES else "#999999"
        d.rectangle(e.box, outline=col, width=lw)
        d.text((e.box[0] + 3, e.box[1] + 2), f"{e.cls} {e.conf:.2f}", fill=col)
    if target is not None:
        x1, y1, x2, y2 = target.box
        for k in range(3):
            d.rectangle((x1 - 4 - k * 3, y1 - 4 - k * 3, x2 + 4 + k * 3, y2 + 4 + k * 3), outline="#ff0000", width=lw)
        cx, cy = target.center
        r = 10 * lw
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline="#ff0000", width=lw * 2)
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    return im


def screen_changed(a, b, threshold=1.5):
    a = a.convert("L").resize((320, 180))
    b = b.convert("L").resize((320, 180))
    diff = ImageChops.difference(a, b)
    mean = sum(diff.getdata()) / (320 * 180)
    return mean > threshold, mean


class Kola:
    def __init__(self, weights, use_ocr=True, log=print, on_frame=None, speed=1.0):
        from .screen import Screen  # first: makes the process DPI-aware before the mouse library loads
        from .detector import load_detector
        from .executor import Executor
        from .ocr import OCR
        self.log = log
        self.on_frame = on_frame or (lambda img: None)
        self.screen = Screen()
        self.detector = load_detector(weights)
        self.ocr = OCR() if use_ocr and OCR.available() else None
        self.hands = Executor(speed=speed)
        if use_ocr and self.ocr is None:
            self.log("OCR not installed (pip install rapidocr_onnxruntime): text targets like chips/titles won't work.")

    # ---- perception ----
    def look(self):
        img = self.screen.grab()
        t = time.time()
        els = self.detector.detect(img)
        ctx = Context(img, els, self.ocr, known_classes=self.detector.classes)
        self.log(f"  👁  saw {len(els)} elements in {time.time() - t:.2f}s: " + summarize(els))
        return ctx

    def describe_screen(self):
        ctx = self.look()
        self.on_frame(annotate(ctx.img, ctx.elements))
        return ctx

    # ---- execution ----
    def run(self, steps, stop=None):
        for i, step in enumerate(steps, 1):
            if stop is not None and stop.is_set():
                self.log("Stopped.")
                return False
            self.log(f"Step {i}/{len(steps)}: {step_text(step)}")
            if not self.run_step(step):
                self.log(f"✗ Step {i} failed.")
                return False
        self.log("✓ Task complete.")
        return True

    def run_step(self, step):
        a = step["action"]
        if a == "type":
            self.hands.type_text(step["text"])
            return True
        if a == "press":
            self.hands.press(step["key"])
            return True
        if a == "select_all":
            self.hands.select_all()
            return True
        if a == "wait":
            time.sleep(float(step.get("seconds", 1)))
            return True
        if a == "scroll":
            x, y = self.screen.center() if self.screen.mon else (None, None)
            if x is None:
                self.screen.grab()
                x, y = self.screen.center()
            self.hands.scroll(x, y, int(step.get("clicks", -5)))
            time.sleep(1.0)
            return True
        if a == "wait_for":
            deadline = time.time() + float(step.get("timeout", 8))
            while time.time() < deadline:
                ctx = self.look()
                el, why = ground(step["target"], ctx)
                if el:
                    self.on_frame(annotate(ctx.img, ctx.elements))
                    self.log(f"  ✓ ready: {why}")
                    return True
                time.sleep(0.8)
            self.log(f"  timed out waiting for {describe(step['target'])}")
            return False
        if a in POINTER_ACTIONS:
            return self._pointer_step(step)
        self.log(f"  unknown action {a}")
        return False

    def _pointer_step(self, step):
        target = step["target"]
        for attempt in range(int(step.get("attempts", 4))):
            ctx = self.look()
            try:
                el, why = ground(target, ctx)
            except RuntimeError as e:  # OCR missing
                self.log(f"  {e}")
                return False
            self.on_frame(annotate(ctx.img, ctx.elements, el))
            if el is not None:
                self.log(f"  🎯 {why}")
                x, y = self.screen.to_screen(*el.center)
                self.hands.pointer(step["action"], x, y)
                time.sleep(float(step.get("settle", 1.5)))
                changed, amount = screen_changed(ctx.img, self.screen.grab())
                self.log(f"  {'✓ screen changed' if changed else '… no visible change'} (diff {amount:.1f})")
                return True
            self.log(f"  {why}")
            if not self._recover(target, attempt, ctx):
                return False
        return False

    def _recover(self, target, attempt, ctx):
        """Make a hidden target visible: open the sidebar, or scroll the feed."""
        typ = target.get("type")
        if typ in SIDEBAR_CLASSES and attempt == 0:
            menu, _ = ground({"type": "menu_button"}, ctx)
            if menu is not None:
                self.log("  ↳ sidebar looks collapsed — opening the menu")
                self.hands.pointer("left_click", *self.screen.to_screen(*menu.center))
                time.sleep(1.2)
                return True
        if typ in FEED_CLASSES or target.get("inside", {}).get("type") in FEED_CLASSES:
            self.log("  ↳ not on screen — scrolling down")
            x, y = self.screen.center()
            self.hands.scroll(x, y, -5)
            time.sleep(1.5)
            return True
        return False


def summarize(els):
    counts = {}
    for e in els:
        counts[e.cls] = counts.get(e.cls, 0) + 1
    return ", ".join(f"{k}×{v}" if v > 1 else k for k, v in counts.items()) or "nothing"


def step_text(step):
    a = step["action"]
    if a == "type":
        return f'type "{step["text"]}"'
    if a == "press":
        return f"press {step['key']}"
    if a in ("select_all", "wait", "scroll"):
        return a
    return f"{a} → {describe(step['target'])}"
