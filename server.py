# -*- coding: utf-8 -*-
"""
Stream Deck caseiro: servidor que roda no PC (Windows).
O tablet abre a pagina no navegador e cada botao dispara uma acao aqui.
Sem dependencias: so a biblioteca padrao do Python 3.7+.
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import queue
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

VERSION = "1.0.0"
REPO = "K15uc0/streamdeck-web"          # de onde vem as atualizacoes
IS_WINDOWS = sys.platform.startswith("win")
FROZEN = getattr(sys, "frozen", False)   # True quando roda como StreamDeck.exe

# Arquivos do programa (pagina, config padrao): dentro do .exe ou ao lado do .py
APP_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(APP_DIR, "web")
DEFAULT_CONFIG = os.path.join(APP_DIR, "config.padrao.json")
EXE_PATH = sys.executable if FROZEN else None


def documents_dir():
    if IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes
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


# Dados do usuario (botoes, abas, codigo, sons): ficam fora do programa,
# por isso continuam intactos quando o programa e atualizado.
if os.environ.get("STREAMDECK_DATA"):
    BASE = os.environ["STREAMDECK_DATA"]
elif FROZEN:
    BASE = os.path.join(documents_dir(), "StreamDeck")
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(BASE, exist_ok=True)

CONFIG_PATH = os.path.join(BASE, "config.json")
TOKEN_PATH = os.path.join(BASE, "token.txt")
TABS_PATH = os.path.join(BASE, "abas.json")
FILE_LOCK = threading.Lock()
LOG_PATH = os.path.join(BASE, "streamdeck.log")
SOUNDS_DIR = os.path.join(BASE, "sons")
SOUND_EXT = (".mp3", ".wav", ".wma", ".m4a")
PORTS = (8765, 8766, 8767)  # usa a primeira livre

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
for i in range(1, 25):
    VK["f%d" % i] = 0x6F + i  # F1 = 0x70
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


# ------------------------------------------------------------ efeitos sonoros ---
def sound_path(name):
    name = str(name).strip().strip('"')
    if os.path.isabs(name):
        return name
    return os.path.join(SOUNDS_DIR, name)


def list_sounds():
    if not os.path.isdir(SOUNDS_DIR):
        return []
    out = []
    for root, _dirs, files in os.walk(SOUNDS_DIR):
        for f in files:
            if f.lower().endswith(SOUND_EXT):
                out.append(os.path.relpath(os.path.join(root, f), SOUNDS_DIR).replace("\\", "/"))
    return sorted(out, key=str.lower)


class SoundPlayer:
    """Toca varios sons ao mesmo tempo pelo MCI do Windows (sem dependencias).
    Todos os comandos rodam numa unica thread, como o MCI prefere."""

    def __init__(self):
        self.q = queue.Queue()
        self.playing = []
        self.n = 0
        threading.Thread(target=self._loop, daemon=True).start()

    def play(self, path, volume=100, exclusive=False):
        self.q.put(("play", path, volume, exclusive))

    def stop_all(self):
        self.q.put(("stop",))

    def _mci(self, cmd):
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, 0)
        if err:
            ebuf = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(err, ebuf, 255)
            raise RuntimeError(ebuf.value or "erro MCI %d" % err)
        return buf.value

    def _close(self, alias):
        try:
            self._mci("close " + alias)
        except Exception:
            pass

    def _loop(self):
        while True:
            try:
                item = self.q.get(timeout=1)
            except queue.Empty:
                item = None
            if IS_WINDOWS:
                for alias in list(self.playing):  # libera sons que terminaram
                    try:
                        if self._mci("status %s mode" % alias) != "playing":
                            self._close(alias)
                            self.playing.remove(alias)
                    except Exception:
                        self.playing.remove(alias)
            if item is None:
                continue
            if item[0] == "stop" or (item[0] == "play" and item[3]):
                for alias in self.playing:
                    if IS_WINDOWS:
                        self._close(alias)
                self.playing = []
                if item[0] == "stop":
                    print("  sons parados")
                    continue
            _, path, volume, _ = item
            if not IS_WINDOWS:
                print("  [simulado] tocar:", path, "vol", volume)
                continue
            self.n += 1
            alias = "sd%d" % self.n
            try:
                self._mci('open "%s" type mpegvideo alias %s' % (path, alias))
                try:
                    self._mci("setaudio %s volume to %d" % (alias, max(0, min(100, int(volume))) * 10))
                except Exception:
                    pass
                self._mci("play " + alias)
                self.playing.append(alias)
            except Exception as e:
                print("  erro ao tocar %s: %s" % (path, e))
                self._close(alias)


PLAYER = SoundPlayer()


# ---------------------------------------------------------- requisicao web ---
def http_request(method, url, body=""):
    data = body.encode("utf-8") if body and method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        ctype = "application/json" if body.strip()[:1] in "{[" else "application/x-www-form-urlencoded"
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=5) as r:
        r.read(1024)
        print("  http %s %s -> %d" % (method, url, r.status))

# ------------------------------------------------------------ atualizacoes ---
UPDATE = {"available": False, "latest": None, "notes": "", "page": None, "asset": None,
          "error": None, "checked": None, "state": "idle"}


def parse_ver(v):
    out = []
    for part in str(v).lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out + [0] * (3 - len(out)))


def check_updates():
    url = os.environ.get("STREAMDECK_UPDATE_URL") or "https://api.github.com/repos/%s/releases/latest" % REPO
    req = urllib.request.Request(url, headers={"User-Agent": "StreamDeck/" + VERSION,
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        asset = None
        for a in data.get("assets", []):
            if a.get("name", "").lower().endswith(".exe"):
                asset = a.get("browser_download_url")
        was = UPDATE["available"]
        UPDATE.update(latest=tag.lstrip("vV"), notes=data.get("body") or "", page=data.get("html_url"),
                      asset=asset, error=None, checked=time.strftime("%d/%m %H:%M"),
                      available=parse_ver(tag) > parse_ver(VERSION))
        if UPDATE["available"] and not was:
            print("* nova versao disponivel: %s (instalada: %s)" % (UPDATE["latest"], VERSION))
    except Exception as e:
        code = getattr(e, "code", None)
        UPDATE.update(error="nenhuma versao publicada ainda" if code == 404 else str(e),
                      checked=time.strftime("%d/%m %H:%M"))
    return UPDATE


def update_loop():
    time.sleep(3)
    while True:
        check_updates()
        time.sleep(6 * 3600)


def cleanup_old_exe():
    if not FROZEN:
        return
    old = EXE_PATH + ".old"
    for _ in range(30):
        if not os.path.exists(old):
            return
        try:
            os.remove(old)
            return
        except OSError:
            time.sleep(2)


def apply_update():
    """Baixa o novo StreamDeck.exe, troca pelo atual e reinicia.
    Os dados (Documentos\\StreamDeck) nao sao tocados."""
    try:
        UPDATE["state"] = "downloading"
        print("* baixando versao %s..." % UPDATE["latest"])
        new = EXE_PATH + ".new"
        req = urllib.request.Request(UPDATE["asset"], headers={"User-Agent": "StreamDeck/" + VERSION})
        with urllib.request.urlopen(req, timeout=120) as r, open(new, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
        with open(new, "rb") as f:
            head = f.read(2)
        if head != b"MZ" or os.path.getsize(new) < 1_000_000:
            os.remove(new)
            raise RuntimeError("arquivo baixado invalido")
        old = EXE_PATH + ".old"
        if os.path.exists(old):
            os.remove(old)
        os.replace(EXE_PATH, old)      # o Windows permite renomear o .exe em uso
        os.replace(new, EXE_PATH)
        UPDATE["state"] = "restarting"
        print("* atualizado para %s, reiniciando..." % UPDATE["latest"])
        subprocess.Popen([EXE_PATH], cwd=os.path.dirname(EXE_PATH), creationflags=0x00000010)
        time.sleep(1.5)
        os._exit(0)
    except Exception as e:
        UPDATE["state"] = "error"
        UPDATE["error"] = "falha ao atualizar: %s" % e
        print("! " + UPDATE["error"])


def update_status():
    st = dict(UPDATE)
    st.update(ok=True, version=VERSION, auto=bool(FROZEN and UPDATE["asset"]))
    return st


# ------------------------------------------------------- iniciar com o Windows ---
def startup_file():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "StreamDeck.cmd")


def autostart_enabled():
    return IS_WINDOWS and os.path.exists(startup_file())


def set_autostart(on):
    if not IS_WINDOWS:
        raise RuntimeError("so no Windows")
    path = startup_file()
    if on:
        if FROZEN:
            line = '@start "Stream Deck" /min "%s"\r\n' % EXE_PATH
        else:
            line = '@cd /d "%s"\r\n@start "Stream Deck" /min "%s" "%s"\r\n' % (
                APP_DIR, sys.executable, os.path.abspath(__file__))
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


ACTIVE_PORT = [None]


# ----------------------------------------------------------------- acoes ---
def run_action(action):
    t = action.get("type")
    if t == "hotkey":
        send_keys(action["keys"])
    elif t == "open":
        target = action["target"]
        if target.startswith(("http://", "https://")):
            webbrowser.open(target)
        elif IS_WINDOWS:
            os.startfile(target)
        else:
            print("  [simulado] abrir:", target)
    elif t == "command":
        if IS_WINDOWS:
            subprocess.Popen(action["command"], shell=True,
                             creationflags=0x08000000)  # sem janela de console
        else:
            print("  [simulado] comando:", action["command"])
    elif t == "sound":
        path = sound_path(action["file"])
        if not os.path.isfile(path):
            raise ValueError("arquivo de som nao encontrado: %s" % action["file"])
        PLAYER.play(path, action.get("volume", 100), bool(action.get("exclusive")))
    elif t == "stopsound":
        PLAYER.stop_all()
    elif t == "text":
        type_text(action["text"], bool(action.get("enter")))
    elif t == "http":
        http_request(action.get("method", "GET").upper(), action["url"], action.get("body", ""))
    elif t == "multi":
        for step in action["steps"]:
            run_action(step)
            time.sleep(action.get("delay", 0.1))
    else:
        raise ValueError("tipo de acao desconhecido: %s" % t)


# ---------------------------------------------------------------- config ---
def ensure_config():
    """Na primeira execucao cria o config.json a partir do padrao."""
    if not os.path.exists(CONFIG_PATH):
        import shutil
        shutil.copyfile(DEFAULT_CONFIG, CONFIG_PATH)
        return True
    return False


def load_config():
    with FILE_LOCK:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def write_json(path, data):
    """Grava com seguranca. No Windows o arquivo pode estar momentaneamente
    preso (antivirus, indexador, OneDrive): tenta de novo e, se preciso,
    grava direto por cima."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    for _ in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.remove(tmp)
    except OSError:
        pass


ACTION_TYPES = {"hotkey", "open", "command", "multi", "page", "none",
                "sound", "stopsound", "text", "http"}


def validate_action(a, n_pages, where):
    if not isinstance(a, dict) or a.get("type") not in ACTION_TYPES:
        raise ValueError("%s: tipo de acao invalido" % where)
    t = a["type"]
    if t == "hotkey":
        keys = a.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError("%s: informe as teclas" % where)
        for k in keys:
            vk_of(str(k))
    elif t == "open" and not str(a.get("target", "")).strip():
        raise ValueError("%s: informe o que abrir" % where)
    elif t == "command" and not str(a.get("command", "")).strip():
        raise ValueError("%s: informe o comando" % where)
    elif t == "sound" and not str(a.get("file", "")).strip():
        raise ValueError("%s: escolha o arquivo de som" % where)
    elif t == "text" and not str(a.get("text", "")):
        raise ValueError("%s: informe o texto" % where)
    elif t == "http":
        if not str(a.get("url", "")).startswith(("http://", "https://")):
            raise ValueError("%s: o endereco deve comecar com http:// ou https://" % where)
        if str(a.get("method", "GET")).upper() not in ("GET", "POST"):
            raise ValueError("%s: metodo deve ser GET ou POST" % where)
    elif t == "page":
        to = a.get("to")
        if not isinstance(to, int) or not (0 <= to < n_pages):
            raise ValueError("%s: pagina de destino invalida" % where)
    elif t == "multi":
        steps = a.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("%s: sequencia vazia" % where)
        for s in steps:
            if isinstance(s, dict) and s.get("type") in ("page", "multi"):
                raise ValueError("%s: sequencia nao aceita pagina/sequencia" % where)
            validate_action(s, n_pages, where)


def validate_config(cfg):
    if not isinstance(cfg, dict):
        raise ValueError("configuracao invalida")
    for key, lo, hi in (("columns", 1, 10), ("rows", 1, 8)):
        v = cfg.get(key)
        if not isinstance(v, int) or not (lo <= v <= hi):
            raise ValueError("%s deve ficar entre %d e %d" % (key, lo, hi))
    pages = cfg.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("precisa ter ao menos uma pagina")
    for pi, pg in enumerate(pages):
        if not isinstance(pg, dict) or not isinstance(pg.get("buttons"), list):
            raise ValueError("pagina %d invalida" % (pi + 1))
        for bi, b in enumerate(pg["buttons"]):
            where = "Pagina %d, botao %d" % (pi + 1, bi + 1)
            if not isinstance(b, dict):
                raise ValueError(where + ": invalido")
            validate_action(b.get("action", {"type": "none"}), len(pages), where)


def save_config(cfg):
    validate_config(cfg)
    with FILE_LOCK:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "rb") as f:
                    old = f.read()
                with open(os.path.join(BASE, "config.bak.json"), "wb") as f:
                    f.write(old)
            except OSError as e:
                print("  aviso: sem copia de seguranca (%s)" % e)
        write_json(CONFIG_PATH, cfg)


def load_tabs():
    try:
        with open(TABS_PATH, "r", encoding="utf-8") as f:
            tabs = json.load(f)
        return tabs if isinstance(tabs, list) else []
    except (OSError, ValueError):
        return []


def save_tabs(tabs):
    if not isinstance(tabs, list) or len(tabs) > 30:
        raise ValueError("lista de abas invalida")
    clean = []
    for t in tabs:
        if not isinstance(t, dict) or not str(t.get("host", "")).strip():
            raise ValueError("aba invalida")
        clean.append({"name": str(t.get("name", ""))[:40], "host": str(t["host"])[:100],
                      "code": str(t.get("code", ""))[:64]})
    with FILE_LOCK:
        write_json(TABS_PATH, clean)


def find_button(cfg, page_idx, btn_idx):
    return cfg["pages"][page_idx]["buttons"][btn_idx]


def get_token():
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            tok = f.read().strip()
            if tok:
                return tok
    tok = secrets.token_hex(4)
    with open(TOKEN_PATH, "w") as f:
        f.write(tok)
    return tok


TOKEN = get_token()

PIXEL = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
         b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")

MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript",
        ".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml",
        ".jpg": "image/jpeg", ".ico": "image/x-icon"}


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1: atende "Expect: 100-continue" e conexoes mantidas abertas,
    # que o navegador antigo do Android usa. timeout evita conexoes presas.
    protocol_version = "HTTP/1.1"
    timeout = 30

    def log_message(self, fmt, *args):
        pass

    def log_error(self, fmt, *args):
        raw = getattr(self, "raw_requestline", b"") or b""
        kind = " (tentativa de HTTPS: use http://)" if raw[:1] == b"\x16" else ""
        print("  pedido invalido de %s: %s%s %r" % (self.client_address[0], fmt % args, kind, raw[:30]))

    def log_request(self, code="-", size="-"):
        path = (getattr(self, "path", "") or "").split("?")[0]
        if not path:
            return
        if path in ("/ping.gif",) or (path == "/api/config" and self.command == "GET" and code == 200):
            return
        print("  %s %s %s -> %s" % (self.client_address[0], self.command, path, code))

    def _note_client(self):
        ip = self.client_address[0]
        if ip not in SEEN:
            SEEN.add(ip)
            print("  novo aparelho conectado: %s  [%s]" % (ip, time.strftime("%H:%M:%S")))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Connection", "close" if self.close_connection else "keep-alive")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _local(self):
        return self.client_address[0] in ("127.0.0.1", "::1")

    def _body_json(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n <= 0:
            return {}
        if n > 2_000_000:
            raise ValueError("tamanho invalido (%d)" % n)
        raw = b""
        while len(raw) < n:
            chunk = self.rfile.read(n - len(raw))
            if not chunk:
                break
            raw += chunk
        return json.loads(raw.decode("utf-8"))

    def _authed(self, q):
        if (q.get("k") or [""])[0] == TOKEN:
            return True
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "sdk" and value == TOKEN:
                return True
        return False

    def do_POST(self):
        self._note_client()
        url = urlparse(self.path)
        # funcoes so do proprio PC (tela de conexao)
        if url.path.startswith("/api/local/"):
            if not self._local():
                return self._json(403, {"ok": False, "error": "so no proprio PC"})
            try:
                body = self._body_json()
                if url.path == "/api/local/autostart":
                    set_autostart(bool(body.get("on")))
                    return self._json(200, {"ok": True, "autostart": autostart_enabled()})
                if url.path == "/api/local/sounds":
                    open_folder(SOUNDS_DIR)
                    return self._json(200, {"ok": True})
                if url.path == "/api/local/data":
                    open_folder(BASE)
                    return self._json(200, {"ok": True})
            except Exception as e:
                return self._json(400, {"ok": False, "error": str(e)})
            return self._json(404, {"ok": False})
        if url.path.startswith("/api/update") and (self._local() or self._authed(parse_qs(url.query))):
            if url.path == "/api/update/check":
                check_updates()
                return self._json(200, update_status())
            if url.path == "/api/update/apply":
                if not (FROZEN and UPDATE["available"] and UPDATE["asset"]):
                    return self._json(400, {"ok": False, "error": "atualizacao automatica indisponivel"})
                if UPDATE["state"] not in ("downloading", "restarting"):
                    threading.Thread(target=apply_update, daemon=True).start()
                return self._json(200, {"ok": True})
        if not self._authed(parse_qs(url.query)):
            print("! salvamento recusado: codigo de acesso ausente ou errado")
            return self._json(403, {"ok": False, "error": "codigo de acesso invalido"})
        if url.path not in ("/api/config", "/api/tabs"):
            return self._json(404, {"ok": False})
        try:
            data = self._body_json()
            if url.path == "/api/tabs":
                save_tabs(data)
                return self._json(200, {"ok": True})
            save_config(data)
            print("* configuracao salva")
            return self._json(200, {"ok": True})
        except Exception as e:
            print("! erro ao salvar:", e)
            return self._json(400, {"ok": False, "error": str(e)})

    def do_GET(self):
        self._note_client()
        url = urlparse(self.path)
        q = parse_qs(url.query)
        k = (q.get("k") or [""])[0]

        # tela de conexao: so no proprio PC
        if url.path in ("/conectar", "/api/local/info") and not self._local():
            return self._send(403, "Abra esta pagina no proprio PC.", "text/plain; charset=utf-8")
        if url.path == "/conectar":
            url = url._replace(path="/conectar.html")
            self.path = "/conectar.html"
        if url.path == "/api/local/info":
            base = "http://%s:%d" % (lan_ip(), ACTIVE_PORT[0])
            return self._json(200, {"ok": True, "base": base, "first": "%s/?k=%s" % (base, TOKEN),
                                    "code": TOKEN, "name": socket.gethostname(), "autostart": autostart_enabled(),
                                    "windows": IS_WINDOWS, "data": BASE, "update": update_status()})
        if url.path == "/api/update":
            if self._local() or self._authed(q):
                return self._json(200, update_status())
            return self._json(403, {"ok": False})

        # sinal de vida para as abas de outros aparelhos (imagem 1x1)
        if url.path == "/ping.gif":
            return self._send(200, PIXEL, "image/gif")

        # primeiro acesso com o codigo: guarda no navegador e limpa o endereco
        if url.path == "/" and k == TOKEN:
            sync = ""
            for part in url.query.split("&"):
                if part.startswith("sync="):
                    sync = part[5:]
            self.send_response(302)
            self.send_header("Set-Cookie", "sdk=%s; Max-Age=315360000; Path=/; HttpOnly" % TOKEN)
            self.send_header("Location", "/#sync=" + sync if sync else "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if url.path.startswith("/api/"):
            if not self._authed(q):
                return self._json(403, {"ok": False, "error": "codigo invalido"})
            if url.path == "/api/config":
                try:
                    return self._json(200, load_config())
                except Exception as e:
                    return self._json(500, {"ok": False, "error": str(e)})
            if url.path == "/api/info":
                return self._json(200, {"ok": True, "name": socket.gethostname(),
                                        "code": TOKEN, "sounds": list_sounds(),
                                        "tabs": load_tabs(), "version": VERSION,
                                        "update": update_status()})
            if url.path == "/api/press":
                try:
                    p = int(q["p"][0])
                    b = int(q["b"][0])
                    btn = find_button(load_config(), p, b)
                    print("> %s" % btn.get("label", "?"))
                    run_action(btn["action"])
                    return self._json(200, {"ok": True})
                except Exception as e:
                    print("  erro:", e)
                    return self._json(500, {"ok": False, "error": str(e)})
            return self._json(404, {"ok": False})

        # arquivos estaticos
        path = url.path
        if path == "/":
            path = "/index.html"
        full = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            return self._send(404, "nao encontrado", "text/plain")
        with open(full, "rb") as f:
            data = f.read()
        ext = os.path.splitext(full)[1].lower()
        self._send(200, data, MIME.get(ext, "application/octet-stream"))


class Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        print("  conexao com %s falhou: %s" % (client_address[0], sys.exc_info()[1]))

    """Nao deixa duas copias do servidor dividirem a mesma porta (no Windows
    isso acontece por padrao e uma delas 'engole' os acessos)."""
    allow_reuse_address = not IS_WINDOWS
    daemon_threads = True

    def server_bind(self):
        if IS_WINDOWS:
            self.socket.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", -5), 1)
        super().server_bind()


def stop_old_instances():
    """Encerra copias antigas do Stream Deck que ainda estejam escutando nas
    nossas portas (so processos nessas portas, nada mais)."""
    if not IS_WINDOWS:
        return
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             timeout=10, creationflags=0x08000000).stdout
    except Exception as e:
        print("  aviso: nao consegui verificar copias antigas (%s)" % e)
        return
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].upper() in ("LISTENING", "ESCUTANDO"):
            port = parts[1].rsplit(":", 1)[-1]
            if port.isdigit() and int(port) in PORTS and parts[4].isdigit():
                pid = int(parts[4])
                if pid != os.getpid():
                    pids.add(pid)
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True,
                       creationflags=0x08000000)
        print("  copia antiga encerrada (PID %d)" % pid)
    if pids:
        time.sleep(1)


class Tee:
    """Mostra na janela e grava em streamdeck.log."""

    def __init__(self, stream, path):
        self.stream = stream
        try:
            self.f = open(path, "w", encoding="utf-8", buffering=1)
        except OSError:
            self.f = None

    def write(self, text):
        try:
            self.stream.write(text)
            self.stream.flush()
        except Exception:
            pass
        if self.f:
            try:
                self.f.write(text)
            except Exception:
                pass

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass


SEEN = set()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    sys.stdout = Tee(sys.stdout, LOG_PATH)
    sys.stderr = sys.stdout
    print("Iniciando em %s" % time.strftime("%d/%m/%Y %H:%M:%S"))
    print("Stream Deck %s | dados em %s" % (VERSION, BASE))
    first_run = ensure_config()
    load_config()  # valida o JSON antes de subir
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    stop_old_instances()
    srv = port = None
    for port in PORTS:
        try:
            srv = Server(("0.0.0.0", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        print("Nenhuma porta livre (%s)." % ", ".join(map(str, PORTS)))
        sys.exit(1)
    ACTIVE_PORT[0] = port
    base = "http://%s%s" % (lan_ip(), "" if port == 80 else ":%d" % port)
    print("=" * 56)
    print(" Stream Deck rodando.")
    print()
    print(" Primeiro acesso no tablet (so uma vez):")
    print("   %s/?k=%s" % (base, TOKEN))
    print()
    print(" Depois disso, basta abrir:")
    print("   %s" % base)
    print()
    print(" Tela de conexao com QR code (neste PC):")
    print("   http://127.0.0.1:%d/conectar" % port)
    print()
    print(" Deixe esta janela aberta. Ctrl+C para parar.")
    print("=" * 56)
    threading.Thread(target=update_loop, daemon=True).start()
    threading.Thread(target=cleanup_old_exe, daemon=True).start()
    if first_run or "--conectar" in sys.argv:
        threading.Timer(1.0, webbrowser.open, ["http://127.0.0.1:%d/conectar" % port]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
