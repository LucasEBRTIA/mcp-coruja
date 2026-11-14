"""Diferenca entre elementos de dois frames (funcao pura)."""


def _key(e):
    return e["t"], e["txt"].casefold()


def diff_elements(prev, cur, move_px=6):
    """prev/cur: elementos com id/t/txt/box/c.

    Casa por (tipo, texto): mesmo texto em outra posicao = moved; texto novo =
    added + o id antigo em removed. Sem heuristica de posicao: "mesma caixa,
    texto diferente" e outro elemento, e o agente precisa saber disso.
    """
    free = list(range(len(prev)))
    added, moved = [], []
    for e in cur:
        i = next((j for j in free if _key(prev[j]) == _key(e)), None)
        if i is None:
            added.append(e)
            continue
        free.remove(i)
        p = prev[i]
        if max(abs(p["box"][0] - e["box"][0]), abs(p["box"][1] - e["box"][1])) > move_px:
            moved.append({"id": p["id"], "box": e["box"]})
    return {"added": added, "removed": [prev[j]["id"] for j in free], "moved": moved}
