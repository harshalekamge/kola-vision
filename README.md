# Kola Vision

**Screen understanding and action execution** for *Kola: Multimodal AI Assistant for Accessible
Screen Navigation and Personalized Interaction*.

Kola Vision is Kola's eyes and hands. It looks at the screen, finds YouTube elements with a trained
YOLO model, reads on-screen text with OCR, picks the element the user asked for, and moves the
mouse to hover and click it, then checks that the screen changed.

| Doc | What's in it |
|---|---|
| **README.md** (this file) | How to install and run |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the system works, module by module |
| [docs/DATASET_AND_TRAINING.md](docs/DATASET_AND_TRAINING.md) | Auto-labeled dataset, YOLO model, training, results |
| [docs/INTERFACE.md](docs/INTERFACE.md) | The step format the language module sends to this module |

---

## Run the demo

### 1. Install (once)

Windows, in the project folder:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
```

The first `pip install` gets PyTorch with NVIDIA GPU support. Without an NVIDIA GPU, skip it
(`requirements.txt` installs the CPU version). Check the GPU is detected:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

**Low-bandwidth alternative (~80 MB, no PyTorch):** `pip install -r requirements-lite.txt`, then use the
`.onnx` model below.

### 2. Get the trained model

- `models/kola_yolo.onnx` **is included in the repo**, so the demo works right after cloning.
- `models/kola_yolo.pt` (same model, runs on the GPU) is not in git. Download it from the Colab
  training run and put it in `models/`. When it's there, the demo uses it automatically.

To train your own, see [docs/DATASET_AND_TRAINING.md](docs/DATASET_AND_TRAINING.md).

### 3. Start Kola

Every new terminal needs `.venv\Scripts\activate` first (the prompt shows `(.venv)`).

```bash
python kola_demo.py
```

It uses `models/kola_yolo.pt` with the full install and `models/kola_yolo.onnx` with the lite install.
To choose a file yourself: `python kola_demo.py --weights models/kola_yolo.pt`.

The first start downloads EasyOCR's text models (~100 MB). Wait for **"Kola is ready."** in the log.

### 4. Use it

1. Open YouTube in Chrome, **logged in**, and press **F11** (full screen). Keep it behind the Kola window.
2. **👁 Look at screen** shows every element the model detects.
3. Run a task in one of three ways:
   - **Say a command:** pick a scenario or type one, then **▶ Run command**.
   - **Pick action + navigation point:** e.g. `left_click` + `watch_later`, then **▶ Do it**.
   - **Steps:** edit the JSON plan and **▶ Run steps** (see [docs/INTERFACE.md](docs/INTERFACE.md)).

Kola minimizes itself, moves the cursor, acts, and comes back with a log of what it saw and did.
**Emergency stop:** move the mouse hard into a screen corner.

### Demo commands

| # | Command | Before running |
|---|---|---|
| 1 | Go to the Watch Later section | Any YouTube page. Opens the sidebar itself if collapsed |
| 2 | Search for Claude Code and play the video released 6 days ago | Use an upload age that will appear in the results, or say "play the first video" |
| 3 | Switch feed to Gaming videos | Home page. Use a chip that's visible |
| 4 | Click the Sign up button on the Firebase ad | Needs that ad on screen. Use the button text and advertiser you see |
| 5 | Play the first video on the Shorts shelf | Scroll so the Shorts shelf is visible |

Other forms that work: `right click history`, `hover over subscriptions`, `click Liked videos`
(clicks any visible text).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named 'ultralytics'` | The venv isn't active. Run `.venv\Scripts\activate` |
| `running scripts is disabled` when activating | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Clicks land in the wrong place | Set Windows display scaling to 100%, or keep Chrome on the primary monitor |
| Address bar detected as a search box | Use Chrome full screen (F11) |
| Text targets (chips, titles) fail | Wait for "Kola is ready."; check the text is actually on screen |
| macOS | Allow Terminal in Privacy & Security → *Screen Recording* and *Accessibility* |

Run the logic tests (no model or screen needed): `python tests/test_logic.py`

## Project layout

```
kola_demo.py              demo app (Tkinter UI)
kola/                     the module: detector, OCR, grounding, planner, executor, agent
collector/extension/      Chrome extension that auto-labels YouTube screenshots
collector/collector_server.py   saves screenshots + labels as a YOLO dataset
tools/review_labels.py    draws labels on sample images to check them
train.py                  training script (local GPU or Colab)
train_colab.ipynb         Colab notebook for training on a free GPU
tests/test_logic.py       planner + grounding tests
docs/                     detailed documentation
```
