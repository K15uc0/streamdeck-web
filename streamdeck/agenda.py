# -*- coding: utf-8 -*-
"""Agendamentos (config "schedules"): roda acoes em horarios do PC (hora local).

Formato em docs/ARQUITETURA.md (2.8). Regras:
- daily: "time" HH:MM nos dias "days" (0=domingo..6=sabado; vazio = todos);
- every: a cada "minutes" (1..1440) alinhado a meia-noite (15 -> :00 :15 :30 :45),
  janela opcional "from" / "to" (as duas inclusive), que pode cruzar a
  meia-noite (22:00 a 02:00); nesse caso a parte depois da meia-noite conta
  como do dia em que a janela comecou (para o filtro "days");
- once: "at" YYYY-MM-DDTHH:MM; depois de rodar fica enabled=false.
Roda no maximo uma vez por minuto previsto; o que passou com o PC desligado
nao e recuperado. Datas sem fuso (hora local "ingenua"): o horario de verao
nao entra na conta."""
import copy
import datetime as _dt
import re
import threading
import time

from . import actions

MAX_SCHEDULES = 50
MAX_NAME = 60
ID_RE = re.compile(r"^[a-z0-9]{1,16}$")
HM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d$")
TICK = 10.0          # segundos entre conferencias
LOOKAHEAD = 8        # dias procurados por next_run


# ---------------------------------------------------------------- horarios ---
def hm(s):
    """"HH:MM" -> minutos desde a meia-noite."""
    m = HM_RE.match(s)
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_at(s):
    return _dt.datetime.strptime(s, "%Y-%m-%dT%H:%M")


def weekday(d):
    """Dia da semana no formato do contrato: 0=domingo..6=sabado."""
    return (d.weekday() + 1) % 7


def _day_ok(days, d):
    return not days or weekday(d) in days


def _floor(now):
    return now.replace(second=0, microsecond=0)


def _in_window(when, m, d):
    """(dentro da janela?, dia que vale para o filtro days)."""
    f = hm(when["from"]) if when.get("from") else None
    t = hm(when["to"]) if when.get("to") else None
    if f is None and t is None:
        return True, d
    if f is None:
        return m <= t, d
    if t is None:
        return m >= f, d
    if f < t:
        return f <= m <= t, d
    if f == t:          # mesma hora: o dia todo
        return True, d
    # cruza a meia-noite
    if m >= f:
        return True, d
    if m <= t:
        return True, d - _dt.timedelta(days=1)
    return False, d


def matches(when, minute):
    """O minuto (datetime sem segundos) e um horario previsto?"""
    if not isinstance(when, dict):
        return False
    typ = when.get("type")
    days = when.get("days") or []
    m = minute.hour * 60 + minute.minute
    if typ == "daily":
        return m == hm(when["time"]) and _day_ok(days, minute)
    if typ == "every":
        if m % int(when["minutes"]) != 0:
            return False
        ok, d = _in_window(when, m, minute)
        return ok and _day_ok(days, d)
    if typ == "once":
        return minute == parse_at(when["at"])
    return False


def next_run(item, now):
    """Proximo minuto previsto (>= minuto atual) ou None (desligado, once que
    ja passou)."""
    if not isinstance(item, dict) or item.get("enabled") is False:
        return None
    when = item.get("when") or {}
    if not isinstance(when, dict):
        return None
    start = _floor(now)
    typ = when.get("type")
    try:
        if typ == "once":
            at = parse_at(when["at"])
            return at if at >= start else None
        if typ == "daily":
            t = hm(when["time"])
            for i in range(LOOKAHEAD):
                d = _dt.datetime.combine(start.date() + _dt.timedelta(days=i), _dt.time(t // 60, t % 60))
                if d >= start and _day_ok(when.get("days") or [], d):
                    return d
            return None
        if typ == "every":
            step = int(when["minutes"])
            if step < 1:
                raise ValueError("minutos invalidos")
            for i in range(LOOKAHEAD):
                day = _dt.datetime.combine(start.date() + _dt.timedelta(days=i), _dt.time(0, 0))
                m0 = 0
                if i == 0:
                    cur = start.hour * 60 + start.minute
                    m0 = -(-cur // step) * step
                for m in range(m0, 1440, step):
                    d = day + _dt.timedelta(minutes=m)
                    if matches(when, d):
                        return d
            return None
    except Exception:  # noqa: BLE001 - item malformado nao derruba os outros
        return None
    return None


def due(item, last_minute, now):
    """Deve rodar agora? last_minute: minuto em que rodou por ultimo (ou None).
    Nunca roda duas vezes no mesmo minuto (nem se o relogio voltar)."""
    if not isinstance(item, dict) or item.get("enabled") is False:
        return False
    minute = _floor(now)
    if last_minute is not None and minute == last_minute:
        return False
    try:
        return matches(item.get("when") or {}, minute)
    except Exception:  # noqa: BLE001
        return False


def disable_all(cfg):
    """Importar/restaurar: desliga todos os agendamentos (o usuario revisa e
    liga). Devolve quantos estavam ligados."""
    n = 0
    items = cfg.get("schedules") if isinstance(cfg, dict) else None
    for x in items if isinstance(items, list) else []:
        if isinstance(x, dict) and x.get("enabled") is not False:
            x["enabled"] = False
            n += 1
    return n


# --------------------------------------------------------------- validacao ---
def _days(v, where):
    if v is None:
        return
    if not isinstance(v, list) or len(v) > 7:
        raise ValueError("%s: dias invalidos" % where)
    for x in v:
        if not isinstance(x, int) or isinstance(x, bool) or not 0 <= x <= 6:
            raise ValueError("%s: dias devem ser de 0 (domingo) a 6 (sabado)" % where)
    if len(set(v)) != len(v):
        raise ValueError("%s: dias repetidos" % where)


def _hm_field(when, key, where, required):
    v = when.get(key)
    if v is None and not required:
        return
    if not isinstance(v, str) or not HM_RE.match(v):
        raise ValueError("%s: horario invalido em %s (use HH:MM)" % (where, key))


WHEN_KEYS = {"daily": ("type", "time", "days"),
             "every": ("type", "minutes", "from", "to", "days"),
             "once": ("type", "at")}


def validate_when(when, where):
    if not isinstance(when, dict) or when.get("type") not in WHEN_KEYS:
        raise ValueError("%s: quando invalido (daily, every ou once)" % where)
    typ = when["type"]
    for k in when:
        if k not in WHEN_KEYS[typ]:
            raise ValueError("%s: campo desconhecido em quando: %s" % (where, k))
    if typ == "daily":
        _hm_field(when, "time", where, True)
        _days(when.get("days"), where)
    elif typ == "every":
        v = when.get("minutes")
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 1440:
            raise ValueError("%s: minutos devem ficar entre 1 e 1440" % where)
        _hm_field(when, "from", where, False)
        _hm_field(when, "to", where, False)
        _days(when.get("days"), where)
    else:
        v = when.get("at")
        if not isinstance(v, str) or not AT_RE.match(v):
            raise ValueError("%s: data invalida (use AAAA-MM-DDTHH:MM)" % where)
        try:
            parse_at(v)
        except ValueError:
            raise ValueError("%s: data invalida" % where)


def validate(items, n_pages):
    """Confere config["schedules"]. Levanta ValueError com mensagem."""
    if items is None:
        return
    if not isinstance(items, list):
        raise ValueError("agendamentos invalidos")
    if len(items) > MAX_SCHEDULES:
        raise ValueError("no maximo %d agendamentos" % MAX_SCHEDULES)
    seen = set()
    for i, it in enumerate(items):
        where = "Agendamento %d" % (i + 1)
        if not isinstance(it, dict):
            raise ValueError(where + ": invalido")
        for k in it:
            if k not in ("id", "name", "enabled", "when", "action"):
                raise ValueError("%s: campo desconhecido: %s" % (where, k))
        sid = it.get("id")
        if not isinstance(sid, str) or not ID_RE.match(sid):
            raise ValueError("%s: id invalido" % where)
        if sid in seen:
            raise ValueError("%s: id repetido" % where)
        seen.add(sid)
        name = it.get("name", "")
        if not isinstance(name, str) or len(name) > MAX_NAME:
            raise ValueError("%s: nome invalido (maximo %d caracteres)" % (where, MAX_NAME))
        if "enabled" in it and not isinstance(it["enabled"], bool):
            raise ValueError("%s: enabled deve ser true ou false" % where)
        validate_when(it.get("when"), where)
        a = it.get("action")
        if isinstance(a, dict) and a.get("type") == "page":
            raise ValueError("%s: agendamento nao pode trocar de pagina" % where)
        actions.validate(a, max(1, n_pages), where)


# ---------------------------------------------------------------- execucao ---
def _iso(d):
    return d.isoformat(timespec="seconds") if d is not None else None


def _check(it):
    """Levanta ValueError se o "when" de um item ligado esta malformado."""
    if it.get("enabled") is not False:
        validate_when(it.get("when"), "agendamento")


def _load_config():
    from . import storage
    return storage.load_config()


class Agenda(object):
    """Confere os agendamentos a cada TICK segundos numa thread."""

    def __init__(self, get_config=_load_config, clock=_dt.datetime.now):
        self.get_config = get_config
        self.clock = clock
        self.lock = threading.Lock()
        self.fired = {}       # id -> minuto em que rodou (so em memoria)
        self.info = {}        # id -> {"last": epoch, "last_error": str|None}
        self.once_done = {}   # id -> "at" de once que ja rodou (so em memoria)
        self.bad = set()      # ids malformados ja avisados no log
        self._stop = threading.Event()
        self._thread = None

    # -- thread
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="agenda", daemon=True)
        self._thread.start()

    def stop(self, timeout=2.0):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
        self._thread = None

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001 - a thread nunca morre
                print("! agendamentos: %s" % e)
            self._stop.wait(TICK)

    def items(self):
        try:
            cfg = self.get_config()
        except Exception:
            return []
        items = cfg.get("schedules") if isinstance(cfg, dict) else None
        return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []

    def tick(self, now=None):
        """Dispara o que esta previsto para o minuto atual. Devolve as threads."""
        now = now or self.clock()
        minute = _floor(now)
        started = []
        for it in self.items():
            sid = it.get("id")
            with self.lock:
                try:
                    _check(it)
                    if not due(it, self.fired.get(sid), now):
                        continue
                except Exception as e:  # noqa: BLE001
                    self._broken(sid, e)
                    continue
                self.fired[sid] = minute
            t = threading.Thread(target=self._run, args=(it, True), name="agenda:%s" % sid, daemon=True)
            t.start()
            started.append(t)
        return started

    def _run(self, it, scheduled):
        sid = it.get("id")
        print("* agendamento: %s" % (it.get("name") or sid))
        err = None
        try:
            actions.run(it.get("action"), key="agenda:%s" % sid)
        except Exception as e:  # noqa: BLE001
            err = str(e) or e.__class__.__name__
            print("! agendamento %s: %s" % (it.get("name") or sid, err))
        with self.lock:
            self.info[sid] = {"last": time.time(), "last_error": err}
        when = it.get("when") if isinstance(it.get("when"), dict) else {}
        if scheduled and when.get("type") == "once":
            with self.lock:
                self.once_done[sid] = when.get("at")
            self._disable(sid)
        return err

    def _disable(self, sid):
        """once: desliga no config (salvar segue as regras normais de copia)."""
        try:
            from . import storage
            cfg = copy.deepcopy(storage.load_config())
            for x in cfg.get("schedules") or []:
                if isinstance(x, dict) and x.get("id") == sid:
                    x["enabled"] = False
                    storage.save_config(cfg)
                    return True
        except Exception as e:  # noqa: BLE001
            print("! agendamento %s: nao deu para desligar (%s)" % (sid, e))
        return False

    def _broken(self, sid, e):
        """Chamado com self.lock: avisa uma vez por id e marca o erro."""
        if sid not in self.bad:
            self.bad.add(sid)
            print("! agendamento %s invalido: %s" % (sid, e))
        inf = self.info.setdefault(sid, {"last": None, "last_error": None})
        inf["last_error"] = "agendamento invalido"

    def guard_once(self, cfg, now=None):
        """Salvar pelo editor: um once que ja rodou (e cujo horario passou) nao
        volta ligado por causa de um autosave com dados antigos. Devolve quantos
        foram desligados."""
        now = now or self.clock()
        n = 0
        items = cfg.get("schedules") if isinstance(cfg, dict) else None
        for x in items if isinstance(items, list) else []:
            if not isinstance(x, dict) or x.get("enabled") is False:
                continue
            w = x.get("when")
            if not isinstance(w, dict) or w.get("type") != "once":
                continue
            with self.lock:
                done = self.once_done.get(x.get("id"))
            try:
                past = parse_at(w.get("at")) <= _floor(now)
            except Exception:  # noqa: BLE001
                past = False
            if done is not None and done == w.get("at") and past:
                x["enabled"] = False
                n += 1
        return n

    def find(self, sid):
        for it in self.items():
            if it.get("id") == sid:
                return it
        return None

    def run_now(self, sid):
        """Teste pela API: roda ja (sem desligar o once). None se nao existe;
        senao a mensagem de erro (ou "" se deu certo)."""
        it = self.find(sid)
        if it is None:
            return None
        return self._run(it, False) or ""

    def status(self, now=None):
        now = now or self.clock()
        out = []
        for it in self.items():
            sid = it.get("id")
            with self.lock:
                inf = dict(self.info.get(sid) or {})
                fired = self.fired.get(sid)
            last = inf.get("last")
            ref = now
            if fired is not None and fired == _floor(now):
                # ja rodou neste minuto: o proximo e a partir do minuto seguinte
                ref = _floor(now) + _dt.timedelta(minutes=1)
            try:
                _check(it)
                nxt = next_run(it, ref)
            except Exception as e:  # noqa: BLE001
                with self.lock:
                    self._broken(sid, e)
                    inf = dict(self.info.get(sid) or {})
                nxt = None
            out.append({"id": sid, "next": _iso(nxt),
                        "last": _iso(_dt.datetime.fromtimestamp(last)) if last else None,
                        "last_error": inf.get("last_error")})
        return {"ok": True, "now": _iso(now.replace(microsecond=0)), "items": out}


AGENDA = Agenda()


def start():
    AGENDA.start()


def stop():
    AGENDA.stop()
