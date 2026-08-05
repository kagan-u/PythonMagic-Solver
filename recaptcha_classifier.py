import os

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("ORT_NUM_THREADS", "2")

import ast
import base64
import io
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_MODEL = Path(__file__).parent / "models" / "recaptcha_cls_s.onnx"
_DEFAULT_THRESHOLD = 0.55

_TARGET_ALIASES = {
    "bicycle": "Bicycle", "bicycles": "Bicycle", "bike": "Bicycle", "bikes": "Bicycle",
    "bridge": "Bridge", "bridges": "Bridge",
    "bus": "Bus", "buses": "Bus", "busses": "Bus",
    "car": "Car", "cars": "Car", "vehicle": "Car", "vehicles": "Car",
    "chimney": "Chimney", "chimneys": "Chimney",
    "crosswalk": "Crosswalk", "crosswalks": "Crosswalk",
    "cross walk": "Crosswalk", "cross walks": "Crosswalk",
    "hydrant": "Hydrant", "hydrants": "Hydrant",
    "fire hydrant": "Hydrant", "fire hydrants": "Hydrant",
    "a fire hydrant": "Hydrant",
    "motorcycle": "Motorcycle", "motorcycles": "Motorcycle",
    "motorbike": "Motorcycle", "motorbikes": "Motorcycle",
    "mountain": "Mountain", "mountains": "Mountain",
    "mountains or hills": "Mountain", "hill": "Mountain", "hills": "Mountain",
    "palm": "Palm", "palms": "Palm", "palm tree": "Palm", "palm trees": "Palm",
    "stair": "Stair", "stairs": "Stair", "staircase": "Stair",
    "tractor": "Tractor", "tractors": "Tractor",
    "traffic light": "Traffic Light", "traffic lights": "Traffic Light",
    "trafficlight": "Traffic Light", "trafic light": "Traffic Light",
    "traffic signal": "Traffic Light", "traffic signals": "Traffic Light",
}


def _normalize_target(target: str):
    t = (target or "").strip().lower()
    for art in ("a ", "an ", "the "):
        if t.startswith(art):
            t = t[len(art):]
    if t in _TARGET_ALIASES:
        return _TARGET_ALIASES[t]
    for key, cls in _TARGET_ALIASES.items():
        if key in t:
            return cls
    return None


class OnnxClassifier:

    def __init__(self, model_path: str = None, threshold: float = _DEFAULT_THRESHOLD):
        import onnxruntime as ort
        self.model_path = str(model_path or _DEFAULT_MODEL)
        self.threshold = threshold
        so = ort.SessionOptions()
        so.intra_op_num_threads = 2
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(
            self.model_path, so, providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        meta = self.sess.get_modelmeta().custom_metadata_map
        self.names = ast.literal_eval(meta["names"])
        imgsz = meta.get("imgsz", "[128, 128]")
        self.imgsz = ast.literal_eval(imgsz)[0] if imgsz.startswith("[") else int(imgsz)
        self._lock = threading.Lock()
        log.info("OnnxClassifier loaded: %s (%d classes, imgsz=%d)",
                 self.model_path, len(self.names), self.imgsz)

    def _preprocess(self, image_b64: str):
        import numpy as np
        from PIL import Image
        raw = base64.b64decode(image_b64)
        w, h = im.size
        s = self.imgsz / min(w, h)
        im = im.resize((round(w * s), round(h * s)))
        w, h = im.size
        l, t = (w - self.imgsz) // 2, (h - self.imgsz) // 2
        im = im.crop((l, t, l + self.imgsz, t + self.imgsz))
        a = np.asarray(im, dtype=np.float32) / 255.0
        return np.transpose(a, (2, 0, 1))[None]

    def predict(self, image_b64: str):
        import numpy as np
        x = self._preprocess(image_b64)
        with self._lock:
            out = self.sess.run(None, {self.inp: x})[0][0]
        idx = int(np.argmax(out))
        return self.names[idx], float(out[idx])

    def classify(self, image_b64: str, target: str,
                 max_keys: int = 8, timeout: int = 40) -> bool:
        want = _normalize_target(target)
        if want is None:
            return False
        try:
            pred, conf = self.predict(image_b64)
        except Exception as e:
            log.debug("onnx classify error: %s", str(e).splitlines()[0])
            return False
        return pred == want and conf >= self.threshold


_classifier = None


def get_classifier(model_path: str = None):
    global _classifier
    if _classifier is None:
        path = Path(model_path or _DEFAULT_MODEL)
        if not path.exists():
            return None
        _classifier = OnnxClassifier(str(path))
    return _classifier
