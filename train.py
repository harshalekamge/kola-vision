"""Train Kola's UI element detector (YOLO) on the collected dataset.

    python train.py                       # defaults: yolo11n, 960px, 60 epochs
    python train.py --epochs 30 --model yolo11s.pt

The best model is copied to models/kola_yolo.pt, which the demo app loads.
GPU is used automatically if available (CUDA or Apple MPS). On CPU, use
--epochs 25 and expect ~1 hour for ~500 images; or train on Google Colab
(see train_colab.ipynb).
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from kola.classes import CLASSES  # noqa: E402


def write_yaml(ds: Path) -> Path:
    """(Re)write data.yaml with an absolute path so it works on any machine."""
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASSES))
    y = ds / "data.yaml"
    y.write_text(f"path: {ds.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n{names}\n")
    return y


def pick_device():
    import torch
    if torch.cuda.is_available():
        return 0, -1           # GPU 0, auto batch size
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", 8
    return "cpu", 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(ROOT / "dataset"))
    ap.add_argument("--model", default="yolo11n.pt", help="yolo11n.pt (fast) or yolo11s.pt (more accurate)")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=960, help="UI elements are small; 960 works better than 640")
    a = ap.parse_args()

    ds = Path(a.dataset)
    if not any((ds / "images" / "train").glob("*.jpg")):
        sys.exit(f"No training images in {ds}. Collect data with the Chrome extension first.")
    if not any((ds / "images" / "val").glob("*.jpg")):
        # tiny datasets may end up with an empty val split: move a few images over
        imgs = sorted((ds / "images" / "train").glob("*.jpg"))[: max(1, len(list((ds / 'images' / 'train').glob('*.jpg'))) // 7)]
        for p in imgs:
            shutil.move(str(p), ds / "images" / "val" / p.name)
            shutil.move(str(ds / "labels" / "train" / (p.stem + ".txt")), ds / "labels" / "val" / (p.stem + ".txt"))
    data = write_yaml(ds)

    from ultralytics import YOLO
    device, batch = pick_device()
    print(f"Training {a.model} on {device} | imgsz {a.imgsz} | epochs {a.epochs}")
    model = YOLO(a.model)
    model.train(
        data=str(data), epochs=a.epochs, imgsz=a.imgsz, batch=batch, device=device,
        project=str(ROOT / "runs"), name="kola", exist_ok=True, patience=15, plots=True,
        # UI-specific augmentation: never mirror (text and layout are not symmetric),
        # no rotation; small scale/translate changes mimic zoom levels and window sizes.
        fliplr=0.0, flipud=0.0, degrees=0.0, scale=0.3, translate=0.1, mosaic=0.5,
        hsv_h=0.01, hsv_s=0.3, hsv_v=0.3,
    )
    best = ROOT / "runs" / "kola" / "weights" / "best.pt"
    (ROOT / "models").mkdir(exist_ok=True)
    shutil.copy(best, ROOT / "models" / "kola_yolo.pt")
    print(f"\nSaved model -> {ROOT / 'models' / 'kola_yolo.pt'}")

    try:  # small ONNX copy for laptops without PyTorch (pip install -r requirements-lite.txt)
        onnx = YOLO(str(best)).export(format="onnx", imgsz=a.imgsz, simplify=True)
        shutil.copy(onnx, ROOT / "models" / "kola_yolo.onnx")
        print(f"Saved ONNX  -> {ROOT / 'models' / 'kola_yolo.onnx'}")
    except Exception as e:
        print("ONNX export skipped:", e)

    metrics = YOLO(str(best)).val(data=str(data), imgsz=a.imgsz, device=device, verbose=False)
    print("\nPer-class mAP50:")
    for i, m in zip(metrics.box.ap_class_index, metrics.box.ap50):
        print(f"  {CLASSES[int(i)]:15} {m:.3f}")
    print(f"  {'ALL':15} {metrics.box.map50:.3f}")


if __name__ == "__main__":
    main()
