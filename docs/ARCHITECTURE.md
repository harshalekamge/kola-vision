# Architecture

Kola Vision turns a task ("go to Watch Later") into real mouse and keyboard actions by looking at
the screen like a person does: pixels in, actions out.

```
                        ┌────────────────────────── Kola Vision ──────────────────────────┐
 user command ─► Language module ─► steps ─► Grounding ─► Executor ─► mouse / keyboard
 (teammate)      (planner.py is a        ▲          │
                  placeholder for now)    │          └─► Verify (screenshot diff)
                                          │
                       screenshot ─► YOLO detector ─► elements (type + box + confidence)
                                 └─► OCR ──────────► words (text + box)
                        └──────────────────────────────────────────────────────────────────┘
```

## The loop

For every pointer step (click, hover...), the agent runs **look → understand → act → verify**:

1. **Look:** take a screenshot of the primary monitor.
2. **Understand:** the YOLO model finds every known element; OCR reads text only if the step needs it.
3. **Ground:** pick the single element that matches the step's target.
4. **Act:** glide the cursor there, hover, then click, right-click, double-click or just hover.
5. **Verify:** compare screenshots before and after; log whether the screen changed.
6. **Recover** if the target wasn't found: open the sidebar (for sidebar items) or scroll the feed
   (for cards), then look again. Up to 4 attempts.

## Modules

| File | Role |
|---|---|
| `kola/classes.py` | The 24 element classes, the sidebar's top-to-bottom order, and which are sidebar / single-instance / feed elements |
| `kola/screen.py` | Screen capture with `mss`; converts image pixels to mouse coordinates (handles Windows DPI scaling and Mac Retina) |
| `kola/detector.py` | Runs the trained model: `.pt` via Ultralytics (GPU), `.onnx` via onnxruntime (no PyTorch) |
| `kola/ocr.py` | Reads on-screen words. Uses RapidOCR, Windows OCR or EasyOCR, whichever is installed |
| `kola/grounding.py` | Matches a target description to one element: by type, text, reading order and containment |
| `kola/planner.py` | Rule-based stand-in for the language module: English sentence → steps |
| `kola/executor.py` | `pyautogui` mouse and keyboard: smooth eased movement, hover pause, clicks, typing |
| `kola/agent.py` | Ties it together: runs steps, recovery, verification, draws the "what Kola sees" overlay |
| `kola_demo.py` | Demo UI (CustomTkinter): task bar, live view, plain-language progress; runs the agent in a background thread |

## Screen understanding: two complementary signals

**The detector** knows *what kind* of thing each element is: a chip, a video card, a sponsored card,
the search box. It works on pixels only, at about 30 ms per screenshot on a GPU. It cannot tell
*which* chip says "Gaming".

**OCR** knows *what text* is where, but not what's a button, a title or an ad.

**Grounding combines them.** Each element's text is the OCR words whose centers fall inside its box.
That's enough for every demo scenario:

| Scenario | Target | How grounding resolves it |
|---|---|---|
| Go to Watch Later | `{type: watch_later}` | Most confident `watch_later` detection |
| Switch feed to Gaming | `{type: chip, text: "Gaming"}` | Chip whose text matches "Gaming" |
| Search + play the "6 days ago" video | `{type: video_card, contains: ["6 days ago"]}` | Card whose text contains the phrase |
| Sign up on the Firebase ad | `{type: text, text: "Sign up", inside: {type: sponsored_card, contains: ["~firebase"]}}` | Find the Firebase ad, then the "Sign up" text inside it |
| First Short on the shelf | `{type: short_card, index: 0}` | First `short_card` in reading order |

### Grounding rules

- **Single-instance classes** (sidebar items, menu, search box/button): take the highest-confidence
  detection. This ignores look-alikes such as Chrome's address bar.
- **Repeated classes** (cards, chips): sorted in **reading order**, rows top to bottom, then left to
  right. `index` picks from this order; `-1` is the last.
- **Text matching** ignores case and punctuation and allows partial matches. A `~` prefix allows fuzzy
  matching for OCR errors and truncated titles ("Claude code just became Free…").
- **`inside`** restricts the search to within another element's box.
- **`type: "text"`**, or any type the model doesn't know, clicks matching OCR text anywhere on
  screen. This is the fallback for elements without a trained class ("Liked videos").

## Acting like a person

Accessibility users and observers need to *see* what the assistant does, so the executor:
- moves the cursor along an eased path, taking 0.3–1.1 s depending on distance (adjustable speed);
- pauses on the target so YouTube shows its hover effect before clicking;
- minimizes the Kola window while acting, so it doesn't cover the page.

Screen coordinates: on Windows the process is made DPI-aware, so screenshot pixels equal mouse
coordinates even at 125%/150% scaling. On Retina Macs the 2× factor is computed from the screenshot.

## Recovery and verification

| Situation | Recovery |
|---|---|
| Sidebar target missing and the sidebar is collapsed (only Home/Shorts/Subscriptions visible) | Click the menu button, look again |
| Sidebar target missing and the sidebar is open | Scroll over the sidebar toward the target (up or down, from the sidebar's top-to-bottom order) |
| Card missing (video, Short, ad) | Scroll the feed down, look again |
| Results still loading after a search | `wait_for` step polls until the target type appears |

After every action, the before/after screenshots are compared (mean pixel difference) and the log
reports whether the screen changed.

## Design decisions

- **Vision instead of the DOM at run time.** Page code is only used to *label* training data. At run
  time Kola relies on pixels only, so the approach carries over to desktop apps and other sites without
  accessible markup.
- **Element types, not individual buttons.** Training `chip` instead of `gaming_chip` keeps the
  class set small and lets OCR handle the open vocabulary (any chip, title or button label).
- **Steps as the interface.** The language module and this module only share a small JSON format
  ([INTERFACE.md](INTERFACE.md)), so they can be built and tested separately.

## Limitations

- Knows YouTube's 24 element types (v2). Other sites need new data (the collector makes this cheap).
- Big YouTube redesigns need re-collecting and retraining.
- OCR can misread stylized or very small text.
- Sponsored cards depend on ads appearing, so they have the least training data.
- The placeholder planner understands only the demo sentence patterns.
