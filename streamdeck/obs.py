# -*- coding: utf-8 -*-
"""Cliente do OBS (obs-websocket v5, porta 4455) so com a biblioteca padrao.

- WebSocket (RFC 6455) minimo sobre socket: handshake do cliente com
  conferencia do Sec-WebSocket-Accept, quadros do cliente mascarados, texto,
  ping/pong, close e mensagens fragmentadas.
- Protocolo v5: Hello (op 0) -> Identify (op 1, com autenticacao SHA-256
  quando o OBS pede senha) -> Identified (op 2); Request (op 6) /
  RequestResponse (op 7) com requestId; eventos (op 5) atualizam o estado.
- Uma thread em segundo plano conecta e reconecta a cada 5 s. Os pedidos dos
  botoes esperam no maximo ~3 s e nunca travam o servidor HTTP.
Ajustes (host, port, password) ficam em seguranca.json, chave "obs"."""
import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4455
RETRY = 5.0                # segundos entre tentativas de conexao
TIMEOUT = 3.0              # espera maxima de um pedido
IDLE = 15.0                # silencio maximo antes do keepalive (GetVersion)
FETCH_TRIES = 3            # tentativas de carregar o estado inicial
MAX_MSG = 16 * 1024 * 1024
MAX_MUTE_INPUTS = 40       # fontes de audio consultadas ao conectar
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# inscricoes de eventos (EventSubscription do obs-websocket)
SUB_GENERAL, SUB_SCENES, SUB_INPUTS, SUB_OUTPUTS = 1 << 0, 1 << 2, 1 << 3, 1 << 6
SUBSCRIPTIONS = SUB_GENERAL | SUB_SCENES | SUB_INPUTS | SUB_OUTPUTS

OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class ObsError(Exception):
    pass


# --------------------------------------------------------------- WebSocket ---
def accept_key(key):
    """Valor esperado do Sec-WebSocket-Accept para a chave do cliente."""
    return base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")


def auth_string(password, salt, challenge):
    """base64(sha256(base64(sha256(senha + salt)) + challenge))."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode("utf-8")).digest())
    return base64.b64encode(hashlib.sha256(secret + challenge.encode("utf-8")).digest()).decode("ascii")


def encode_frame(opcode, payload=b"", mask=True, fin=True, mask_key=None):
    """Um quadro WebSocket. Cliente sempre mascara (mask=True)."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    head = bytearray([(0x80 if fin else 0) | (opcode & 0x0F)])
    n = len(payload)
    mbit = 0x80 if mask else 0
    if n < 126:
        head.append(mbit | n)
    elif n < 65536:
        head.append(mbit | 126)
        head += struct.pack("!H", n)
    else:
        head.append(mbit | 127)
        head += struct.pack("!Q", n)
    if mask:
        key = mask_key if mask_key is not None else os.urandom(4)
        head += key
        payload = _mask(payload, key)
    return bytes(head) + payload


def _mask(data, key):
    if not data:
        return b""
    # xor rapido com inteiros grandes (sem numpy)
    n = len(data)
    k = (key * (n // 4 + 1))[:n]
    return (int.from_bytes(data, "big") ^ int.from_bytes(k, "big")).to_bytes(n, "big")


def _kill(sock):
    """Derruba o socket (shutdown desbloqueia um recv parado em outra thread)."""
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def _recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("conexao fechada")
        buf += chunk
    return bytes(buf)


def read_frame(recv):
    """Le um quadro com recv(n) -> bytes exatos. Devolve (fin, opcode, payload)."""
    b1, b2 = recv(2)
    fin, op = bool(b1 & 0x80), b1 & 0x0F
    masked, n = bool(b2 & 0x80), b2 & 0x7F
    if n == 126:
        n = struct.unpack("!H", recv(2))[0]
    elif n == 127:
        n = struct.unpack("!Q", recv(8))[0]
    if n > MAX_MSG:
        raise ValueError("mensagem grande demais")
    key = recv(4) if masked else None
    data = recv(n) if n else b""
    if key:
        data = _mask(data, key)
    return fin, op, data


def decode_frame(data):
    """Decodifica um quadro de bytes. Devolve (fin, opcode, payload, resto)."""
    pos = [0]

    def recv(n):
        if pos[0] + n > len(data):
            raise ValueError("quadro incompleto")
        out = data[pos[0]:pos[0] + n]
        pos[0] += n
        return out
    fin, op, payload = read_frame(recv)
    return fin, op, payload, data[pos[0]:]


class WebSocket(object):
    """Conexao WebSocket de cliente (sem TLS; o OBS fica na rede local)."""

    def __init__(self, host, port, path="/", timeout=TIMEOUT, protocol="obswebsocket.json", on_sock=None):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass
        self.send_lock = threading.Lock()
        self.closed = False
        if on_sock is not None:
            on_sock(self.sock)    # permite derrubar a conexao durante o handshake
        try:
            self._handshake(host, port, path, protocol)
        except Exception:
            self.sock.close()
            raise

    def _handshake(self, host, port, path, protocol):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n" % (path, host, port, key))
        if protocol:
            req += "Sec-WebSocket-Protocol: %s\r\n" % protocol
        self.sock.sendall((req + "\r\n").encode("ascii"))
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1)
            if not chunk:
                raise ConnectionError("o servidor fechou a conexao no handshake")
            head += chunk
            if len(head) > 16384:
                raise ConnectionError("resposta de handshake grande demais")
        lines = head.decode("iso-8859-1").split("\r\n")
        parts = lines[0].split()
        if len(parts) < 2 or parts[1] != "101":
            raise ConnectionError("handshake recusado: %s" % lines[0])
        hdrs = {}
        for line in lines[1:]:
            k, _, v = line.partition(":")
            hdrs[k.strip().lower()] = v.strip()
        if hdrs.get("sec-websocket-accept") != accept_key(key):
            raise ConnectionError("Sec-WebSocket-Accept invalido")

    def send_text(self, text):
        self._send(OP_TEXT, text.encode("utf-8"))

    def _send(self, op, data):
        with self.send_lock:
            self.sock.sendall(encode_frame(op, data))

    def recv_text(self):
        """Proxima mensagem de texto (junta fragmentos, responde ping).
        None quando a conexao fecha."""
        parts, first_op = [], None
        while True:
            fin, op, data = read_frame(self._frame_reader())
            if op == OP_PING:
                self._send(OP_PONG, data)
                continue
            if op == OP_PONG:
                continue
            if op == OP_CLOSE:
                try:
                    self._send(OP_CLOSE, data[:2])
                except OSError:
                    pass
                self.closed = True
                return None
            if op in (OP_TEXT, OP_BIN):
                parts, first_op = [data], op
            elif op == OP_CONT and first_op is not None:
                parts.append(data)
            else:
                raise ValueError("quadro inesperado (%d)" % op)
            if fin:
                msg = b"".join(parts)
                if first_op == OP_TEXT:
                    return msg.decode("utf-8")
                parts, first_op = [], None   # binario: ignora

    def _frame_reader(self):
        """recv(n) para um quadro: timeout so escapa antes do primeiro byte;
        no meio do quadro espera mais um pouco (senao o fluxo se perderia)."""
        started = [False]

        def recv(n):
            buf, tries = bytearray(), 0
            while len(buf) < n:
                try:
                    chunk = self.sock.recv(n - len(buf))
                except socket.timeout:
                    if not started[0] and not buf:
                        raise
                    tries += 1
                    if tries > 3:
                        raise ConnectionError("quadro incompleto do OBS")
                    continue
                if not chunk:
                    raise ConnectionError("conexao fechada")
                started[0] = True
                buf += chunk
            return bytes(buf)
        return recv

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self._send(OP_CLOSE, struct.pack("!H", 1000))
            except OSError:
                pass
        _kill(self.sock)


# ------------------------------------------------------------- obs-websocket ---
def _empty_state():
    return {"ok": False, "stream": False, "record": False, "scene": "", "muted": {}}


class ObsClient(object):
    """Conexao mantida em segundo plano com o OBS e estado em cache."""

    def __init__(self, settings=None, inputs_wanted=None):
        # settings: funcao () -> {"host", "port", "password"} (ou None = padrao)
        self.settings = settings or (lambda: {})
        self.inputs_wanted = inputs_wanted or (lambda: [])
        self.lock = threading.Lock()
        self.ws = None
        self.pending = {}          # requestId -> [Event, resposta]
        self.n = 0
        self.state = _empty_state()
        self.scenes, self.inputs = [], []
        self.error = ""
        self.wake = threading.Event()
        self.stopped = False
        self.thread = None
        self.retry = RETRY
        self.idle = IDLE
        self.gen = 0               # geracao dos ajustes (reconnect/stop incrementa)
        self.neg = None            # socket em negociacao (antes do Identified)
        self.mute_ev = {}          # fonte -> instante do ultimo evento de mute

    # --------------------------------------------------------- ciclo ---
    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, name="obs", daemon=True)
            self.thread.start()

    def stop(self):
        self.stopped = True
        self._bump()
        self.wake.set()
        self._drop()

    def reconnect(self):
        """Ajustes mudaram: derruba a conexao (inclusive a em negociacao) e
        tenta de novo ja."""
        self._bump()
        self.error = ""
        self._drop()
        self.wake.set()
        self.start()

    def _bump(self):
        with self.lock:
            self.gen += 1
            sock, self.neg = self.neg, None
        if sock is not None:
            _kill(sock)

    def connected(self):
        ws = self.ws
        return ws is not None and not ws.closed

    def _loop(self):
        while not self.stopped:
            self.wake.clear()
            gen = self.gen
            try:
                self._session(gen)
            except Exception as e:
                # queda pedida por reconnect/stop nao e erro
                if gen == self.gen and not self.stopped:
                    self.error = _friendly(e)
            self._drop()
            if self.stopped:
                break
            self.wake.wait(self.retry)

    def _drop(self):
        with self.lock:
            ws, self.ws = self.ws, None
            self.state = dict(_empty_state())
            self.mute_ev = {}
            for item in self.pending.values():
                item[0].set()
            self.pending = {}
        if ws is not None:
            ws.close()

    def _session(self, gen=None):
        if gen is None:
            gen = self.gen
        cfg = self.settings() or {}
        host = cfg.get("host") or DEFAULT_HOST
        port = int(cfg.get("port") or DEFAULT_PORT)

        def hold(sock):
            with self.lock:
                if gen == self.gen and not self.stopped:
                    self.neg = sock
                    return
            _kill(sock)
            raise ObsError("conexao cancelada")
        ws = WebSocket(host, port, on_sock=hold)
        try:
            self._negotiate(ws, cfg)
        finally:
            with self.lock:
                if self.neg is ws.sock:
                    self.neg = None
        with self.lock:
            if self.stopped or gen != self.gen:
                stale = True
            else:
                stale = False
                self.ws = ws
                self.state = dict(_empty_state())
                self.state["ok"] = True
        if stale:
            ws.close()
            return
        self.error = ""
        threading.Thread(target=self._fetch_all, args=(ws,), daemon=True).start()
        ws.sock.settimeout(self.idle)
        waiting = False
        while True:
            try:
                msg = ws.recv_text()
            except socket.timeout:
                if waiting:
                    raise ObsError("o OBS parou de responder")
                waiting = True
                # keepalive leve; a resposta (sem pedido pendente) e ignorada
                ws.send_text(json.dumps({"op": 6, "d": {"requestType": "GetVersion", "requestId": "ka"}}))
                continue
            waiting = False
            if msg is None:
                raise ObsError("o OBS fechou a conexao")
            try:
                self._dispatch(json.loads(msg))
            except (ValueError, TypeError, AttributeError, KeyError):
                pass

    def _negotiate(self, ws, cfg):
        ws.sock.settimeout(TIMEOUT)
        hello = json.loads(ws.recv_text() or "{}")
        if hello.get("op") != 0:
            ws.close()
            raise ObsError("resposta inesperada do OBS")
        d = hello.get("d") or {}
        ident = {"rpcVersion": 1, "eventSubscriptions": SUBSCRIPTIONS}
        auth = d.get("authentication")
        if auth:
            pw = cfg.get("password") or ""
            if not pw:
                ws.close()
                raise ObsError("o OBS pede senha: informe a senha do WebSocket")
            ident["authentication"] = auth_string(pw, auth.get("salt", ""), auth.get("challenge", ""))
        ws.send_text(json.dumps({"op": 1, "d": ident}))
        msg = ws.recv_text()
        if msg is None:
            ws.close()
            raise ObsError("senha do OBS errada" if auth else "o OBS recusou a conexao")
        if json.loads(msg).get("op") != 2:
            ws.close()
            raise ObsError("resposta inesperada do OBS")

    def _dispatch(self, m):
        op, d = m.get("op"), m.get("d") or {}
        if op == 7:
            with self.lock:
                item = self.pending.pop(d.get("requestId"), None)
            if item is not None:
                item[1] = d
                item[0].set()
        elif op == 5:
            self._event(d.get("eventType"), d.get("eventData") or {})

    def _event(self, kind, data):
        st = self.state
        if kind == "CurrentProgramSceneChanged":
            st["scene"] = data.get("sceneName", "")
        elif kind == "StreamStateChanged":
            st["stream"] = bool(data.get("outputActive"))
        elif kind == "RecordStateChanged":
            st["record"] = bool(data.get("outputActive"))
        elif kind == "InputMuteStateChanged":
            muted = dict(st["muted"])     # copia: snapshot() pode estar lendo
            name = data.get("inputName", "")
            muted[name] = bool(data.get("inputMuted"))
            self.mute_ev[name] = time.time()
            st["muted"] = muted
        elif kind == "SceneListChanged":
            self.scenes = [s.get("sceneName", "") for s in reversed(data.get("scenes") or [])]
        elif kind in ("InputCreated", "InputRemoved", "InputNameChanged"):
            threading.Thread(target=self._fetch_inputs, daemon=True).start()

    def _fetch_all(self, ws=None):
        """Carrega o estado inicial; falha nao derruba a conexao: tenta de
        novo algumas vezes com espera crescente."""
        delay = 0.5
        for n in range(FETCH_TRIES):
            if ws is not None and self.ws is not ws:
                return
            try:
                self._fetch_once()
                return
            except Exception as e:
                if ws is not None and self.ws is not ws:
                    return
                self.error = _friendly(e)
                print("  obs: falha ao carregar o estado (tentativa %d): %s" % (n + 1, self.error))
            time.sleep(delay)
            delay *= 2

    def _fetch_once(self):
        r = self.request("GetCurrentProgramScene")
        self.state["scene"] = r.get("currentProgramSceneName") or r.get("sceneName") or ""
        self.state["stream"] = bool(self.request("GetStreamStatus").get("outputActive"))
        self.state["record"] = bool(self.request("GetRecordStatus").get("outputActive"))
        scenes = self.request("GetSceneList").get("scenes") or []
        self.scenes = [s.get("sceneName", "") for s in reversed(scenes)]   # ordem da lista do OBS
        self._fetch_inputs()
        self.error = ""

    def _fetch_inputs(self):
        inputs = self.request("GetInputList").get("inputs") or []
        self.inputs = [i.get("inputName", "") for i in inputs]
        wanted = [n for n in (self.inputs_wanted() or []) if n in self.inputs]
        audio = [i.get("inputName", "") for i in inputs
                 if "audio" in str(i.get("inputKind", "")) or "wasapi" in str(i.get("inputKind", ""))]
        names = list(dict.fromkeys(wanted + audio))[:MAX_MUTE_INPUTS]
        got = {}
        for name in names:
            t0 = time.time()
            try:
                got[name] = (bool(self.request("GetInputMute", {"inputName": name}).get("inputMuted")), t0)
            except ObsError:
                pass   # fonte sem audio
        # junta por fonte sem passar por cima de eventos mais novos que o pedido
        with self.lock:
            muted = dict(self.state["muted"])
            for name, (val, t0) in got.items():
                if self.mute_ev.get(name, 0) < t0:
                    muted[name] = val
            self.state["muted"] = muted

    # ------------------------------------------------------- pedidos ---
    def request(self, kind, data=None, timeout=TIMEOUT):
        """Manda um pedido ao OBS e devolve responseData (dict).
        Levanta ObsError com mensagem em portugues."""
        with self.lock:
            ws = self.ws
            if ws is None:
                raise ObsError("OBS nao esta conectado" + (" (%s)" % self.error if self.error else ""))
            self.n += 1
            rid = "sd%d" % self.n
            item = [threading.Event(), None]
            self.pending[rid] = item
        d = {"requestType": kind, "requestId": rid}
        if data:
            d["requestData"] = data
        try:
            ws.send_text(json.dumps({"op": 6, "d": d}))
        except OSError:
            with self.lock:
                self.pending.pop(rid, None)
            raise ObsError("OBS nao esta conectado")
        if not item[0].wait(timeout):
            with self.lock:
                self.pending.pop(rid, None)
            raise ObsError("o OBS nao respondeu a tempo")
        resp = item[1]
        if resp is None:
            raise ObsError("OBS nao esta conectado")
        st = resp.get("requestStatus") or {}
        if not st.get("result"):
            raise ObsError("o OBS recusou %s: %s" % (kind, st.get("comment") or "codigo %s" % st.get("code")))
        return resp.get("responseData") or {}

    def snapshot(self):
        st = self.state
        return {"ok": bool(st["ok"] and self.ws is not None), "stream": st["stream"], "record": st["record"],
                "scene": st["scene"], "muted": dict(st["muted"])}


def _friendly(e):
    if isinstance(e, ObsError):
        return str(e)
    if isinstance(e, ConnectionRefusedError):
        return "OBS fechado ou WebSocket desligado (Ferramentas > Configurações do WebSocket)"
    if isinstance(e, socket.timeout):
        return "o OBS nao respondeu"
    return "sem conexao com o OBS (%s)" % e


# --------------------------------------------------------- ajustes e global ---
def load_settings():
    """{"host", "port", "password"} salvos (ou {})."""
    from . import storage
    obs = storage.load_settings().get("obs")
    return obs if isinstance(obs, dict) else {}


_CACHE = {"obs": None}


def cached_settings():
    """Ajustes do OBS em memoria (renovados quando seguranca.json e salvo)."""
    c = _CACHE["obs"]
    if c is None:
        c = _CACHE["obs"] = load_settings()
    return c


def _settings_saved(data):
    obs = data.get("obs") if isinstance(data, dict) else None
    _CACHE["obs"] = dict(obs) if isinstance(obs, dict) else {}


def save_settings(body):
    """Valida e grava host/port/senha. Senha ausente mantem a anterior;
    senha "" apaga."""
    from . import storage
    if not isinstance(body, dict):
        raise ValueError("dados invalidos")
    host = str(body.get("host") or DEFAULT_HOST).strip()
    if not host or len(host) > 253 or any(c in host for c in " /\\@?#\r\n"):
        raise ValueError("endereco do OBS invalido")
    port = body.get("port", DEFAULT_PORT)
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ValueError("porta do OBS invalida")
    if not (1 <= port <= 65535):
        raise ValueError("porta do OBS invalida")
    data = storage.load_settings()
    old = data.get("obs") if isinstance(data.get("obs"), dict) else {}
    new = {"host": host, "port": port, "password": old.get("password", "")}
    if "password" in body and body["password"] is not None:
        pw = str(body["password"])
        if len(pw) > 200:
            raise ValueError("senha longa demais")
        new["password"] = pw
    data["obs"] = new
    storage.save_settings(data)
    return new


def lit_inputs():
    """Fontes citadas em lit "obs:mute=<fonte>" e acoes obs_mute do config."""
    from . import storage
    out = []
    try:
        cfg = storage.load_config()
    except Exception:
        return out

    def scan(b):
        if not isinstance(b, dict):
            return
        lit = b.get("lit")
        if isinstance(lit, str) and lit.startswith("obs:mute="):
            out.append(lit[9:])
        for k in ("action", "hold", "double"):
            a = b.get(k)
            if isinstance(a, dict) and a.get("type") == "obs_mute" and a.get("input"):
                out.append(str(a["input"]))
        for x in b.get("buttons") or [] if b.get("kind") == "folder" else []:
            scan(x)
    for pg in cfg.get("pages") or []:
        for b in (pg.get("buttons") or []) if isinstance(pg, dict) else []:
            scan(b)
    return out


CLIENT = ObsClient(load_settings, lit_inputs)


def _register_hook():
    from . import storage
    if _settings_saved not in storage.SETTINGS_HOOKS:
        storage.SETTINGS_HOOKS.append(_settings_saved)


_register_hook()


def status():
    """GET /api/local/obs."""
    s = load_settings()
    return {"ok": True, "host": s.get("host") or DEFAULT_HOST, "port": int(s.get("port") or DEFAULT_PORT),
            "has_password": bool(s.get("password")), "connected": CLIENT.connected(), "error": CLIENT.error}


def state_for_api():
    """Bloco "obs" do /api/state, ou None se nunca configurado nem conectado."""
    if CLIENT.ws is None and not cached_settings():
        return None
    return CLIENT.snapshot()


def request(kind, data=None):
    return CLIENT.request(kind, data)


def start():
    CLIENT.start()
