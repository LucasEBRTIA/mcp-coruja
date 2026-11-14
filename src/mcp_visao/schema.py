"""Funcoes puras de formato (sem I/O, sem modelos): JSON <-> linha compacta."""

import json


def quad_to_box(quad):
    """[[x,y],...] 4 pontos do OCR -> [x, y, largura, altura] em ints."""
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    x, y = min(xs), min(ys)
    return [round(x), round(y), round(max(xs) - x), round(max(ys) - y)]


def to_compact(payload):
    """Uma linha por elemento, sem chaves repetidas (secao 6.4 do plano)."""
    if "added" in payload:  # diff: +novo, -removido, ~movido
        lines = [f'#{payload["frame"]} changed']
        for e in payload["added"]:
            box = ",".join(str(v) for v in e["box"])
            lines.append(f'+{e["id"]} {e["t"]} "{e["txt"]}" {box} {e["c"]:.2f}')
        lines += [f'-{i}' for i in payload["removed"]]
        lines += [f'~{m["id"]} {",".join(str(v) for v in m["box"])}' for m in payload["moved"]]
        return "\n".join(lines)

    head = f'#{payload["frame"]} {payload["size"][0]}x{payload["size"][1]}'
    if payload.get("truncated"):
        head += f' trunc={payload["truncated"]}'
    lines = [head]
    for e in payload["elements"]:
        box = ",".join(str(v) for v in e["box"])
        lines.append(f'{e["id"]} {e["t"]} "{e["txt"]}" {box} {e["c"]:.2f}')
    return "\n".join(lines)


def to_json(payload):
    return json.dumps(payload, ensure_ascii=False)
