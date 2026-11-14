"""Auto-check do observe offline: OCR + detector na fixture do jogo."""

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp_visao.server import _read  # noqa: E402

img = cv2.imdecode(np.fromfile(str(ROOT / "tests" / "fixtures" / "game.jpg"), np.uint8), cv2.IMREAD_COLOR)
assert img is not None, "fixture game.jpg ausente"

els = _read(img, 0.5)
assert len(els) >= 10, len(els)
assert all(e["t"] in ("text", "button", "icon") for e in els)
assert all(e["box"][2] > 0 and e["box"][3] > 0 for e in els)
assert all(e["box"][0] < img.shape[1] and e["box"][1] < img.shape[0] for e in els)

txt = " ".join(e["txt"] for e in els).casefold()
assert "bonnie" in txt, txt  # "Fale com Bonnie" na HUD

print("ok:", len(els), "elementos;", sum(e["t"] == "text" for e in els), "textos")
