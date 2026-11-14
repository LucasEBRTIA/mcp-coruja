# MCP Coruja — "olhos baratos" para agentes de IA

> Plugin/MCP que captura a tela de um programa ou jogo, processa localmente com modelos ONNX
> (OCR + detecção de elementos + objetos do jogo + legenda opcional) e devolve **JSON compacto**
> com coordenadas e texto, em vez de mandar imagens para o modelo de linguagem.

---

## 1. Problema e objetivo

**Problema:** quando o agente testa um programa/jogo mandando screenshots, os tokens acabam muito rápido.
Alternativas como o `agent-desktop` retornam JSON, mas dependem de acessibilidade/UI Automation e não
funcionam em vários programas e jogos (que desenham tudo por conta própria).

**Objetivo:** uma ferramenta que enxerga a tela por *pixels* (funciona em qualquer coisa), mas entrega ao
agente só o que importa, em texto estruturado.

**Metas mensuráveis**
- Reduzir o custo por "passo de observação" em pelo menos 10x comparado a enviar screenshot.
- Latência de uma observação completa abaixo de 500 ms na RTX 4060 Ti (OCR + UI).
- Funcionar em janela, tela cheia sem borda e (quando possível) tela cheia exclusiva.

**Fora do escopo (por enquanto):** substituir totalmente a visão do LLM. A imagem continua disponível
**sob demanda** (recorte pequeno) quando o JSON não bastar.

---

## 2. Princípios de design

1. **JSON por padrão, imagem só quando pedida.**
2. **Cada modelo faz uma coisa.** Modelos pequenos e especializados, carregados sob demanda.
3. **Saída compacta.** Cada campo extra custa token. Nada de campos decorativos.
4. **Diferença entre frames.** Se quase nada mudou, devolver só o que mudou.
5. **Perfis por jogo.** Configuração e modelos extras ficam isolados por perfil.
6. **Tudo local.** Sem enviar prints para a nuvem.

---

## 3. Arquitetura

```
 Agente (LLM)  <--MCP (stdio)-->  Servidor MCP
                                      |
              +-----------------------+------------------------+
              |                       |                        |
        Captura de tela        Pipeline de visão         Controle (opcional)
        (janela/monitor)       (modelos ONNX)            (mouse/teclado)
              |                       |
              |        +--------------+--------------+----------------+
              |        |              |              |                |
              |      OCR        Detector UI    Detector do jogo   Legendador
              |   (sempre)       (sempre)       (por perfil)     (sob demanda)
              |        \              |              /                |
              |         +----- Fusão / normalização ------+          |
              |                       |                              |
              +---------------> Frame store (último frame, diff) <---+
                                      |
                                  JSON final
```

### Fluxo de uma observação
1. Captura o frame da janela alvo.
2. Compara com o frame anterior (hash/diff por blocos). Se igual → devolve `unchanged`.
3. Roda OCR e detector de UI em paralelo (e o detector do jogo, se o perfil tiver).
4. Fusão: junta texto com as caixas detectadas, remove duplicatas, ordena.
5. Atribui IDs curtos (`e1`, `e2`...) e devolve JSON compacto.
6. O agente pode referenciar o ID depois (`click_element("e7")`).

---

## 4. Stack sugerida

| Parte | Escolha | Observação |
|---|---|---|
| Linguagem | **Python 3.11+** | Melhor ecossistema de ONNX/visão |
| MCP | **`mcp` (FastMCP)** | Servidor stdio, simples de registrar no cliente |
| Inferência | **onnxruntime-gpu** (CUDA) ou **onnxruntime-directml** | DirectML funciona sem instalar CUDA toolkit |
| Captura (janela/monitor) | **`dxcam`** ou **`windows-capture`** | Usam DXGI/WGC, funcionam bem com jogos. `mss` como fallback simples |
| Captura de janela em segundo plano | `PrintWindow` / Windows Graphics Capture | Útil quando a janela não está em foco |
| OCR | **RapidOCR (ONNX)** ou PaddleOCR convertido | Rápido e bom em texto de UI |
| Detector de UI | **YOLO de ícones/elementos** (ex.: o do OmniParser) | **Verificar a licença** antes de redistribuir (YOLO costuma ser AGPL) |
| Detector do jogo | **YOLO pequeno treinado por jogo** (n/s) | Exportado para ONNX |
| Open-vocabulary (anotação) | **YOLO-World / Grounding DINO** | Usado para pré-anotar, não em produção |
| Legendador | **Florence-2 (ONNX)** | Só sob demanda |
| Controle | `pydirectinput` / `pyautogui` / `SendInput` | Jogos geralmente exigem entrada em baixo nível |
| Imagens | `numpy`, `opencv-python`, `Pillow` | |

> Dica: fixe versões no `requirements.txt` e documente o provedor de execução usado (CUDA ou DirectML).

---

## 5. Estrutura de pastas

```
mcp-coruja/
├─ README.md
├─ pyproject.toml
├─ requirements.txt
├─ config/
│  ├─ default.yaml
│  └─ profiles/
│     ├─ exemplo-jogo.yaml
│     └─ minecraft.yaml
├─ models/                      # arquivos .onnx (não versionar)
│  ├─ ocr/
│  ├─ ui_detector/
│  ├─ games/<perfil>/
│  └─ captioner/
├─ src/mcp_coruja/
│  ├─ server.py                 # definição das tools MCP
│  ├─ capture/
│  │  ├─ base.py                # interface Capturer
│  │  ├─ dxcam_capture.py
│  │  └─ window_utils.py        # listar/achar janelas, foco, DPI
│  ├─ vision/
│  │  ├─ ocr.py
│  │  ├─ ui_detector.py
│  │  ├─ game_detector.py
│  │  ├─ captioner.py
│  │  ├─ fusion.py              # junta OCR + caixas, remove duplicatas
│  │  └─ diff.py                # diferença entre frames
│  ├─ state/
│  │  └─ frame_store.py         # último frame, IDs de elementos
│  ├─ control/
│  │  └─ input.py               # clique, tecla, scroll
│  ├─ output/
│  │  └─ formatter.py           # JSON compacto / limites de tokens
│  └─ config.py
├─ tools/
│  ├─ annotate_with_owl.py      # pré-anotação com open-vocabulary
│  └─ export_yolo_onnx.py
├─ datasets/                    # prints + labels por jogo
└─ tests/
   ├─ fixtures/                 # prints de exemplo
   └─ test_fusion.py
```

---

## 6. Formato do JSON de saída

### 6.1 Observação completa (`observe`)

```json
{
  "frame": 128,
  "win": "Meu Jogo",
  "size": [1920, 1080],
  "changed": true,
  "ms": 310,
  "elements": [
    { "id": "e1", "t": "button", "txt": "Jogar",    "box": [820, 400, 280, 70], "c": 0.97 },
    { "id": "e2", "t": "button", "txt": "Opções",   "box": [820, 490, 280, 70], "c": 0.96 },
    { "id": "e3", "t": "text",   "txt": "v1.2.0",   "box": [1820, 1040, 80, 24], "c": 0.91 },
    { "id": "e4", "t": "icon",   "txt": "",         "box": [24, 24, 48, 48],    "c": 0.82 }
  ],
  "objects": [
    { "id": "o1", "cls": "enemy", "box": [300, 500, 90, 140], "c": 0.88 }
  ],
  "scene": null
}
```

**Convenções**
- `box` = `[x, y, largura, altura]` em **pixels da janela** (não do monitor). Origem no canto superior esquerdo.
- `c` = confiança de 0 a 1 (2 casas).
- `t` = tipo: `button`, `text`, `icon`, `input`, `checkbox`, `menu`, `other`.
- `objects` só existe se o perfil tiver detector do jogo.
- `scene` só vem preenchido quando o agente pedir `describe_scene` (ou `with_scene=true`).
- IDs mudam a cada frame novo; o agente deve usar o ID do **último** `observe`.

### 6.2 Sem mudanças

```json
{ "frame": 129, "changed": false }
```

### 6.3 Só diferenças (`observe` com `mode="diff"`)

```json
{
  "frame": 130,
  "changed": true,
  "added":   [ { "id": "e9", "t": "text", "txt": "Game Over", "box": [700, 300, 500, 90], "c": 0.95 } ],
  "removed": ["e4"],
  "moved":   [ { "id": "e2", "box": [820, 500, 280, 70] } ]
}
```

### 6.4 Modo ultra-compacto (opcional, para economizar ainda mais)

Uma linha por elemento, sem chaves repetidas:

```
#128 1920x1080 changed
e1 button "Jogar" 820,400,280,70 .97
e2 button "Opções" 820,490,280,70 .96
o1 enemy 300,500,90,140 .88
```

Implemente os dois formatos (`format="json" | "compact"`) e meça qual gasta menos tokens com o seu modelo.

### 6.5 Limites de saída
- `max_elements` (padrão 60): ordena por área/confiança e corta o resto, avisando `"truncated": 23`.
- `min_conf` (padrão 0.5).
- `region` opcional para observar só uma parte da tela.

---

## 7. Ferramentas MCP (tools)

### Observação
| Tool | Parâmetros | Retorno |
|---|---|---|
| `list_windows` | — | Lista de janelas `{id, title, process, size}` |
| `set_target` | `window` (id ou parte do título) ou `monitor` | Define a janela alvo e o perfil |
| `observe` | `mode` (`full`\|`diff`), `region?`, `format?`, `with_scene?`, `max_elements?`, `min_conf?` | JSON da seção 6 |
| `find` | `text?`, `type?`, `cls?`, `fuzzy?` | Elementos que batem, do último frame |
| `wait_for` | `text` ou `cls`, `timeout_s`, `interval_ms` | Retorna quando aparecer (ou timeout) |
| `read_region` | `box` | Só OCR dentro da região (barato, bom para HUD/contadores) |

### Visão sob demanda
| Tool | Parâmetros | Retorno |
|---|---|---|
| `look` | `box`, `scale?` (padrão 0.5), `quality?` | **Imagem** recortada e reduzida (usar só quando o JSON não bastar) |
| `describe_scene` | `box?` | Descrição em texto (legendador) |
| `detect_open` | `prompts: ["chest","door"]` | Detecção open-vocabulary pontual (mais lenta) |

### Controle (fase posterior)
| Tool | Parâmetros | Retorno |
|---|---|---|
| `click` | `id` ou `x,y`, `button?`, `double?` | `ok` + `observe` em diff opcional |
| `move_mouse` | `x,y`, `duration_ms?` | `ok` |
| `press` | `keys` (ex.: `"w"`, `"ctrl+s"`), `hold_ms?` | `ok` |
| `type_text` | `text`, `delay_ms?` | `ok` |
| `scroll` | `dy`, `x?`, `y?` | `ok` |

> Regra de ouro: toda ação de controle pode devolver `observe(mode="diff")` automaticamente
> (`auto_observe=true`). Isso poupa uma chamada e mostra o efeito da ação.

### Perfis e diagnóstico
| Tool | Parâmetros | Retorno |
|---|---|---|
| `load_profile` | `name` | Carrega modelos/config do jogo |
| `status` | — | Modelos carregados, provedor (CUDA/DML), VRAM, FPS médio |
| `save_debug` | `path?` | Salva o último frame com as caixas desenhadas (para você depurar) |

---

## 8. Perfis por jogo

`config/profiles/exemplo-jogo.yaml`

```yaml
name: exemplo-jogo
window_match: "Meu Jogo"          # trecho do título ou nome do processo
capture:
  backend: dxcam
  fps_cap: 30
  region: null                     # ou [x, y, w, h] para recortar a área útil
models:
  ocr: default
  ui_detector: default
  game_detector: models/games/exemplo-jogo/best.onnx
  classes: [enemy, item, player, chest, healthbar]
thresholds:
  ui: 0.5
  game: 0.4
  ocr: 0.6
hud_regions:                       # leituras baratas e frequentes
  vida:    [40, 30, 200, 24]
  municao: [1700, 1000, 160, 40]
output:
  format: compact
  max_elements: 50
input:
  method: sendinput                # jogos geralmente precisam disso
```

---

## 9. Plano de implementação (fases)

### Fase 0 — Preparação (1 dia)
- [ ] Criar repositório e ambiente virtual.
- [ ] Instalar `onnxruntime-gpu` (ou `-directml`) e confirmar que `CUDAExecutionProvider`/`DmlExecutionProvider` aparece.
- [ ] Separar 20–30 prints de teste: 10 de menus, 10 de jogo, 5 de programas comuns.

### Fase 1 — MVP: captura + OCR (2–3 dias)
- [ ] Captura de janela com `dxcam`/`windows-capture`.
- [ ] OCR com RapidOCR → lista de `{txt, box, c}`.
- [ ] Tools: `list_windows`, `set_target`, `observe` (só OCR), `find`.
- [ ] Registrar no cliente MCP e testar com um programa simples.
- **Pronto quando:** o agente consegue abrir um menu e achar "Opções" sem receber imagem.

### Fase 2 — Detector de UI + fusão (3–4 dias)
- [ ] Integrar o detector de elementos de UI em ONNX.
- [ ] Implementar `fusion.py`: texto dentro de caixa vira um elemento; caixas sobrepostas (IoU) são mescladas.
- [ ] IDs curtos e ordenação estável (cima→baixo, esquerda→direita).
- [ ] Formato compacto + `max_elements`.
- **Pronto quando:** botões sem texto (ícones) aparecem como elementos clicáveis.

### Fase 3 — Economia de tokens (2–3 dias)
- [ ] `diff.py`: hash por blocos para detectar `changed:false` rápido.
- [ ] Modo `diff` com `added/removed/moved`.
- [ ] `read_region` e `hud_regions` para leituras baratas.
- [ ] Medir tokens por observação (compare com screenshot) e registrar os números no README.

### Fase 4 — Visão sob demanda (2 dias)
- [ ] `look(box, scale)` devolvendo imagem pequena.
- [ ] `describe_scene` com Florence-2 (carregamento preguiçoso).
- **Pronto quando:** o agente usa JSON na maior parte do tempo e `look` só em dúvida.

### Fase 5 — Controle (3 dias)
- [ ] `click`, `press`, `type_text`, `scroll`, `move_mouse`.
- [ ] Conversão de coordenadas janela → tela (considerar DPI e posição da janela).
- [ ] `auto_observe` com diff após cada ação.
- [ ] Teste em jogo: verificar se a entrada chega (se não, trocar para `SendInput` em baixo nível).

### Fase 6 — Detector do jogo (1–2 semanas, por jogo)
- [ ] Capturar 300–1000 prints do jogo (variar cenas, luz, resolução).
- [ ] Pré-anotar com open-vocabulary (`tools/annotate_with_owl.py`) e corrigir à mão (Label Studio / CVAT / Roboflow).
- [ ] Treinar YOLO pequeno (n ou s) e exportar para ONNX.
- [ ] Criar o perfil do jogo e avaliar (mAP, e teste real de uso).
- Se o jogo for seu (Unity/Unreal/Godot): gerar caixas direto pelo motor e treinar com milhares de prints automáticos.

### Fase 7 — Robustez e polimento
- [ ] Tratamento de erros (janela fechada, minimizada, mudou de resolução).
- [ ] Logs e `save_debug`.
- [ ] Testes automatizados com prints de `tests/fixtures`.
- [ ] README com instalação, perfis e exemplos de uso.

---

## 10. Esqueleto inicial do servidor (ponto de partida)

```python
# src/mcp_coruja/server.py
from mcp.server.fastmcp import FastMCP

from .state.frame_store import FrameStore
from .capture.window_utils import list_windows as _list_windows, find_window
from .capture.dxcam_capture import DxcamCapturer
from .vision.ocr import OcrEngine
from .vision.ui_detector import UiDetector
from .vision.fusion import fuse
from .vision.diff import frame_changed
from .output.formatter import to_json, to_compact

mcp = FastMCP("coruja")

store = FrameStore()
capturer = None          # criado em set_target
ocr = None               # carregamento preguiçoso
ui = None


def _models():
    global ocr, ui
    if ocr is None:
        ocr = OcrEngine()
    if ui is None:
        ui = UiDetector()
    return ocr, ui


@mcp.tool()
def list_windows() -> list[dict]:
    """Lista janelas abertas (id, título, processo, tamanho)."""
    return _list_windows()


@mcp.tool()
def set_target(window: str) -> dict:
    """Define a janela alvo pelo id ou por parte do título."""
    global capturer
    win = find_window(window)
    capturer = DxcamCapturer(win)
    store.reset(win)
    return {"ok": True, "win": win["title"], "size": win["size"]}


@mcp.tool()
def observe(mode: str = "full", format: str = "compact",
            max_elements: int = 60, min_conf: float = 0.5) -> str:
    """Captura a janela alvo e devolve elementos (texto + caixas)."""
    frame = capturer.grab()
    if not frame_changed(store.last_frame, frame):
        return '{"changed": false}'

    o, u = _models()
    texts = o.run(frame)
    boxes = u.run(frame)
    elements = fuse(texts, boxes, min_conf=min_conf)[:max_elements]

    result = store.update(frame, elements)   # atribui IDs e calcula diff
    payload = result["diff"] if mode == "diff" else result["full"]
    return to_compact(payload) if format == "compact" else to_json(payload)


if __name__ == "__main__":
    mcp.run()      # stdio
```

Registro no cliente MCP (exemplo genérico):

```json
{
  "mcpServers": {
    "coruja": {
      "command": "python",
      "args": ["-m", "mcp_coruja.server"],
      "cwd": "C:/caminho/para/mcp-coruja"
    }
  }
}
```

---

## 11. Como medir se está valendo a pena

Faça este teste antes e depois, com o mesmo roteiro (ex.: abrir menu → iniciar jogo → andar 10 s):

| Métrica | Screenshot | MCP Coruja |
|---|---|---|
| Tokens por observação | | |
| Tokens por roteiro completo | | |
| Latência por observação | | |
| Passos que falharam por não "enxergar" | | |

Se o último número for alto, aumente o uso de `look` ou melhore o detector do jogo.

---

## 12. Riscos e como lidar

| Risco | Mitigação |
|---|---|
| Tela cheia exclusiva não capturada | Usar modo janela sem borda; testar `windows-capture`/WGC |
| Jogo com anti-cheat bloqueia captura/entrada | Usar só em jogos offline/seus, ou seguir as regras do jogo. Não use em jogos online competitivos |
| Licença do modelo de UI (AGPL) | Ler a licença antes de distribuir; para uso pessoal é mais tranquilo |
| OCR errando em fontes estilizadas | Ajustar pré-processamento (contraste, escala) ou treinar OCR/usar `look` |
| Coordenadas erradas por DPI/escala | Normalizar tudo para pixels da janela e converter só na hora do clique |
| Muita VRAM com vários modelos | Carregamento preguiçoso e descarregar o legendador depois de usar |
| Detector do jogo generaliza mal | Mais variedade de prints, aumento de dados, retreino incremental |
| IDs mudam entre frames | Sempre usar IDs do último `observe`; oferecer `find` por texto como alternativa estável |

---

## 13. Prompt de sistema sugerido para o agente

```
Você tem acesso ao MCP "coruja", que enxerga a tela por texto estruturado.

Regras de uso:
1. Comece com set_target e depois observe.
2. Prefira observe(mode="diff") nas observações seguintes.
3. Use read_region para ler contadores/HUD em vez de observe completo.
4. Só use look(box) quando o JSON não for suficiente (ex.: precisa ver cor, forma, gráfico).
5. Use os IDs do último observe para clicar. Se o ID não existir mais, observe de novo.
6. Depois de cada ação, confira o resultado (auto_observe ou observe diff) antes de continuar.
7. Evite observações repetidas sem ação entre elas.
```

---

## 14. Próximos passos para você começar hoje

1. Criar o repositório com a estrutura da seção 5.
2. Instalar: `mcp`, `onnxruntime-gpu`, `rapidocr-onnxruntime`, `dxcam`, `opencv-python`, `numpy`.
3. Implementar a **Fase 1** (captura + OCR + `observe`) e registrar no seu cliente MCP.
4. Testar com 3 programas diferentes e ver onde falha a captura.
5. Só depois partir para o detector de UI e o resto.

Pesquisas úteis para quando chegar nas fases 2 e 6:
- OmniParser (detector de UI + legenda por elemento)
- RapidOCR / PaddleOCR ONNX
- YOLO-World e Grounding DINO para pré-anotação
- Exportação de YOLO para ONNX (Ultralytics `model.export(format="onnx")`)
- Roboflow Universe (datasets de jogos prontos)

---

*Versão 1 do plano. Ajuste prazos conforme seu ritmo; a ordem das fases é o que mais importa.*
