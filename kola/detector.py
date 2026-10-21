"""The trained YOLO model: screenshot -> list of UI elements with boxes."""
from dataclasses import dataclass, field


@dataclass
class Element:
    cls: str
    conf: float
    box: tuple  # (x1, y1, x2, y2) in screenshot pixels
    text: str = ""  # filled by OCR when needed
    meta: dict = field(default_factory=dict)

    @property
    def center(self):
        x1, y1, x2, y2 = self.box
        return (x1 + x2) / 2, (y1 + y2) / 2

    @property
    def area(self):
        x1, y1, x2, y2 = self.box
        return max(0, x2 - x1) * max(0, y2 - y1)

    def contains_point(self, x, y, pad=2):
        x1, y1, x2, y2 = self.box
        return x1 - pad <= x <= x2 + pad and y1 - pad <= y <= y2 + pad

    def to_dict(self):
        return {"type": self.cls, "conf": round(self.conf, 3), "box": [round(v) for v in self.box], "text": self.text}


class Detector:
    def __init__(self, weights: str, conf: float = 0.35, imgsz: int = 960):
        from ultralytics import YOLO
        self.model = YOLO(weights)
        self.names = self.model.names
        self.conf = conf
        self.imgsz = imgsz

    @property
    def classes(self):
        return list(self.names.values())

    def detect(self, img):
        r = self.model.predict(img, conf=self.conf, imgsz=self.imgsz, verbose=False)[0]
        out = []
        for b, c, s in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist()):
            out.append(Element(cls=self.names[int(c)], conf=float(s), box=tuple(b)))
        return out
