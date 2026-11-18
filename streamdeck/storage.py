# -*- coding: utf-8 -*-
"""Arquivos de dados: JSON atomico, config (cache, versao, migracao), abas,
ajustes de seguranca e codigo de acesso."""
import json
import os
import re
import secrets
import shutil
import threading
import time

from . import paths, schema

FILE_LOCK = threading.Lock()


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


# ---------------------------------------------------------------- config ---
def ensure_config():
    """Na primeira execucao cria o config.json a partir do padrao."""
    if not os.path.exists(paths.CONFIG_PATH):
        shutil.copyfile(paths.DEFAULT_CONFIG, paths.CONFIG_PATH)
        return True
    return False


CONFIG_CACHE = {"key": None, "data": None}


def config_version():
    """Muda sempre que o config.json muda (os aparelhos usam para se atualizar)."""
    try:
        st = os.stat(paths.CONFIG_PATH)
        return "%d-%d" % (st.st_mtime_ns, st.st_size)
    except OSError:
        return "0"


def _migrate_file(data, raw):
    """Config antigo no disco: guarda copia (config.v1.bak.json) e grava o novo."""
    new, changed = schema.migrate(data)
    if not changed:
        return data
    try:
        with open(paths.CONFIG_V1_BAK, "wb") as f:
            f.write(raw)
    except OSError as e:
        print("  aviso: sem copia do config antigo (%s)" % e)
    try:
        schema.validate_config(new)
    except ValueError as e:
        print("  aviso: config migrado tem problemas: %s" % e)
    write_json(paths.CONFIG_PATH, new)
    print("* configuracao atualizada para a versao %d (copia em %s)"
          % (schema.CONFIG_VERSION, os.path.basename(paths.CONFIG_V1_BAK)))
    return new


def load_config():
    """Le o config.json; relido do disco so quando o arquivo muda.
    Config antigo (v1) e migrado na hora."""
    with FILE_LOCK:
        key = config_version()
        if CONFIG_CACHE["key"] != key or CONFIG_CACHE["data"] is None:
            with open(paths.CONFIG_PATH, "rb") as f:
                raw = f.read()
            data = _migrate_file(json.loads(raw.decode("utf-8-sig")), raw)
            CONFIG_CACHE["data"] = data
            CONFIG_CACHE["key"] = config_version()
        return CONFIG_CACHE["data"]


def save_config(cfg):
    cfg, _ = schema.migrate(cfg)   # aparelho com pagina antiga em cache
    schema.validate_config(cfg)
    with FILE_LOCK:
        if os.path.exists(paths.CONFIG_PATH):
            try:
                with open(paths.CONFIG_PATH, "rb") as f:
                    old = f.read()
                with open(paths.CONFIG_BAK, "wb") as f:
                    f.write(old)
            except OSError as e:
                print("  aviso: sem copia de seguranca (%s)" % e)
        write_json(paths.CONFIG_PATH, cfg)


# ------------------------------------------------------------------ abas ---
HOST_RE = re.compile(r"^[A-Za-z0-9.\-]{1,90}(:\d{1,5})?$")
CODE_RE = re.compile(r"^[A-Za-z0-9]{0,64}$")


def load_tabs():
    try:
        with open(paths.TABS_PATH, "r", encoding="utf-8") as f:
            tabs = json.load(f)
        return tabs if isinstance(tabs, list) else []
    except (OSError, ValueError):
        return []


def save_tabs(tabs):
    if not isinstance(tabs, list) or len(tabs) > 30:
        raise ValueError("lista de abas invalida")
    clean = []
    for t in tabs:
        if not isinstance(t, dict):
            raise ValueError("aba invalida")
        host, code = str(t.get("host", "")).strip(), str(t.get("code", "")).strip()
        if not HOST_RE.match(host) or not CODE_RE.match(code):
            raise ValueError("aba invalida: %s" % host[:40])
        clean.append({"name": str(t.get("name", ""))[:40], "host": host, "code": code})
    with FILE_LOCK:
        write_json(paths.TABS_PATH, clean)


# --------------------------------------------------------------- ajustes ---
def load_settings():
    try:
        with open(paths.SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    with FILE_LOCK:
        write_json(paths.SETTINGS_PATH, data)


# ------------------------------------------------------- codigo de acesso ---
def _read_token():
    if os.path.exists(paths.TOKEN_PATH):
        with open(paths.TOKEN_PATH) as f:
            tok = f.read().strip()
            if tok:
                return tok
    return new_token()


def new_token():
    tok = secrets.token_hex(8)   # 64 bits
    with open(paths.TOKEN_PATH, "w") as f:
        f.write(tok)
    _TOKEN[0] = tok
    return tok


_TOKEN = [None]


def token():
    """Codigo de acesso atual (lido do disco na primeira vez)."""
    if _TOKEN[0] is None:
        _TOKEN[0] = _read_token()
    return _TOKEN[0]
