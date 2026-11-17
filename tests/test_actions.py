"""Auto-check da validacao das acoes em lote: python tests/test_actions.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_coruja.server import _check_action, _run_action  # noqa: E402

for good in (
    {"click": "e7"},
    {"click": "o1"},
    {"click": [10, 20]},
    {"press": "ctrl+s"},
    {"type": "texto qualquer"},
    {"scroll": -3},
    {"wait": 500},
    {"wait": 0},
):
    _check_action(good)

for bad in (
    {},
    {"click": "e7", "type": "x"},
    {"jump": 1},
    {"click": 7},
    "click",
    {"press": ""},
    {"press": 3},
    {"type": None},
    {"scroll": "3"},
    {"scroll": True},
    {"scroll": 1.5},
    {"wait": -1},
    {"wait": 20000},
    {"wait": "500"},
    {"click": [1, 2, 3]},
):
    try:
        _check_action(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"deveria falhar: {bad!r}")

# wait e a unica acao que nao toca no SO: da para executar num teste
assert _run_action({"wait": 10}) is None

print("ok")
