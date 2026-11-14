"""Auto-check sem pytest: python tests/test_keys.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_coruja.control import parse_keys  # noqa: E402

assert parse_keys("s") == ([], 0x53)                 # S
assert parse_keys("w") == ([], 0x57)                 # W
assert parse_keys("1") == ([], 0x31)
assert parse_keys("ctrl+s") == ([0x11], 0x53)
assert parse_keys("ctrl+shift+ESC") == ([0x11, 0x10], 0x1B)
assert parse_keys("alt+f4") == ([0x12], 0x73)
assert parse_keys("enter") == ([], 0x0D)
assert parse_keys("up") == ([], 0x26)

for bad in ("", "ctrl+", "ctrl+tecla_que_nao_existe", "hiper+s"):
    try:
        parse_keys(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"deveria falhar: {bad!r}")

print("ok")
