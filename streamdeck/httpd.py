# -*- coding: utf-8 -*-
"""Servidor HTTP e tabela de rotas.

Ordem das barreiras (nao mudar):
  todo pedido: rede local -> Host deste PC -> limite de tentativas
  GET : /ping.gif | /conectar, /editar e /api/local/* so no PC | "/?k=" grava cookie |
        /api/*: cabecalho X-StreamDeck/Origin -> codigo de acesso -> rota | arquivos de web/
  POST: cabecalho X-StreamDeck/Origin -> /api/local/* so no PC | codigo de acesso -> rota
        (POST /api/config so no PC)
"""
import json
import os
import shutil
import tempfile
import posixpath
import re
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import VERSION, actions, agenda, audio, diag, library, media, obs, paths, schema, security, state, storage, updates, \
    tocando, templates, windows, winapi

SYNC_RE = re.compile(r"^[A-Za-z0-9%._~!*'()\-]{0,8000}$")
DRAIN_MAX = 256 * 1024 * 1024    # corpo grande demais: descarta ate isso antes de responder

PIXEL = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
         b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")

MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript",
        ".css": "text/css", ".png": "image/png", ".json": "application/json", ".svg": "image/svg+xml",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
        ".ico": "image/x-icon"}

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: http:; connect-src 'self'; frame-ancestors 'none'; "
       "base-uri 'none'; form-action 'none'")

TEXT = "text/plain; charset=utf-8"
QUIET = ("/ping.gif", "/api/state", "/api/volume")   # nao aparecem no log
SEEN = set()

# (metodo, caminho) -> metodo do Handler. Rotas /api/local/* so respondem no proprio PC.
ROUTES = {
    ("GET", "/api/local/info"): "local_info",
    ("GET", "/api/local/hello"): "local_hello",
    ("POST", "/api/local/quit"): "local_quit",
    ("GET", "/api/update"): "get_update",
    ("GET", "/api/state"): "get_state",
    ("GET", "/api/volume"): "get_volume",
    ("GET", "/api/config"): "get_config",
    ("GET", "/api/actions"): "get_actions",
    ("GET", "/api/info"): "get_info",
    ("GET", "/api/press"): "get_press",
    ("GET", "/api/library"): "get_library",
    ("GET", "/api/templates"): "get_templates",
    ("GET", "/api/images"): "get_images",
    ("GET", "/api/local/windows"): "local_windows",
    ("GET", "/api/local/export"): "local_export",
    ("GET", "/api/local/backups"): "local_backups",
    ("GET", "/api/local/diag"): "local_diag",
    ("POST", "/api/local/backups/restore"): "local_backup_restore",
    ("POST", "/api/local/openlog"): "local_openlog",
    ("POST", "/api/local/images"): "local_images",
    ("POST", "/api/local/import"): "local_import",
    ("POST", "/api/local/autostart"): "local_autostart",
    ("POST", "/api/local/sounds"): "local_sounds",
    ("POST", "/api/local/data"): "local_data",
    ("POST", "/api/local/test"): "local_test",
    ("POST", "/api/local/newcode"): "local_newcode",
    ("GET", "/api/local/obs"): "local_obs",
    ("POST", "/api/local/obs"): "local_obs_save",
    ("GET", "/api/local/obs/scenes"): "local_obs_scenes",
    ("GET", "/api/local/schedules"): "local_schedules",
    ("POST", "/api/local/schedules/run"): "local_schedules_run",
    ("POST", "/api/update/check"): "post_update_check",
    ("POST", "/api/update/apply"): "post_update_apply",
    ("POST", "/api/config"): "post_config",
    ("POST", "/api/tabs"): "post_tabs",
}
# gesto do /api/press -> campo do botao com a acao
PRESS_KINDS = {"tap": "action", "hold": "hold", "double": "double"}
# paginas e arquivos que so abrem no proprio PC
# rotas do PC cujo corpo e um arquivo (bytes), com o limite de tamanho;
# /api/local/sounds so com ?name= (sem ele, abre a pasta sons)
RAW_POST = {"/api/local/images": media.MAX_IMAGE, "/api/local/sounds": media.MAX_SOUND,
            "/api/local/import": media.MAX_IMPORT}
LOCAL_PAGES = ("/conectar", "/conectar.html", "/editar", "/editar.html",
               "/css/editar.css", "/js/editar.js")


def _norm_path(path):
    """Caminho do pedido normalizado (// viram /, sem . e .., minusculo)."""
    p = re.sub(r"/+", "/", (path or "/").replace("\\", "/"))
    p = posixpath.normpath(p).lower()
    return p if p.startswith("/") else "/" + p


def _local_files():
    """Arquivos reais (normcase) das paginas que so abrem no proprio PC."""
    out = set()
    for p in LOCAL_PAGES:
        if p.endswith((".html", ".css", ".js")):
            out.add(os.path.normcase(os.path.realpath(os.path.join(paths.WEB_DIR, p.lstrip("/")))))
    return out


def is_local_only(path, full=None):
    """O pedido (ou o arquivo resolvido full) so pode ser atendido no proprio PC?"""
    n = _norm_path(path)
    if n in LOCAL_PAGES or n.startswith("/api/local/") or n == "/api/local":
        return True
    if full is not None and os.path.normcase(os.path.realpath(full)) in _local_files():
        return True
    return False


BACKUP_PREFIX = "/api/local/backups/"   # GET /api/local/backups/<nome>
NO_CODE = {("GET", "/api/local/info")}       # ja restritas ao proprio PC
# do proprio PC (tela Conectar/Editar) a API nao pede o codigo de acesso


def _int(q, name):
    return int(q[name][0])


_DIAG_CACHE = {"plat": None, "addr": None, "addr_t": 0.0}


def _platform_str():
    """Texto da plataforma (calculado uma vez so)."""
    if _DIAG_CACHE["plat"] is None:
        try:
            import platform
            _DIAG_CACHE["plat"] = platform.platform()
        except Exception:  # noqa: BLE001
            _DIAG_CACHE["plat"] = sys.platform
    return _DIAG_CACHE["plat"]


def _addresses():
    """Enderecos IPv4 guardados por 60 s."""
    now = time.time()
    if _DIAG_CACHE["addr"] is None or now - _DIAG_CACHE["addr_t"] > 60:
        _DIAG_CACHE["addr"] = diag.ipv4_addresses()
        _DIAG_CACHE["addr_t"] = now
    return _DIAG_CACHE["addr"]


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.1: atende "Expect: 100-continue" e conexoes mantidas abertas,
    # que o navegador antigo do Android usa. timeout evita conexoes presas.
    protocol_version = "HTTP/1.1"
    timeout = 30
    disable_nagle_algorithm = True   # resposta sai na hora (sem atraso de ate 200 ms por toque)
    wbufsize = 65536                 # cabecalhos e corpo no mesmo pacote
    server_version = "StreamDeck"
    sys_version = ""

    def handle_expect_100(self):
        ok = super().handle_expect_100()
        self.wfile.flush()   # o "pode enviar" precisa sair ja (navegador antigo do Android)
        return ok

    # --------------------------------------------------------------- log ---
    def log_message(self, fmt, *args):
        pass

    def log_error(self, fmt, *args):
        raw = getattr(self, "raw_requestline", b"") or b""
        raw = re.sub(rb"k=[^&\s]*", b"k=***", raw[:60])
        kind = " (tentativa de HTTPS: use http://)" if raw[:1] == b"\x16" else ""
        print("  pedido invalido de %s: %s%s %r" % (self.client_address[0], fmt % args, kind, raw[:30]))

    def log_request(self, code="-", size="-"):
        path = (getattr(self, "path", "") or "").split("?")[0]
        if not path:
            return
        if path in QUIET or (path == "/api/config" and self.command == "GET" and code == 200):
            return
        print("  %s %s %s -> %s" % (self.client_address[0], self.command, path, code))

    def _note_client(self):
        ip = self.client_address[0]
        if ip not in SEEN:
            SEEN.add(ip)
            print("  novo aparelho conectado: %s  [%s]" % (ip, time.strftime("%H:%M:%S")))

    # ---------------------------------------------------------- resposta ---
    def _security_headers(self, html=False):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if html:
            self.send_header("Content-Security-Policy", CSP)

    def _send(self, code, body, ctype="application/json; charset=utf-8", cors_img=False, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Connection", "close" if self.close_connection else "keep-alive")
        self.send_header("Content-Length", str(len(body)))
        if not (extra and "Cache-Control" in extra):
            self.send_header("Cache-Control", "no-store")
        if extra:
            for name, value in extra.items():
                self.send_header(name, value)
        if cors_img:   # ping.gif precisa ser carregado pelas abas de outros PCs
            self.send_header("X-Content-Type-Options", "nosniff")
        else:
            self._security_headers(html=ctype.startswith("text/html"))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.wfile.flush()

    def _json(self, code, obj, extra=None):
        self._send(code, json.dumps(obj, ensure_ascii=False, separators=(",", ":")), extra=extra)

    # ----------------------------------------------------------- pedido ---
    def _local(self):
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _body_json(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n <= 0:
            return {}
        if n > 2000000:
            raise ValueError("tamanho invalido (%d)" % n)
        raw = b""
        while len(raw) < n:
            chunk = self.rfile.read(n - len(raw))
            if not chunk:
                break
            raw += chunk
        return json.loads(raw.decode("utf-8"))

    def _body_file(self, limit):
        """Corpo bruto num arquivo temporario (ate limit bytes). Se passar do
        limite, descarta o corpo (ate DRAIN_MAX) antes de recusar, para a
        resposta chegar ao navegador; acima disso so fecha a conexao."""
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n <= 0:
            raise ValueError("arquivo vazio")
        if n > limit:
            self.close_connection = True
            if n <= DRAIN_MAX:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk:
                        break
                    left -= len(chunk)
            raise ValueError("arquivo grande demais (maximo %d MB)" % (limit // (1024 * 1024)))
        tmp = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024)
        left = n
        while left > 0:
            chunk = self.rfile.read(min(65536, left))
            if not chunk:
                break
            tmp.write(chunk)
            left -= len(chunk)
        if left:
            tmp.close()
            raise ValueError("envio incompleto")
        tmp.seek(0)
        return tmp

    def _cookie_token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "sdk":
                return value
        return ""

    def _authed(self, q):
        return security.same_token((q.get("k") or [""])[0]) or security.same_token(self._cookie_token())

    def _deny_auth(self):
        security.note_fail(self.client_address[0])
        return self._json(403, {"ok": False, "error": "codigo de acesso invalido"})

    def _api_header_ok(self):
        """Sites de terceiros nao conseguem mandar cabecalhos proprios para ca
        (o navegador bloqueia), e o Origin, quando vem, tem de ser este PC."""
        if self.headers.get("X-StreamDeck") != "1":
            return False
        origin = self.headers.get("Origin")
        if origin and origin != "null":
            host = urlparse(origin).netloc
            if not security.host_allowed(host) or host.lower() != (self.headers.get("Host") or "").lower():
                return False
        return True

    def _guard(self):
        """Barreiras aplicadas a todo pedido. Devolve False se ja respondeu."""
        ip = self.client_address[0]
        if not security.ip_allowed(ip):
            print("! recusado: %s nao e da rede local" % ip)
            self.close_connection = True
            self._send(403, "Somente rede local.", TEXT)
            return False
        if not security.host_allowed(self.headers.get("Host")):
            self.close_connection = True
            self._send(421, "Endereco nao reconhecido. Use o IP deste PC.", TEXT)
            return False
        if security.fail_blocked(ip):
            self.close_connection = True
            self._send(429, "Muitas tentativas com codigo errado. Aguarde 10 minutos.", TEXT)
            return False
        self._note_client()
        return True

    def _route(self, method, path, q):
        name = ROUTES.get((method, path))
        if name is None:
            return self._json(404, {"ok": False})
        return getattr(self, name)(q)

    # ------------------------------------------------------------- POST ---
    def do_POST(self):
        if not self._guard():
            return
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if not self._api_header_ok():
            return self._json(403, {"ok": False, "error": "pedido recusado"})

        # funcoes so do proprio PC (tela de conexao)
        if url.path.startswith("/api/local/"):
            if not self._local():
                return self._json(403, {"ok": False, "error": "so no proprio PC"})
            if ("POST", url.path) not in ROUTES:
                return self._json(404, {"ok": False})
            try:
                if url.path in RAW_POST and (url.path != "/api/local/sounds" or "name" in q):
                    name = ROUTES[("POST", url.path)]
                    if url.path == "/api/local/sounds":
                        name = "local_sound_upload"
                    with self._body_file(RAW_POST[url.path]) as f:
                        return getattr(self, name)(q, f)
                return self._route("POST", url.path, self._body_json())
            except Exception as e:
                return self._json(400, {"ok": False, "error": str(e)})

        if not (self._local() or self._authed(q)):
            print("! pedido recusado de %s: codigo de acesso ausente ou errado" % self.client_address[0])
            return self._deny_auth()
        if not self._local():
            diag.note_client(self.client_address[0], self.headers.get("User-Agent"))
        return self._route("POST", url.path, q)

    # -------------------------------------------------------------- GET ---
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._guard():
            return
        url = urlparse(self.path)
        q = parse_qs(url.query)
        k = (q.get("k") or [""])[0]

        # sinal de vida para as abas de outros aparelhos (imagem 1x1, sem dados)
        if url.path == "/ping.gif":
            return self._send(200, PIXEL, "image/gif", cors_img=True)

        # tela de conexao: so no proprio PC
        if is_local_only(url.path):
            if not self._local():
                return self._send(403, "Abra esta pagina no proprio PC.", TEXT)
        if url.path in ("/conectar", "/editar"):
            url = url._replace(path=url.path + ".html")

        # primeiro acesso com o codigo: guarda no navegador e limpa o endereco
        if url.path == "/" and k:
            return self._first_access(url, k)

        # imagens dos botoes: <img> nao manda cabecalho, entao so o codigo
        if url.path.startswith("/img/"):
            if not (self._authed(q) or self._local()):
                # imagens nao contam como tentativa de codigo errado
                return self._send(403, "acesso negado", TEXT)
            from urllib.parse import unquote
            found = media.image_file(unquote(url.path[5:]))
            if not found:
                return self._send(404, "nao encontrado", TEXT)
            with open(found[0], "rb") as f:
                data = f.read()
            return self._send(200, data, found[1], extra={"Cache-Control": "private, max-age=3600"})

        if url.path.startswith("/api/"):
            if not self._api_header_ok():
                return self._json(403, {"ok": False, "error": "pedido recusado"})
            key = ("GET", url.path)
            if key not in NO_CODE and not (self._authed(q) or self._local()):
                return self._deny_auth()
            if not self._local():
                diag.note_client(self.client_address[0], self.headers.get("User-Agent"))
            if url.path.startswith(BACKUP_PREFIX) and self._local():
                return self.local_backup_get(url.path[len(BACKUP_PREFIX):])
            return self._route("GET", url.path, q)

        return self._static(url.path)

    def _first_access(self, url, k):
        if not security.same_token(k):
            security.note_fail(self.client_address[0])
            return self._send(403, "Codigo de acesso invalido. Leia o QR code de novo na tela do PC.", TEXT)
        sync = ""
        for part in url.query.split("&"):
            if part.startswith("sync="):
                sync = part[5:]
        if not SYNC_RE.match(sync):
            sync = ""
        self.send_response(302)
        self.send_header("Set-Cookie", "sdk=%s; Max-Age=315360000; Path=/; HttpOnly; SameSite=Strict"
                         % storage.token())
        self.send_header("Location", "/#sync=" + sync if sync else "/")
        self.send_header("Content-Length", "0")
        self._security_headers()
        self.end_headers()
        self.wfile.flush()

    def _static(self, path):
        """Arquivos estaticos (so de dentro da pasta web)."""
        if path == "/":
            path = "/index.html"
        full = os.path.join(paths.WEB_DIR, path.lstrip("/").replace("\\", "/"))
        if not paths.inside(full, paths.WEB_DIR) or not os.path.isfile(full):
            return self._send(404, "nao encontrado", "text/plain")
        if is_local_only(path, full) and not self._local():
            return self._send(403, "Abra esta pagina no proprio PC.", TEXT)
        with open(full, "rb") as f:
            data = f.read()
        ext = os.path.splitext(full)[1].lower()
        ctype = MIME.get(ext, "application/octet-stream")
        if _norm_path(path) == "/manifest.json":
            ctype = "application/manifest+json"
        self._send(200, data, ctype)

    # ======================================================== rotas GET ===
    def local_hello(self, q):
        """Usado por uma copia nova para saber se esta porta e do Stream Deck."""
        return self._json(200, {"ok": True, "app": "streamdeck", "pid": os.getpid()})

    def local_quit(self, body):
        """Uma copia nova pediu a porta: responde e fecha este servidor."""
        print("* pedido para fechar pela API local (outra copia, instalador ou tela Conectar); encerrando.")
        self._json(200, {"ok": True})

        def bye():
            time.sleep(0.3)
            try:
                from . import tray
                tray.stop()       # tira o icone da bandeja antes de sair
            except Exception:
                pass
            os._exit(0)
        threading.Thread(target=bye, daemon=True).start()

    def local_info(self, q):
        base = "http://%s:%d" % (security.lan_ip(), state.PORT[0])
        tok = storage.token()
        return self._json(200, {"ok": True, "base": base, "first": "%s/?k=%s" % (base, tok),
                                "code": tok, "weak": len(tok) < 16,
                                "name": socket.gethostname(), "autostart": winapi.autostart_enabled(),
                                "windows": paths.IS_WINDOWS, "data": paths.BASE,
                                "settings": storage.load_settings(), "update": updates.update_status()})

    def get_update(self, q):
        return self._json(200, updates.update_status())

    def get_state(self, q):
        """Consulta leve e frequente dos aparelhos."""
        st = {"ok": True, "v": storage.config_version(), "update": bool(updates.UPDATE["available"])}
        try:
            st["toggles"] = state.toggles(storage.load_config())
        except Exception:
            st["toggles"] = state.toggles()
        try:
            st["since"] = state.since(storage.load_config())
        except Exception:
            st["since"] = state.since()
        st["app"] = windows.foreground_exe()
        st["sounds"] = audio.PLAYER.sounds()
        ob = obs.state_for_api()
        if ob is not None:
            st["obs"] = ob
        tocando.touch()
        st["nowplaying"] = tocando.current()
        if q.get("levels") or q.get("mix"):
            st["levels"] = audio.levels()
        return self._json(200, st)

    def get_volume(self, q):
        try:
            if "c" in q:   # c = controle (master, effects, mic)
                v = q.get("v", [None])[0]
                mute = q.get("mute", [""])[0] == "toggle"
                audio.set_level(q["c"][0], None if v is None else int(v), toggle_mute=mute)
            return self._json(200, {"ok": True, "levels": audio.levels()})
        except Exception as e:
            return self._json(400, {"ok": False, "error": str(e)})

    def get_config(self, q):
        try:
            return self._json(200, storage.load_config(), extra={"X-Config-Version": storage.config_version()})
        except Exception as e:
            return self._json(500, {"ok": False, "error": str(e)})

    def get_actions(self, q):
        return self._json(200, {"ok": True, "actions": actions.schema()})

    def get_info(self, q):
        return self._json(200, {"ok": True, "name": socket.gethostname(),
                                "code": storage.token(), "sounds": audio.list_sounds(),
                                "tabs": storage.load_tabs(), "version": VERSION,
                                "local": self._local(),
                                "update": updates.update_status()})

    def get_press(self, q):
        g = (q.get("g") or ["tap"])[0] or "tap"
        if g not in PRESS_KINDS:
            return self._json(400, {"ok": False, "error": "gesto invalido"})
        try:
            p, b = _int(q, "p"), _int(q, "b")
            f = _int(q, "f") if (q.get("f") or [""])[0] != "" else None
            if p < 0 or b < 0 or (f is not None and f < 0):
                raise IndexError("botao inexistente")
            cfg = storage.load_config()
            btn = cfg["pages"][p]["buttons"][b]
            if f is not None:
                if btn.get("kind") != "folder":
                    raise ValueError("este botao nao e uma pasta")
                btn = btn["buttons"][f]
            elif btn.get("kind") == "folder":   # abrir a pasta acontece no aparelho
                return self._json(200, {"ok": True, "toggles": state.toggles(cfg)})
            if btn.get("kind", "button") != "button":
                raise ValueError("este controle nao e um botao")
            a = btn.get(PRESS_KINDS[g])
            if g != "tap" and not isinstance(a, dict):
                return self._json(400, {"ok": False, "error": "este botao nao tem acao %s" % (
                    "ao segurar" if g == "hold" else "no toque duplo")})
            print("> %s%s" % (btn.get("label") or "?", "" if g == "tap" else " (%s)" % g))
            actions.run(a or {"type": "none"}, key=state.key(p, b, f))
            if btn.get("toggle") is True and g == "tap":
                state.flip(p, b, f)
            return self._json(200, {"ok": True, "toggles": state.toggles(cfg)})
        except Exception as e:
            print("  erro:", e)
            return self._json(500, {"ok": False, "error": str(e)})

    def get_library(self, q):
        return self._json(200, {"ok": True, "groups": library.groups()})

    def get_templates(self, q):
        return self._json(200, {"ok": True, "templates": templates.templates()})

    def get_images(self, q):
        return self._json(200, {"ok": True, "images": media.list_images()})

    def local_windows(self, q):
        try:
            wins = [{"title": w["title"], "exe": w["exe"], "path": w["path"]} for w in windows.list_windows()]
        except Exception as e:
            print("  erro ao listar janelas:", e)
            wins = []
        return self._json(200, {"ok": True, "windows": wins})

    def local_export(self, q):
        tmp, name = media.export_zip()
        with tmp:
            tmp.seek(0, 2)
            size = tmp.tell()
            tmp.seek(0)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close" if self.close_connection else "keep-alive")
            self._security_headers()
            self.end_headers()
            if self.command != "HEAD":
                shutil.copyfileobj(tmp, self.wfile)
            self.wfile.flush()
        print("* copia de seguranca exportada (%s)" % name)

    def local_backups(self, q):
        return self._json(200, {"ok": True, "backups": storage.list_backups()})

    def local_backup_get(self, name):
        try:
            return self._json(200, schema.migrate(storage.read_backup(name))[0])
        except ValueError as e:
            return self._json(400, {"ok": False, "error": str(e)})
        except (KeyError, OSError):
            return self._json(404, {"ok": False, "error": "copia nao encontrada"})

    def local_diag(self, q):
        plat = _platform_str()
        try:
            auto = winapi.autostart_enabled()
        except Exception:  # noqa: BLE001
            auto = None
        return self._json(200, {
            "ok": True, "version": VERSION, "python": sys.version.split()[0], "frozen": paths.FROZEN,
            "platform": plat, "data_dir": paths.BASE, "port": state.PORT[0], "lan_ip": security.lan_ip(),
            "addresses": _addresses(), "uptime_s": int(time.time() - diag.STARTED),
            "clients": diag.clients(), "recent_errors": diag.recent_errors(), "log_path": paths.LOG_PATH,
            "autostart": auto, "update": updates.update_status()})

    # ======================================================= rotas POST ===
    def local_backup_restore(self, body):
        name = body.get("name") if isinstance(body, dict) else None
        try:
            v, n_off = storage.restore_backup(name)
        except KeyError:
            return self._json(404, {"ok": False, "error": "copia nao encontrada"})
        except (ValueError, OSError) as e:
            print("! erro ao restaurar copia: %s" % e)
            return self._json(400, {"ok": False, "error": str(e)})
        print("* versao anterior restaurada: %s" % name)
        return self._json(200, {"ok": True, "v": v, "schedules_disabled": n_off})

    def local_openlog(self, body):
        if paths.IS_WINDOWS:
            os.startfile(paths.LOG_PATH)   # noqa: S606 - arquivo fixo do proprio programa
        else:
            print("  (abriria o log: %s)" % paths.LOG_PATH)
        return self._json(200, {"ok": True})

    def local_images(self, q, f):
        name = media.save_image((q.get("name") or [""])[0], f.read())
        print("* imagem adicionada: %s" % name)
        return self._json(200, {"ok": True, "name": name})

    def local_sound_upload(self, q, f):
        name = media.save_sound((q.get("name") or [""])[0], f.read())
        print("* som adicionado: %s" % name)
        return self._json(200, {"ok": True, "name": name})

    def local_import(self, q, f):
        storage.backup_current()
        n_img, n_snd, n_off = media.import_zip(f)
        print("* copia de seguranca importada: %d imagem(ns), %d som(ns)" % (n_img, n_snd))
        return self._json(200, {"ok": True, "images": n_img, "sounds": n_snd,
                                "schedules_disabled": n_off, "v": storage.config_version()})

    def local_autostart(self, body):
        winapi.set_autostart(bool(body.get("on")))
        return self._json(200, {"ok": True, "autostart": winapi.autostart_enabled()})

    def local_sounds(self, body):
        winapi.open_folder(paths.SOUNDS_DIR)
        return self._json(200, {"ok": True})

    def local_data(self, body):
        winapi.open_folder(paths.BASE)
        return self._json(200, {"ok": True})

    def local_test(self, body):
        """Botao "Testar" do editor: valida e executa a acao sem salvar."""
        a = body.get("action") if isinstance(body, dict) else None
        try:
            try:
                n_pages = len(storage.load_config().get("pages") or [])
            except Exception:
                n_pages = schema.MAX_PAGES
            actions.validate(a, max(1, n_pages), "Teste")
            print("> teste: %s" % a.get("type"))
            actions.run(a)
            return self._json(200, {"ok": True})
        except Exception as e:
            print("  erro no teste:", e)
            return self._json(200, {"ok": False, "error": str(e)})

    def local_schedules(self, q):
        return self._json(200, agenda.AGENDA.status())

    def local_schedules_run(self, body):
        sid = body.get("id") if isinstance(body, dict) else None
        if not isinstance(sid, str) or not agenda.ID_RE.match(sid):
            return self._json(400, {"ok": False, "error": "id invalido"})
        err = agenda.AGENDA.run_now(sid)
        if err is None:
            return self._json(404, {"ok": False, "error": "agendamento nao encontrado"})
        if err:
            return self._json(200, {"ok": False, "error": err})
        return self._json(200, {"ok": True})

    def local_obs(self, q):
        return self._json(200, obs.status())

    def local_obs_save(self, body):
        obs.save_settings(body)
        obs.CLIENT.reconnect()
        print("* ajustes do OBS salvos")
        return self._json(200, obs.status())

    def local_obs_scenes(self, q):
        if not obs.CLIENT.connected():
            return self._json(200, {"ok": False, "error": "OBS nao esta conectado", "scenes": [], "inputs": []})
        return self._json(200, {"ok": True, "scenes": list(obs.CLIENT.scenes), "inputs": list(obs.CLIENT.inputs)})

    def local_newcode(self, body):
        storage.new_token()
        print("* novo codigo de acesso gerado; os aparelhos precisam ler o QR de novo")
        return self._json(200, {"ok": True})

    def post_update_check(self, q):
        updates.check_updates()
        return self._json(200, updates.update_status())

    def post_update_apply(self, q):
        if not updates.can_apply():
            return self._json(400, {"ok": False, "error": "atualizacao automatica indisponivel"})
        if updates.UPDATE["state"] not in ("downloading", "restarting"):
            threading.Thread(target=updates.apply_update, daemon=True).start()
        return self._json(200, {"ok": True})

    def post_tabs(self, q):
        try:
            storage.save_tabs(self._body_json())
            return self._json(200, {"ok": True})
        except Exception as e:
            print("! erro ao salvar:", e)
            return self._json(400, {"ok": False, "error": str(e)})

    def post_config(self, q):
        try:
            if not self._local():
                print("! edicao recusada de %s: a configuracao so e editada no PC" % self.client_address[0])
                return self._json(403, {"ok": False, "error": "edite pelo PC"})
            cfg = self._body_json()
            from . import agenda
            n_once = agenda.AGENDA.guard_once(cfg)   # once que ja rodou nao volta ligado
            storage.save_config(cfg)
            print("* configuracao salva")
            return self._json(200, {"ok": True, "v": storage.config_version(), "once_disabled": n_once})
        except Exception as e:
            print("! erro ao salvar:", e)
            return self._json(400, {"ok": False, "error": str(e)})


class Server(ThreadingHTTPServer):
    """Nao deixa duas copias do servidor dividirem a mesma porta (no Windows
    isso acontece por padrao e uma delas 'engole' os acessos)."""
    allow_reuse_address = not paths.IS_WINDOWS
    daemon_threads = True

    def handle_error(self, request, client_address):
        print("  conexao com %s falhou: %s" % (client_address[0], sys.exc_info()[1]))

    def server_bind(self):
        if paths.IS_WINDOWS:
            self.socket.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", -5), 1)
        super().server_bind()
