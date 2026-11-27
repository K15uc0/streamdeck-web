# -*- coding: utf-8 -*-
"""Navegador do PC (2.12): ponte com a extensao "Stream Deck" (Chrome/Edge) e
atalhos de teclado quando a extensao nao esta ligada.

Seguranca (ver tambem httpd.py, rotas /api/browser/*):
- So o proprio PC (127.0.0.1) fala com /api/browser/*, e so com o Origin
  chrome-extension://<id>. Sites comuns nunca conseguem mandar esse Origin.
- Parear: o Conectar gera um codigo curto (5 min, uso unico, 5 erros e ele
  morre). A extensao troca o codigo por uma chave longa, que vale so para o
  id daquela extensao. Comparacao em tempo constante. "Desparear" apaga a chave.
- A extensao nao le paginas: so lista abas (titulo, endereco) e recebe comandos.
  Ela so pode rodar script no YouTube (pausar e rolar); rolar em outros sites
  e pausar sem aba do YouTube viram atalho de teclado.
- Para o celular so vai o dominio da aba (nunca o endereco completo).
"""
import collections
import hmac
import json
import os
import re
import secrets
import shutil
import threading
import time
from urllib.parse import urlparse

from . import paths, winapi

STATE_PATH = os.path.join(paths.BASE, "navegador.json")
EXT_SRC = os.path.join(paths.APP_DIR, "extensao")       # dentro do programa
EXT_COPY = os.path.join(paths.BASE, "extensao")         # copia fixa (o .exe de arquivo unico usa pasta temporaria)
ORIGIN_RE = re.compile(r"^chrome-extension://([a-p]{32})$")   # ids do Chrome/Edge
CODE_ABC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"                # sem 0/O/1/I
CODE_LEN = 6
CODE_TTL = 300
CODE_TRIES = 5
ONLINE_S = 30           # sem contato ha mais que isso: usa atalhos de teclado
POLL_MAX = 25           # long-poll da extensao (s)
MAX_POLLS = 2           # long-polls ao mesmo tempo (o resto volta na hora)
MAX_TABS = 200
MAX_QUEUE = 20
CMD_TTL = 10            # comando que ninguem buscou em 10 s e descartado

OPS = ("tab_next", "tab_prev", "open_url", "yt_toggle", "scroll", "back", "forward", "reload", "close_tab",
       "activate")
SCROLL = ("up", "down", "top", "bottom")
# fallback: atalhos na janela em primeiro plano
KEYS = {"tab_next": ["ctrl", "tab"], "tab_prev": ["ctrl", "shift", "tab"], "yt_toggle": ["k"],
        "back": ["alt", "left"], "forward": ["alt", "right"], "reload": ["f5"], "close_tab": ["ctrl", "w"],
        "scroll:down": ["pagedown"], "scroll:up": ["pageup"], "scroll:top": ["home"], "scroll:bottom": ["end"]}
BROWSER_EXES = ("chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe", "vivaldi.exe")


class BrowserError(ValueError):
    pass


def valid_url(u):
    if not isinstance(u, str) or len(u) > 2000 or not u.startswith(("http://", "https://")):
        return False
    if any(ord(c) < 33 for c in u):
        return False
    return bool(urlparse(u).netloc)


def check_cmd(cmd):
    """Confere um comando {op, ...}. Devolve o comando limpo ou levanta BrowserError."""
    if not isinstance(cmd, dict) or cmd.get("op") not in OPS:
        raise BrowserError("operacao do navegador invalida")
    op = cmd["op"]
    out = {"op": op}
    if op == "open_url":
        if not valid_url(cmd.get("url")):
            raise BrowserError("o endereco deve comecar com http:// ou https://")
        out["url"] = cmd["url"]
    elif op == "scroll":
        if cmd.get("dir") not in SCROLL:
            raise BrowserError("direcao de rolagem invalida")
        out["dir"] = cmd["dir"]
    elif op in ("activate", "close_tab"):
        t = cmd.get("tab")
        if t is not None:
            if not isinstance(t, int) or isinstance(t, bool) or t < 0:
                raise BrowserError("aba invalida")
            out["tab"] = t
        elif op == "activate":
            raise BrowserError("aba invalida")
    return out


def _host(url):
    try:
        h = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def _clean_tab(t):
    if not isinstance(t, dict):
        return None
    tid, win = t.get("id"), t.get("window", 0)
    if not isinstance(tid, int) or isinstance(tid, bool) or tid < 0:
        return None
    url = t.get("url") if isinstance(t.get("url"), str) else ""
    return {"id": tid, "window": win if isinstance(win, int) and not isinstance(win, bool) else 0,
            "title": (t.get("title") if isinstance(t.get("title"), str) else "")[:200],
            "host": _host(url[:2000])[:120] if url.startswith(("http://", "https://")) else "",
            "active": t.get("active") is True, "audible": t.get("audible") is True,
            "current": t.get("current") is True,
            "yt": url.startswith(("https://www.youtube.com/", "https://m.youtube.com/", "https://youtube.com/",
                                  "https://music.youtube.com/"))}


def _manifest(folder):
    try:
        with open(os.path.join(folder, "manifest.json"), "rb") as f:
            return f.read()
    except OSError:
        return None


def ext_folder():
    """Pasta para "Carregar sem compactacao". Rodando pelo codigo: extensao/ do
    projeto. No .exe: copia em <dados>/extensao (o Chrome guarda o caminho; a
    pasta do .exe de arquivo unico muda a cada abertura), atualizada quando o
    manifest muda. Devolve None se a extensao nao veio com o programa."""
    if not os.path.isfile(os.path.join(EXT_SRC, "manifest.json")):
        return None
    if not paths.FROZEN:
        return EXT_SRC
    src = _manifest(EXT_SRC)
    if _manifest(EXT_COPY) != src:
        shutil.copytree(EXT_SRC, EXT_COPY, dirs_exist_ok=True)
    return EXT_COPY


class Ponte(object):
    """Estado da extensao pareada, abas e fila de comandos."""

    def __init__(self, path=None):
        self.path = path or STATE_PATH
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.code, self.code_until, self.code_fails = None, 0.0, 0
        self.tabs, self.tabs_at, self.seen = [], 0.0, 0.0
        self.queue = collections.deque()
        self.polls = 0
        self._paired = None
        self._load()

    # ------------------------------------------------------------ disco ---
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and ORIGIN_RE.match("chrome-extension://%s" % d.get("ext_id")) \
                    and isinstance(d.get("key"), str) and len(d["key"]) >= 32:
                self._paired = {"ext_id": d["ext_id"], "key": d["key"], "at": d.get("at") or 0}
        except (OSError, ValueError):
            self._paired = None

    def _save(self):
        tmp = self.path + ".tmp"
        if self._paired is None:
            try:
                os.remove(self.path)
            except OSError:
                pass
            return
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._paired, f)
        os.replace(tmp, self.path)

    # -------------------------------------------------------- pareamento ---
    def new_code(self):
        with self.lock:
            self.code = "".join(secrets.choice(CODE_ABC) for _ in range(CODE_LEN))
            self.code_until = time.time() + CODE_TTL
            self.code_fails = 0
            return self.code

    def pair(self, ext_id, code):
        """Troca o codigo pela chave longa. Devolve a chave."""
        if not isinstance(ext_id, str) or not re.match(r"^[a-p]{32}$", ext_id):
            raise BrowserError("extensao invalida")
        code = str(code or "").strip().upper().replace("-", "").replace(" ", "")
        with self.lock:
            if not self.code or time.time() > self.code_until:
                self.code = None
                raise BrowserError("codigo vencido: gere outro em Conectar > Navegador")
            if not hmac.compare_digest(code.encode("utf-8"), self.code.encode("utf-8")):
                self.code_fails += 1
                if self.code_fails >= CODE_TRIES:
                    self.code = None
                raise BrowserError("codigo errado")
            self.code = None
            key = secrets.token_hex(32)
            self._paired = {"ext_id": ext_id, "key": key, "at": int(time.time())}
            self.tabs, self.seen = [], time.time()
            self.queue.clear()
            self._save()
        print("* extensao do navegador pareada")
        return key

    def unpair(self):
        with self.cond:
            self._paired = None
            self.code = None
            self.tabs, self.seen = [], 0.0
            self.queue.clear()
            self._save()
            self.cond.notify_all()
        print("* extensao do navegador despareada")

    def check(self, ext_id, key):
        """A extensao (id do Origin) e a chave conferem com o pareamento?"""
        p = self._paired
        if not p or not isinstance(key, str) or not key:
            return False
        same_id = hmac.compare_digest(str(ext_id).encode("utf-8"), p["ext_id"].encode("utf-8"))
        same_key = hmac.compare_digest(key.encode("utf-8"), p["key"].encode("utf-8"))
        return same_id and same_key

    def paired(self):
        return self._paired is not None

    # ----------------------------------------------------------- abas ---
    def set_tabs(self, tabs):
        if not isinstance(tabs, list):
            raise BrowserError("lista de abas invalida")
        clean = [c for c in (_clean_tab(t) for t in tabs[:MAX_TABS]) if c]
        with self.lock:
            self.tabs, self.tabs_at, self.seen = clean, time.time(), time.time()
        return len(clean)

    def connected(self):
        if not self._paired:
            return False
        return self.polls > 0 or 0 <= time.time() - self.seen < ONLINE_S

    def tab_list(self):
        with self.lock:
            return [dict(t) for t in self.tabs] if self.connected() else []

    # -------------------------------------------------------- comandos ---
    def push(self, cmd):
        with self.cond:
            now = time.time()
            while self.queue and (len(self.queue) >= MAX_QUEUE or now - self.queue[0][0] > CMD_TTL):
                self.queue.popleft()
            self.queue.append((now, cmd))
            self.cond.notify_all()

    def wait(self, timeout=POLL_MAX):
        """Long-poll da extensao: devolve a lista de comandos (pode ser vazia).
        None = long-polls demais ao mesmo tempo."""
        timeout = max(0.0, min(float(timeout), POLL_MAX))
        with self.cond:
            if self.polls >= MAX_POLLS:
                return None
            self.polls += 1
            self.seen = time.time()
            try:
                end = time.time() + timeout
                while not self.queue and self._paired:
                    left = end - time.time()
                    if left <= 0:
                        break
                    self.cond.wait(left)
                now = time.time()
                out = [c for (t, c) in self.queue if now - t <= CMD_TTL]
                self.queue.clear()
                return out
            finally:
                self.polls -= 1
                self.seen = time.time()

    def can(self, op):
        """A extensao faz este comando? Rolar so no YouTube (unico site com
        permissao de script); pausar so se houver aba do YouTube."""
        if not self.connected():
            return False
        if op == "scroll":
            return any(t["current"] and t["yt"] for t in self.tabs)
        if op == "yt_toggle":
            return any(t["yt"] for t in self.tabs)
        return True

    def status(self):
        p = self._paired
        return {"paired": bool(p), "connected": self.connected(), "ext_id": p["ext_id"] if p else None,
                "paired_at": p["at"] if p else None, "last_seen": int(self.seen) if self.seen else None,
                "tabs": len(self.tabs) if self.connected() else 0,
                "code": self.code if self.code and time.time() < self.code_until else None,
                "code_left": max(0, int(self.code_until - time.time())) if self.code else 0}


PONTE = Ponte()


# ------------------------------------------------------------- execucao ---
def _foreground_exe():
    try:
        from . import windows
        return (windows.foreground_exe() or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _open_default(url):
    if paths.IS_WINDOWS:
        import webbrowser
        webbrowser.open(url)
    else:
        print("  [simulado] abrir site:", url)


def fallback(cmd):
    """Mesma acao por atalhos de teclado na janela em primeiro plano."""
    op = cmd["op"]
    if op == "activate":
        raise BrowserError("escolher aba precisa da extensao (Conectar > Navegador)")
    if op == "open_url":
        if _foreground_exe() in BROWSER_EXES:
            winapi.send_keys(["ctrl", "l"])
            time.sleep(0.15)
            winapi.type_text(cmd["url"], enter=True)
        else:
            _open_default(cmd["url"])
        return "keys"
    k = KEYS["scroll:" + cmd["dir"]] if op == "scroll" else KEYS[op]
    winapi.send_keys(k)
    return "keys"


def execute(cmd, ponte=None):
    """Roda o comando: pela extensao se ela estiver ligada, senao por atalhos.
    Devolve "ext" ou "keys"."""
    ponte = ponte or PONTE
    cmd = check_cmd(cmd)
    if ponte.can(cmd["op"]):
        ponte.push(cmd)
        return "ext"
    return fallback(cmd)
