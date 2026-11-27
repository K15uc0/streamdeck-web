# -*- coding: utf-8 -*-
"""Notificacoes do Windows (2.12, experimental, desligado por padrao).

Le o banco local da central de notificacoes:
  %LOCALAPPDATA%\\Microsoft\\Windows\\Notifications\\wpndatabase.db
com sqlite3 so leitura (URI mode=ro); se estiver travado, copia o banco (e o
-wal/-shm) para uma pasta temporaria e le a copia.

ESQUEMA ASSUMIDO (nao documentado pela Microsoft; tirado de descricoes
publicas de analise forense do Windows 10/11, pode mudar ou diferir):
  Notification(Id INTEGER, HandlerId INTEGER, Type TEXT ('toast', 'tile',
               'badge'...), Payload BLOB/TEXT (XML do toast), ArrivalTime
               INTEGER (FILETIME: 100 ns desde 1601))
  NotificationHandler(RecordId INTEGER, PrimaryId TEXT (AppUserModelId ou
               nome do app))
So Id, HandlerId, Payload e ArrivalTime sao obrigatorios; Type e a tabela de
apps sao usados se existirem. Qualquer diferenca que impeca a leitura desliga
o recurso com o estado "indisponível nesta versão do Windows" (nunca derruba
o servidor).

Privacidade: o texto das notificacoes nunca vai para o log; so e entregue a
aparelhos com Controle total (e ao proprio PC).
"""
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from urllib.request import pathname2url

from . import avisos, paths

POLL_EVERY = 5.0
MAX_PER_POLL = 10
UNAVAILABLE = "indisponível nesta versão do Windows"
REQUIRED = ("Id", "HandlerId", "Payload", "ArrivalTime")


def db_path():
    base = os.environ.get("LOCALAPPDATA") or ""
    return os.path.join(base, "Microsoft", "Windows", "Notifications", "wpndatabase.db")


class SchemaError(Exception):
    """Banco sem as tabelas/colunas esperadas."""


# ---------------------------------------------------------------- parser ---
def filetime_to_epoch(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return v / 10000000.0 - 11644473600.0


def parse_toast(payload):
    """(titulo, texto) do XML de um toast, ou None se nao der para ler."""
    if payload is None:
        return None
    if isinstance(payload, (bytes, bytearray)):
        raw = bytes(payload)
        for enc in ("utf-8-sig", "utf-16"):
            try:
                payload = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return None
    payload = str(payload).strip().strip("\x00")
    if not payload or "<!DOCTYPE" in payload.upper() or "<!ENTITY" in payload.upper():
        return None    # sem DTD/entidades (XML de outro app nunca precisa)
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    if root.tag.split("}")[-1].lower() != "toast":
        return None
    texts = []
    for node in root.iter():
        if node.tag.split("}")[-1].lower() == "text":
            t = "".join(node.itertext()).strip()
            if t:
                texts.append(re.sub(r"\s+", " ", t))
    if not texts:
        return None
    return texts[0][:120], " ".join(texts[1:])[:300]


def app_name(primary):
    """Nome amigavel a partir do AppUserModelId/PrimaryId."""
    s = str(primary or "").strip()
    if not s:
        return "Windows"
    if "!" in s:                       # Pacote_hash!App
        pkg, app = s.split("!", 1)
        s = app if app.lower() not in ("app", "application") else pkg.split("_")[0]
    s = re.split(r"[\\/]", s)[-1]
    if s.lower().endswith(".exe"):
        s = s[:-4]
    if "." in s and " " not in s:      # Microsoft.Windows.Explorer -> Explorer
        s = s.split(".")[-1] or s
    return s[:60] or "Windows"


def ignored(app, primary, lst):
    a, p = (app or "").lower(), (primary or "").lower()
    for x in lst or []:
        x = x.strip().lower()
        if x and (x == a or x in p):
            return True
    return False


# ---------------------------------------------------------------- leitura ---
def _connect(path):
    uri = "file:%s?mode=ro" % pathname2url(os.path.abspath(path))
    return sqlite3.connect(uri, uri=True, timeout=1.0)


def _columns(con, table):
    return set(r[1] for r in con.execute("PRAGMA table_info(%s)" % table).fetchall())


def _query(con, after):
    ncols = _columns(con, "Notification")
    if not all(c in ncols for c in REQUIRED):
        raise SchemaError("Notification sem colunas esperadas")
    hcols = _columns(con, "NotificationHandler")
    join = "RecordId" in hcols and "PrimaryId" in hcols
    sql = ("SELECT n.Id, n.ArrivalTime, n.Payload, %s FROM Notification n %s WHERE n.Id > ? %s ORDER BY n.Id"
           % ("h.PrimaryId" if join else "NULL",
              "LEFT JOIN NotificationHandler h ON h.RecordId = n.HandlerId" if join else "",
              "AND n.Type = 'toast'" if "Type" in ncols else ""))
    return con.execute(sql, (after,)).fetchall()


def _max_id(con):
    if not all(c in _columns(con, "Notification") for c in REQUIRED):
        raise SchemaError("Notification sem colunas esperadas")
    r = con.execute("SELECT MAX(Id) FROM Notification").fetchone()
    return int(r[0] or 0)


def _with_db(path, fn):
    """fn(con); se o banco estiver travado, usa uma copia temporaria."""
    try:
        con = _connect(path)
        try:
            return fn(con)
        finally:
            con.close()
    except sqlite3.OperationalError as e:
        if "locked" not in str(e).lower() and "busy" not in str(e).lower():
            raise
    tmp = tempfile.mkdtemp(prefix="sdnotif")
    try:
        dst = os.path.join(tmp, "wpn.db")
        shutil.copyfile(path, dst)
        for suf in ("-wal", "-shm"):
            if os.path.exists(path + suf):
                shutil.copyfile(path + suf, dst + suf)
        con = sqlite3.connect(dst, timeout=1.0)   # copia: pode aplicar o -wal
        try:
            return fn(con)
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Leitor(object):
    """Le os toasts novos; entrega em avisos (so Controle total)."""

    def __init__(self, path=None, fila=None):
        self.path = path
        self.fila = fila
        self.lock = threading.Lock()
        self.busy = False
        self.last_poll = 0.0
        self.after = None          # maior Id ja visto (None = ainda sem base)
        self.status = "desligado"
        self.failed = False

    def _path(self):
        return self.path or db_path()

    def reset(self):
        with self.lock:
            self.after = None
            self.failed = False
            self.status = "desligado"

    def poll_once(self, ignored_apps=()):
        """Uma leitura (sincrona). Devolve quantos avisos entraram."""
        path = self._path()
        if not os.path.exists(path):
            self._fail(UNAVAILABLE)
            return 0
        try:
            if self.after is None:      # primeira leitura: so marca a base (nada antigo)
                self.after = _with_db(path, _max_id)
                self.status = "ativo"
                return 0
            rows = _with_db(path, lambda con: _query(con, self.after))
        except (SchemaError, sqlite3.Error, OSError, ValueError, TypeError):
            self._fail(UNAVAILABLE)
            return 0
        self.status = "ativo"
        n = 0
        for row in rows:
            try:
                nid = int(row[0])
            except (TypeError, ValueError):
                continue
            self.after = max(self.after, nid)
            if n >= MAX_PER_POLL:
                continue
            parsed = parse_toast(row[2])
            if not parsed:
                continue
            app = app_name(row[3])
            if ignored(app, row[3], ignored_apps):
                continue
            title, text = parsed
            if self.fila is not None:
                self.fila.push("windows", title, text, "info", True, app)
            else:
                avisos.push("windows", title, text, "info", True, app)
            n += 1
        return n

    def _fail(self, msg):
        self.failed = True
        self.status = msg

    def maybe_poll(self, now=None):
        """Chamado pelo /api/state (so quando algum aparelho consulta).
        Le no maximo a cada 5 s, em thread curta, sem travar o pedido."""
        st = avisos.settings()
        if not st["types"].get("windows"):
            if self.after is not None or self.status != "desligado":
                self.reset()
            return False
        if not paths.IS_WINDOWS:
            self.status = "só no Windows"
            return False
        now = now if now is not None else time.time()
        with self.lock:
            if self.failed or self.busy or now - self.last_poll < POLL_EVERY:
                return False
            self.busy = True
            self.last_poll = now
        ign = list(st["ignored_apps"])

        def run():
            try:
                self.poll_once(ign)
            except Exception:  # noqa: BLE001 - recurso experimental nunca derruba nada
                self._fail(UNAVAILABLE)
            finally:
                self.busy = False
        threading.Thread(target=run, name="notif-windows", daemon=True).start()
        return True

    def info(self):
        st = avisos.settings()
        if not st["types"].get("windows"):
            return "desligado"
        if not paths.IS_WINDOWS:
            return "só no Windows"
        return self.status if self.status != "desligado" else "aguardando um aparelho"


LEITOR = Leitor()


def retry():
    """Ajustes mudaram: tenta de novo (ex.: depois de desligar e ligar)."""
    LEITOR.reset()
