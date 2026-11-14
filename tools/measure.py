"""Custo por observacao: compacto vs JSON vs screenshot (secao 11 do plano).

Uso: python tools/measure.py "Titulo da janela" "Outra janela" ...
Nao rouba foco: a captura e por PrintWindow, entao janela coberta tambem vale.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_coruja import server as s  # noqa: E402
from mcp_coruja.schema import to_compact  # noqa: E402


def main(titles):
    print(f'{"janela":30} {"ms":>5} {"el":>4} {"compact":>8} {"json":>6} '
          f'{"tok":>5} {"img_tok":>8} {"ganho":>6}')
    for title in titles:
        r = s.set_target(title)
        if not r["ok"]:
            print(f'{title:30} {r["error"]}')
            continue
        payload = json.loads(s.observe(format="json", max_elements=200))
        if "elements" not in payload:
            print(f'{title:30} {payload}')
            continue
        compact = to_compact(payload)
        as_json = json.dumps(payload, ensure_ascii=False)
        w, h = payload["size"]
        tok = round(len(compact) / 4)
        img_tok = round(w / 28) * round(h / 28)
        print(f'{title[:30]:30} {payload["ms"]:5} {len(payload["elements"]):4} '
              f'{len(compact):8} {len(as_json):6} {tok:5} {img_tok:8} '
              f'{img_tok / tok:5.1f}x')
        if payload.get("truncated"):
            print(f'{"":30} truncado: +{payload["truncated"]} elementos')


if __name__ == "__main__":
    main(sys.argv[1:])
