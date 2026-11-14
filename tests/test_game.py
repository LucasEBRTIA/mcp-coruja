"""Auto-check do decoder do detector treinado (sem ONNX): python tests/test_game.py"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_coruja.game_detector import _decode  # noqa: E402

CLASSES = ["enemy", "chest"]

# [cx, cy, w, h, score_enemy, score_chest], em pixels do modelo
out = np.array([
    [100, 100, 40, 40, 0.90, 0.10],  # enemy
    [102, 102, 40, 40, 0.80, 0.10],  # enemy duplicado: NMS por classe remove
    [300, 300, 50, 50, 0.20, 0.70],  # chest
    [500, 500, 20, 20, 0.05, 0.05],  # abaixo do limiar
])

found = _decode(out, CLASSES, min_conf=0.3)
assert [f["txt"] for f in found] == ["enemy", "chest"], found
assert found[0]["box"] == [80.0, 80.0, 40.0, 40.0], found[0]
assert found[0]["c"] == 0.9 and found[1]["c"] == 0.7

# NMS e por classe: mesma caixa, classes diferentes, as duas sobrevivem
same = np.array([[100, 100, 40, 40, 0.9, 0.05], [100, 100, 40, 40, 0.05, 0.9]])
assert len(_decode(same, CLASSES, min_conf=0.3)) == 2

# nada acima do limiar
assert _decode(out, CLASSES, min_conf=0.95) == []

# caminho real do ONNX: o modelo de UI tem o mesmo layout (4 + 1 classe) e serve de cobaia
import cv2  # noqa: E402

from mcp_coruja.detector import MODEL_PATH  # noqa: E402
from mcp_coruja.game_detector import GameDetector  # noqa: E402

if MODEL_PATH.exists():
    fixture = Path(__file__).resolve().parent / "fixtures" / "game.jpg"
    img = cv2.imdecode(np.fromfile(str(fixture), np.uint8), cv2.IMREAD_COLOR)
    found_real = GameDetector(MODEL_PATH, ["icon"]).run(img, min_conf=0.35)
    assert found_real, "detector real nao achou nada na fixture"
    h, w = img.shape[:2]
    assert all(f["txt"] == "icon" for f in found_real)
    assert all(0 <= f["box"][0] < w and 0 <= f["box"][1] < h for f in found_real), found_real[:2]
else:
    print("aviso: models/ui_detector ausente, pulando o teste do ONNX real")

print("ok:", [f["txt"] for f in found])
