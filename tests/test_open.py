"""Auto-check do detector open-vocabulary: python tests/test_open.py

Pula se os pesos nao foram baixados (tools/fetch_models.py open). A fixture e um
print do jogo com o personagem no meio; o topo de "character" tem que cair nele.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp_visao.open_detector import OpenDetector, available  # noqa: E402

if not available():
    print("skip: models/open_detector ausente")
    sys.exit(0)

# np.fromfile: cv2.imread nao abre caminho com acento no Windows
img = cv2.imdecode(np.fromfile(str(ROOT / "tests" / "fixtures" / "game.jpg"), np.uint8), cv2.IMREAD_COLOR)
assert img is not None, "fixture game.jpg ausente"

found = OpenDetector().detect(img, ["character"], min_conf=0.15)
assert found, "character nao detectado"

h, w = img.shape[:2]
top = found[0]
cx = top["box"][0] + top["box"][2] / 2
cy = top["box"][1] + top["box"][3] / 2
assert top["txt"] == "character"
assert 0.25 * w < cx < 0.75 * w and 0.2 * h < cy < 0.95 * h, (top, w, h)
assert top["box"][2] * top["box"][3] < 0.5 * w * h, top

print("ok:", top)
