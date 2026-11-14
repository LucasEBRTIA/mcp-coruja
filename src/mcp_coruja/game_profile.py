"""Perfil por jogo: janela, regioes de HUD, prompts e detector treinado (opcional).

Layout: profiles/<nome>/profile.json, e os arquivos que o perfil apontar (detector.onnx,
frames/). Sem detector, o perfil so entrega janela + regioes + prompts para detect_open.
"""

import json
import pathlib

DIR = pathlib.Path(__file__).resolve().parents[2] / "profiles"


def names(base=DIR):
    return sorted(p.parent.name for p in base.glob("*/profile.json"))


def load(name, base=DIR):
    """Le e valida o perfil. ValueError com o motivo quando o arquivo esta errado."""
    path = base / name / "profile.json"
    if not path.exists():
        raise ValueError(f"perfil nao encontrado: {name} (crie {path})")
    try:
        # utf-8-sig: Notepad/PowerShell gravam BOM e json.loads nao aceita
        p = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ValueError(f"profile.json invalido em {name}: {e}") from e
    p["name"], p["dir"] = name, path.parent
    hud = {}
    for k, box in (p.get("hud") or {}).items():
        if len(box) != 4:
            raise ValueError(f"{name}: hud '{k}' precisa de [x,y,w,h]")
        hud[k] = [int(v) for v in box]
    p["hud"] = hud
    if p.get("detector"):
        p["detector_path"] = path.parent / p["detector"]
        if not p.get("classes"):
            raise ValueError(f"{name}: 'detector' exige 'classes' (nomes na ordem do treino)")
        if len(p["classes"]) != int(p.get("num_classes", len(p["classes"]))):
            raise ValueError(f"{name}: 'num_classes' nao bate com 'classes'")
    return p
