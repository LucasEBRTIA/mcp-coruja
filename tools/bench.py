"""Mede o custo do lado da ferramenta: latencia e tamanho da resposta por chamada.

Uso: python tools/bench.py "titulo da janela" [repeticoes]

Roda no mesmo processo, sem o hop do MCP, e imprime uma tabela markdown pronta para o
BENCHMARK.md. "tokens" e estimativa grosseira (chars/4): o que importa aqui e comparar
chamadas entre si, nao cravar o numero exato do tokenizador do modelo.
"""

import base64
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from mcp_coruja import server as s  # noqa: E402


def measure(label, fn, runs):
    ms, chars = [], []
    for _ in range(runs):
        t = time.perf_counter()
        out = fn()
        ms.append((time.perf_counter() - t) * 1000)
        chars.append(len(out if isinstance(out, str) else str(out)))
    return label, statistics.median(ms), statistics.median(chars)


def main():
    if len(sys.argv) < 2:
        sys.exit('uso: python tools/bench.py "titulo da janela" [repeticoes]')
    target = sys.argv[1]
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    print("alvo:", s.set_target(target))
    s._ensure_foreground()
    r = s._rect(s._target["hwnd"])
    w, h = r.right - r.left, r.bottom - r.top

    s.observe()  # aquece: carrega OCR + detector fora da medicao
    time.sleep(0.3)

    jobs = [
        ("observe (full, 60 elementos)", lambda: s.observe(), True),
        ("observe (diff, sem mudanca)", lambda: s.observe(mode="diff"), True),
        ("read_region (faixa do topo)", lambda: s.read_region([0, 0, w, min(120, h)]), True),
        ("look (scale 0.5, base64)", lambda: base64.b64encode(s.look(scale=0.5).data).decode(), False),
        ("detect_open (1 prompt)", lambda: s.detect_open(["text"], max_boxes=5), True),
    ]
    if s._profile and s._profile.get("detector"):
        jobs.append(("detect_game (detector do perfil)", lambda: s.detect_game(max_boxes=5), True))

    rows = [(label, *measure(label, fn, runs)[1:], is_text) for label, fn, is_text in jobs]
    print()
    print("| chamada | mediana (ms) | resposta (chars) | ~tokens |")
    print("| :--- | ---: | ---: | ---: |")
    for label, ms, chars, is_text in rows:
        tokens = f"{chars / 4:.0f}" if is_text else "imagem"
        print(f"| {label} | {ms:.0f} | {chars:.0f} | {tokens} |")
    print()
    print(f"(mediana de {runs} execucoes; ~tokens = chars/4)")


if __name__ == "__main__":
    main()
