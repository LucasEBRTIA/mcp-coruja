"""Auto-check sem pytest: python tests/test_schema.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_visao.schema import quad_to_box, to_compact, to_json  # noqa: E402

# retangulo torto de 100x50
assert quad_to_box([[10, 20], [110, 22], [108, 70], [12, 68]]) == [10, 20, 100, 50]

payload = {
    "frame": 128,
    "size": [1920, 1080],
    "truncated": 23,
    "elements": [{"id": "e1", "t": "text", "txt": "Jogar", "box": [820, 400, 280, 70], "c": 0.97}],
}
assert to_compact(payload).splitlines() == [
    "#128 1920x1080 trunc=23",
    'e1 text "Jogar" 820,400,280,70 0.97',
]
assert to_json({"txt": "Opções"}) == '{"txt": "Opções"}'

diff = {"frame": 130, "added": [{"id": "e9", "t": "text", "txt": "Game Over",
                                 "box": [700, 300, 500, 90], "c": 0.95}],
        "removed": ["e4"], "moved": [{"id": "e2", "box": [820, 500, 280, 70]}]}
assert to_compact(diff).splitlines() == [
    "#130 changed",
    '+e9 text "Game Over" 700,300,500,90 0.95',
    "-e4",
    "~e2 820,500,280,70",
]

print("ok")
