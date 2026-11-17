"""Auto-check sem pytest: python tests/test_fusion.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_coruja.fusion import clean_texts, fuse  # noqa: E402

# ruido do OCR: 1 ideograma sozinho cai; texto CJK de verdade fica
ruido = [{"txt": "品", "box": [10, 10, 20, 20], "c": 0.9},
         {"txt": "凹", "box": [50, 10, 20, 20], "c": 0.6},
         {"txt": "Início", "box": [100, 10, 60, 20], "c": 0.9},
         {"txt": "首页", "box": [200, 10, 40, 20], "c": 0.9}]
assert [t["txt"] for t in clean_texts(ruido)] == ["Início", "首页"]

# mesma caixa, mesmo texto: fica a de maior confianca
dup = [{"txt": "Configurações", "box": [10, 10, 100, 20], "c": 0.7},
       {"txt": "configurações", "box": [12, 11, 99, 19], "c": 0.9}]
assert [(t["txt"], t["c"]) for t in clean_texts(dup)] == [("configurações", 0.9)]

# caixas do mesmo texto longe uma da outra continuam as duas
longe = [{"txt": "OK", "box": [10, 10, 40, 20], "c": 0.9},
         {"txt": "OK", "box": [500, 400, 40, 20], "c": 0.8}]
assert len(clean_texts(longe)) == 2
assert clean_texts([]) == []

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
