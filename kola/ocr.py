"""OCR: reads text on screen so Kola can match "Gaming", a video title, "6 days ago", "Sign up"...

Runs once per screenshot (lazily, only when a step needs text) and returns word boxes.
"""
from .detector import Element


class OCR:
    def __init__(self, langs=("en",)):
        self.langs = list(langs)
        self._reader = None

    @staticmethod
    def available() -> bool:
        try:
            import easyocr  # noqa: F401
            return True
        except Exception:
            return False

    def _get(self):
        if self._reader is None:
            import easyocr
            try:
                import torch
                gpu = torch.cuda.is_available()
            except Exception:
                gpu = False
            self._reader = easyocr.Reader(self.langs, gpu=gpu, verbose=False)
        return self._reader

    def read(self, img):
        """Whole screenshot -> list of Element(cls='text', text=..., box=...)."""
        import numpy as np
        res = self._get().readtext(np.array(img), paragraph=False)
        words = []
        for pts, text, conf in res:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            words.append(Element(cls="text", conf=float(conf), box=(min(xs), min(ys), max(xs), max(ys)), text=text))
        return words
