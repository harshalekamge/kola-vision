"""Kola demo app: tell Kola what to do on YouTube and watch it see the screen and act.

    python kola_demo.py                      # picks models/kola_yolo.pt (full install) or .onnx (lite)
    python kola_demo.py --weights path/to/best.pt --no-ocr

Put YouTube in Chrome behind this window (best: Chrome full screen with F11).
Emergency stop: move the mouse hard into a screen corner.
Needs: pip install customtkinter
"""
import argparse
import json
import queue
import re
import threading
import time
from pathlib import Path

try:
    import customtkinter as ctk
except ImportError:
    raise SystemExit("The Kola app needs CustomTkinter for its interface. Install it with:  pip install customtkinter")

from kola.classes import CLASSES, FRIENDLY
from kola.planner import plan

ROOT = Path(__file__).resolve().parent

# ---------- design tokens ----------
BG = "#ECEFF3"        # window background
CARD = "#FFFFFF"      # cards
SOFT = "#F3F5F8"      # inner panels, input bar
LINE = "#E4E8EE"      # hairlines, outlines
INK = "#16181D"       # text, primary buttons
INK_HOVER = "#2C2F37"
MUTED = "#8A90A0"     # secondary text
BEACON = "#F4A62A"    # what Kola is about to act on (matches the ring in the live view)
DONE = "#2E9E73"
ALERT = "#D2453B"

EXAMPLES = [
    ("Watch later", "Go to the Watch Later section"),
    ("Search and play", "Search for Claude Code and play the video released 6 days ago"),
    ("Gaming feed", "Switch feed to Gaming videos"),
    ("Sign up on an ad", "Click the Sign up button on the Firebase ad"),
    ("First Short", "Play the first video on the Shorts shelf"),
]
ACTIONS = {"Click": "left_click", "Right-click": "right_click", "Double-click": "double_click", "Hover": "hover"}
TARGET_NAMES = {FRIENDLY[c]: c for c in CLASSES} | {"Any text on screen": "text"}


# ---------- plain-language step descriptions ----------
ORDINAL = {0: "first", 1: "second", 2: "third", 3: "fourth", 4: "fifth", -1: "last"}
NOUN = {
    "home": "Home", "shorts": "Shorts", "subscriptions": "Subscriptions", "history": "History",
    "watch_later": "Watch later", "menu_button": "the menu button", "search_box": "the search box",
    "search_button": "the search button", "chip": "topic", "video_card": "video",
    "short_card": "Shorts video", "sponsored_card": "sponsored card",
}


def _clean(p):
    return p.lstrip("~")


def target_name(t):
    typ = t.get("type", "text")
    if typ == "text":
        name = f"“{_clean(t.get('text', ''))}”"
    elif typ == "chip" and t.get("text"):
        name = f"the “{_clean(t['text'])}” topic"
    elif typ in ("video_card", "short_card", "sponsored_card", "chip"):
        idx = t.get("index", 0)
        name = f"the {ORDINAL.get(idx, f'#{idx + 1}')} {NOUN[typ]}"
        if t.get("contains"):
            name = f"the {NOUN[typ]} showing " + " and ".join(f"“{_clean(c)}”" for c in t["contains"])
    else:
        name = NOUN.get(typ) or FRIENDLY.get(typ) or typ.replace("_", " ")
    if t.get("inside"):
        inner = t["inside"]
        owner = ", ".join(_clean(c) for c in inner.get("contains", []))
        name += f" in the {owner + ' ' if owner else ''}{NOUN.get(inner.get('type'), 'area')}"
    return name


def say(step):
    a = step["action"]
    if a == "type":
        return f"Type “{step['text']}”"
    if a == "select_all":
        return "Select any text already there"
    if a == "press":
        return f"Press {step['key'].title()}"
    if a == "scroll":
        return "Scroll down"
    if a == "wait":
        return "Wait a moment"
    if a == "wait_for":
        return "Wait for results to load" if step["target"].get("type") == "video_card" else f"Wait for {target_name(step['target'])}"
    verb = {"left_click": "Click", "right_click": "Right-click", "double_click": "Double-click", "hover": "Hover over"}[a]
    return f"{verb} {target_name(step['target'])}"


def friendly_detail(msg):
    """Turn an agent log line into a short phrase for the progress list."""
    m = msg.strip()
    if m.startswith("👁"):
        n = re.search(r"saw (\d+) elements", m)
        return f"Looking at the screen… recognised {n.group(1)} elements" if n else "Looking at the screen…"
    if m.startswith("🎯"):
        c = re.search(r"conf ([\d.]+)", m)
        return f"Found it ({round(float(c.group(1)) * 100)}% sure)" if c else "Found it"
    if m.startswith("↳"):
        return m[1:].strip().capitalize()
    if "screen changed" in m:
        return "Done, the screen changed"
    if "no visible change" in m:
        return "Done (no visible change on screen)"
    if m.startswith("✓ ready"):
        return "Results are on screen"
    return m


class Tooltip:
    """Small label that appears next to a widget on hover."""

    def __init__(self, widget, text, font):
        self.widget, self.text, self.font, self.tip = widget, text, font, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() // 2 - 14
        self.tip = ctk.CTkToplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.configure(fg_color=INK)
        ctk.CTkLabel(self.tip, text=self.text, font=self.font, text_color=CARD, fg_color=INK,
                     padx=10, pady=4).pack()
        self.tip.geometry(f"+{x}+{y}")

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class App:
    def __init__(self, root, weights, use_ocr):
        self.root, self.weights, self.use_ocr = root, weights, use_ocr
        self.kola = None
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self._last_frame = None
        self._ctk_img = None
        self._rows = []
        self._current = None
        self._last_problem = ""

        fam = "Segoe UI Variable Text"
        self.f_title = ctk.CTkFont(fam, 20, "bold")
        self.f_h = ctk.CTkFont(fam, 15, "bold")
        self.f_body = ctk.CTkFont(fam, 13)
        self.f_bold = ctk.CTkFont(fam, 13, "bold")
        self.f_small = ctk.CTkFont(fam, 12)
        self.f_input = ctk.CTkFont(fam, 15)
        self.f_icon = ctk.CTkFont("Segoe UI Symbol", 17)
        self.f_mono = ctk.CTkFont("Consolas", 12)

        root.title("Kola")
        root.geometry("1440x880")
        root.minsize(1180, 740)
        root.configure(fg_color=BG)
        root.grid_columnconfigure(2, weight=1)
        root.grid_rowconfigure(1, weight=1)

        self._rail()
        self._topbar()
        self._left_column()
        self._center()
        self._right_column()

        threading.Thread(target=self._load, daemon=True).start()
        root.after(80, self._poll)

    # ---------- building blocks ----------
    def card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=24, **kw)

    def label(self, parent, text, font=None, color=INK, **kw):
        return ctk.CTkLabel(parent, text=text, font=font or self.f_body, text_color=color, **kw)

    def pill(self, parent, text, command, dark=True, **kw):
        return ctk.CTkButton(parent, text=text, command=command, height=kw.pop("height", 40), corner_radius=20,
                             font=kw.pop("font", self.f_bold),
                             fg_color=INK if dark else CARD, hover_color=INK_HOVER if dark else SOFT,
                             text_color=CARD if dark else INK, border_width=0 if dark else 1, border_color=LINE, **kw)

    def circle(self, parent, icon, command, dark=False, size=44):
        return ctk.CTkButton(parent, text=icon, command=command, width=size, height=size, corner_radius=size // 2,
                             font=self.f_icon, fg_color=INK if dark else CARD, hover_color=INK_HOVER if dark else SOFT,
                             text_color=CARD if dark else INK, border_width=0 if dark else 1, border_color=LINE)

    # ---------- layout ----------
    def _rail(self):
        rail = ctk.CTkFrame(self.root, fg_color="transparent", width=76)
        rail.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(18, 4), pady=18)
        logo = ctk.CTkLabel(rail, text="K", width=44, height=44, corner_radius=22, fg_color=CARD,
                            text_color=INK, font=self.f_title)
        logo.pack(pady=(0, 60))
        for icon, tip, cmd, dark in (("👁", "Look at screen", self.look, True),
                                     ("☰", "Show or hide steps and log", self.toggle_panel, False),
                                     ("■", "Stop", self.stop.set, False)):
            b = self.circle(rail, icon, cmd, dark=dark)
            b.pack(pady=7)
            Tooltip(b, tip, self.f_small)

    def _topbar(self):
        bar = ctk.CTkFrame(self.root, fg_color="transparent")
        bar.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(10, 22), pady=(18, 10))
        self.label(bar, "Kola", self.f_title).pack(side="left", padx=(0, 16))
        status = ctk.CTkFrame(bar, fg_color=CARD, corner_radius=22, height=44)
        status.pack(side="left")
        self.dot = ctk.CTkLabel(status, text="●", text_color=MUTED, font=self.f_body, width=10)
        self.dot.pack(side="left", padx=(18, 8), pady=8)
        self.status = self.label(status, "Getting ready…", self.f_bold)
        self.status.pack(side="left")
        self.model_label = self.label(status, "", self.f_small, MUTED)
        self.model_label.pack(side="left", padx=(12, 18))
        self.pill(bar, "Look at screen", self.look, width=150, height=44).pack(side="right")

    def _left_column(self):
        col = ctk.CTkFrame(self.root, fg_color="transparent", width=250)
        col.grid(row=1, column=1, sticky="ns", padx=(10, 6), pady=(0, 18))
        self.label(col, "Try a task", self.f_h).pack(anchor="w", padx=6, pady=(2, 8))
        for title, command in EXAMPLES:
            c = self.card(col)
            c.pack(fill="x", pady=6, padx=2)
            head = ctk.CTkFrame(c, fg_color="transparent")
            head.pack(fill="x", padx=18, pady=(16, 4))
            self.label(head, title, self.f_h).pack(side="left")
            ctk.CTkButton(head, text="↗", width=30, height=30, corner_radius=15, fg_color=SOFT, hover_color=LINE,
                          text_color=INK, font=self.f_body, command=lambda t=command: self._use_example(t)).pack(side="right")
            self.label(c, command, self.f_small, MUTED, wraplength=200, justify="left", anchor="w").pack(
                fill="x", padx=18, pady=(0, 16))
            for w in (c, head):
                w.bind("<Button-1>", lambda e, t=command: self._use_example(t))

    def _center(self):
        c = self.card(self.root)
        c.grid(row=1, column=2, sticky="nsew", padx=6, pady=(0, 18))
        c.grid_columnconfigure(0, weight=1)
        c.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(c, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        self.label(head, "What Kola sees", self.f_h).pack(side="left")
        legend = ctk.CTkFrame(head, fg_color="transparent")
        legend.pack(side="right")
        ctk.CTkLabel(legend, text="", width=12, height=12, corner_radius=6, fg_color=BEACON).pack(side="left")
        self.label(legend, "acting on", self.f_small, MUTED).pack(side="left", padx=(6, 14))
        ctk.CTkLabel(legend, text="", width=12, height=12, corner_radius=6, fg_color="#4363d8").pack(side="left")
        self.label(legend, "recognised", self.f_small, MUTED).pack(side="left", padx=6)

        self.view_box = ctk.CTkFrame(c, fg_color=SOFT, corner_radius=18)
        self.view_box.grid(row=1, column=0, sticky="nsew", padx=24)
        self.view = ctk.CTkLabel(self.view_box, text="Kola's view of your screen appears here.\n\n"
                                 "Press “Look at screen”, or tell Kola what to do below.",
                                 font=self.f_body, text_color=MUTED)
        self.view.pack(fill="both", expand=True, padx=10, pady=10)
        self.view_box.bind("<Configure>", lambda e: self._last_frame is not None and self._show(self._last_frame))

        # steps (JSON) and log, side by side under the live view
        self.panel = ctk.CTkFrame(c, fg_color="transparent")
        self.panel.grid(row=2, column=0, sticky="ew", padx=24, pady=(14, 0))
        self.panel.grid_columnconfigure((0, 1), weight=1, uniform="p")
        for col, title in ((0, "Steps"), (1, "Log")):
            box = ctk.CTkFrame(self.panel, fg_color=SOFT, corner_radius=18)
            box.grid(row=0, column=col, sticky="nsew", padx=(0, 7) if col == 0 else (7, 0))
            head = ctk.CTkFrame(box, fg_color="transparent")
            head.pack(fill="x", padx=16, pady=(10, 4))
            self.label(head, title, self.f_bold).pack(side="left")
            text = ctk.CTkTextbox(box, height=150, font=self.f_mono if col == 0 else self.f_small, fg_color=SOFT, text_color=INK,
                                  corner_radius=0, border_width=0, wrap="none" if col == 0 else "word",
                                  scrollbar_button_color=SOFT, scrollbar_button_hover_color=LINE)
            text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            if col == 0:
                self.label(head, "editable", self.f_small, MUTED).pack(side="left", padx=8)
                self.pill(head, "Run steps", self.run_steps_text, height=30, font=self.f_small, width=100).pack(side="right")
                self.steps_text = text
                text.insert("1.0", "[]")
            else:
                self.label(head, "what Kola saw and did", self.f_small, MUTED).pack(side="left", padx=8)
                self.log_text = text
                text.configure(state="disabled")

        bar = ctk.CTkFrame(c, fg_color=SOFT, corner_radius=22)
        bar.grid(row=3, column=0, sticky="ew", padx=24, pady=20)
        self.cmd = ctk.CTkEntry(bar, placeholder_text="Tell Kola what to do, for example: Go to Watch Later",
                                height=48, border_width=0, fg_color=SOFT, font=self.f_input, text_color=INK,
                                placeholder_text_color=MUTED)
        self.cmd.pack(side="left", fill="x", expand=True, padx=(18, 8), pady=6)
        self.cmd.bind("<Return>", lambda e: self.run_command())
        self.circle(bar, "↑", self.run_command, dark=True, size=42).pack(side="right", padx=8, pady=8)

    def _right_column(self):
        col = ctk.CTkFrame(self.root, fg_color="transparent", width=340)
        col.grid(row=1, column=3, sticky="ns", padx=(6, 22), pady=(0, 18))
        col.grid_propagate(False)
        col.grid_columnconfigure(0, weight=1)
        col.grid_rowconfigure(0, weight=1)

        # progress
        p = self.card(col)
        p.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self.label(p, "Progress", self.f_h).pack(anchor="w", padx=22, pady=(18, 8))
        self.steps_box = ctk.CTkScrollableFrame(p, fg_color="transparent", scrollbar_button_color=CARD,
                                                scrollbar_button_hover_color=LINE)
        self.steps_box.pack(fill="both", expand=True, padx=10)
        self.empty = self.label(self.steps_box, "Each step shows up here as Kola works.", self.f_small, MUTED)
        self.empty.pack(anchor="w", padx=12)
        self.result = self.label(p, "", self.f_bold, wraplength=290, justify="left", anchor="w")
        self.result.pack(fill="x", padx=22, pady=(4, 18))

        # do one thing
        d = self.card(col)
        d.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.label(d, "Do one thing", self.f_h).pack(anchor="w", padx=22, pady=(18, 2))
        self.label(d, "Pick an action and a place on YouTube.", self.f_small, MUTED).pack(anchor="w", padx=22, pady=(0, 10))
        row = ctk.CTkFrame(d, fg_color="transparent")
        row.pack(fill="x", padx=22)
        menu = dict(fg_color=SOFT, button_color=SOFT, button_hover_color=LINE, text_color=INK, corner_radius=14,
                    dropdown_fg_color=CARD, dropdown_text_color=INK, dropdown_hover_color=SOFT,
                    font=self.f_body, dropdown_font=self.f_body, height=38)
        self.action = ctk.CTkOptionMenu(row, values=list(ACTIONS), width=110, **menu)
        self.action.set("Click")
        self.action.pack(side="left")
        self.target = ctk.CTkOptionMenu(row, values=list(TARGET_NAMES), command=self._target_changed, **menu)
        self.target.set(FRIENDLY["watch_later"])
        self.target.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.ttext = ctk.CTkEntry(d, placeholder_text="Label to look for (optional)", height=38, corner_radius=14,
                                  border_width=0, fg_color=SOFT, font=self.f_body, text_color=INK,
                                  placeholder_text_color=MUTED)
        self.ttext.pack(fill="x", padx=22, pady=(8, 0))
        self.ttext.bind("<Return>", lambda e: self.run_manual())
        row2 = ctk.CTkFrame(d, fg_color="transparent")
        row2.pack(fill="x", padx=22, pady=(8, 18))
        self.label(row2, "Which one", self.f_small, MUTED).pack(side="left")
        self.index = ctk.CTkOptionMenu(row2, values=[str(i) for i in range(1, 11)], width=64, **menu)
        self.index.set("1")
        self.index.pack(side="left", padx=8)
        self.pill(row2, "Do it", self.run_manual, width=96).pack(side="right")

        # settings
        s = self.card(col)
        s.grid(row=2, column=0, sticky="ew")
        self.label(s, "Settings", self.f_h).pack(anchor="w", padx=22, pady=(18, 8))
        sp = ctk.CTkFrame(s, fg_color="transparent")
        sp.pack(fill="x", padx=22)
        self.label(sp, "Cursor speed", self.f_body).pack(side="left")
        self.speed = ctk.DoubleVar(value=1.0)
        ctk.CTkSlider(sp, from_=2.0, to=0.4, variable=self.speed, width=140, button_color=INK,
                      button_hover_color=INK_HOVER, progress_color=INK, fg_color=LINE).pack(side="right")
        self.hide = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(s, text="Minimize Kola while it works", variable=self.hide, font=self.f_body,
                        text_color=INK, fg_color=INK, hover_color=INK_HOVER, border_color="#C9CFD9",
                        checkmark_color=CARD, corner_radius=7, checkbox_width=22, checkbox_height=22).pack(
            anchor="w", padx=22, pady=(12, 18))

    def toggle_panel(self):
        """Show or hide the steps + log panel under the live view."""
        if self.panel.winfo_ismapped():
            self.panel.grid_remove()
        else:
            self.panel.grid()

    # ---------- plumbing ----------
    def log(self, msg):
        self.q.put(("log", msg))

    def frame(self, img):
        self.q.put(("frame", img))

    def set_state(self, text, kind):
        self.status.configure(text=text)
        self.dot.configure(text_color={"idle": MUTED, "ready": DONE, "busy": BEACON, "error": ALERT}[kind])

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self._on_log(val)
                elif kind == "frame":
                    self._last_frame = val
                    self._show(val)
                elif kind == "state":
                    self.set_state(*val)
                elif kind == "model":
                    self.model_label.configure(text=val)
                elif kind == "step":
                    self._on_step(*val)
                elif kind == "done":
                    self._finish(val)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _on_log(self, msg):
        line = f"{time.strftime('%H:%M:%S')}  {msg}"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        if msg.startswith("  ") and self._current is not None and self._current <= len(self._rows):
            detail = self._rows[self._current - 1][2]
            detail.configure(text=friendly_detail(msg))
            if not detail.winfo_ismapped():
                detail.pack(fill="x")
            if any(k in msg for k in ("not visible", "timed out", "only ", "needs text", "unknown")):
                self._last_problem = msg.strip()

    def _show(self, img):
        try:
            scale = ctk.ScalingTracker.get_widget_scaling(self.view_box)
        except Exception:
            scale = 1.0
        w = max(300, int((self.view_box.winfo_width() - 24) / scale))
        h = max(200, int((self.view_box.winfo_height() - 24) / scale))
        r = min(w / img.width, h / img.height)
        size = (max(1, int(img.width * r)), max(1, int(img.height * r)))
        self._ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        self.view.configure(image=self._ctk_img, text="")

    def _load(self):
        if not Path(self.weights).exists():
            self.q.put(("state", ("Model missing: put kola_yolo.pt or .onnx in models/", "error")))
            self.log(f"Model file not found: {self.weights}")
            return
        try:
            from kola.agent import Kola
            self.kola = Kola(self.weights, use_ocr=self.use_ocr, log=self.log, on_frame=self.frame)
            self.kola.on_step = lambda i, state: self.q.put(("step", (i, state)))
            if self.kola.ocr is not None:
                self.q.put(("state", ("Getting text reading ready…", "idle")))
                self.log(f"Warming up OCR ({self.kola.ocr.backend})…")
                from PIL import Image
                self.kola.ocr.read(Image.new("RGB", (200, 60), "white"))
            self.q.put(("model", Path(self.weights).name))
            self.q.put(("state", ("Ready", "ready")))
            self.log("Kola is ready.")
        except Exception as e:
            self.q.put(("state", ("Couldn't start, see the log", "error")))
            self.log(f"Failed to load model: {e}")

    # ---------- running tasks ----------
    def _show_plan(self, steps):
        for w in self.steps_box.winfo_children():
            w.destroy()
        self._rows = []
        for i, step in enumerate(steps, 1):
            row = ctk.CTkFrame(self.steps_box, fg_color="transparent")
            row.pack(fill="x", pady=5)
            icon = ctk.CTkLabel(row, text="○", width=28, font=self.f_h, text_color=MUTED)
            icon.pack(side="left", anchor="n")
            col = ctk.CTkFrame(row, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True)
            title = self.label(col, say(step), self.f_body, wraplength=240, justify="left", anchor="w", height=22)
            title.pack(fill="x")
            detail = self.label(col, "", self.f_small, MUTED, wraplength=240, justify="left", anchor="w", height=18)
            self._rows.append((icon, title, detail))
        self.result.configure(text="")
        self.steps_text.delete("1.0", "end")
        self.steps_text.insert("1.0", json.dumps(steps, indent=2))

    def _on_step(self, i, state):
        if i > len(self._rows):
            return
        icon, title, _ = self._rows[i - 1]
        if state == "running":
            self._current = i
            icon.configure(text="◉", text_color=BEACON)
            title.configure(font=self.f_bold)
        elif state == "done":
            icon.configure(text="✓", text_color=DONE)
            title.configure(font=self.f_body)
        elif state == "failed":
            icon.configure(text="✕", text_color=ALERT)
            title.configure(font=self.f_body)

    def _finish(self, ok):
        self.busy = False
        self._current = None
        if ok:
            self.result.configure(text="Done." if self._rows else "", text_color=DONE)
        elif self.stop.is_set():
            self.result.configure(text="Stopped.", text_color=MUTED)
        else:
            reason = self._last_problem or "see the log for details."
            self.result.configure(text=f"Kola couldn't finish: {reason}", text_color=ALERT)
        self.set_state("Ready", "ready")
        if self.hide.get():
            self.root.deiconify()
            self.root.lift()

    def _say(self, text, color=MUTED):
        self.result.configure(text=text, text_color=color)

    def _start(self, steps=None, fn=None):
        if self.kola is None:
            return self._say("Kola is still getting ready. Try again in a moment.")
        if self.busy:
            return self._say("Kola is busy. Press ■ to stop first.")
        if steps is not None:
            self._show_plan(steps)
            fn = lambda: self.kola.run(steps, self.stop)  # noqa: E731
        self.busy = True
        self._last_problem = ""
        self.stop.clear()
        self.kola.hands.speed = float(self.speed.get())
        self.set_state("Working…", "busy")
        if self.hide.get():
            self.root.iconify()

        def work():
            time.sleep(0.9 if self.hide.get() else 0.2)  # let the window get out of the way
            ok = False
            try:
                ok = bool(fn())
            except Exception as e:
                self.log(f"Error: {e}")
                self._last_problem = str(e)
            finally:
                self.q.put(("done", ok))
        threading.Thread(target=work, daemon=True).start()

    def _use_example(self, command):
        self.cmd.delete(0, "end")
        self.cmd.insert(0, command)
        self.cmd.focus_set()

    def _target_changed(self, value):
        cls = TARGET_NAMES.get(value)
        hint = {"search_box": "What to search for", "text": "Text to click"}.get(cls, "Label to look for (optional)")
        self.ttext.configure(placeholder_text=hint)

    def run_command(self):
        text = self.cmd.get().strip()
        if not text:
            self.cmd.focus_set()
            return
        try:
            steps, why = plan(text)
        except ValueError:
            return self._say("Kola doesn't understand that yet. Try one of the tasks on the left.", ALERT)
        self.log(f"Plan: {why} ({len(steps)} steps)")
        self._start(steps)

    def run_manual(self):
        cls = TARGET_NAMES.get(self.target.get(), "text")
        text = self.ttext.get().strip()
        if cls == "search_box" and text:
            steps, _ = plan(f"Search for {text}")
            return self._start(steps)
        if cls == "text" and not text:
            return self._say("Type the text you want Kola to click.", ALERT)
        tgt = {"type": cls}
        if text:
            tgt["text"] = "~" + text
        idx = int(self.index.get() or 1) - 1
        if idx:
            tgt["index"] = idx
        self._start([{"action": ACTIONS[self.action.get()], "target": tgt, "settle": 2}])

    def run_steps_text(self):
        try:
            steps = json.loads(self.steps_text.get("1.0", "end"))
        except json.JSONDecodeError as e:
            return self._say(f"The steps aren't valid JSON: {e}", ALERT)
        self._start(steps)

    def look(self):
        if self.kola is not None and not self.busy:
            for w in self.steps_box.winfo_children():
                w.destroy()
            self._rows = []
            self._say("")
        self._start(fn=lambda: self.kola.describe_screen() is not None)


def default_weights():
    """Use the .pt model when PyTorch/Ultralytics is installed, otherwise the .onnx model."""
    import importlib.util
    pt, onnx = ROOT / "models" / "kola_yolo.pt", ROOT / "models" / "kola_yolo.onnx"
    has_ultralytics = importlib.util.find_spec("ultralytics") is not None
    has_onnxruntime = importlib.util.find_spec("onnxruntime") is not None
    if pt.exists() and (has_ultralytics or not (onnx.exists() and has_onnxruntime)):
        return str(pt)
    if onnx.exists():
        return str(onnx)
    return str(pt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=default_weights(),
                    help="trained model: .pt (full install, uses the GPU) or .onnx (lite install)")
    ap.add_argument("--no-ocr", action="store_true", help="skip OCR (chips/titles/text targets won't work)")
    a = ap.parse_args()
    ctk.set_appearance_mode("light")
    root = ctk.CTk()
    App(root, a.weights, not a.no_ocr)
    root.mainloop()


if __name__ == "__main__":
    main()
