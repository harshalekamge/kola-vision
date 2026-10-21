# Kola Vision — screen understanding & action module

Part of **Kola: Multimodal AI Assistant for Accessible Screen Navigation and Personalized Interaction**.
This module is Kola's *eyes and hands*: it looks at the screen, understands what's there, finds the
target and performs the action (move → hover → click / type), then verifies the screen changed.

```
 command / steps ──► Grounding ◄── Screen understanding ◄── screenshot
 (language module)      │            (trained YOLO + OCR)
                        ▼
                    Executor  ──► smooth cursor move, hover, click, type ──► verify
```

| Part | File | What it does |
|---|---|---|
| Dataset collector | `collector/extension/` + `collector/collector_server.py` | Auto-labels YouTube elements from the page and saves screenshot + YOLO labels |
| **Trained model** | `train.py` / `train_colab.ipynb` | YOLO detector for 12 YouTube UI element types |
| Perception | `kola/detector.py`, `kola/ocr.py` | Elements + on-screen text |
| Grounding | `kola/grounding.py` | Picks the one element that matches the target (text, index, "inside") |
| Hands | `kola/executor.py`, `kola/agent.py` | Visible cursor motion, clicks, typing, recovery (open sidebar / scroll), verification |
| Placeholder language | `kola/planner.py` | Turns the 5 scenario sentences into steps until the language module is connected |
| Demo UI | `kola_demo.py` | Command box, action + target picker, steps editor, live "what Kola sees" view |

Detected classes: `home, shorts, subscriptions, history, watch_later, menu_button, search_box,
search_button, chip, video_card, short_card, sponsored_card`.

---

## Tonight's plan (~3 hours)

### 1. Install
Python 3.10–3.12 recommended.

**Slow internet (recommended):** about 80 MB, no PyTorch. Train on Colab, run the demo with the ONNX model.
```bash
pip install -r requirements-lite.txt
```
**Full install (~3.5 GB):** only if you want to train on your own GPU. `pip install -r requirements.txt`

### 2. Collect the dataset (45–60 min, mostly automatic)
1. Start the server: `python collector/collector_server.py`
2. Chrome → `chrome://extensions` → turn on **Developer mode** → **Load unpacked** → pick `collector/extension`.
3. Open **youtube.com, logged in** (Watch later only exists when logged in).
4. Click the extension icon → **Preview labels**. Colored boxes appear for ~4 s.
   Check that sidebar items, search box/button, chips and video cards are boxed correctly.
5. Set screenshots to **300** → **Start**. Don't touch that Chrome window while it runs
   (it scrolls, toggles the sidebar, changes zoom and visits search/subscriptions pages by itself).
6. Switch YouTube to **dark theme** (avatar → Appearance) and run another **200–300**.
7. Run ~100 more with **Chrome full screen (F11)**, because the demo runs that way.
8. Check labels: `python tools/review_labels.py` → open images in `dataset/review/`.
   Every class should have 100+ boxes. `sponsored_card` depends on YouTube showing ads, so it may be low. That's OK.

### 3. Train (30–60 min)
- **NVIDIA GPU:** `python train.py`
- **No GPU:** use Google Colab (free T4 GPU). Zip the `dataset` folder, open `train_colab.ipynb` in Colab,
  upload `dataset.zip`, `train.py` and `kola/classes.py`, then run all cells. It downloads `kola_yolo.onnx` (~10 MB).
- **CPU only and no Colab:** `python train.py --epochs 25` (slower and less accurate, but works).

Put the result at `models/kola_yolo.onnx` (or `kola_yolo.pt` with the full install). Training prints per-class accuracy (mAP50). Show this in the presentation.
Also show `runs/kola/` → `results.png`, `confusion_matrix.png`, `val_batch0_pred.jpg`.

### 4. Run the demo
```bash
python kola_demo.py
```
With the lite install, OCR runs offline (RapidOCR).

---

## Presenting

- Chrome with YouTube, **logged in, full screen (F11)**, behind the Kola window. Kola minimizes itself while acting.
- **👁 Look at screen** first: it shows every element the model detected. This is the "screen understanding" result.
- Then run the scenarios from the dropdown, or use **2 · Pick action + navigation point** (e.g. `left_click` + `watch_later`).
- **Emergency stop:** slam the mouse into a screen corner.

| # | Command | Notes |
|---|---|---|
| 1 | Go to the Watch Later section | Opens the sidebar first if it's collapsed |
| 2 | Search for Claude Code and play the video released 6 days ago | Change "6 days ago" to whatever age is on screen tomorrow. Scrolls if needed |
| 3 | Switch feed to Gaming videos | Use a chip that exists on your home feed |
| 4 | Click the Sign up button on the Firebase ad | Only works if that ad is shown. Use the button text and advertiser you actually see |
| 5 | Play the first video on the Shorts shelf | Scroll the home feed so the Shorts shelf is visible |

The **Steps** box shows the JSON plan. That's the interface the language module will produce later.

---

## Interface with the language module

The language module only has to output a list of steps:

```json
[
  {"action": "left_click", "target": {"type": "search_box"}},
  {"action": "select_all"},
  {"action": "type", "text": "Claude Code"},
  {"action": "left_click", "target": {"type": "search_button"}},
  {"action": "wait_for", "target": {"type": "video_card"}, "timeout": 10},
  {"action": "left_click", "target": {"type": "video_card", "contains": ["~claude code", "6 days ago"]}}
]
```

- **actions:** `left_click, right_click, double_click, hover, type, press, select_all, scroll, wait, wait_for`
- **target:** `type` (a class, or `"text"` for any visible text), `text`, `contains` (all phrases),
  `index` (0 = first in reading order, -1 = last), `inside` (another target).
  A `~` before a phrase means fuzzy match.

```python
from kola.agent import Kola
kola = Kola("models/kola_yolo.pt")
kola.run(steps)
```

---

## Troubleshooting

- **Preview labels shows nothing for a class.** YouTube changed its HTML. The selectors are at the top of
  `collector/extension/labeler.js`. Inspect the element in DevTools and update the tag name.
- **Clicks land in the wrong place on Windows.** Use 100% display scaling, or keep it. `kola/screen.py`
  makes the process DPI-aware, but some setups still differ.
- **macOS:** allow Terminal/Python in System Settings → Privacy & Security → *Screen Recording* and *Accessibility*.
- **Text targets fail.** Make sure `easyocr` is installed and the text is actually visible on screen.
- **Run logic tests:** `python tests/test_logic.py`
