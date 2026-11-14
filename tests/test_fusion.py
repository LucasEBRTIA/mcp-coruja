"""Auto-check sem pytest: python tests/test_fusion.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_visao.fusion import fuse  # noqa: E402

texts = [
    {"txt": "Jogar", "box": [830, 410, 60, 20], "c": 0.9},   # dentro do botao
    {"txt": "v1.2.0", "box": [1800, 1040, 60, 18], "c": 0.9},  # solto
]
icons = [{"box": [820, 400, 280, 70], "c": 0.95},
         {"box": [24, 24, 6, 6], "c": 0.8}]  # pequeno demais: descartado

out = fuse(texts, icons)
assert [(e["t"], e["txt"]) for e in out] == [("button", "Jogar"), ("text", "v1.2.0")]
assert out[0]["box"] == [820, 400, 280, 70] and out[0]["c"] == 0.95

assert fuse([], []) == []
assert fuse(texts, []) == [{"t": "text", "txt": "Jogar", "box": [830, 410, 60, 20], "c": 0.9},
                           {"t": "text", "txt": "v1.2.0", "box": [1800, 1040, 60, 18], "c": 0.9}]

# caixa grande engolindo 3 textos e descartada, textos continuam soltos
many = [{"txt": t, "box": [10 + i * 100, 10, 90, 20], "c": 0.9} for i, t in enumerate("abc")]
assert [e["t"] for e in fuse(many, [{"box": [0, 0, 400, 40], "c": 0.4}])] == ["text"] * 3

print("ok")
