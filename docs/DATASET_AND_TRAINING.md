# Dataset and Training

The detector is a YOLO11n model fine-tuned on screenshots of YouTube. The dataset was created
automatically: no boxes were drawn by hand.

## 1. Classes

| ID | Class | What it is |
|---|---|---|
| 0 | `home` | Sidebar: Home |
| 1 | `shorts` | Sidebar: Shorts |
| 2 | `subscriptions` | Sidebar: Subscriptions |
| 3 | `history` | Sidebar: History |
| 4 | `watch_later` | Sidebar: Watch later |
| 5 | `menu_button` | Hamburger button that opens/collapses the sidebar |
| 6 | `search_box` | Search input |
| 7 | `search_button` | Magnifying-glass button |
| 8 | `chip` | Topic filter chip ("All", "Music", "Gaming"...) |
| 9 | `video_card` | A video tile on the home grid or in search results |
| 10 | `short_card` | A vertical card in a Shorts shelf |
| 11 | `sponsored_card` | An ad / sponsored tile |
| 12 | `your_channel` | Sidebar (You): Your channel *(v2)* |
| 13 | `playlists` | Sidebar (You): Playlists *(v2)* |
| 14 | `music` | Sidebar (Explore): Music *(v2)* |
| 15 | `gaming` | Sidebar (Explore): Gaming *(v2)* |
| 16 | `playables` | Sidebar (Explore): Playables *(v2)* |
| 17 | `premium` | Sidebar (More from YouTube): YouTube Premium *(v2)* |
| 18 | `youtube_music` | Sidebar (More from YouTube): YouTube Music *(v2)* |
| 19 | `youtube_kids` | Sidebar (More from YouTube): YouTube Kids *(v2)* |
| 20 | `report_history` | Sidebar (bottom): Report history *(v2)* |

**v1** (the first model, results below) has classes 0–11. **v2** adds 12–20. A v1 model still
handles the v2 destinations by reading their labels with OCR, limited to the sidebar area.

The order is defined in `kola/classes.py`. Class IDs in label files depend on it, so new classes must
be appended at the end.

## 2. Auto-labeling

YouTube's page already knows where every element is. A Chrome extension
(`collector/extension/labeler.js`) uses that:

1. Finds elements in the page's DOM: sidebar entries by link (`/feed/history`, `list=WL`...) or
   visible name; the search box, chips, video cards, Shorts and ad tiles by their YouTube components.
2. Keeps only what a person can actually see: at least 60% inside the viewport, not hidden, and not
   covered by another element (checked with `elementFromPoint` at 3 points).
3. Takes a screenshot of the visible tab, reads the boxes again, and **discards the sample if anything
   moved** (animations, lazy-loading thumbnails). This keeps labels aligned with pixels.
4. Sends image and boxes to `collector/collector_server.py`, which writes YOLO labels
   (`class x_center y_center width height`, normalized 0–1) and randomly assigns 85% to train, 15% to val.

**The DOM is only the labeler.** The trained model never sees it at run time, only pixels.

### Variety

The extension's auto mode changes conditions between captures:

- visits home, search results (18 different queries) and subscriptions;
- toggles the sidebar between expanded and collapsed (mini guide);
- randomizes zoom between 80% and 125%;
- scrolls to random positions (40% of captures at the top);
- *(v2)* scrolls the expanded sidebar to the top, bottom or a random position, so items far down
  the sidebar (Explore, More from YouTube, Report history) are captured.

Manually, collection was repeated in **light theme**, **dark theme** and **F11 full screen**.

### Collected dataset (v1)

700 screenshots (585 train, 115 val), 11,884 labeled boxes:

| Class | Boxes | Class | Boxes |
|---|---|---|---|
| home | 732 | search_box | 664 |
| shorts | 700 | search_button | 664 |
| subscriptions | 700 | chip | 4,779 |
| history | 390 | video_card | 1,609 |
| watch_later | 390 | short_card | 385 |
| menu_button | 664 | sponsored_card | 207 |

`history` and `watch_later` appear only when the sidebar is fully expanded, which is about half the
captures. `sponsored_card` depends on YouTube serving ads.

To check labels by eye: `python tools/review_labels.py` draws them on random images in `dataset/review/`.

## 3. Model

**YOLO11n** (Ultralytics) is a one-stage object detector: one forward pass outputs boxes, classes and
confidences for the whole image.

- **Backbone:** convolutional layers that extract visual features (edges → icons, text blocks, thumbnails).
- **Neck:** merges features at three scales, so small targets (sidebar icons) and large ones (cards) are both found.
- **Head:** for each location, predicts box edges and a score for each of the 12 classes.

Size: 2.6 M parameters, 6.5 GFLOPs, 5.5 MB (`.pt`) / 10.4 MB (`.onnx`).

**Transfer learning:** training starts from weights pre-trained on COCO (80 everyday object classes).
The classification head is replaced for 12 classes; 493 of 499 weight tensors are reused.

## 4. Training setup

| Setting | Value | Why |
|---|---|---|
| Image size | 960 | UI elements are small; 640 loses detail |
| Epochs | 60 (patience 15) | Converged by ~epoch 20; early stopping not triggered |
| Batch | Auto (17 on a T4) | Uses ~60% of GPU memory |
| Optimizer | AdamW, lr 0.000625 (auto-selected) | Ultralytics default for small datasets |
| `fliplr`, `flipud` | 0 | Mirrored text and layouts never occur on screen |
| `degrees` | 0 | Screens are never rotated |
| `scale`, `translate` | 0.3, 0.1 | Simulate zoom levels and window sizes |
| `hsv_h/s/v` | 0.01 / 0.3 / 0.3 | Robust to light/dark themes, little hue change |
| `mosaic` | 0.5 (off for the last 10 epochs) | More varied element positions |

Hardware: Google Colab, Tesla T4. Training time: **21 minutes**.

### Losses

| Loss | Meaning | Epoch 1 → 60 |
|---|---|---|
| `box_loss` | How far predicted box edges are from the true box | 1.597 → 0.194 |
| `cls_loss` | How wrong the class prediction is | 3.297 → 0.196 |
| `dfl_loss` | Fine-grained box-edge distribution error | 1.390 → 0.782 |

## 5. Results: v1 model (validation set, 115 images, 1,937 boxes)

| Metric | Value | Meaning |
|---|---|---|
| Precision | 0.983 | Of the elements it reports, 98.3% are correct |
| Recall | 0.986 | Of the elements actually on screen, it finds 98.6% |
| mAP50 | 0.990 | Average precision when a box must overlap the truth by ≥50% |
| mAP50-95 | 0.987 | Same, averaged over stricter overlaps 50%–95% |

Per class (mAP50):

| Class | mAP50 | Class | mAP50 |
|---|---|---|---|
| home | 0.995 | search_box | 0.995 |
| shorts | 0.995 | search_button | 0.995 |
| subscriptions | 0.995 | chip | 0.995 |
| history | 0.995 | video_card | 0.990 |
| watch_later | 0.995 | short_card | 0.981 |
| menu_button | 0.995 | sponsored_card | 0.956 |

Speed: about 32 ms per image on a T4. On the RTX 3050 laptop the full look step (capture + detect) takes 0.15–0.4 s.

Training plots are in `runs/kola/`: `results.png` (curves), `confusion_matrix.png`, `val_batch0_pred.jpg`.

### Reading these numbers honestly

Validation screenshots come from the same collection sessions as training, so they share accounts,
dates and recommendations. Accuracy on a new day, account or language may be lower. Sponsored cards
score lowest because there were only 207 examples. A stronger evaluation would use a test set
collected separately.

## 6. Reproduce

### Collect
1. `python collector/collector_server.py`
2. Chrome → `chrome://extensions` → Developer mode → **Load unpacked** → `collector/extension`
3. YouTube, logged in → extension → **Preview labels** to check boxes → **Start** (300 screenshots)
4. Repeat in dark theme and in F11 full screen
5. `python tools/review_labels.py`

### Train on Colab (free GPU)
1. Zip the `dataset` folder → `dataset.zip`
2. Upload `train_colab.ipynb` to colab.research.google.com; **Runtime → Change runtime type → T4 GPU**
3. Run the cells; upload `dataset.zip`, `train.py` and `kola/classes.py` when asked
4. The last cell downloads `kola_yolo.pt`, `kola_yolo.onnx` and `kola_results.zip` (plots)
5. Put the models in `models/`

### Train locally (NVIDIA GPU)
```bash
python train.py              # yolo11n, 960 px, 60 epochs
python train.py --model yolo11s.pt --epochs 80   # bigger, more accurate
```

## 7. Training v2 (the extra sidebar classes)

The v1 screenshots show items like *Playlists* and *Gaming* **without labels** for them. Training v2
on that data would teach the model those items are background, so v2 needs a fresh dataset.

1. Keep v1: rename `dataset` to `dataset_v1` and `models/kola_yolo.pt` to `models/kola_yolo_v1.pt`.
2. Reload the extension (`chrome://extensions` → ↻) and refresh YouTube.
3. **Preview labels** with the sidebar expanded, and scrolled down: the new items get boxes.
4. Collect as before (light 300, dark 300, F11 100) with **Scroll the sidebar** ticked.
5. `python tools/review_labels.py`: every new class should have 100+ boxes.
6. Train on Colab exactly as for v1; record the new per-class results here.
