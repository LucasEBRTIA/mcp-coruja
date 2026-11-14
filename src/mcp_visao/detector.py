"""Detector de elementos de UI: YOLOv8 (OmniParser icon_detect) em ONNX.

Entrada fixa 640x640, uma classe ("icone/elemento"). Pesos: models/ui_detector/.
Baixado de https://huggingface.co/onnx-community/OmniParser-icon_detect_640x640
Licenca dos pesos: AGPL-3.0 (derivado do YOLOv8) - ok para uso pessoal, ver antes de distribuir.
"""

import pathlib

import cv2
import numpy as np
import onnxruntime as ort

MODEL_PATH = pathlib.Path(__file__).resolve().parents[2] / "models" / "ui_detector" / "icon_detect.onnx"


def _providers():
    avail = ort.get_available_providers()
    return [p for p in ("DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider") if p in avail]


class IconDetector:
    def __init__(self, path=MODEL_PATH):
        self.sess = ort.InferenceSession(str(path), providers=_providers())
        inp = self.sess.get_inputs()[0]
        self.name, self.size = inp.name, inp.shape[2]

    def run(self, img, min_conf=0.5, iou=0.5):
        """Frame BGR -> [{box: [x, y, w, h], c}] em pixels do frame."""
        h, w = img.shape[:2]
        r = min(self.size / w, self.size / h)
        nw, nh = round(w * r), round(h * r)
        dx, dy = (self.size - nw) // 2, (self.size - nh) // 2
        canvas = np.full((self.size, self.size, 3), 114, np.uint8)
        canvas[dy:dy + nh, dx:dx + nw] = cv2.resize(img, (nw, nh))
        x = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None].astype(np.float32) / 255

        out = self.sess.run(None, {self.name: x})[0][0].T  # [n, 4 + classes]
        out = out[out[:, 4] >= min_conf]
        if not len(out):
            return []
        cx, cy, bw, bh, score = out.T
        boxes = np.stack([cx - bw / 2, cy - bh / 2, bw, bh], 1)
        keep = cv2.dnn.NMSBoxes(boxes.tolist(), score.tolist(), min_conf, iou)
        return [{"box": [int((boxes[i][0] - dx) / r), int((boxes[i][1] - dy) / r),
                         int(boxes[i][2] / r), int(boxes[i][3] / r)],
                 "c": round(float(score[i]), 2)} for i in np.array(keep).flatten()]
