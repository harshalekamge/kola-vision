"""Draw the auto-generated labels on random dataset images so you can check them by eye.

    python tools/review_labels.py            # 12 random images -> dataset/review/
    python tools/review_labels.py --n 30

Also prints how many boxes each class has (make sure every class has 100+).
"""
import argparse
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kola.classes import CLASSES  # noqa: E402

COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0",
          "#f032e6", "#bcf60c", "#fabebe", "#008080", "#9a6324", "#800000"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(ROOT / "dataset"))
    ap.add_argument("--n", type=int, default=12)
    a = ap.parse_args()
    ds = Path(a.dataset)

    imgs = sorted((ds / "images").glob("*/*.jpg"))
    if not imgs:
        sys.exit(f"No images in {ds}/images – collect data first.")
    counts = {c: 0 for c in CLASSES}
    for lbl in (ds / "labels").glob("*/*.txt"):
        for line in lbl.read_text().splitlines():
            if line.strip():
                counts[CLASSES[int(line.split()[0])]] += 1
    print(f"{len(imgs)} images")
    for c, n in counts.items():
        flag = "" if n >= 100 else "   <-- low, collect more pages that show this"
        print(f"  {c:15} {n:6}{flag}")

    out = ds / "review"
    out.mkdir(exist_ok=True)
    for p in random.sample(imgs, min(a.n, len(imgs))):
        lbl = ds / "labels" / p.parent.name / (p.stem + ".txt")
        im = Image.open(p).convert("RGB")
        W, H = im.size
        d = ImageDraw.Draw(im)
        for line in lbl.read_text().splitlines():
            cid, xc, yc, w, h = line.split()
            cid = int(cid)
            xc, yc, w, h = float(xc) * W, float(yc) * H, float(w) * W, float(h) * H
            col = COLORS[cid % len(COLORS)]
            d.rectangle([xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2], outline=col, width=3)
            d.text((xc - w / 2 + 3, yc - h / 2 + 2), CLASSES[cid], fill=col)
        im.save(out / p.name, quality=85)
    print(f"Review images written to {out}")


if __name__ == "__main__":
    main()
