# -*- coding: utf-8 -*-
"""Chamadas ao Windows: teclado (SendInput), pasta Documentos, iniciar com o
Windows e abrir pasta. Fora do Windows tudo e simulado (so imprime)."""
import os
import sys
import time

IS_WINDOWS = sys.platform.startswith("win")


def documents_dir():
    if IS_WINDOWS:
        try:
            import ctypes
            import uuid
            fid = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")  # Documentos
            buf = ctypes.c_wchar_p()
            guid = (ctypes.c_byte * 16).from_buffer_copy(fid.bytes_le)
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(buf)) == 0:
                path = buf.value
                ctypes.windll.ole32.CoTaskMemFree(buf)
                return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


# ---------------------------------------------------------------- teclado ---
VK = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "capslock": 0x14,
    "mute": 0xAD, "volumedown": 0xAE, "volumeup": 0xAF,
    "next": 0xB0, "prev": 0xB1, "stop": 0xB2, "playpause": 0xB3,
    ".": 0xBE, ",": 0xBC, "-": 0xBD, "=": 0xBB, ";": 0xBA, "/": 0xBF,
}
for _i in range(1, 25):
    VK["f%d" % _i] = 0x6F + _i  # F1 = 0x70
EXTENDED = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28,
            0x5B, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}


def vk_of(name):
    n = name.strip().lower()
    if n in VK:
        return VK[n]
    if len(n) == 1 and (n.isalpha() or n.isdigit()):
        return ord(n.upper())
    raise ValueError("tecla desconhecida: %s" % name)


def send_keys(keys):
    codes = [vk_of(k) for k in keys]
    if not IS_WINDOWS:
        print("  [simulado] teclas:", "+".join(keys))
        return
    import ctypes
    user32 = ctypes.windll.user32
    KEYUP = 0x0002
    for c in codes:
        user32.keybd_event(c, 0, 1 if c in EXTENDED else 0, 0)
        time.sleep(0.01)
    for c in reversed(codes):
        user32.keybd_event(c, 0, (1 if c in EXTENDED else 0) | KEYUP, 0)
        time.sleep(0.01)


# ----------------------------------------------------------- digitar texto ---
def type_text(text, enter=False):
    if not IS_WINDOWS:
        print("  [simulado] digitar:", repr(text), "+ Enter" if enter else "")
        return
    import ctypes
    from ctypes import wintypes

    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    KEYUP, UNICODE = 0x0002, 0x0004
    send = ctypes.windll.user32.SendInput

    def press(vk=0, scan=0, flags=0):
        arr = (INPUT * 2)()
        for i, f in enumerate((flags, flags | KEYUP)):
            arr[i].type = 1
            arr[i].u.ki = KEYBDINPUT(vk, scan, f, 0, 0)
        send(2, arr, ctypes.sizeof(INPUT))

    data = text.replace("\r\n", "\n").encode("utf-16-le")
    for i in range(0, len(data), 2):
        unit = int.from_bytes(data[i:i + 2], "little")
        if unit == 10:
            press(vk=0x0D)
        else:
            press(scan=unit, flags=UNICODE)
        time.sleep(0.005)
    if enter:
        time.sleep(0.05)
        press(vk=0x0D)


# ------------------------------------------------------- iniciar com o Windows ---
def startup_file():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "StreamDeck.cmd")


def autostart_enabled():
    return IS_WINDOWS and os.path.exists(startup_file())


def set_autostart(on):
    if not IS_WINDOWS:
        raise RuntimeError("so no Windows")
    from . import paths
    path = startup_file()
    if on:
        if paths.FROZEN:
            line = '@start "Stream Deck" /min "%s"\r\n' % paths.EXE_PATH
        else:
            line = '@cd /d "%s"\r\n@start "Stream Deck" /min "%s" "%s"\r\n' % (
                paths.APP_DIR, sys.executable, paths.SCRIPT)
        with open(path, "w", encoding="mbcs") as f:
            f.write(line)
    elif os.path.exists(path):
        os.remove(path)


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    if IS_WINDOWS:
        os.startfile(path)
    else:
        print("  [simulado] abrir pasta:", path)
