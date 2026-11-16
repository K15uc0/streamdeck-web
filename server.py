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
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
TOKEN_PATH = os.path.join(BASE, "token.txt")
WEB_DIR = os.path.join(BASE, "web")
PORT = 8765

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
    elif t == "multi":
        for step in action["steps"]:
            run_action(step)
            time.sleep(action.get("delay", 0.1))
    else:
        raise ValueError("tipo de acao desconhecido: %s" % t)


# ---------------------------------------------------------------- config ---
def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


ACTION_TYPES = {"hotkey", "open", "command", "multi", "page", "none"}


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
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "rb") as f:
            old = f.read()
        with open(os.path.join(BASE, "config.bak.json"), "wb") as f:
            f.write(old)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


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

    def do_POST(self):
        url = urlparse(self.path)
        k = (parse_qs(url.query).get("k") or [""])[0]
        if k != TOKEN:
            return self._json(403, {"ok": False, "error": "codigo invalido"})
        if url.path != "/api/config":
            return self._json(404, {"ok": False})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > 2_000_000:
                raise ValueError("tamanho invalido")
            cfg = json.loads(self.rfile.read(n).decode("utf-8"))
            save_config(cfg)
            print("* configuracao salva")
            return self._json(200, {"ok": True})
        except Exception as e:
            return self._json(400, {"ok": False, "error": str(e)})

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        k = (q.get("k") or [""])[0]

        if url.path.startswith("/api/"):
            if k != TOKEN:
                return self._json(403, {"ok": False, "error": "codigo invalido"})
            if url.path == "/api/config":
                try:
                    return self._json(200, load_config())
                except Exception as e:
                    return self._json(500, {"ok": False, "error": str(e)})
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
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("=" * 52)
    print(" Stream Deck rodando.")
    print(" No navegador do tablet, abra:")
    print()
    print("   http://%s:%d/?k=%s" % (lan_ip(), PORT, TOKEN))
    print()
    print(" Deixe esta janela aberta. Ctrl+C para parar.")
    print("=" * 52)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
