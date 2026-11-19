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


_SENDINPUT = []


def _sendinput():
    """Estruturas do SendInput (montadas uma vez). Devolve press(vk, scan, flags, up)."""
    if _SENDINPUT:
        return _SENDINPUT[0]
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

    send = ctypes.windll.user32.SendInput

    def key(vk=0, scan=0, flags=0):
        """Um evento de tecla (flags pode ter KEYUP)."""
        arr = (INPUT * 1)()
        arr[0].type = 1                    # INPUT_KEYBOARD
        arr[0].u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
        send(1, arr, ctypes.sizeof(INPUT))

    _SENDINPUT.append(key)
    return key


KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004


def send_keys(keys):
    codes = [vk_of(k) for k in keys]
    if not IS_WINDOWS:
        print("  [simulado] teclas:", "+".join(keys))
        return
    key = _sendinput()
    for c in codes:
        key(vk=c, flags=KEYEVENTF_EXTENDEDKEY if c in EXTENDED else 0)
        time.sleep(0.01)
    for c in reversed(codes):
        key(vk=c, flags=(KEYEVENTF_EXTENDEDKEY if c in EXTENDED else 0) | KEYEVENTF_KEYUP)
        time.sleep(0.01)


# ----------------------------------------------------------- digitar texto ---
def type_text(text, enter=False):
    if not IS_WINDOWS:
        print("  [simulado] digitar:", repr(text), "+ Enter" if enter else "")
        return
    key = _sendinput()

    def press(vk=0, scan=0, flags=0):
        key(vk, scan, flags)
        key(vk, scan, flags | KEYEVENTF_KEYUP)

    data = text.replace("\r\n", "\n").encode("utf-16-le")
    for i in range(0, len(data), 2):
        unit = int.from_bytes(data[i:i + 2], "little")
        if unit == 10:
            press(vk=0x0D)
        else:
            press(scan=unit, flags=KEYEVENTF_UNICODE)
        time.sleep(0.005)
    if enter:
        time.sleep(0.05)
        press(vk=0x0D)


# ------------------------------------------------------- iniciar com o Windows ---
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "StreamDeck"


def startup_file():
    """Arquivo .cmd antigo (ate a 2.3.0) na pasta Inicializar."""
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "StreamDeck.cmd")


def _autostart_command():
    from . import paths
    if paths.FROZEN:
        return '"%s" --minimizado' % paths.EXE_PATH
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(w):
        exe = w
    return '"%s" "%s"' % (exe, paths.SCRIPT)


def autostart_enabled():
    if not IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            val, _t = winreg.QueryValueEx(k, RUN_NAME)
        return bool(val)
    except OSError:
        return False


def set_autostart(on):
    if not IS_WINDOWS:
        raise RuntimeError("so no Windows")
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


def migrate_autostart():
    """Troca o .cmd antigo da pasta Inicializar pelo registro do usuario."""
    if not IS_WINDOWS:
        return
    old = startup_file()
    if not os.path.exists(old):
        return
    try:
        set_autostart(True)
        os.remove(old)
        print("  iniciar com o Windows: passou a usar o registro do usuario")
    except Exception as e:
        print("  aviso: nao consegui migrar o iniciar com o Windows (%s)" % e)


def minimize_console():
    """Minimiza a janela do console (usado com --minimizado)."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)   # SW_MINIMIZE
    except Exception:
        pass


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    if IS_WINDOWS:
        os.startfile(path)
    else:
        print("  [simulado] abrir pasta:", path)
