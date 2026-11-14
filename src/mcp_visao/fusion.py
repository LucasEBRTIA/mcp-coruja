"""Junta OCR + caixas de icone num unico array de elementos (funcao pura)."""


def _center(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2


def _contains(outer, inner):
    cx, cy = _center(inner)
    x, y, w, h = outer
    return x <= cx <= x + w and y <= cy <= y + h


def fuse(texts, icons, min_h=10):
    """texts: [{txt, box, c}] do OCR; icons: [{box, c}] do detector.

    Texto cujo centro cai dentro da caixa vira rotulo do icone (t="button").
    Icone sozinho fica t="icon"; texto fora de qualquer caixa fica t="text".
    """
    used = set()
    out = []
    for ic in icons:
        if ic["box"][3] < min_h:
            continue
        inside = [i for i, t in enumerate(texts) if _contains(ic["box"], t["box"])]
        if len(inside) > 2:
            continue  # caixa-painel que engoliu varios textos: nao e um elemento
        used.update(inside)
        txt = " ".join(texts[i]["txt"] for i in inside)[:80]
        out.append({"t": "button" if txt else "icon", "txt": txt, "box": ic["box"], "c": ic["c"]})
    out += [{"t": "text", "txt": t["txt"], "box": t["box"], "c": t["c"]}
            for i, t in enumerate(texts) if i not in used]
    out.sort(key=lambda e: (e["box"][1], e["box"][0]))
    return out
