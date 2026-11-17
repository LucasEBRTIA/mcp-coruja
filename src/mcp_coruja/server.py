"""MCP Coruja - janela alvo -> texto compacto (OCR + detector) e controle de entrada.

Rodar: python -m mcp_coruja.server   (stdio)
"""

import ctypes
import json
import pathlib
import time
from ctypes import wintypes

import mss
import cv2
import numpy as np
import onnxruntime as ort
from mcp.server.mcpserver import Image, MCPServer
from rapidocr_onnxruntime import RapidOCR

from .detector import MODEL_PATH, IconDetector
from .diff import diff_elements
from .fusion import fuse
from . import control, game_profile
from .schema import quad_to_box, to_compact

# Janela em pixels reais (sem isso, box e clique saem escalados pelo DPI).
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [wintypes.HDC, ctypes.c_void_p]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
                            ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
user32.GetWindowDC.restype = wintypes.HDC
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]

mcp = MCPServer("coruja")

_target = {"hwnd": None, "title": ""}
_state = {"frame": 0, "img": None, "elements": [], "open": []}
_ocr = None
_icon = None
_captioner = None
_open_detector = None
_profile = None
_game = {"path": None, "det": None}


def _proc_name(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        return buf.value.rsplit("\\", 1)[-1]
    finally:
        kernel32.CloseHandle(h)


def _windows():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            w, h = r.right - r.left, r.bottom - r.top
            if w > 0 and h > 0:
                found.append({
                    "id": hwnd,
                    "title": buf.value,
                    "process": _proc_name(hwnd),
                    "size": [w, h],
                })
        return True

    user32.EnumWindows(visit, 0)
    found.sort(key=lambda w: w["title"].casefold())
    return found


def _grab(hwnd):
    if not user32.IsWindow(hwnd):
        raise ValueError("janela fechada; chame set_target")
    if user32.IsIconic(hwnd):
        raise ValueError("janela minimizada")
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        raise ValueError("janela sem area visivel")
    img = _printwindow(hwnd, w, h)
    if img.max() > 8:
        return img
    # shortcut: DirectX/tela cheia costuma voltar preto do PrintWindow; cai no mss
    # (sÃ³ correto se a janela estiver na frente). Upgrade: WGC/windows-capture.
    with mss.MSS() as sct:
        shot = sct.grab({"left": r.left, "top": r.top, "width": w, "height": h})
    return np.array(shot)[:, :, :3]  # BGRA -> BGR


class _BmiHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BmiHeader), ("bmiColors", wintypes.DWORD * 3)]


def _printwindow(hwnd, w, h):
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT
    bmi = _BitmapInfo()
    bmi.bmiHeader.biSize = ctypes.sizeof(_BmiHeader)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return np.ascontiguousarray(np.frombuffer(buf, np.uint8).reshape(h, w, 4)[:, :, :3])  # BGRA -> BGR


def _ocr_engine():
    global _ocr
    if _ocr is None:
        dml = "DmlExecutionProvider" in ort.get_available_providers()
        _ocr = RapidOCR(det_use_dml=dml, cls_use_dml=dml, rec_use_dml=dml)
    return _ocr


def _icon_engine():
    """None quando o modelo nao esta em models/ui_detector (segue so com OCR)."""
    global _icon
    if _icon is None:
        _icon = IconDetector() if MODEL_PATH.exists() else False
    return _icon or None


def _caption_engine():
    """Florence-2 e pesado (~660 MB de pesos): carrega na primeira chamada."""
    global _captioner
    if _captioner is None:
        from .describe import Captioner, available
        _captioner = Captioner() if available() else False
    return _captioner or None


def _open_engine():
    """OWLv2 (~615 MB): carrega so quando detect_open for usado."""
    global _open_detector
    if _open_detector is None:
        from .open_detector import OpenDetector, available
        _open_detector = OpenDetector() if available() else False
    return _open_detector or None


def _ocr_texts(img, min_conf):
    result, _ = _ocr_engine()(img)
    return [{"txt": txt.strip(), "box": quad_to_box(quad), "c": round(float(score), 2)}
            for quad, txt, score in result or [] if score >= min_conf and txt.strip()]


def _read(img, min_conf, with_icons=True):
    icons = _icon_engine() if with_icons else None
    # 0.3: no OmniParser os icones ficam na faixa 0.3-0.5; o min_conf do OCR (0.5) cortaria quase tudo.
    icons = icons.run(img, min_conf=0.3) if icons else []
    return fuse(_ocr_texts(img, min_conf), icons)


def _shift(elements, dx, dy):
    for e in elements:
        e["box"] = [e["box"][0] + dx, e["box"][1] + dy, e["box"][2], e["box"][3]]
    return elements


def _crop(img, box):
    """box=[x,y,w,h] ou None (janela toda). Erro claro quando cai fora."""
    x, y, w, h = box or (0, 0, img.shape[1], img.shape[0])
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x >= img.shape[1] or y >= img.shape[0]:
        raise ValueError(f"box {[x, y, w, h]} fora da janela {img.shape[1]}x{img.shape[0]}")
    return img[y:y + h, x:x + w], x, y


def _region(spec):
    """Regiao nomeada do perfil ('hp', 'minimap') ou box cru."""
    if isinstance(spec, str):
        if not _profile:
            raise ValueError(f"sem perfil ativo para a regiao '{spec}'; use set_profile antes")
        if spec not in _profile["hud"]:
            raise ValueError(f"regiao '{spec}' nao existe no perfil {_profile['name']}")
        return _profile["hud"][spec]
    return spec


@mcp.tool()
def list_windows() -> list[dict]:
    """Lista janelas visiveis (id, titulo, processo, tamanho)."""
    return _windows()


@mcp.tool()
def set_target(window: str) -> dict:
    """Define a janela alvo pelo id ou por um trecho do titulo."""
    wins = _windows()
    if window.isdigit():
        hit = next((w for w in wins if w["id"] == int(window)), None)
    else:
        needle = window.casefold()
        hit = next((w for w in wins if needle in w["title"].casefold()), None)
    if not hit:
        return {"ok": False, "error": f"janela nao encontrada: {window}"}
    _target.update(hwnd=hit["id"], title=hit["title"])
    _state.update(frame=0, img=None, elements=[], open=[])
    return {"ok": True, "win": hit["title"], "size": hit["size"]}


@mcp.tool()
def list_profiles() -> list[dict]:
    """Perfis em profiles/<nome>/profile.json: janela, regioes de HUD, prompts e detector."""
    out = []
    for name in game_profile.names():
        try:
            p = game_profile.load(name)
        except ValueError as e:
            out.append({"name": name, "error": str(e)})
            continue
        out.append({"name": name, "window": p.get("window", ""), "hud": list(p["hud"]),
                    "prompts": p.get("prompts", []), "detector": bool(p.get("detector"))})
    return out


@mcp.tool()
def set_profile(name: str) -> dict:
    """Ativa um perfil: aponta o alvo para a janela dele e habilita HUD nomeado e detector."""
    global _profile
    try:
        p = game_profile.load(name)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    win = p.get("window", "")
    res = set_target(win) if win else {"ok": False, "error": "perfil sem 'window'"}
    _profile = p
    out = {"ok": True, "profile": name, "hud": list(p["hud"]), "detector": bool(p.get("detector")),
           "win": res.get("win"), "size": res.get("size")}
    if not res.get("ok"):
        out["error"] = f"janela do perfil nao encontrada ({win}); abra o jogo e chame set_profile de novo"
    return out


@mcp.tool()
def observe(mode: str = "full", format: str = "compact", max_elements: int = 60,
            min_conf: float = 0.5, region: list[int] | str | None = None) -> str:
    """Captura a janela alvo e devolve os elementos vistos, com caixas e IDs.

    mode="diff" devolve so o que mudou desde o observe anterior (added/removed/moved).
    region=[x,y,w,h] ou o nome de uma regiao do perfil (ex.: "minimap").
    Objeto sem texto (bau, inimigo, minimapa): detect_open. Duvida visual (cor, forma): look.
    """
    if _target["hwnd"] is None:
        return json.dumps({"error": "chame set_target antes"})
    t0 = time.perf_counter()
    try:
        img = _grab(_target["hwnd"])
    except ValueError as e:
        return json.dumps({"error": str(e)})

    _state["frame"] += 1
    if _state["img"] is not None and np.array_equal(img, _state["img"]):
        return json.dumps({"frame": _state["frame"], "changed": False})
    _state["img"] = img

    try:
        crop, x, y = _crop(img, _region(region))
    except ValueError as e:
        return json.dumps({"error": str(e)})
    elements = _shift(_read(crop, min_conf), x, y)
    elements = [{"id": f"e{i}", **e} for i, e in enumerate(elements, 1)]
    prev, _state["elements"] = _state["elements"], elements  # find() ve o frame inteiro

    ms = int((time.perf_counter() - t0) * 1000)
    if mode == "diff" and prev:
        payload = {"frame": _state["frame"], "ms": ms,
                   **diff_elements(prev, elements)}
        payload["added"] = payload["added"][:max_elements]
    else:
        payload = {
            "frame": _state["frame"],
            "win": _target["title"],
            "size": [img.shape[1], img.shape[0]],
            "changed": True,
            "ms": ms,
            "elements": elements[:max_elements],
        }
        if len(elements) > max_elements:
            payload["truncated"] = len(elements) - max_elements
    return to_compact(payload) if format == "compact" else json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def read_region(box: list[int] | str, min_conf: float = 0.6, format: str = "compact") -> str:
    """OCR so dentro de box=[x,y,w,h] ou de uma regiao nomeada do perfil (ex.: "mission").

    Barato: bom para HUD/contadores num loop.
    """
    if _target["hwnd"] is None:
        return json.dumps({"error": "chame set_target antes"})
    t0 = time.perf_counter()
    try:
        img = _grab(_target["hwnd"])
    except ValueError as e:
        return json.dumps({"error": str(e)})

    try:
        crop, x, y = _crop(img, _region(box))
    except ValueError as e:
        return json.dumps({"error": str(e)})
    elements = _shift(_read(crop, min_conf, with_icons=False), x, y)
    elements = [{"id": f"e{i}", **e} for i, e in enumerate(elements, 1)]
    payload = {"frame": _state["frame"], "size": [crop.shape[1], crop.shape[0]], "changed": True,
               "ms": int((time.perf_counter() - t0) * 1000), "elements": elements}
    return to_compact(payload) if format == "compact" else json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def look(box: list[int] | None = None, scale: float = 0.5, quality: int = 80) -> Image | str:
    """Recorte da janela alvo como imagem pequena (JPEG). Use so quando o texto nao bastar."""
    if _target["hwnd"] is None:
        return json.dumps({"error": "chame set_target antes"})
    try:
        img = _grab(_target["hwnd"])
    except ValueError as e:
        return json.dumps({"error": str(e)})
    try:
        crop, _, _ = _crop(img, box)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    if scale != 1:
        crop = cv2.resize(crop, (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))),
                          interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:  # pragma: no cover
        return json.dumps({"error": "falha ao codificar JPEG"})
    return Image(data=buf.tobytes(), format="jpeg")


@mcp.tool()
def describe_scene(box: list[int] | None = None) -> str:
    """Descreve o que aparece na janela alvo (ou em box) com Florence-2. Lento: so sob demanda."""
    if _target["hwnd"] is None:
        return json.dumps({"error": "chame set_target antes"})
    t0 = time.perf_counter()
    try:
        img = _grab(_target["hwnd"])
    except ValueError as e:
        return json.dumps({"error": str(e)})
    engine = _caption_engine()
    if engine is None:
        return json.dumps({"error": "modelo ausente: rode python tools/fetch_models.py captioner"})
    try:
        crop, _, _ = _crop(img, box)
        scene = engine.caption(crop)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:  # sessao ONNX quebrada nao deve derrubar o servidor
        return json.dumps({"error": f"falha no legendador: {type(e).__name__}: {e}"})
    return json.dumps({"scene": scene, "ms": int((time.perf_counter() - t0) * 1000)}, ensure_ascii=False)


@mcp.tool()
def detect_open(prompts: list[str] | None = None, box: list[int] | None = None, min_conf: float = 0.1,
                max_boxes: int = 12) -> str:
    """Acha objeto SEM texto (bau, porta, inimigo, minimapa, item) pelo nome. Nao precisa treinar.

    Como usar bem:
    - prompts em ingles, frases curtas: ["wooden chest"], ["enemy", "health bar"]. Nada de
      pergunta; o texto so rotula caixas que o ViT ja propos. Sem prompts, usa os do perfil.
    - nao use aqui o que observe/read_region ja resolvem (texto, botoes): esses sao ~10x mais rapidos.
    - lento (~1.3 s): uma chamada por duvida, nao em loop de frame.
    - 0.1 (padrao) traz candidatos ordenados por score; aumente para 0.3 se quiser so o obvio.
      Icone de HUD parecido (bonequinho, mapa) pode pontuar acima do objeto real: confira a caixa.
    - box=[x,y,w,h] limita a busca (ex.: so o canto do HUD) e reduz falso positivo.
    - devolve uma linha por caixa: id (oN), tipo object, o prompt, x,y,w,h e confianca; os IDs
      valem direto no click. Sem linhas = nada encontrado. RefaÃ§a se a tela mudou.
    """
    if _target["hwnd"] is None:
        return json.dumps({"error": "chame set_target antes"})
    prompts = [p.strip() for p in (prompts or (_profile or {}).get("prompts") or []) if p and p.strip()]
    if not prompts:
        return json.dumps({"error": "informe prompts, ex.: [\"enemy\"], ou defina 'prompts' no perfil"})
    engine = _open_engine()
    if engine is None:
        return json.dumps({"error": "modelo ausente: rode python tools/fetch_models.py open"})
    try:
        img = _grab(_target["hwnd"])
    except ValueError as e:
        return json.dumps({"error": str(e)})
    try:
        crop, x, y = _crop(img, box)
        found = engine.detect(crop, prompts, min_conf)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:  # sessao ONNX quebrada nao deve derrubar o servidor
        return json.dumps({"error": f"falha no detector: {type(e).__name__}: {e}"})
    found = _shift(found, x, y)[:max_boxes]
    found = [{"id": f"o{i}", **e} for i, e in enumerate(found, 1)]
    _state["open"] = found
    return to_compact({"frame": _state["frame"], "size": [img.shape[1], img.shape[0]], "elements": found})


@mcp.tool()
def detect_game(min_conf: float = 0.0, max_boxes: int = 30) -> str:
    """Roda o detector treinado do perfil atual (classes do perfil). Sem modelo pronto = erro explicado.

    Mesmo formato do detect_open: uma linha por caixa (id oN, tipo object, classe, x,y,w,h, conf);
    os IDs valem direto no click.
    """
    if _target["hwnd"] is None:
        hint = (f"janela do perfil {_profile['name']} nao esta aberta; abra e rode set_profile"
                if _profile else "chame set_target/set_profile antes")
        return json.dumps({"error": hint})
    if not _profile or not _profile.get("detector"):
        return json.dumps({"error": "sem detector treinado: coloque profiles/<jogo>/detector.onnx e "
                                    "'detector' + 'classes' no profile.json"})
    path = _profile["detector_path"]
    if not path.exists():
        return json.dumps({"error": f"arquivo do detector nao existe: {path}"})
    global _game
    if _game["path"] != str(path):
        try:
            from .game_detector import GameDetector
            _game = {"path": str(path), "det": GameDetector(path, _profile["classes"])}
        except Exception as e:
            return json.dumps({"error": f"falha ao carregar detector: {type(e).__name__}: {e}"})
    try:
        img = _grab(_target["hwnd"])
    except ValueError as e:
        return json.dumps({"error": str(e)})
    conf = min_conf or float(_profile.get("conf", 0.3))
    try:
        found = _game["det"].run(img, conf)
    except Exception as e:  # sessao ONNX quebrada nao deve derrubar o servidor
        return json.dumps({"error": f"falha no detector: {type(e).__name__}: {e}"})
    found = [{"id": f"o{i}", "t": "object", **e} for i, e in enumerate(found[:max_boxes], 1)]
    _state["open"] = found
    return to_compact({"frame": _state["frame"], "size": [img.shape[1], img.shape[0]], "elements": found})


@mcp.tool()
def capture_frames(count: int = 50, interval_ms: int = 200) -> str:
    """Salva N frames em profiles/<perfil>/frames (dataset para treinar o detector depois).

    Use intervalo >= 150 ms e varie a cena entre as capturas.
    """
    if _target["hwnd"] is None:
        return json.dumps({"error": "chame set_target antes"})
    if not 1 <= count <= 1000:
        return json.dumps({"error": "count deve ficar entre 1 e 1000"})
    out = (_profile["dir"] / "frames") if _profile else pathlib.Path(__file__).resolve().parents[2] / "debug" / "frames"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    saved = 0
    for i in range(count):
        try:
            img = _grab(_target["hwnd"])
        except ValueError as e:
            return json.dumps({"error": str(e), "saved": saved})
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        (out / f"{stamp}-{i:04d}.jpg").write_bytes(buf.tobytes())
        saved += 1
        if i + 1 < count:
            time.sleep(interval_ms / 1000)
    return json.dumps({"saved": saved, "folder": str(out)})


@mcp.tool()
def find(text: str) -> list[dict]:
    """Busca (sem diferenciar maiusculas) no ultimo observe. IDs estaveis para clicar."""
    needle = text.casefold()
    return [e for e in _state["elements"] if needle in e["txt"].casefold()]


def _rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def _frame_host(hwnd):
    """UWP: quem aceita foco e a ApplicationFrameWindow; o CoreWindow recusa SetForegroundWindow."""
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if cls.value != "Windows.UI.Core.CoreWindow":
        return None
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, 256)
    found = []

    def visit(h, _):
        c = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, c, 64)
        if c.value == "ApplicationFrameWindow":
            t = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, t, 256)
            if t.value == title.value:
                found.append(h)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(visit), 0)
    return found[0] if found else None


def _ensure_foreground():
    """Erro (str) se a janela alvo nao estiver na frente: clicar as cegas acerta outro app."""
    hwnd = _target["hwnd"]
    if hwnd is None:
        return "chame set_target antes"
    # Captura e coordenadas ficam no hwnd alvo; so o foco vai para o frame do UWP.
    focus = _frame_host(hwnd) or hwnd
    if user32.GetForegroundWindow() == focus:
        return None
    root = user32.GetAncestor(hwnd, 2)  # GA_ROOT
    candidates = [focus] + ([root] if root and root not in (hwnd, focus) else [])
    user32.ShowWindow(focus, 9)  # SW_RESTORE
    for h in candidates:
        user32.SwitchToThisWindow(h, True)  # funciona onde SetForegroundWindow e recusado
        if user32.GetForegroundWindow() == h:
            return None
        user32.SetForegroundWindow(h)
        if user32.GetForegroundWindow() == h:
            return None
        control.tap_alt()  # sem isso o Windows ignora SetForegroundWindow de processo em segundo plano
        user32.SetForegroundWindow(h)
        if user32.GetForegroundWindow() == h:
            return None
        fg = user32.GetForegroundWindow()
        tid_fg = user32.GetWindowThreadProcessId(fg, None)
        tid_self = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(tid_self, tid_fg, True)
        user32.SetForegroundWindow(h)
        user32.AttachThreadInput(tid_self, tid_fg, False)
        if user32.GetForegroundWindow() == h:
            return None
    return "nao consegui trazer a janela alvo para a frente; nenhuma entrada foi enviada"


def _after(auto_observe, wait=0.15):
    if not auto_observe:
        return json.dumps({"ok": True})
    time.sleep(wait)
    return observe(mode="diff")


def _screen_xy(x, y):
    r = _rect(_target["hwnd"])
    return r.left + x, r.top + y


def _element(target):
    return next((e for src in (_state["elements"], _state["open"]) for e in src if e["id"] == target), None)


ACTION_KEYS = ("click", "press", "type", "scroll", "wait")


def _check_action(a):
    """Valida so a forma (nada de OS): erro aqui aborta o lote inteiro antes de agir."""
    if not isinstance(a, dict) or len(a) != 1 or next(iter(a)) not in ACTION_KEYS:
        raise ValueError(f"acao invalida {a!r}: use uma chave de {list(ACTION_KEYS)}")
    (key, val), = a.items()
    ok = {"click": lambda v: isinstance(v, str) or (isinstance(v, (list, tuple)) and len(v) == 2),
          "press": lambda v: isinstance(v, str) and bool(v.strip()),
          "type": lambda v: isinstance(v, str),
          "scroll": lambda v: isinstance(v, int) and not isinstance(v, bool),
          "wait": lambda v: isinstance(v, (int, float)) and 0 <= v <= 10000}[key]
    if not ok(val):
        raise ValueError(f"valor invalido em {a!r}")


def _run_action(a):
    (key, val), = a.items()
    if key == "click":
        if isinstance(val, str):
            el = _element(val)
            if not el:
                raise ValueError(f"{val} nao existe no ultimo observe/detect_open")
            bx, by, bw, bh = el["box"]
            x, y = bx + bw // 2, by + bh // 2
        else:
            x, y = int(val[0]), int(val[1])
        control.click_at(*_screen_xy(x, y))
    elif key == "press":
        control.press(val)
    elif key == "type":
        control.type_text(val)
    elif key == "scroll":
        control.scroll(int(val))
    else:
        time.sleep(float(val) / 1000)


@mcp.tool()
def click(target: str = "", x: int = -1, y: int = -1, button: str = "left",
          double: bool = False, auto_observe: bool = True) -> str:
    """Clica no elemento `target` (id do ultimo observe) ou em x,y da janela (pixels da janela)."""
    err = _ensure_foreground()
    if err:
        return json.dumps({"error": err})
    if target:
        el = _element(target)
        if not el:
            return json.dumps({"error": f"{target} nao existe no ultimo observe/detect_open; rode um deles"})
        bx, by, bw, bh = el["box"]
        x, y = bx + bw // 2, by + bh // 2
    if x < 0 or y < 0:
        return json.dumps({"error": "informe target ou x,y"})
    try:
        control.click_at(*_screen_xy(x, y), button=button, double=double)
    except OSError as e:
        return json.dumps({"error": str(e)})
    return _after(auto_observe)


@mcp.tool()
def press(keys: str, hold_ms: int = 0, auto_observe: bool = True) -> str:
    """Aperta teclas na janela alvo: 'w', 'ctrl+s', 'shift+up', 'enter'."""
    err = _ensure_foreground()
    if err:
        return json.dumps({"error": err})
    try:
        control.press(keys, hold_ms)
    except (OSError, ValueError) as e:
        return json.dumps({"error": str(e)})
    return _after(auto_observe)


@mcp.tool()
def type_text(text: str, delay_ms: int = 10, auto_observe: bool = True) -> str:
    """Digita texto (unicode) na janela alvo. delay_ms=0 perde/corrompe caracteres em apps lentos."""
    err = _ensure_foreground()
    if err:
        return json.dumps({"error": err})
    try:
        control.type_text(text, delay_ms)
    except OSError as e:
        return json.dumps({"error": str(e)})
    return _after(auto_observe)


@mcp.tool()
def do(actions: list[dict], auto_observe: bool = True) -> str:
    """Executa varias acoes em sequencia numa unica chamada (um clique, uma digitacao, um enter...).

    Use quando os passos NAO precisam de inspecao entre si: clicar na busca, digitar e dar enter;
    abrir menu e escolher item. Economiza um passo de modelo por acao.
    Cada acao e um dict com UMA chave:
      {"click": "e7"}        id do ultimo observe/detect_open
      {"click": [820, 300]}  coordenada da janela
      {"type": "texto"}      texto unicode
      {"press": "enter"}     tecla ou combo: ctrl+s, shift+up
      {"scroll": -3}         roda do mouse (positivo = para cima)
      {"wait": 800}          pausa em ms (use depois de enter para a pagina carregar)
    Para no primeiro erro e diz quantas rodaram. No fim devolve o diff (auto_observe),
    truncado em 15 elementos quando nao existe frame anterior. Precisa ver no meio? Use solto.
    """
    if _target["hwnd"] is None:
        return json.dumps({"error": "chame set_target antes"})
    if not actions:
        return json.dumps({"error": "informe ao menos uma acao"})
    try:
        for a in actions:
            _check_action(a)
    except ValueError as e:
        return json.dumps({"error": f"{e}; nada foi executado"})
    err = _ensure_foreground()
    if err:
        return json.dumps({"error": err})
    try:
        for i, a in enumerate(actions):
            if i:
                time.sleep(0.05)  # rajada de SendInput embaralha teclas (medido: 0 ms corrompe)
            _run_action(a)
    except (OSError, ValueError) as e:
        return json.dumps({"error": str(e), "done": i, "of": len(actions)})
    if not auto_observe:
        return json.dumps({"ok": True, "done": len(actions)})
    time.sleep(0.3)
    return observe(mode="diff", max_elements=15)


@mcp.tool()
def scroll(dy: int, x: int = -1, y: int = -1, auto_observe: bool = True) -> str:
    """Roda a roda do mouse dy entalhes (positivo = para cima) em x,y da janela ou onde o cursor estiver."""
    err = _ensure_foreground()
    if err:
        return json.dumps({"error": err})
    sx, sy = _screen_xy(x, y) if x >= 0 and y >= 0 else (None, None)
    try:
        control.scroll(dy, sx, sy)
    except OSError as e:
        return json.dumps({"error": str(e)})
    return _after(auto_observe)


@mcp.tool()
def move_mouse(x: int, y: int) -> dict:
    """Move o cursor para x,y da janela alvo (sem clique)."""
    if _target["hwnd"] is None:
        return {"ok": False, "error": "chame set_target antes"}
    try:
        control.move_to(*_screen_xy(x, y))
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


@mcp.tool()
def save_debug(folder: str = "") -> str:
    """Salva o frame atual em PNG e os elementos vistos em JSON, para inspecao offline."""
    if _target["hwnd"] is None:
        return json.dumps({"error": "chame set_target antes"})
    try:
        img = _grab(_target["hwnd"])
    except ValueError as e:
        return json.dumps({"error": str(e)})
    out = pathlib.Path(folder) if folder else pathlib.Path(__file__).resolve().parents[2] / "debug"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ok, buf = cv2.imencode(".png", img)
    (out / f"{stamp}.png").write_bytes(buf.tobytes())  # write_bytes: cv2.imwrite nao aceita acento
    (out / f"{stamp}.json").write_text(
        json.dumps({"win": _target["title"], "elements": _state["elements"]}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return json.dumps({"png": str(out / f"{stamp}.png"), "json": str(out / f"{stamp}.json")})


if __name__ == "__main__":
    mcp.run()  # stdio
