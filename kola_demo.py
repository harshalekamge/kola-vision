"""Kola demo app — screen understanding + task execution on YouTube.

    python kola_demo.py                      # picks models/kola_yolo.pt (full install) or .onnx (lite)
    python kola_demo.py --weights path/to/best.pt --no-ocr

Put YouTube in Chrome behind this window (best: Chrome full screen with F11).
Emergency stop: move the mouse hard into a screen corner.
"""
import argparse
import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext, ttk

from kola.classes import CLASSES, FRIENDLY
from kola.planner import plan

ROOT = Path(__file__).resolve().parent

SCENARIOS = [
    "Go to the Watch Later section",
    "Search for Claude Code and play the video released 6 days ago",
    "Switch feed to Gaming videos",
    "Click the Sign up button on the Firebase ad",
    "Play the first video on the Shorts shelf",
]
ACTIONS = ["left_click", "right_click", "double_click", "hover"]


class App:
    def __init__(self, root, weights, use_ocr):
        self.root = root
        self.weights = weights
        self.use_ocr = use_ocr
        self.kola = None
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self._photo = None

        root.title("Kola — Screen Understanding & Action")
        root.geometry("1380x820")
        root.minsize(1100, 680)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Sub.TLabel", foreground="#666")
        style.configure("Go.TButton", font=("Segoe UI", 10, "bold"))

        left = ttk.Frame(root, padding=12)
        left.pack(side="left", fill="y")
        right = ttk.Frame(root, padding=(0, 12, 12, 12))
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="Kola", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Multimodal assistant · screen understanding module", style="Sub.TLabel").pack(anchor="w", pady=(0, 10))

        # --- natural-language command ---
        box = ttk.LabelFrame(left, text=" 1 · Say a command ", padding=8)
        box.pack(fill="x", pady=4)
        self.scenario = ttk.Combobox(box, values=[f"Scenario {i + 1}: {s}" for i, s in enumerate(SCENARIOS)], state="readonly", width=52)
        self.scenario.set("Pick a demo scenario…")
        self.scenario.bind("<<ComboboxSelected>>", self.pick_scenario)
        self.scenario.pack(fill="x")
        self.cmd = ttk.Entry(box, width=54)
        self.cmd.pack(fill="x", pady=6)
        self.cmd.bind("<Return>", lambda e: self.run_command())
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Button(row, text="Plan only", command=self.plan_only).pack(side="left")
        ttk.Button(row, text="▶ Run command", style="Go.TButton", command=self.run_command).pack(side="right")

        # --- manual target picker (the original requirement) ---
        box = ttk.LabelFrame(left, text=" 2 · Pick action + navigation point ", padding=8)
        box.pack(fill="x", pady=4)
        grid = ttk.Frame(box)
        grid.pack(fill="x")
        ttk.Label(grid, text="Action").grid(row=0, column=0, sticky="w")
        self.action = ttk.Combobox(grid, values=ACTIONS, state="readonly", width=16)
        self.action.set("left_click")
        self.action.grid(row=0, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(grid, text="Target").grid(row=1, column=0, sticky="w")
        self.target = ttk.Combobox(grid, values=[f"{c} — {FRIENDLY[c]}" for c in CLASSES] + ["text — any text on screen"], state="readonly", width=32)
        self.target.set(f"watch_later — {FRIENDLY['watch_later']}")
        self.target.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(grid, text="Text (optional)").grid(row=2, column=0, sticky="w")
        self.ttext = ttk.Entry(grid, width=24)
        self.ttext.grid(row=2, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(grid, text="Which one (#)").grid(row=3, column=0, sticky="w")
        self.index = ttk.Spinbox(grid, from_=1, to=50, width=5)
        self.index.set(1)
        self.index.grid(row=3, column=1, sticky="w", padx=4, pady=2)
        ttk.Button(box, text="▶ Do it", style="Go.TButton", command=self.run_manual).pack(anchor="e", pady=(6, 0))

        # --- steps JSON (contract with the language module) ---
        box = ttk.LabelFrame(left, text=" 3 · Steps (interface with the language module) ", padding=8)
        box.pack(fill="both", expand=True, pady=4)
        self.steps = scrolledtext.ScrolledText(box, height=10, width=54, font=("Consolas", 9))
        self.steps.pack(fill="both", expand=True)
        ttk.Button(box, text="▶ Run steps", command=self.run_steps_text).pack(anchor="e", pady=(6, 0))

        # --- controls ---
        box = ttk.Frame(left)
        box.pack(fill="x", pady=6)
        ttk.Button(box, text="👁 Look at screen", command=self.look).pack(side="left")
        ttk.Button(box, text="■ Stop", command=self.stop.set).pack(side="left", padx=6)
        self.hide = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Hide while acting", variable=self.hide).pack(side="right")
        sp = ttk.Frame(left)
        sp.pack(fill="x")
        ttk.Label(sp, text="Cursor speed").pack(side="left")
        self.speed = tk.DoubleVar(value=1.0)
        ttk.Scale(sp, from_=2.0, to=0.4, variable=self.speed, length=180).pack(side="left", padx=6)

        # --- right: what Kola sees + log ---
        ttk.Label(right, text="What Kola sees", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.view = tk.Label(right, bg="#111", fg="#aaa", text="Press “Look at screen” or run a task", height=24)
        self.view.pack(fill="both", expand=True, pady=(4, 8))
        self.logbox = scrolledtext.ScrolledText(right, height=11, font=("Consolas", 9), state="disabled")
        self.logbox.pack(fill="x")
        self.status = ttk.Label(right, text="Loading model…", style="Sub.TLabel")
        self.status.pack(anchor="w", pady=(4, 0))

        threading.Thread(target=self._load, daemon=True).start()
        root.after(80, self._poll)

    # ---------- plumbing ----------
    def log(self, msg):
        self.q.put(("log", msg))

    def frame(self, img):
        self.q.put(("frame", img))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", f"{time.strftime('%H:%M:%S')}  {val}\n")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                elif kind == "frame":
                    self._show(val)
                elif kind == "status":
                    self.status.configure(text=val)
                elif kind == "done":
                    self.busy = False
                    if self.hide.get():
                        self.root.deiconify()
                        self.root.lift()
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _show(self, img):
        from PIL import ImageTk
        w = max(400, self.view.winfo_width() - 4)
        h = max(250, self.view.winfo_height() - 4)
        img = img.copy()
        img.thumbnail((w, h))
        self._photo = ImageTk.PhotoImage(img)
        self.view.configure(image=self._photo, text="", height=0)

    def _load(self):
        if not Path(self.weights).exists():
            self.q.put(("status", f"Model not found: {self.weights}"))
            self.log(f"Model file not found: {self.weights}. Train it first (python train.py) or pass --weights.")
            return
        try:
            from kola.agent import Kola
            self.kola = Kola(self.weights, use_ocr=self.use_ocr, log=self.log, on_frame=self.frame)
            if self.kola.ocr is not None:
                self.log(f"Warming up OCR ({self.kola.ocr.backend})…")
                from PIL import Image
                self.kola.ocr.read(Image.new("RGB", (200, 60), "white"))
            self.q.put(("status", f"Ready · model {Path(self.weights).name} · classes: {', '.join(self.kola.detector.classes)}"))
            self.log("Kola is ready.")
        except Exception as e:
            self.q.put(("status", f"Failed to load: {e}"))
            self.log(f"Failed to load model: {e}")

    def _start(self, fn):
        if self.kola is None:
            self.log("Model not loaded yet.")
            return
        if self.busy:
            self.log("Busy — press Stop first.")
            return
        self.busy = True
        self.stop.clear()
        self.kola.hands.speed = float(self.speed.get())
        if self.hide.get():
            self.root.iconify()

        def work():
            time.sleep(0.9 if self.hide.get() else 0.2)  # let the window get out of the way
            try:
                fn()
            except Exception as e:
                self.log(f"Error: {e}")
            finally:
                self.q.put(("done", None))
        threading.Thread(target=work, daemon=True).start()

    def _set_steps(self, steps):
        self.steps.delete("1.0", "end")
        self.steps.insert("1.0", json.dumps(steps, indent=2))

    # ---------- actions ----------
    def pick_scenario(self, _e=None):
        i = self.scenario.current()
        self.cmd.delete(0, "end")
        self.cmd.insert(0, SCENARIOS[i])
        self.plan_only()

    def plan_only(self):
        try:
            steps, why = plan(self.cmd.get())
            self._set_steps(steps)
            self.log(f'Plan: {why} ({len(steps)} steps)')
            return steps
        except ValueError as e:
            self.log(str(e))
            return None

    def run_command(self):
        steps = self.plan_only()
        if steps:
            self._start(lambda: self.kola.run(steps, self.stop))

    def run_manual(self):
        cls = self.target.get().split(" — ")[0]
        tgt = {"type": cls}
        if self.ttext.get().strip():
            tgt["text"] = "~" + self.ttext.get().strip()
        idx = int(self.index.get() or 1) - 1
        if idx:
            tgt["index"] = idx
        steps = [{"action": self.action.get(), "target": tgt, "settle": 2}]
        self._set_steps(steps)
        self._start(lambda: self.kola.run(steps, self.stop))

    def run_steps_text(self):
        try:
            steps = json.loads(self.steps.get("1.0", "end"))
        except json.JSONDecodeError as e:
            self.log(f"Steps JSON is invalid: {e}")
            return
        self._start(lambda: self.kola.run(steps, self.stop))

    def look(self):
        self._start(self.kola.describe_screen if self.kola else (lambda: None))


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
    root = tk.Tk()
    App(root, a.weights, not a.no_ocr)
    root.mainloop()


if __name__ == "__main__":
    main()
