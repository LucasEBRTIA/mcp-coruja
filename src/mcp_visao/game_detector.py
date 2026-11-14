"""Detector treinado do jogo: YOLOv8 exportado em ONNX com N classes.

O download/treino fica fora do servidor; aqui so carregamos o best.onnx do perfil e
decodificamos as saidas (mesmo layout do ultralytics: [1, 4 + classes, n]).
"""

import cv2
import numpy as np
import onnxruntime as ort

from .detector import _providers


def _decode(out, classes, min_conf=0.3, iou=0.5):
    """out: [n, 4 + n_classes] (cx,cy,w,h + score por classe) em pixels do modelo.

    Uma caixa por classe (NMS por classe), do mais confiavel para o menos.
    """
    scores = out[:, 4:]
    cls = scores.argmax(1)
    conf = scores.max(1)
    keep = conf >= min_conf
    if not keep.any():
        return []
    out, cls, conf = out[keep], cls[keep], conf[keep]
    cx, cy, bw, bh = out[:, 0], out[:, 1], out[:, 2], out[:, 3]
    boxes = np.stack([cx - bw / 2, cy - bh / 2, bw, bh], 1)
    found = []
    for ci, name in enumerate(classes):
        idx = np.where(cls == ci)[0]
        if not len(idx):
            continue
        kept = np.array(cv2.dnn.NMSBoxes(boxes[idx].tolist(), conf[idx].tolist(), min_conf, iou)).flatten()
        for k in kept:
            i = idx[k]
            found.append({"txt": name, "c": round(float(conf[i]), 2),
                          "box": [float(v) for v in boxes[i]]})
    found.sort(key=lambda e: -e["c"])
    return found


class GameDetector:
    def __init__(self, path, classes):
        self.sess = ort.InferenceSession(str(path), providers=_providers())
        inp = self.sess.get_inputs()[0]
        self.name = inp.name
        self.size = inp.shape[2] if isinstance(inp.shape[2], int) else 640
        self.classes = list(classes)

    def run(self, img, min_conf=0.3, iou=0.5):
        """Frame BGR -> [{txt, c, box:[x,y,w,h]}] em pixels do frame."""
        h, w = img.shape[:2]
        r = min(self.size / w, self.size / h)
        nw, nh = round(w * r), round(h * r)
        dx, dy = (self.size - nw) // 2, (self.size - nh) // 2
        canvas = np.full((self.size, self.size, 3), 114, np.uint8)
        canvas[dy:dy + nh, dx:dx + nw] = cv2.resize(img, (nw, nh))
        x = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None].astype(np.float32) / 255

        out = self.sess.run(None, {self.name: x})[0][0].T  # [n, 4 + n_classes]
        found = _decode(out, self.classes, min_conf, iou)
        for e in found:  # desfaz o letterbox
            x1, y1, bw, bh = e["box"]
            e["box"] = [round((x1 - dx) / r), round((y1 - dy) / r), round(bw / r), round(bh / r)]
        return found
