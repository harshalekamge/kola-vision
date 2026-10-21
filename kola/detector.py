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


class OnnxDetector:
    """Runs the exported model with onnxruntime only (~15 MB, no PyTorch needed)."""

    def __init__(self, weights: str, conf: float = 0.35, iou: float = 0.5):
        import ast
        import onnxruntime as ort
        from .classes import CLASSES
        self.sess = ort.InferenceSession(weights, providers=["CPUExecutionProvider"])
        inp = self.sess.get_inputs()[0]
        self.input_name = inp.name
        self.imgsz = inp.shape[2] if isinstance(inp.shape[2], int) else 960
        meta = self.sess.get_modelmeta().custom_metadata_map
        self.names = ast.literal_eval(meta["names"]) if "names" in meta else dict(enumerate(CLASSES))
        self.conf, self.iou = conf, iou

    @property
    def classes(self):
        return list(self.names.values())

    def detect(self, img):
        import numpy as np
        from PIL import Image
        W, H = img.size
        s = self.imgsz
        r = min(s / W, s / H)
        nw, nh = round(W * r), round(H * r)
        px, py = (s - nw) // 2, (s - nh) // 2
        canvas = Image.new("RGB", (s, s), (114, 114, 114))
        canvas.paste(img.convert("RGB").resize((nw, nh), Image.BILINEAR), (px, py))
        x = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0

        out = self.sess.run(None, {self.input_name: x})[0][0].T  # (N, 4 + num_classes)
        scores = out[:, 4:]
        cls = scores.argmax(1)
        conf = scores.max(1)
        m = conf >= self.conf
        b, cls, conf = out[m, :4], cls[m], conf[m]
        if not len(b):
            return []
        xyxy = np.stack([b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2, b[:, 0] + b[:, 2] / 2, b[:, 1] + b[:, 3] / 2], 1)
        keep = _nms(xyxy + cls[:, None] * 4096.0, conf, self.iou)  # class-aware NMS
        res = []
        for i in keep:
            x1, y1, x2, y2 = xyxy[i]
            box = ((x1 - px) / r, (y1 - py) / r, (x2 - px) / r, (y2 - py) / r)
            box = (max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3]))
            res.append(Element(cls=self.names[int(cls[i])], conf=float(conf[i]), box=box))
        return res


def _nms(boxes, scores, thr):
    import numpy as np
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        a = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        ar = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        order = rest[inter / (a + ar - inter + 1e-9) < thr]
    return keep


def load_detector(weights: str):
    """.onnx -> lightweight onnxruntime detector; .pt -> ultralytics (needs PyTorch)."""
    if str(weights).lower().endswith(".onnx"):
        return OnnxDetector(weights)
    return Detector(weights)
