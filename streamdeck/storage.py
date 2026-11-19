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
    _backup_bytes(raw)
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


def save_config(cfg, force=False):
    """Grava o config. Antes, guarda o estado ANTERIOR no historico se a
    ultima copia tem mais de BACKUP_EVERY segundos (ou sempre, com force):
    assim o salvamento automatico do editor nao enche o historico e a copia
    representa o estado de antes da sessao de edicao."""
    cfg, _ = schema.migrate(cfg)   # aparelho com pagina antiga em cache
    schema.validate_config(cfg)
    with FILE_LOCK:
        if os.path.exists(paths.CONFIG_PATH):
            try:
                with open(paths.CONFIG_PATH, "rb") as f:
                    old = f.read()
                with open(paths.CONFIG_BAK, "wb") as f:
                    f.write(old)
                if force or _backup_due():
                    _backup_bytes(old)
            except OSError as e:
                print("  aviso: sem copia de seguranca (%s)" % e)
        write_json(paths.CONFIG_PATH, cfg)


# ------------------------------------------------------ historico (copias) ---
BACKUP_KEEP = 20
BACKUP_EVERY = 600   # segundos entre copias automaticas
# novo: config-<seq 6>-AAAAMMDD-HHMMSS.json ; antigo: config-AAAAMMDD-HHMMSS[-n].json
BACKUP_RE = re.compile(r"^config-(?:\d{6}-\d{8}-\d{6}|\d{8}-\d{6}(?:-\d{1,3})?)\.json$")
NEW_RE = re.compile(r"^config-(\d{6})-(\d{8}-\d{6})\.json$")
_LAST = {"t": None}   # relogio (_clock) da ultima copia feita nesta execucao


def _clock():
    """Relogio usado pelo historico (trocado nos testes)."""
    return time.time()


def backups_dir():
    return os.path.join(paths.BASE, "backups")


def _key(n):
    m = NEW_RE.match(n)
    if m:
        return (1, int(m.group(1)), "", 0)
    base = n[:-5].split("-")
    return (0, 0, base[1] + base[2], int(base[3]) if len(base) > 3 else 0)


def _backup_names():
    """Nomes das copias validas, da mais nova para a mais antiga (pela
    sequencia; as antigas, sem sequencia, vem antes pela data do nome)."""
    try:
        names = [n for n in os.listdir(backups_dir()) if BACKUP_RE.match(n)]
    except OSError:
        return []
    return sorted(names, key=_key, reverse=True)


def _stamp_of(n):
    m = NEW_RE.match(n)
    return m.group(2) if m else n[7:22]


def _backup_due():
    """True se a ultima copia foi feita ha mais de BACKUP_EVERY segundos."""
    now = _clock()
    last = _LAST["t"]
    if last is None:
        names = _backup_names()
        if not names:
            return True
        try:
            last = os.path.getmtime(os.path.join(backups_dir(), names[0]))
        except OSError:
            return True
    # relogio voltou para tras: conta como vencido (copia a mais e inofensiva)
    return now - last > BACKUP_EVERY or now < last


def _next_seq(folder, names):
    seq = 0
    try:
        with open(os.path.join(folder, "seq.txt"), "r") as f:
            seq = int(f.read().strip() or 0)
    except (OSError, ValueError):
        pass
    for n in names:
        m = NEW_RE.match(n)
        if m:
            seq = max(seq, int(m.group(1)))
    seq += 1
    with open(os.path.join(folder, "seq.txt"), "w") as f:
        f.write(str(seq))
    return seq


def _backup_bytes(raw):
    """Guarda raw como copia (se diferente da mais nova) e mantem so as
    BACKUP_KEEP mais recentes. Nunca levanta erro."""
    try:
        if not raw:
            return None
        folder = backups_dir()
        os.makedirs(folder, exist_ok=True)
        names = _backup_names()
        _LAST["t"] = _clock()
        if names:
            try:
                with open(os.path.join(folder, names[0]), "rb") as f:
                    if f.read() == raw:
                        return names[0]
            except OSError:
                pass
        seq = _next_seq(folder, names)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(_clock()))
        name = "config-%06d-%s.json" % (seq % 1000000, stamp)
        with open(os.path.join(folder, name), "wb") as f:
            f.write(raw)
        for old in _backup_names()[BACKUP_KEEP:]:
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass
        return name
    except Exception as e:  # noqa: BLE001 - copia nunca impede de salvar
        print("  aviso: sem copia no historico (%s)" % e)
        return None


def _backup_file():
    try:
        with open(paths.CONFIG_PATH, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    return _backup_bytes(raw)


def backup_current():
    """Copia o config.json atual para o historico (antes de importar/restaurar)."""
    with FILE_LOCK:
        return _backup_file()


def _backup_path(name):
    if not isinstance(name, str) or not BACKUP_RE.match(name):
        raise ValueError("nome de copia invalido")
    full = os.path.join(backups_dir(), name)
    if not paths.inside(full, backups_dir()) or not os.path.isfile(full):
        raise KeyError("copia nao encontrada")
    return full


def read_backup(name):
    with open(_backup_path(name), "rb") as f:
        return json.loads(f.read().decode("utf-8-sig"))


def _norm(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def list_backups():
    try:
        cur = _norm(load_config())
    except Exception:  # noqa: BLE001
        cur = None
    out = []
    for n in _backup_names():
        full = os.path.join(backups_dir(), n)
        item = {"name": n, "when": 0, "size": 0, "pages": 0, "buttons": 0, "current": False}
        try:
            try:
                item["when"] = int(time.mktime(time.strptime(_stamp_of(n), "%Y%m%d-%H%M%S")))
            except (ValueError, OverflowError):
                item["when"] = int(os.path.getmtime(full))
            item["size"] = os.path.getsize(full)
            data, _ = schema.migrate(read_backup(n))
            item["current"] = cur is not None and _norm(data) == cur
            pages = data.get("pages") or []
            item["pages"] = len(pages)
            item["buttons"] = sum(len([x for x in (p.get("buttons") or []) if schema._used(x)])
                                  for p in pages if isinstance(p, dict))
        except Exception:  # noqa: BLE001 - copia estragada ainda aparece
            pass
        out.append(item)
    return out


def restore_backup(name):
    """Valida a copia, guarda o atual no historico e restaura."""
    data, _ = schema.migrate(read_backup(name))
    schema.validate_config(data)
    save_config(data, force=True)
    return config_version()


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


SETTINGS_HOOKS = []    # funcoes (data) chamadas depois de salvar os ajustes


def save_settings(data):
    with FILE_LOCK:
        write_json(paths.SETTINGS_PATH, data)
    for fn in list(SETTINGS_HOOKS):
        try:
            fn(data)
        except Exception:
            pass


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
