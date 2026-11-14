"""Pre-anota os frames de um perfil com o OWLv2, no formato YOLO, para treinar depois.

Uso: python tools/annotate.py zzz [--conf 0.2]
Le profiles/<perfil>/frames/*.jpg, usa os 'prompts' do perfil como classes e escreve
profiles/<perfil>/dataset/{images,labels} + classes.txt (indice = ordem dos prompts).
Corrija as caixas no CVAT/Label Studio antes de treinar; isto e so o ponto de partida.
"""

import argparse
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import cv2
import numpy as np

from mcp_visao.game_profile import load
from mcp_visao.open_detector import OpenDetector, available


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--conf", type=float, default=0.2)
    args = ap.parse_args()

    if not available():
        sys.exit("modelo ausente: rode python tools/fetch_models.py open")
    p = load(args.profile)
    prompts = p.get("prompts") or []
    if not prompts:
        sys.exit(f"perfil {args.profile} sem 'prompts'")
    frames = sorted((p["dir"] / "frames").glob("*.jpg"))
    if not frames:
        sys.exit(f"nenhum frame em {p['dir'] / 'frames'}; use capture_frames primeiro")

    out = p["dir"] / "dataset"
    images, labels = out / "images", out / "labels"
    images.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)
    (out / "classes.txt").write_text("\n".join(prompts) + "\n", encoding="utf-8")

    det = OpenDetector()
    boxes = 0
    for f in frames:
        img = cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        h, w = img.shape[:2]
        found = det.detect(img, prompts, args.conf)
        lines = []
        for e in found:
            x, y, bw, bh = e["box"]
            lines.append(f"{prompts.index(e['txt'])} {(x + bw / 2) / w:.6f} {(y + bh / 2) / h:.6f} "
                         f"{bw / w:.6f} {bh / h:.6f}")
        if not lines:  # frame sem caixa fica de fora do dataset
            continue
        shutil.copyfile(f, images / f.name)
        (labels / (f.stem + ".txt")).write_text("\n".join(lines) + "\n", encoding="utf-8")
        boxes += len(lines)

    print(f"{len(list(images.glob('*.jpg')))} imagens, {boxes} caixas em {out}")


if __name__ == "__main__":
    main()
