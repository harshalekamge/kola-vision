# Interface with the Language Module

The language module (user intent → plan) and Kola Vision (screen understanding → execution) meet at
one point: a **list of steps** in JSON. The language module decides *what* to do; Kola Vision finds
*where* on the screen and does it.

Until the language module is connected, `kola/planner.py` produces these steps from the demo sentences.

## Using it from Python

```python
from kola.agent import Kola

kola = Kola("models/kola_yolo.pt", log=print)
ok = kola.run([
    {"action": "left_click", "target": {"type": "watch_later"}}
])
```

`run()` returns `True` if every step succeeded. `log` receives progress messages (what was seen,
what was chosen, whether the screen changed). They can be spoken to the user.

## Step format

```json
{"action": "<action>", "target": {...}, "settle": 2}
```

| Action | Fields | What it does |
|---|---|---|
| `left_click` | `target` | Move to the target, hover, left-click |
| `right_click` | `target` | ... right-click |
| `double_click` | `target` | ... double-click |
| `hover` | `target` | Move to the target and stay |
| `type` | `text` | Type text at the current focus |
| `press` | `key` | Press one key, e.g. `"enter"`, `"esc"` |
| `select_all` | — | Ctrl+A (Cmd+A on Mac) |
| `scroll` | `clicks` (default `-5`) | Scroll the page; negative is down |
| `wait` | `seconds` | Pause |
| `wait_for` | `target`, `timeout` (s, default 8) | Wait until the target is visible |

Optional on pointer steps: `settle` (seconds to wait after acting, default 1.5) and `attempts`
(look/recover tries, default 4).

## Target format

| Field | Example | Meaning |
|---|---|---|
| `type` | `"chip"` | An element class, or `"text"` for any visible text |
| `text` | `"Gaming"` | The element's visible text must match |
| `contains` | `["~claude code", "6 days ago"]` | All phrases must appear in the element's text |
| `index` | `0`, `2`, `-1` | Which match, in reading order (0 = first, -1 = last) |
| `inside` | `{"type": "sponsored_card"}` | Only search inside this other element |

A `~` before a phrase allows a fuzzy match (OCR mistakes, truncated titles). Without it the match is
stricter. Matching always ignores case and punctuation.

**Element types:** `home`, `shorts`, `subscriptions`, `history`, `watch_later`, `menu_button`,
`search_box`, `search_button`, `chip`, `video_card`, `short_card`, `sponsored_card`, plus `text`.
Any other type name is treated as text to find on screen (e.g. `"liked_videos"` → "liked videos").

## The five scenarios as steps

**1. "Go to the Watch Later section."**
```json
[{"action": "left_click", "target": {"type": "watch_later"}, "settle": 2}]
```
If the sidebar is collapsed, Kola opens it with the menu button first.

**2. "Search for Claude Code and play the video released 6 days ago."**
```json
[
  {"action": "left_click", "target": {"type": "search_box"}},
  {"action": "select_all"},
  {"action": "type", "text": "Claude Code"},
  {"action": "left_click", "target": {"type": "search_button"}},
  {"action": "wait_for", "target": {"type": "video_card"}, "timeout": 10},
  {"action": "left_click", "target": {"type": "video_card", "contains": ["6 days ago"]}, "settle": 3}
]
```
To match a title too: `"contains": ["~claude code just became free", "6 days ago"]`.

**3. "Switch feed to Gaming videos."**
```json
[{"action": "left_click", "target": {"type": "chip", "text": "Gaming"}, "settle": 2}]
```

**4. "Click the Sign up button on the Firebase ad."**
```json
[{"action": "left_click", "target": {"type": "text", "text": "Sign up",
   "inside": {"type": "sponsored_card", "contains": ["~firebase"]}}, "settle": 3}]
```

**5. "Play the first video on the Shorts shelf."**
```json
[{"action": "left_click", "target": {"type": "short_card", "index": 0}, "settle": 3}]
```

## What the language module should do

- Output only the step list; leave screen positions to Kola Vision.
- Prefer element types over raw text when one fits (`chip` + `text`, not just `text`).
- Use `~` for anything spoken loosely or likely to be truncated on screen, like video titles.
- Split multi-part requests into ordered steps, and add `wait_for` after anything that loads a new page.
- On failure, `run()` returns `False` and the log says which step failed and why
  (e.g. `chip "Gaming" not visible`), so the assistant can tell the user or ask for clarification.
