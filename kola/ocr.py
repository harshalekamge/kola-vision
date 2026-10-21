"""OCR: reads text on screen so Kola can match "Gaming", a video title, "6 days ago", "Sign up"...

Engines, picked automatically in this order:
  * RapidOCR  (rapidocr_onnxruntime) — light, no PyTorch, works offline   <- requirements-lite.txt
  * winocr    — Windows' built-in OCR, tiny download
  * EasyOCR   — needs PyTorch (full install)

Runs once per screenshot (lazily, only when a step needs text) and returns word boxes.
"""
from .detector import Element

BACKENDS = ("rapidocr_onnxruntime", "winocr", "easyocr")


def _has(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


class OCR:
    def __init__(self, langs=("en",)):
        self.langs = list(langs)
        self.backend = next((b for b in BACKENDS if _has(b)), None)
        self._engine = None

    @staticmethod
    def available() -> bool:
        return any(_has(b) for b in BACKENDS)

    def read(self, img):
        """Whole screenshot -> list of Element(cls='text', text=..., box=...)."""
        if self.backend == "rapidocr_onnxruntime":
            return self._read_rapid(img)
        if self.backend == "winocr":
            return self._read_winocr(img)
        if self.backend == "easyocr":
            return self._read_easyocr(img)
        raise RuntimeError("No OCR engine installed (pip install rapidocr_onnxruntime)")

    # ---- RapidOCR ----
    def _read_rapid(self, img):
        import numpy as np
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
        arr = np.array(img.convert("RGB"))[:, :, ::-1]  # RGB -> BGR (OpenCV order)
        result, _ = self._engine(arr)
        return [_from_quad(pts, text, conf) for pts, text, conf in (result or [])]

    # ---- Windows built-in OCR ----
    def _read_winocr(self, img):
        import asyncio
        import winocr
        img = img.convert("RGBA")
        scale = 1.0
        if max(img.size) > 4000:
            scale = 4000 / max(img.size)
            img = img.resize((int(img.width * scale), int(img.height * scale)))
        if hasattr(winocr, "recognize_pil_sync"):
            res = winocr.recognize_pil_sync(img, self.langs[0])
        else:
            res = asyncio.run(winocr.recognize_pil(img, self.langs[0]))
        data = res if isinstance(res, dict) else winocr.picklify(res)
        words = []
        for line in data.get("lines", []):
            for wd in line.get("words", []):
                r = wd["bounding_rect"]
                x, y, w, h = (r["x"] / scale, r["y"] / scale, r["width"] / scale, r["height"] / scale)
                words.append(Element(cls="text", conf=1.0, box=(x, y, x + w, y + h), text=wd["text"]))
        return words

    # ---- EasyOCR ----
    def _read_easyocr(self, img):
        import numpy as np
        if self._engine is None:
            import easyocr
            try:
                import torch
                gpu = torch.cuda.is_available()
            except Exception:
                gpu = False
            self._engine = easyocr.Reader(self.langs, gpu=gpu, verbose=False)
        return [_from_quad(pts, text, conf) for pts, text, conf in self._engine.readtext(np.array(img.convert("RGB")))]


def _from_quad(pts, text, conf):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return Element(cls="text", conf=float(conf), box=(min(xs), min(ys), max(xs), max(ys)), text=text)
