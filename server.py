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

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
TOKEN_PATH = os.path.join(BASE, "token.txt")
TABS_PATH = os.path.join(BASE, "abas.json")
FILE_LOCK = threading.Lock()
WEB_DIR = os.path.join(BASE, "web")
SOUNDS_DIR = os.path.join(BASE, "sons")
SOUND_EXT = (".mp3", ".wav", ".wma", ".m4a")
PORTS = (8765, 8766, 8767)  # usa a primeira livre

IS_WINDOWS = sys.platform.startswith("win")

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
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _authed(self, q):
        if (q.get("k") or [""])[0] == TOKEN:
            return True
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "sdk" and value == TOKEN:
                return True
        return False

    def do_POST(self):
        url = urlparse(self.path)
        if not self._authed(parse_qs(url.query)):
            print("! salvamento recusado: codigo de acesso ausente ou errado")
            return self._json(403, {"ok": False, "error": "codigo de acesso invalido"})
        if url.path not in ("/api/config", "/api/tabs"):
            return self._json(404, {"ok": False})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > 2_000_000:
                raise ValueError("tamanho invalido (%d)" % n)
            raw = b""
            while len(raw) < n:
                chunk = self.rfile.read(n - len(raw))
                if not chunk:
                    break
                raw += chunk
            data = json.loads(raw.decode("utf-8"))
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
        url = urlparse(self.path)
        q = parse_qs(url.query)
        k = (q.get("k") or [""])[0]

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
                                        "tabs": load_tabs()})
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
    load_config()  # valida o JSON antes de subir
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    srv = port = None
    for port in PORTS:
        try:
            srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        print("Nenhuma porta livre (%s)." % ", ".join(map(str, PORTS)))
        sys.exit(1)
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
    print(" Deixe esta janela aberta. Ctrl+C para parar.")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
