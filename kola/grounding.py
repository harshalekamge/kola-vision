"""Grounding: turn a target description into ONE element on screen.

A target is a small dict (this is the contract with the language-understanding module):

    {"type": "watch_later"}                                   # a detected class
    {"type": "chip", "text": "Gaming"}                        # class + its visible text
    {"type": "video_card", "contains": ["~claude code", "6 days ago"]}
    {"type": "short_card", "index": 0}                        # first in reading order
    {"type": "text", "text": "Sign up",
     "inside": {"type": "sponsored_card", "contains": ["~firebase"]}}

"~" before a phrase means fuzzy match (OCR / truncated titles); without it the match is stricter.
"type": "text" clicks any text OCR finds on screen (fallback for things the model has no class for).
"""
import re
from difflib import SequenceMatcher

from .classes import SIDEBAR_CLASSES, SINGLETON_CLASSES


# ---------- text matching ----------
def norm(s: str) -> str:
    s = s.lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def partial_ratio(needle: str, hay: str) -> float:
    """How well `needle` appears somewhere inside `hay` (0..1)."""
    n, h = norm(needle), norm(hay)
    if not n:
        return 1.0
    if not h:
        return 0.0
    if n in h:
        return 1.0
    nw, hw = n.split(), h.split()
    best = SequenceMatcher(None, n, h).ratio()
    k = len(nw)
    for size in {max(1, k - 1), k, k + 1}:
        for i in range(0, max(1, len(hw) - size + 1)):
            best = max(best, SequenceMatcher(None, n, " ".join(hw[i:i + size])).ratio())
    return best


def phrase_score(pattern: str, text: str) -> float:
    """Score >= threshold means match; returns 0 if below threshold."""
    fuzzy = pattern.startswith("~")
    p = pattern[1:] if fuzzy else pattern
    s = partial_ratio(p, text)
    return s if s >= (0.62 if fuzzy else 0.8) else 0.0


# ---------- geometry ----------
def reading_order(items):
    """Top-to-bottom rows, left-to-right inside a row."""
    if not items:
        return []
    items = sorted(items, key=lambda e: e.center[1])
    heights = sorted(e.box[3] - e.box[1] for e in items)
    tol = max(8, heights[len(heights) // 2] * 0.5)
    rows, cur, cur_y = [], [], None
    for e in items:
        cy = e.center[1]
        if cur and abs(cy - cur_y) > tol:
            rows.append(cur)
            cur = []
        if not cur:
            cur_y = cy
        cur.append(e)
    rows.append(cur)
    return [e for row in rows for e in sorted(row, key=lambda e: e.center[0])]


def union_box(els):
    return (min(e.box[0] for e in els), min(e.box[1] for e in els),
            max(e.box[2] for e in els), max(e.box[3] for e in els))


# ---------- context: what Kola sees in one screenshot ----------
class Context:
    def __init__(self, img, elements, ocr=None, known_classes=None):
        self.img = img
        self.elements = elements
        self.ocr = ocr
        self.known = set(known_classes or {e.cls for e in elements})
        self._words = None

    @property
    def words(self):
        if self._words is None:
            if self.ocr is None:
                raise RuntimeError("This step needs text reading (OCR). Install it: pip install rapidocr_onnxruntime")
            self._words = self.ocr.read(self.img)
        return self._words

    def text_of(self, el):
        if not el.text:
            inside = [w for w in self.words if el.contains_point(*w.center)]
            el.text = " ".join(w.text for w in reading_order(inside))
        return el.text

    def lines(self, scope=None):
        """OCR words grouped into lines (optionally only inside a scope box)."""
        ws = [w for w in self.words if scope is None or scope.contains_point(*w.center)]
        ordered = reading_order(ws)
        lines, cur = [], []
        for w in ordered:
            if cur:
                prev = cur[-1]
                same_row = abs(w.center[1] - prev.center[1]) < max(6, (prev.box[3] - prev.box[1]) * 0.6)
                close = w.box[0] - prev.box[2] < (prev.box[3] - prev.box[1]) * 1.5
                if not (same_row and close):
                    lines.append(cur)
                    cur = []
            cur.append(w)
        if cur:
            lines.append(cur)
        return lines


# ---------- search ----------
def _text_candidates(ctx, phrase, scope=None):
    """Find on-screen text spans matching `phrase`; returns pseudo-elements sorted by score."""
    from .detector import Element
    fuzzy = phrase.startswith("~")
    p = norm(phrase[1:] if fuzzy else phrase)
    found = []
    for line in ctx.lines(scope):
        for i in range(len(line)):
            for j in range(i + 1, min(len(line), i + 8) + 1):
                span = line[i:j]
                t = " ".join(w.text for w in span)
                s = SequenceMatcher(None, p, norm(t)).ratio()
                if norm(t) == p:
                    s = 1.0
                if s >= (0.6 if fuzzy else 0.75):
                    found.append(Element(cls="text", conf=s, box=union_box(span), text=t))
    found.sort(key=lambda e: -e.conf)
    # drop overlapping weaker duplicates
    out = []
    for e in found:
        if not any(o.contains_point(*e.center) for o in out):
            out.append(e)
    return out


def find_all(target, ctx, scope=None):
    typ = target.get("type", "text")
    if typ == "text" or typ not in ctx.known:
        phrase = target.get("text") or typ.replace("_", " ")
        found = _text_candidates(ctx, phrase, scope)
        if typ in SIDEBAR_CLASSES and ctx.img is not None:
            # The model doesn't know this sidebar item yet: only accept the label inside the sidebar,
            # so "Music" doesn't match the Music topic chip in the feed. The sidebar's right edge comes
            # from sidebar items the model does detect; otherwise assume a typical sidebar width.
            side = [e.box[2] for e in ctx.elements if e.cls in SIDEBAR_CLASSES]
            edge = max(side) + 10 if side else ctx.img.width * 0.14
            found = [e for e in found if e.center[0] < edge]
        return found

    cands = [e for e in ctx.elements if e.cls == typ and (scope is None or scope.contains_point(*e.center))]
    if not cands:
        return []

    patterns = []
    if target.get("text"):
        patterns.append(target["text"])
    patterns += target.get("contains", [])
    if patterns:
        scored = []
        for e in cands:
            txt = ctx.text_of(e)
            scores = [phrase_score(p, txt) for p in patterns]
            if all(scores):
                scored.append((sum(scores) / len(scores), e))
        scored.sort(key=lambda t: -t[0])
        return [e for _, e in scored]

    if typ in SINGLETON_CLASSES:
        return sorted(cands, key=lambda e: -e.conf)
    return reading_order(cands)


def ground(target, ctx):
    """Return (element or None, explanation)."""
    scope = None
    if target.get("inside"):
        containers = find_all(target["inside"], ctx)
        if not containers:
            return None, f"container {describe(target['inside'])} not visible"
        scope = containers[0]
    cands = find_all(target, ctx, scope)
    if not cands:
        return None, f"{describe(target)} not visible"
    idx = int(target.get("index", 0))
    if idx >= len(cands) or idx < -len(cands):
        return None, f"only {len(cands)} × {target.get('type')} visible, wanted #{idx + 1}"
    el = cands[idx]
    why = f"{describe(target)} -> {el.cls} at ({el.center[0]:.0f},{el.center[1]:.0f}) conf {el.conf:.2f}"
    if el.text:
        why += f' text "{el.text[:60]}"'
    return el, why


def describe(t):
    s = t.get("type", "text")
    if t.get("text"):
        s += f' "{t["text"]}"'
    if t.get("contains"):
        s += " containing " + ", ".join(f'"{c}"' for c in t["contains"])
    if t.get("index"):
        s += f" #{int(t['index']) + 1}"
    if t.get("inside"):
        s += " inside " + describe(t["inside"])
    return s
