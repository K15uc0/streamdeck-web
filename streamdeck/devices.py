# -*- coding: utf-8 -*-
"""Aparelhos (2.11): cada celular/tablet tem a sua chave.

O primeiro acesso com o codigo geral (QR, /?k=) cria um aparelho com chave
propria, guardada no cookie sdk (HttpOnly). Depois disso o aparelho entra
so pela chave dele: remover o aparelho corta o acesso na hora, sem trocar
o codigo geral dos outros.

Arquivo: aparelhos.json na pasta de dados (gravacao atomica, sob trava).
As chaves nunca saem daqui: list_public()/find() devolvem copias sem "key".
Comparacao das chaves em tempo constante (hmac.compare_digest), sempre
contra todos os aparelhos (sem sair no primeiro que bate)."""
import copy
import hmac
import json
import os
import re
import secrets
import threading
import time

from . import paths, schema, storage

MAX_DEVICES = 50          # evita lista sem fim (o codigo geral cria aparelhos)
TOUCH_EVERY = 60          # ultimo acesso: grava no disco no maximo a cada 60 s
UPGRADE_TTL = 120         # cookie antigo: pedidos juntos reaproveitam o mesmo aparelho
NAME_MAX = 40
KEY_RE = re.compile(r"^[0-9a-f]{32}$")
PUBLIC = ("id", "name", "created", "last_seen", "last_ip", "pages", "full")

LOCK = threading.RLock()
_CACHE = {"data": None, "mtime": None, "broken": False}
_WRITTEN = {}             # id -> quando o ultimo acesso foi gravado
_UPGRADES = {}            # (ip, navegador) -> (id, quando)


class DevicesError(Exception):
    """aparelhos.json ilegivel ou cheio: nada e gravado."""


def _now():
    return time.time()


def reset():
    """Esquece o que esta na memoria (testes; arquivo trocado por fora)."""
    with LOCK:
        _CACHE.update(data=None, mtime=None, broken=False)
        _WRITTEN.clear()
        _UPGRADES.clear()


def _mtime():
    try:
        return os.stat(paths.DEVICES_PATH).st_mtime_ns
    except OSError:
        return None


def _load():
    """Dados atuais (relidos se o arquivo mudou). Chame com LOCK."""
    mt = _mtime()
    if _CACHE["data"] is not None and mt == _CACHE["mtime"]:
        return _CACHE["data"]
    data, broken = {"devices": []}, False
    if mt is not None:
        try:
            with open(paths.DEVICES_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict) or not isinstance(raw.get("devices"), list):
                raise ValueError("formato invalido")
            raw["devices"] = [d for d in raw["devices"] if isinstance(d, dict)
                              and isinstance(d.get("key"), str) and KEY_RE.match(d["key"])
                              and isinstance(d.get("id"), str)]
            data = raw
        except (OSError, ValueError):
            broken = True
            print("! aparelhos.json ilegivel: nenhum aparelho entra ate corrigir ou apagar o arquivo")
    _CACHE.update(data=data, mtime=mt, broken=broken)
    return data


def _save(data):
    """Grava atomico (arquivo .tmp + replace). Chame com LOCK."""
    if _CACHE["broken"]:
        raise DevicesError("aparelhos.json ilegivel; nada foi gravado")
    storage.write_json(paths.DEVICES_PATH, data)
    _CACHE.update(data=data, mtime=_mtime())


def _public(d):
    out = dict((k, copy.deepcopy(d.get(k))) for k in PUBLIC)
    out["full"] = d.get("full") is True
    return out


def _by_id(data, dev_id):
    for d in data["devices"]:
        if d["id"] == dev_id:
            return d
    raise KeyError("aparelho nao encontrado")


def _kind(ua):
    ua = ua or ""
    for word, name in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                       ("Windows", "PC"), ("Macintosh", "Mac"), ("Linux", "Aparelho")):
        if word in ua:
            return name
    return "Aparelho"


# ------------------------------------------------------------ migracao ---
def migrate():
    """Uma vez so (sem aparelhos.json): o antigo "Permitir encerrar
    programas" (allow_kill) vira Controle total dos aparelhos que ja
    existiam, isto e, os que chegarem com o cookie antigo (codigo geral)."""
    with LOCK:
        if _mtime() is not None:
            return
        legacy = storage.load_settings().get("allow_kill") is True
        _CACHE["broken"] = False
        _save({"devices": [], "legacy_full": legacy})
        _CACHE["data"] = None
    try:
        storage.update_settings(lambda s: s.pop("allow_kill", None))
    except storage.SettingsError:
        pass


# ------------------------------------------------------------- criacao ---
def create(name=None, ua="", ip="", full=False):
    """Novo aparelho. Devolve o registro completo (com a chave, para o cookie)."""
    with LOCK:
        if _mtime() is None:
            migrate()
        data = _load()
        if _CACHE["broken"]:
            raise DevicesError("aparelhos.json ilegivel; nada foi gravado")
        if len(data["devices"]) >= MAX_DEVICES:
            raise DevicesError("limite de %d aparelhos; remova algum em Conectar" % MAX_DEVICES)
        now = int(_now())
        ids = set(d["id"] for d in data["devices"])
        dev_id = secrets.token_hex(4)
        while dev_id in ids:
            dev_id = secrets.token_hex(4)
        dev = {"id": dev_id, "key": secrets.token_hex(16),
               "name": name or "%s %d" % (_kind(ua), len(data["devices"]) + 1),
               "created": now, "last_seen": now, "last_ip": ip or "", "pages": None,
               "full": full is True}
        data = dict(data, devices=data["devices"] + [dev])
        _save(data)
        _WRITTEN[dev_id] = now
        return dict(dev)


def upgrade(ip, ua):
    """Cookie antigo (codigo geral): cria o aparelho (ou devolve o criado ha
    pouco para o mesmo IP e navegador, ja que a pagina faz varios pedidos
    juntos). Devolve o registro completo, com a chave."""
    with LOCK:
        now = _now()
        for k, (_, t) in list(_UPGRADES.items()):
            if now - t > UPGRADE_TTL or now < t:
                del _UPGRADES[k]
        hit = _UPGRADES.get((ip, ua or ""))
        if hit:
            try:
                return dict(_by_id(_load(), hit[0]))
            except KeyError:
                pass
        if _mtime() is None:
            migrate()
        legacy = _load().get("legacy_full") is True
        dev = create(ua=ua, ip=ip, full=legacy)
        _UPGRADES[(ip, ua or "")] = (dev["id"], now)
        return dev


# ------------------------------------------------------------- consulta ---
def find(key):
    """Aparelho da chave (copia sem a chave) ou None."""
    if not isinstance(key, str) or not KEY_RE.match(key):
        return None
    k = key.encode("ascii")
    with LOCK:
        hit = None
        for d in _load()["devices"]:
            if hmac.compare_digest(d["key"].encode("ascii"), k):
                hit = d
        return _public(hit) if hit else None


def get(dev_id):
    with LOCK:
        try:
            return _public(_by_id(_load(), dev_id))
        except KeyError:
            return None


def list_public():
    with LOCK:
        return [_public(d) for d in _load()["devices"]]


def touch(dev_id, ip):
    """Ultimo acesso: sempre na memoria; no disco no maximo a cada 60 s."""
    with LOCK:
        data = _load()
        try:
            d = _by_id(data, dev_id)
        except KeyError:
            return
        now = _now()
        moved = d.get("last_ip") != ip
        d["last_seen"], d["last_ip"] = int(now), ip
        last = _WRITTEN.get(dev_id, 0)
        if moved or now - last >= TOUCH_EVERY or now < last:
            try:
                _save(data)
                _WRITTEN[dev_id] = now
            except (DevicesError, OSError):
                pass


# ----------------------------------------------------------- alteracoes ---
def _change(dev_id, fn):
    with LOCK:
        data = copy.deepcopy(_load())
        fn(_by_id(data, dev_id))
        _save(data)


def rename(dev_id, name):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > NAME_MAX \
            or any(ord(c) < 32 for c in name):
        raise ValueError("nome invalido (1 a %d letras)" % NAME_MAX)
    _change(dev_id, lambda d: d.__setitem__("name", name.strip()))


def set_pages(dev_id, pages):
    """None = todas; lista de indices (0 a MAX_PAGES-1)."""
    if pages is not None:
        if not isinstance(pages, list) or any(
                not isinstance(p, int) or isinstance(p, bool) or p < 0 or p >= schema.MAX_PAGES for p in pages):
            raise ValueError("paginas invalidas")
        pages = sorted(set(pages))
    _change(dev_id, lambda d: d.__setitem__("pages", pages))


def set_full(dev_id, full):
    if not isinstance(full, bool):
        raise ValueError("full deve ser true ou false")
    _change(dev_id, lambda d: d.__setitem__("full", full))


def remove(dev_id):
    """Tira o aparelho: a chave dele deixa de valer no proximo pedido."""
    with LOCK:
        data = _load()
        rest = [d for d in data["devices"] if d["id"] != dev_id]
        if len(rest) == len(data["devices"]):
            return False
        _save(dict(data, devices=rest))
        _WRITTEN.pop(dev_id, None)
        for k, v in list(_UPGRADES.items()):
            if v[0] == dev_id:
                del _UPGRADES[k]
        return True


# ---------------------------------------------------------- permissoes ---
def page_allowed(pages, p):
    return pages is None or p in pages


SENSITIVE = ("command", "open", "app")   # rodam programa/comando qualquer no PC


def sensitive(a):
    """A acao exige Controle total quando vem de um aparelho? command (tambem
    desligar/reiniciar/suspender da biblioteca), open de arquivo/programa (site
    http/https nao), app (abre programa) e sequencias com algum desses."""
    if not isinstance(a, dict):
        return False
    t = a.get("type")
    if t == "open":
        return not str(a.get("target") or "").startswith(("http://", "https://"))
    if t in SENSITIVE:
        return True
    if t == "multi":
        return any(sensitive(s) for s in (a.get("steps") or []) if isinstance(s, dict))
    return False
