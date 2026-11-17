"""Junta OCR + caixas de icone num unico array de elementos (funcao pura)."""

import re

# Ideograma CJK sozinho e ruido: o OCR rapido "inventa" 品/凹/口 em cima de icones.
_CJK_SOLO = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")


def _center(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2


def _contains(outer, inner):
    cx, cy = _center(inner)
    x, y, w, h = outer
    return x <= cx <= x + w and y <= cy <= y + h


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def clean_texts(texts):
    """Tira ruido do OCR antes da fusao: ideograma CJK sozinho e caixa duplicada."""
    out = []
    for t in texts:
        if _CJK_SOLO.match(t["txt"]):
            continue
        dup = next((o for o in out if o["txt"].casefold() == t["txt"].casefold()
                    and _iou(o["box"], t["box"]) > 0.8), None)
        if dup:
            if t["c"] > dup["c"]:
                dup.update(t)
            continue
        out.append(t)
    return out


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
