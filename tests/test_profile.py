"""Auto-check do perfil de jogo: python tests/test_profile.py"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from mcp_coruja.game_profile import load, names  # noqa: E402


def write(base, name, data):
    (base / name).mkdir(parents=True, exist_ok=True)
    (base / name / "profile.json").write_text(json.dumps(data), encoding="utf-8")


with tempfile.TemporaryDirectory() as tmp:
    base = pathlib.Path(tmp)
    write(base, "jogo", {"window": "X", "hud": {"hp": ["10", "20", "30", "40"]},
                         "prompts": ["enemy"], "detector": "det.onnx", "classes": ["enemy"]})
    p = load("jogo", base)
    assert p["name"] == "jogo"
    assert p["hud"]["hp"] == [10, 20, 30, 40]
    assert p["detector_path"] == base / "jogo" / "det.onnx"
    assert names(base) == ["jogo"]

    write(base, "sem_modelo", {"window": "Y"})
    q = load("sem_modelo", base)
    assert q["hud"] == {} and not q.get("detector")

    bad = {
        "hud_curto": {"hud": {"hp": [1, 2, 3]}},
        "detector_sem_classes": {"detector": "d.onnx"},
    }
    for name, data in bad.items():
        write(base, name, data)
        try:
            load(name, base)
        except ValueError:
            pass
        else:
            raise AssertionError(f"deveria falhar: {name}")

    try:
        load("nao_existe", base)
    except ValueError as e:
        assert "nao encontrado" in str(e)
    else:
        raise AssertionError("perfil inexistente deveria falhar")

print("ok")
