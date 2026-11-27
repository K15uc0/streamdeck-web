# -*- coding: utf-8 -*-
"""Avisos do Stream Deck (2.12): fila curta em memoria e regras.

Fila: ultimos 50 avisos com id crescente (comeca no relogio em ms, assim um id
visto antes de reiniciar o servidor nunca e maior que os novos, salvo relogio
voltando; nesse caso since() devolve a fila toda). Os aparelhos pedem
/api/state?since=<id> e recebem so os novos.

Regras (baratas, so com dados JA coletados; nada aqui dispara coleta):
  ia       Claude/Codex >= 80% e >= 95% (uma vez por janela de limite)
  temp     CPU/GPU acima do limite (padrao 90 C), no maximo a cada 5 min
  cpu      CPU > 95% por 1 min seguido
  obs      OBS desconectou / conectou de novo
  device   aparelho novo cadastrado
  schedule agendamento executado (desligado por padrao)
  windows  notificacoes do Windows (notif_windows; so aparelhos com Controle total)

Ajustes em seguranca.json, chave "avisos":
  {"types": {tipo: bool}, "temp_limit": 90, "ignored_apps": [..]}
Texto de aviso nunca vai para o log.
"""
import collections
import threading
import time

MAX = 50
KINDS = ("ia", "temp", "cpu", "obs", "device", "schedule", "windows")
DEFAULT_TYPES = {"ia": True, "temp": True, "cpu": True, "obs": True, "device": True,
                 "schedule": False, "windows": False}
TEMP_DEFAULT = 90
TEMP_MIN, TEMP_MAX = 50, 110
TEMP_EVERY = 300          # s entre avisos da mesma temperatura
CPU_LIMIT = 95.0
CPU_FOR = 60              # s acima do limite
STALE = 15                # amostra do monitor mais velha que isso nao vale
IA_LEVELS = (95, 80)
MAX_IGNORED = 50


# ---------------------------------------------------------------- ajustes ---
_CFG = {"val": None, "t": 0.0}
CFG_TTL = 5.0


def _drop_cache(_data=None):
    _CFG["val"] = None


def _storage():
    """storage importado aqui (storage -> schema -> actions forma ciclo)."""
    from . import storage
    if _drop_cache not in storage.SETTINGS_HOOKS:
        storage.SETTINGS_HOOKS.append(_drop_cache)
    return storage


def _clean(raw):
    raw = raw if isinstance(raw, dict) else {}
    types = dict(DEFAULT_TYPES)
    t = raw.get("types")
    if isinstance(t, dict):
        for k in KINDS:
            if isinstance(t.get(k), bool):
                types[k] = t[k]
    lim = raw.get("temp_limit")
    if not isinstance(lim, (int, float)) or isinstance(lim, bool) or not TEMP_MIN <= lim <= TEMP_MAX:
        lim = TEMP_DEFAULT
    ign = raw.get("ignored_apps")
    ign = [str(x).strip()[:80] for x in ign if str(x).strip()][:MAX_IGNORED] if isinstance(ign, list) else []
    return {"types": types, "temp_limit": int(lim), "ignored_apps": ign}


def settings():
    """Ajustes atuais (com padroes), relidos no maximo a cada 5 s."""
    now = time.time()
    v = _CFG["val"]
    if v is None or now - _CFG["t"] > CFG_TTL or now < _CFG["t"]:
        v = _clean(_storage().load_settings().get("avisos"))
        _CFG.update(val=v, t=now)
    return v


def save_settings(body):
    """Junta body (parcial) aos ajustes e grava. ValueError se invalido."""
    if not isinstance(body, dict):
        raise ValueError("pedido invalido")
    cur = settings()
    new = {"types": dict(cur["types"]), "temp_limit": cur["temp_limit"], "ignored_apps": list(cur["ignored_apps"])}
    if "types" in body:
        t = body["types"]
        if not isinstance(t, dict):
            raise ValueError("types invalido")
        for k, v in t.items():
            if k not in KINDS or not isinstance(v, bool):
                raise ValueError("tipo de aviso invalido: %s" % str(k)[:20])
            new["types"][k] = v
    if "temp_limit" in body:
        lim = body["temp_limit"]
        if not isinstance(lim, (int, float)) or isinstance(lim, bool) or not TEMP_MIN <= lim <= TEMP_MAX:
            raise ValueError("limite de temperatura deve ficar entre %d e %d" % (TEMP_MIN, TEMP_MAX))
        new["temp_limit"] = int(lim)
    if "ignored_apps" in body:
        ign = body["ignored_apps"]
        if not isinstance(ign, list) or len(ign) > MAX_IGNORED or not all(isinstance(x, str) for x in ign):
            raise ValueError("lista de apps ignorados invalida")
        new["ignored_apps"] = [x.strip()[:80] for x in ign if x.strip()]

    def fn(data):
        data["avisos"] = new
    _storage().update_settings(fn)
    _drop_cache()
    return settings()


def enabled(kind):
    return bool(settings()["types"].get(kind))


# ------------------------------------------------------------------- fila ---
class Fila(object):
    def __init__(self, start=None):
        self.lock = threading.Lock()
        self.items = collections.deque(maxlen=MAX)
        self.last = int(time.time() * 1000) if start is None else int(start)

    def push(self, kind, title, text="", level="info", full_only=False, app=None, now=None):
        item = {"id": 0, "t": int(now if now is not None else time.time()), "kind": kind,
                "title": str(title)[:120], "text": str(text or "")[:300], "level": level}
        if app:
            item["app"] = str(app)[:60]
        with self.lock:
            self.last += 1
            item["id"] = self.last
            item["full"] = bool(full_only)
            self.items.append(item)
        return item["id"]

    def last_id(self):
        with self.lock:
            return self.last

    def poll(self, n, full=False):
        """(avisos com id > n que este aparelho pode ver, ultimo id), lidos
        juntos. n maior que o ultimo id (servidor reiniciou com relogio
        atrasado): a fila toda."""
        with self.lock:
            items = list(self.items)
            last = self.last
        if n is None or n > last:
            n = -1
        return [_public(i) for i in items if i["id"] > n and (full or not i["full"])], last

    def since(self, n, full=False):
        return self.poll(n, full)[0]

    def clear(self):
        with self.lock:
            self.items.clear()


def _public(i):
    out = dict(i)
    out.pop("full", None)
    return out


FILA = Fila()


def push(kind, title, text="", level="info", full_only=False, app=None):
    """Enfileira se o tipo estiver ligado. Devolve o id ou None."""
    if not enabled(kind):
        return None
    return FILA.push(kind, title, text, level, full_only, app)


# ----------------------------------------------------------------- regras ---
IA_NAMES = {"claude": "Claude", "codex": "Codex"}
WIN_NAMES = {"five_hour": "limite de 5 h", "weekly": "limite semanal"}


class Regras(object):
    """Estado das regras. Cada check_* recebe dados ja coletados."""

    def __init__(self):
        self.lock = threading.Lock()
        self.ia_fired = {}          # (prov, janela, resets_at) -> maior nivel avisado
        self.temp_last = {}         # "cpu"/"gpu" -> epoch do ultimo aviso
        self.cpu_high = None        # epoch em que passou do limite
        self.cpu_ts = None          # ts da ultima amostra vista
        self.cpu_fired = False
        self.obs_ok = None

    def check_ia(self, st, now=None):
        if not isinstance(st, dict):
            return
        now = now if now is not None else time.time()
        with self.lock:
            for prov in ("claude", "codex"):
                p = st.get(prov)
                if not isinstance(p, dict):
                    continue
                for win in ("five_hour", "weekly"):
                    w = p.get(win)
                    if not isinstance(w, dict) or not isinstance(w.get("used"), (int, float)):
                        continue
                    reset = w.get("resets_at")
                    if reset is None:
                        continue
                    key = (prov, win, reset)
                    done = self.ia_fired.get(key, 0)
                    for lvl in IA_LEVELS:
                        if w["used"] >= lvl:
                            if done < lvl:
                                self.ia_fired[key] = lvl
                                push("ia", "%s: %d%% do %s" % (IA_NAMES[prov], int(w["used"]), WIN_NAMES[win]),
                                     "Renova às %s." % time.strftime("%H:%M", time.localtime(reset)),
                                     "crit" if lvl >= 95 else "warn")
                            break
            for k in [k for k in self.ia_fired if k[2] < now - 86400 * 8]:
                del self.ia_fired[k]

    def check_pc(self, snap, now=None):
        """snap: resumo do monitor ({cpu, temps:{cpu,gpu}, ts}) ja coletado."""
        if not isinstance(snap, dict):
            return
        now = now if now is not None else time.time()
        ts = snap.get("ts") or 0
        if now - ts > STALE:
            return
        lim = settings()["temp_limit"]
        temps = snap.get("temps") or {}
        with self.lock:
            for k, name in (("cpu", "CPU"), ("gpu", "GPU")):
                v = temps.get(k)
                if isinstance(v, (int, float)) and v > lim:
                    last = self.temp_last.get(k)
                    if last is None or now - last >= TEMP_EVERY:
                        self.temp_last[k] = now
                        push("temp", "%s a %d °C" % (name, round(v)), "Acima do limite de %d °C." % lim, "crit")
            cpu = snap.get("cpu")
            if self.cpu_ts is not None and ts - self.cpu_ts > STALE:
                self.cpu_high = None       # buraco nas amostras: recomeca
            self.cpu_ts = ts
            if isinstance(cpu, (int, float)) and cpu > CPU_LIMIT:
                if self.cpu_high is None:
                    self.cpu_high = ts
                elif ts - self.cpu_high >= CPU_FOR and not self.cpu_fired:
                    self.cpu_fired = True
                    push("cpu", "CPU acima de %d%%" % CPU_LIMIT, "Há mais de 1 minuto em %d%%." % round(cpu), "warn")
            elif isinstance(cpu, (int, float)):
                self.cpu_high = None
                self.cpu_fired = False

    def check_obs(self, ob):
        """ob: bloco obs do /api/state (None = OBS nunca configurado)."""
        if not isinstance(ob, dict):
            return
        ok = bool(ob.get("ok"))
        with self.lock:
            prev, self.obs_ok = self.obs_ok, ok
        if prev is True and not ok:
            push("obs", "OBS desconectado", "O Stream Deck perdeu a conexão com o OBS.", "warn")
        elif prev is False and ok:
            push("obs", "OBS conectado de novo", "", "info")


REGRAS = Regras()


def device_new(name):
    push("device", "Aparelho novo conectado", name or "", "info")


def schedule_ran(name, err=None):
    if err:
        push("schedule", "Agendamento com erro", name or "", "warn")
    else:
        push("schedule", "Agendamento executado", name or "", "info")
