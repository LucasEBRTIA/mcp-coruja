"""Entrada de mouse/teclado via SendInput (baixo nivel, funciona em jogos).

Sem dependencia externa. Coordenadas sao de TELA (fisicas, o modulo server
declara DPI awareness); converter a partir da janela e trabalho do chamador.
"""

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
ULONG_PTR = ctypes.c_size_t

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
LEFTDOWN, LEFTUP = 0x0002, 0x0004
RIGHTDOWN, RIGHTUP = 0x0008, 0x0010
MIDDLEDOWN, MIDDLEUP = 0x0020, 0x0040
WHEEL = 0x0800
KEYUP, UNICODE = 0x0002, 0x0004

_BUTTONS = {"left": (LEFTDOWN, LEFTUP), "right": (RIGHTDOWN, RIGHTUP),
            "middle": (MIDDLEDOWN, MIDDLEUP)}
_VK = {"enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09,
       "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
       "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
       "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "win": 0x5B}
_VK.update({f"f{i}": 0x6F + i for i in range(1, 13)})
_MODS = {"ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10}


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _KeyInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _Union(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeyInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _Union)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def _send(*events):
    arr = (_Input * len(events))(*events)
    sent = user32.SendInput(len(events), arr, ctypes.sizeof(_Input))
    if sent != len(events):
        raise OSError(f"SendInput entregou {sent}/{len(events)} eventos (janela elevada ou entrada bloqueada?)")


def _mouse(flags, data=0):
    _send(_Input(INPUT_MOUSE, _Union(mi=_MouseInput(0, 0, data, flags, 0, 0))))


def _key(vk=0, scan=0, flags=0):
    _send(_Input(INPUT_KEYBOARD, _Union(ki=_KeyInput(vk, scan, flags, 0, 0))))


def parse_keys(combo):
    """'ctrl+shift+s' -> ([0x11, 0x10], 0x53). Levanta ValueError se nao souber a tecla."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("combo vazio")
    mods = [_MODS[p] for p in parts[:-1] if p in _MODS]
    if len(mods) != len(parts) - 1:
        raise ValueError(f"modificador desconhecido em: {combo}")
    name = parts[-1]
    if name in _VK:
        return mods, _VK[name]
    if len(name) == 1:
        vk = user32.VkKeyScanW(ord(name)) & 0xFF
        if vk != 0xFF:
            return mods, vk
    raise ValueError(f"tecla desconhecida: {name}")


def _place(x, y):
    """Posiciona o cursor e confere: jogo com ClipCursor prende o ponteiro e o clique cai errado."""
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.02)
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    if abs(p.x - int(x)) > 2 or abs(p.y - int(y)) > 2:
        raise OSError(f"cursor preso em {p.x},{p.y} em vez de {int(x)},{int(y)} "
                      "(jogo com ClipCursor?); clique nao seria confiavel")


def click_at(x, y, button="left", double=False):
    down, up = _BUTTONS[button]
    _place(x, y)
    for _ in range(2 if double else 1):
        _mouse(down)
        time.sleep(0.01)
        _mouse(up)
        if double:
            time.sleep(0.06)


def move_to(x, y):
    _place(x, y)


def press(combo, hold_ms=0):
    mods, vk = parse_keys(combo)
    for m in mods:
        _key(m)
    _key(vk)
    if hold_ms:
        time.sleep(hold_ms / 1000)
    _key(vk, flags=KEYUP)
    for m in reversed(mods):
        _key(m, flags=KEYUP)


def type_text(text, delay_ms=0):
    units = text.encode("utf-16-le")
    for i in range(0, len(units), 2):
        cu = int.from_bytes(units[i:i + 2], "little")
        _key(scan=cu, flags=UNICODE)
        _key(scan=cu, flags=UNICODE | KEYUP)
        if delay_ms:
            time.sleep(delay_ms / 1000)


def scroll(dy, x=None, y=None):
    if x is not None and y is not None:
        _place(x, y)
    _mouse(WHEEL, int(dy) * 120)


def tap_alt():
    """Toque em ALT: da ao processo o direito de chamar SetForegroundWindow (trava do Windows)."""
    _key(0x12)
    _key(0x12, flags=KEYUP)
