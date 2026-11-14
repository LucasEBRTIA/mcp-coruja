"""Auto-check do legendador: python tests/test_describe.py

Pula se os pesos nao foram baixados (tools/fetch_models.py captioner). A imagem e a mesma
do README do modelo; a resposta de referencia cita um carro verde.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp_visao.describe import Captioner, available  # noqa: E402

if not available():
    print("skip: models/captioner ausente")
    sys.exit(0)

# np.fromfile: cv2.imread nao abre caminho com acento no Windows
img = cv2.imdecode(np.fromfile(str(ROOT / "tests" / "fixtures" / "car.jpg"), np.uint8), cv2.IMREAD_COLOR)
assert img is not None, "fixture car.jpg ausente"

text = Captioner().caption(img, "<CAPTION>").casefold()
assert "car" in text, text
print("ok:", text)
