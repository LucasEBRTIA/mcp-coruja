"""Baixa os modelos ONNX para models/ (uma vez; ~1,7 GB no total).

Uso: python tools/fetch_models.py [ui|captioner|open|all]   (sem argumento = all)
Cada ferramenta que depende do modelo responde erro explicando se ele faltar.
"""

import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1] / "models"

JOBS = {
    "ui": {  # detector de elementos de UI (12 MB): sem ele, so OCR
        "repo": "onnx-community/OmniParser-icon_detect_640x640",
        "dest": "ui_detector",
        "files": {"onnx/model.onnx": "icon_detect.onnx"},
    },
    "captioner": {  # Florence-2 (1,1 GB): describe_scene
        "repo": "onnx-community/Florence-2-base-ft",
        "dest": "captioner",
        "files": {n: n for n in (
            "config.json", "generation_config.json", "preprocessor_config.json",
            "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json",
            "onnx/vision_encoder.onnx", "onnx/embed_tokens.onnx",
            "onnx/encoder_model.onnx", "onnx/decoder_model.onnx")},
    },
    "open": {  # OWLv2 (620 MB): detect_open
        "repo": "Xenova/owlv2-base-patch16-ensemble",
        "dest": "open_detector",
        "files": {n: n for n in (
            "config.json", "preprocessor_config.json", "special_tokens_map.json",
            "tokenizer.json", "tokenizer_config.json", "merges.txt", "vocab.json",
            "onnx/model.onnx")},
    },
}


def fetch(repo, url_name, out):
    if out.exists() and out.stat().st_size:
        print("ok (ja existe)", out.relative_to(ROOT.parent))
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    print("baixando", url_name, "->", out.relative_to(ROOT.parent), flush=True)
    tmp = out.with_suffix(out.suffix + ".part")
    url = f"https://huggingface.co/{repo}/resolve/main/{url_name}"
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            got += len(chunk)
            if total:
                print(f"\r  {got / 1e6:6.1f}/{total / 1e6:.1f} MB", end="", flush=True)
    print()
    tmp.replace(out)


if __name__ == "__main__":
    wanted = [a for a in sys.argv[1:] if a != "all"] or list(JOBS)
    bad = [w for w in wanted if w not in JOBS]
    if bad:
        sys.exit(f"modelo desconhecido: {bad}; opcoes: {list(JOBS)} ou all")
    for name in wanted:
        job = JOBS[name]
        for url_name, local in job["files"].items():
            fetch(job["repo"], url_name, ROOT / job["dest"] / local)
    print("pronto:", ", ".join(wanted))
