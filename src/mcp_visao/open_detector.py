"""Detector open-vocabulary (OWLv2) em ONNX: acha objeto pelo nome, sem treino.

Uma passada do ViT em 960x960 da uma caixa por patch; o texto so pontua essas caixas,
entao varios prompts custam quase o mesmo que um. Pesos: models/open_detector
(baixe com tools/fetch_models.py open). Licenca: Apache-2.0 (google/owlv2).
"""

import pathlib

import cv2
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

DIR = pathlib.Path(__file__).resolve().parents[2] / "models" / "open_detector"
SIZE = 960
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32) * 255
STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32) * 255


def available():
    return (DIR / "onnx" / "model.onnx").exists()


class OpenDetector:
    def __init__(self, folder=DIR):
        self.tok = Tokenizer.from_file(str(folder / "tokenizer.json"))
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        avail = ort.get_available_providers()
        self.sess = ort.InferenceSession(
            str(folder / "onnx" / "model.onnx"), opts,
            providers=[p for p in ("DmlExecutionProvider", "CPUExecutionProvider") if p in avail])

    def detect(self, img, prompts, min_conf=0.1, iou=0.5, max_area=0.4):
        """img BGR -> [{t, txt, box, c}] em pixels de img, do mais confiavel para o menos."""
        h, w = img.shape[:2]
        enc = [self.tok.encode(p).ids for p in prompts]
        n = max(len(e) for e in enc)
        ids = np.array([e + [0] * (n - len(e)) for e in enc], np.int64)
        mask = np.array([[1] * len(e) + [0] * (n - len(e)) for e in enc], np.int64)

        x = cv2.resize(img, (SIZE, SIZE), interpolation=cv2.INTER_CUBIC)
        x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32)
        x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]

        logits, boxes = self.sess.run(["logits", "pred_boxes"],
                                      {"pixel_values": x, "input_ids": ids, "attention_mask": mask})
        scores = 1 / (1 + np.exp(-logits[0]))  # [patches, prompts]
        found = []
        for qi, label in enumerate(prompts):
            sc = scores[:, qi]
            rects, confs = [], []
            for i in np.where(sc >= min_conf)[0]:
                cx, cy, bw, bh = boxes[0, i]
                if bw * bh > max_area:  # a imagem inteira casa com quase todo prompt
                    continue
                rects.append([float((cx - bw / 2) * w), float((cy - bh / 2) * h),
                              float(bw * w), float(bh * h)])
                confs.append(float(sc[i]))
            if not rects:
                continue
            keep = np.array(cv2.dnn.NMSBoxes(rects, confs, min_conf, iou)).reshape(-1)
            for k in keep:
                x1, y1, bw, bh = rects[k]
                found.append({"t": "object", "txt": label, "c": round(confs[k], 2),
                              "box": [round(x1), round(y1), round(bw), round(bh)]})
        found.sort(key=lambda e: -e["c"])
        return found
