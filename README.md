# MCP Coruja

Servidor MCP local (Windows) que **transforma uma janela em texto compacto**: captura o frame,
lê o texto com OCR, acha os elementos clicáveis com um detector de UI e devolve isso em linhas
curtas, com coordenadas e IDs. O agente gasta alguns milhares de caracteres em vez de mandar
screenshot, e ainda pode clicar/digitar na janela.

Tudo roda na máquina: ONNX Runtime com DirectML (GPU) ou CPU. Nenhuma chamada de rede em runtime.

Números medidos contra UI Automation e VLM puro (screenshots): **[BENCHMARK.md](BENCHMARK.md)**.

## Requisitos

- Windows 10/11 e Python 3.10+
- ~1,7 GB de modelos em `models/` (não versionados)
- GPU com DirectML é opcional; sem ela cai em CPU e fica ~5x mais lento

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -e .
```

**A ordem importa**: `rapidocr-onnxruntime` arrasta o `onnxruntime` comum, que desliga o
DirectML. Se o `pip list` mostrar `onnxruntime` (e não só `onnxruntime-directml`), o OCR sobe
de ~0,5 s para ~8 s por janela. Correção:

```powershell
.\.venv\Scripts\python -m pip uninstall -y onnxruntime
.\.venv\Scripts\python -m pip install onnxruntime-directml
```

Versões exatas do ambiente testado: `requirements.lock.txt`.

### Modelos

Baixe tudo de uma vez (uma vez só):

```powershell
.\.venv\Scripts\python tools\fetch_models.py          # ou: ui | captioner | open
```

| Pasta | O que é | Quem usa |
|---|---|---|
| `models/ui_detector/icon_detect.onnx` | detector de ícone/elemento de UI (YOLOv8n, 12 MB) | `observe` |
| `models/captioner/` | Florence-2-base-ft (legendador, 1,1 GB) | `describe_scene` |
| `models/open_detector/` | OWLv2 zero-shot (detecção por nome, 620 MB) | `detect_open` |

Sem um modelo, só a ferramenta correspondente responde erro; o resto do servidor segue
funcionando (a UI roda só com OCR se faltar o detector).

### Registrar no cliente MCP

`opencode.example.json` neste repositório tem o modelo de registro. Copie para `opencode.json` e
troque `<CAMINHO_DO_PROJETO>` pelo caminho desta pasta (o arquivo real fica fora do Git porque tem
caminho absoluto). Para outro cliente, o comando é:

```
"C:\...\mcp-coruja\.venv\Scripts\python.exe" -m mcp_coruja.server
```

O servidor fala stdio; não escreva nada em stdout além do protocolo.

## Ferramentas

| Ferramenta | Para quê | Custo |
|---|---|---|
| `list_windows` | janelas visíveis (id, título, processo, tamanho) | ~5 ms |
| `set_target(window)` | escolhe a janela por id ou trecho do título | ~5 ms |
| `list_profiles` | perfis em `profiles/` (janela, HUD, prompts, se tem detector) | ~5 ms |
| `set_profile(name)` | ativa o perfil: janela + HUD nomeado + detector treinado | ~5 ms |
| `observe(mode, format, max_elements, min_conf, region)` | OCR + detector: texto, botões, ícones com caixas e IDs | 250–700 ms |
| `observe(mode="diff")` | só o que mudou desde o observe anterior (`+` novo, `-` removido, `~` moveu) | igual, saída ~2% |
| `read_region(box)` | OCR de um recorte (HUD, contador) | ~200 ms |
| `look(box?, scale?, quality?)` | devolve **imagem** JPEG reduzida | ~30 ms |
| `describe_scene(box?)` | descrição em texto (Florence-2) | 0,5–2 s |
| `detect_open(prompts, box?, min_conf?)` | acha objeto **sem texto** pelo nome (OWLv2 zero-shot) | ~1,3 s |
| `detect_game(min_conf?)` | roda o **detector treinado** do perfil (se houver) | ~100 ms |
| `capture_frames(count, interval_ms)` | salva frames do jogo para montar o dataset | ~40 ms/frame |
| `find(text)` | busca no último `observe`; devolve IDs clicáveis | instantâneo |
| `click(target?, x, y, button, double, auto_observe)` | clique por ID (`eN`/`oN`) ou coordenada da janela | 45 ms (+ observe) |
| `do(actions, auto_observe)` | várias ações numa chamada (`click`/`press`/`type`/`scroll`/`wait`) e um diff no fim | ~50 ms/ação |
| `press(keys, hold_ms, auto_observe)` | teclas e combos (`ctrl+s`, `shift+up`, `enter`) | ~1 ms |
| `type_text(text, delay_ms, auto_observe)` | digita texto unicode | ~15 ms/caractere |
| `scroll(dy, x?, y?)` | roda do mouse (positivo = para cima) | ~50 ms |
| `move_mouse(x, y)` | move o cursor sem clicar | ~25 ms |
| `save_debug(folder?)` | salva frame PNG + elementos JSON (inspeção/fixtures) | ~40 ms |

Coordenadas são sempre **pixels da janela** (não da tela); a conversão para tela acontece só
dentro do clique.

## Fluxo recomendado para o agente

1. `list_windows` → `set_target("Nome do jogo")`, ou `list_profiles` → `set_profile("jogo")` se ele existir.
2. `observe()` uma vez para ter o mapa da tela.
3. `read_region("minimap")` (nome do perfil) ou `read_region([x,y,w,h])` para números de HUD em loop;
   `observe(mode="diff")` depois de cada ação.
4. Clique pelo ID do último observe: `click(target="e7")`. Para passos que não precisam de inspeção
   entre si, mande tudo de uma vez: `do([{"click":"e7"},{"type":"Inteligência Artificial"},{"press":"enter"},{"wait":800}])`.
5. Só quando o texto não bastar: `look(box)` (forma/cor), `detect_open(["chest"])` (objeto sem texto)
   ou `detect_game()` (detector treinado do perfil).
6. IDs valem para o frame em que nasceram. Se a tela mudou, observe de novo.

Exemplo de saída do `observe`:

```
#12 1936x1048
e1 text "Fale com Bonnie" 116,170,180,27 0.98
e2 button "Início" 615,66,69,33 0.46
e3 icon "" 1669,54,67,26 0.41
```

E do `detect_open(["character"], box=[0,300,1500,810])`:

```
#12 1936x1119
o1 object "character" 841,331,267,578 0.31
```

## Perfil de jogo e detector treinado

O perfil é opcional: sem ele, tudo funciona com OWLv2 zero-shot. O perfil serve para (a) agrupar
janela + regiões de HUD com nome e (b) plugar **um detector treinado** se você decidir focar em
um jogo.

Layout: `profiles/<nome>/profile.json` (mais `detector.onnx`, `frames/` e `dataset/` quando existirem).
A pasta `profiles/` é local e fica fora do Git — crie a sua.

```json
{
  "window": "ZenlessZoneZero",
  "hud": {
    "minimap": [1500, 180, 440, 300],
    "mission": [0, 140, 360, 140]
  },
  "prompts": ["character", "enemy", "wooden chest"],
  "conf": 0.3
}
```

Com o perfil ativo, `read_region("minimap")` e `observe(region="mission")` usam as caixas por
nome, e `detect_open()` sem argumento usa os `prompts` do perfil. As caixas de HUD são em pixels
da janela: se mudar a resolução, ajuste os números.

### Se um dia for treinar (não precisa hoje)

1. Ative o perfil e capture o dataset pelo próprio agente: `set_profile("jogo")` e
   `capture_frames(count=300, interval_ms=200)` — varia a cena entre as capturas.
   Os frames vão para `profiles/<jogo>/frames/`.
2. Pré-anote com o OWLv2 usando os prompts do perfil:
   `python tools/annotate.py jogo --conf 0.2`
   Sai `profiles/<jogo>/dataset/{images,labels}` no formato YOLO + `classes.txt`
   (índice = ordem dos prompts). Corrija à mão no CVAT / Label Studio / Roboflow.
3. Treine um YOLO pequeno (`yolov8n`) e exporte ONNX (opset 12). Copie o `best.onnx` para
   `profiles/<jogo>/detector.onnx`.
4. No `profile.json`, adicione `"detector": "detector.onnx"` e `"classes": [...]` **na mesma
   ordem do treino**. Reinicie o servidor MCP (ou chame `set_profile` de novo) e use
   `detect_game()` — devolve `oN object "classe" x,y,w,h conf`, clicável como o resto.

Sem os passos 2–4, nada quebra: `detect_game` responde explicando o que falta.

## Limites conhecidos

- **PrintWindow volta preto** em jogo DirectX/fullscreen; nesse caso a captura cai para `mss`,
  que exige a janela **na frente** (senão captura o que estiver por cima).
- **Jogos com anti-cheat** (ex.: Zenless Zone Zero) ignoram `SendInput`, travam o foco e prendem
  o cursor num clip 1×1. Aí só visão funciona; controle exigiria driver/hardware. O `click`
  detecta o cursor preso e devolve erro em vez de clicar no lugar errado.
- OCR erra fonte estilizada e inventa `品`/`凹` a partir de ícones; `read_region` com recorte
  maior e `min_conf` mais baixo ajuda.
- `describe_scene` em captura de UI costuma dizer "tela com ícones" — o Florence-2-base é bom em
  foto, genérico em interface.
- `detect_open` confunde ícone de HUD com o objeto; passe `box` para a área de jogo e use prompt
  específico ("anime girl" > "character").
- As caixas de HUD do perfil são pixels fixos: resolução diferente = ajustar à mão.
- Primeira chamada de cada modelo paga a carga: OCR ~0,5 s, Florence ~2 s, OWLv2 ~1,5 s.

## Testes

```powershell
.\.venv\Scripts\python tests\test_schema.py     # formato compacto/JSON
.\.venv\Scripts\python tests\test_fusion.py     # texto + caixa -> botão/texto
.\.venv\Scripts\python tests\test_diff.py       # diff entre frames
.\.venv\Scripts\python tests\test_keys.py       # parser de combos
.\.venv\Scripts\python tests\test_actions.py    # validação das ações em lote
.\.venv\Scripts\python tests\test_observe.py    # OCR + detector na fixture
.\.venv\Scripts\python tests\test_describe.py   # Florence (pula sem pesos)
.\.venv\Scripts\python tests\test_open.py       # OWLv2 (pula sem pesos)
.\.venv\Scripts\python tests\test_game.py       # decoder do detector treinado
.\.venv\Scripts\python tests\test_profile.py    # leitura/validação de perfil
```

## Estrutura

```
src/mcp_coruja/
  server.py        ferramentas MCP, captura (PrintWindow/mss), DPI, foco
  control.py       SendInput: clique, teclas, texto, roda; guarda de cursor
  detector.py      YOLOv8 ONNX de elementos de UI
  fusion.py        junta texto do OCR com caixas do detector
  diff.py          comparação entre frames
  schema.py        formato compacto e JSON
  describe.py      Florence-2 (legendador)
  open_detector.py OWLv2 (detecção por nome)
  game_detector.py detector treinado do jogo (YOLOv8 N classes)
  game_profile.py  leitura/validação de profiles/<jogo>/profile.json
profiles/<jogo>/   profile.json, detector.onnx, frames/, dataset/
tools/             downloads, pré-anotação (annotate.py) e medição de custo
tests/             auto-checks (assert, sem pytest)
```

## Licenças dos modelos

Florence-2: MIT. OWLv2: Apache-2.0. Detector de UI (OmniParser): **AGPL-3.0** (derivado do
YOLOv8) — ok para uso pessoal; revise antes de distribuir.
