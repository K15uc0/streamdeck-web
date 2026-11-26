# -*- coding: utf-8 -*-
"""Apoio dos testes: pasta de dados temporaria (STREAMDECK_DATA) antes de
importar o pacote streamdeck, raiz do projeto no sys.path e utilidades.
Importe este modulo ANTES de qualquer "from streamdeck import ...":
paths.BASE e calculado uma vez, na importacao."""
import atexit
import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if not os.environ.get("STREAMDECK_TEST_DATA"):
    _data = tempfile.mkdtemp(prefix="sd-teste-")
    os.environ["STREAMDECK_TEST_DATA"] = _data
    atexit.register(shutil.rmtree, _data, True)
DATA = os.environ["STREAMDECK_TEST_DATA"]
os.environ["STREAMDECK_DATA"] = DATA
# nunca consultar o GitHub durante os testes
os.environ.setdefault("STREAMDECK_UPDATE_URL", "http://127.0.0.1:9/sem-rede")

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
       b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


def fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as f:
        return json.load(f)


def base_config():
    """Config v2 pequeno e valido usado pelos testes."""
    return copy.deepcopy({
        "version": 2,
        "title": "Teste",
        "columns": 4,
        "rows": 2,
        "pages": [
            {"name": "Um", "buttons": [
                {"label": "ON AIR", "icon": "onair", "color": "#ff453a", "toggle": True,
                 "action": {"type": "none"}},
                {"label": "Copiar", "icon": "copy", "color": "#0a84ff",
                 "action": {"type": "hotkey", "keys": ["ctrl", "c"]}},
                {"label": "Oi", "action": {"type": "text", "text": "Ola!", "enter": True}},
                {"kind": "folder", "label": "Pasta", "icon": "folder", "buttons": [
                    {"label": "Dentro", "toggle": True, "action": {"type": "none"}},
                    {"label": "Tecla", "action": {"type": "hotkey", "keys": ["f5"]}},
                ]},
                {"kind": "fader", "label": "Master", "icon": "sound", "target": "master"},
                {"label": "Ir 2", "action": {"type": "page", "to": 1}},
            ]},
            {"name": "Dois", "buttons": [
                {"label": "Voltar", "action": {"type": "page", "to": 0}},
            ]},
        ],
    })


def write_config(cfg):
    """Grava o config.json direto no disco (sem passar pela API)."""
    from streamdeck import paths
    with open(paths.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    # mtime pode nao mudar em sistemas de arquivos grossos: forca releitura
    from streamdeck import storage
    storage.CONFIG_CACHE["key"] = None


class _Sock(object):
    """Socket falso: o Handler le o pedido de um BytesIO e escreve em outro."""

    def __init__(self, raw):
        self.rin = io.BytesIO(raw)
        self.out = _Out()

    def makefile(self, mode, *a, **k):
        return self.rin if "r" in mode else self.out

    def setsockopt(self, *a):
        pass

    def settimeout(self, *a):
        pass

    def sendall(self, data):
        self.out.write(data)


class _Out(io.BytesIO):
    def close(self):   # o Handler fecha no fim; o conteudo continua legivel
        pass


class _Srv(object):
    server_address = ("127.0.0.1", 8765)


def fake_request(method, path, ip="192.168.0.50", headers=None, body=b""):
    """Chama o Handler de verdade como se o pedido viesse de ip (sem rede).
    Devolve (status, cabecalhos dict minusculo, corpo bytes)."""
    from streamdeck.httpd import Handler
    h = {"Host": "127.0.0.1:8765", "X-StreamDeck": "1", "Connection": "close"}
    h.update(headers or {})
    if body:
        h["Content-Length"] = str(len(body))
    lines = ["%s %s HTTP/1.1" % (method, path)] + ["%s: %s" % kv for kv in h.items() if kv[1] is not None]
    raw = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body
    sock = _Sock(raw)
    Handler(sock, (ip, 50000), _Srv())
    resp = sock.out.getvalue()
    head, _, payload = resp.partition(b"\r\n\r\n")
    hl = head.decode("iso-8859-1").split("\r\n")
    status = int(hl[0].split()[1])
    hdrs = {}
    for line in hl[1:]:
        k, _, v = line.partition(":")
        hdrs[k.strip().lower()] = v.strip()
    if "content-length" in hdrs:     # so a primeira resposta
        payload = payload[:int(hdrs["content-length"])]
    return status, hdrs, payload


@contextlib.contextmanager
def quiet():
    """Esconde o que o servidor imprime (log) durante o bloco."""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


# Os testes nunca mandam teclas de verdade (no Windows o SendInput iria para a
# maquina): send_keys/type_text so anotam o pedido em KEYS.
KEYS = []


def _patch_keys():
    from streamdeck import winapi
    orig = winapi.send_keys

    def send_keys(keys):
        [winapi.vk_of(k) for k in keys]     # mesma validacao das teclas
        KEYS.append(("keys", list(keys)))

    def type_text(text, enter=False):
        KEYS.append(("text", text, bool(enter)))
    send_keys.orig = orig
    winapi.send_keys = send_keys
    winapi.type_text = type_text


_patch_keys()


# Som tambem simulado nos testes: o Windows do CI nao tem placa de som (o MCI
# falha ao iniciar) e os testes conferem so a contabilidade (lista, duracao,
# fades), nao o audio de verdade.
def _patch_audio():
    from streamdeck import audio
    audio.IS_WINDOWS = False


_patch_audio()


# Monitor tambem simulado: no Windows do CI a lista real de processos nao tem
# os processos de exemplo que os testes encerram. Testes so-Windows religam.
def _patch_monitor():
    from streamdeck import monitor
    monitor.IS_WINDOWS = False


_patch_monitor()
