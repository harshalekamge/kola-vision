"""Kola collector server.

Receives screenshot + DOM boxes from the Chrome extension and writes a
YOLO-format dataset:

    dataset/
      images/train/*.jpg   images/val/*.jpg
      labels/train/*.txt   labels/val/*.txt
      data.yaml            stats.json

Run:  python collector/collector_server.py   (then use the extension)
"""
import base64
import io
import json
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kola.classes import CLASSES  # noqa: E402

DATASET = ROOT / "dataset"
VAL_FRACTION = 0.15
PORT = 8765
lock = threading.Lock()


def setup():
    for split in ("train", "val"):
        (DATASET / "images" / split).mkdir(parents=True, exist_ok=True)
        (DATASET / "labels" / split).mkdir(parents=True, exist_ok=True)
    write_yaml()


def write_yaml():
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASSES))
    (DATASET / "data.yaml").write_text(
        f"path: {DATASET.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n{names}\n",
        encoding="utf-8",
    )


def load_stats():
    p = DATASET / "stats.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"total": 0, "per_class": {c: 0 for c in CLASSES}}


def save_sample(payload):
    data_url = payload["image"]
    raw = base64.b64decode(data_url.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = img.size
    vw, vh = float(payload["vw"]), float(payload["vh"])

    # Screenshot must cover exactly the viewport the boxes were measured in.
    if abs((w / h) - (vw / vh)) > 0.03 * (vw / vh):
        return {"saved": False, "reason": f"aspect mismatch img {w}x{h} vs viewport {vw:.0f}x{vh:.0f}"}

    lines, counts = [], {}
    for b in payload["boxes"]:
        if b["cls"] not in CLASSES:
            continue
        cid = CLASSES.index(b["cls"])
        x1, y1, x2, y2 = (max(0.0, min(1.0, v)) for v in (b["x1"] / vw, b["y1"] / vh, b["x2"] / vw, b["y2"] / vh))
        bw, bh = x2 - x1, y2 - y1
        if bw <= 0.002 or bh <= 0.002:
            continue
        lines.append(f"{cid} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {bw:.6f} {bh:.6f}")
        counts[b["cls"]] = counts.get(b["cls"], 0) + 1
    if not lines:
        return {"saved": False, "reason": "no valid boxes"}

    split = "val" if random.random() < VAL_FRACTION else "train"
    name = f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    with lock:
        img.save(DATASET / "images" / split / f"{name}.jpg", quality=92)
        (DATASET / "labels" / split / f"{name}.txt").write_text("\n".join(lines) + "\n")
        with open(DATASET / "meta.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"name": name, "split": split, "url": payload.get("url"), "theme": payload.get("theme"),
                                "dpr": payload.get("dpr"), "size": [w, h], "counts": counts}) + "\n")
        stats = load_stats()
        stats["total"] += 1
        for c, n in counts.items():
            stats["per_class"][c] = stats["per_class"].get(c, 0) + n
        (DATASET / "stats.json").write_text(json.dumps(stats, indent=2))
    print(f"[{stats['total']:>5}] {split:5} {name}  {sum(counts.values()):>3} boxes  {payload.get('theme')}  {payload.get('url', '')[:60]}")
    return {"saved": True, "boxes": len(lines), "total": stats["total"]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        if self.path.startswith("/status"):
            self._send(200, load_stats())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/save"):
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n))
            self._send(200, save_sample(payload))
        except Exception as e:  # keep the server alive whatever happens
            print("ERROR:", e)
            self._send(500, {"saved": False, "reason": str(e)})

    def log_message(self, *args):
        pass  # quiet; we print our own lines


if __name__ == "__main__":
    setup()
    s = load_stats()
    print(f"Kola collector listening on http://127.0.0.1:{PORT}  (dataset: {DATASET}, {s['total']} images so far)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
