"""Auto-check sem pytest: python tests/test_diff.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_coruja.diff import diff_elements  # noqa: E402

prev = [{"id": "e1", "t": "text", "txt": "Jogar", "box": [10, 10, 100, 20], "c": 0.9},
        {"id": "e2", "t": "icon", "txt": "", "box": [200, 200, 40, 40], "c": 0.8},
        {"id": "e3", "t": "text", "txt": "Sair", "box": [10, 50, 80, 20], "c": 0.9}]

# 1) nada mudou
d = diff_elements(prev, [dict(e) for e in prev])
assert d == {"added": [], "removed": [], "moved": []}, d

# 2) texto sumiu, aparece outro e um icone andou
cur = [{"id": "e1", "t": "text", "txt": "Jogar", "box": [10, 10, 100, 20], "c": 0.9},
       {"id": "e2", "t": "icon", "txt": "", "box": [400, 200, 40, 40], "c": 0.8},
       {"id": "e4", "t": "text", "txt": "Novo", "box": [10, 90, 80, 20], "c": 0.9}]
d = diff_elements(prev, cur)
assert [e["id"] for e in d["added"]] == ["e4"], d
assert d["removed"] == ["e3"], d
assert d["moved"] == [{"id": "e2", "box": [400, 200, 40, 40]}], d

# 3) mesmo lugar, texto mudou: e outro elemento (added + removed), nao "moved"
d = diff_elements(prev, [{"id": "e5", "t": "text", "txt": "Carregando", "box": [10, 10, 100, 20], "c": 0.9},
                         {"id": "e2", "t": "icon", "txt": "", "box": [200, 200, 40, 40], "c": 0.8},
                         {"id": "e3", "t": "text", "txt": "Sair", "box": [10, 50, 80, 20], "c": 0.9}])
assert [e["id"] for e in d["added"]] == ["e5"], d
assert d["removed"] == ["e1"] and d["moved"] == [], d

print("ok")
