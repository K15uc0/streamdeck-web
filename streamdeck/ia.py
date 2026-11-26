# -*- coding: utf-8 -*-
"""Consumo das IAs (2.9): limites do Claude (via ponte da status line) e do
Codex (logs de sessao). Nunca le credenciais."""
import json
import os
import sys
import time

from . import paths, storage

ANTERIOR_NOME = "statusline_anterior.json"


def _ia_dir():
    d = os.path.join(paths.BASE, "ia")
    os.makedirs(d, exist_ok=True)
    return d


def _num(v):
    try:
        if isinstance(v, bool) or v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _janela(used, resets_at, now):
    used = _num(used)
    resets_at = _num(resets_at)
    if used is None or resets_at is None:
        return None
    used = max(0.0, min(100.0, used))
    if resets_at < now:        # janela ja virou: comecou outra
        used = 0.0
    return {"used": round(used, 1), "left": round(100.0 - used, 1), "resets_at": int(resets_at)}


# ---------------------------------------------------------------- Claude
def _claude(now):
    try:
        with open(os.path.join(_ia_dir(), "claude.json"), "r", encoding="utf-8") as f:
            d = json.load(f)
        rl = d.get("rate_limits") or {}
        out = {}
        for chave, rl_key in (("five_hour", "five_hour"), ("weekly", "seven_day")):
            j = rl.get(rl_key)
            out[chave] = _janela(j.get("used_percentage"), j.get("resets_at"), now) if isinstance(j, dict) else None
        if not out["five_hour"] and not out["weekly"]:
            return None
        out.update(updated=int(d.get("ts") or 0), source="statusline", tokens_today=None)
        return out
    except Exception:
        return None


# ----------------------------------------------------------------- Codex
def _codex_dirs():
    dirs = []
    for base in (os.environ.get("CODEX_HOME"), os.path.join(os.path.expanduser("~"), ".codex")):
        if base:
            d = os.path.join(base, "sessions")
            if d not in dirs:
                dirs.append(d)
    return dirs


def _recent_files(limit=5):
    arqs = []
    for d in _codex_dirs():
        for raiz, _, nomes in os.walk(d):
            for n in nomes:
                if n.endswith(".jsonl"):
                    p = os.path.join(raiz, n)
                    try:
                        arqs.append((os.path.getmtime(p), p))
                    except OSError:
                        pass
    arqs.sort(reverse=True)
    return arqs[:limit]


def _find_rl(o, depth=0):
    """Procura um objeto "rate_limits" em qualquer nivel."""
    if depth > 6:
        return None
    if isinstance(o, dict):
        rl = o.get("rate_limits")
        if isinstance(rl, dict) and (isinstance(rl.get("primary"), dict) or isinstance(rl.get("secondary"), dict)):
            return rl
        for v in o.values():
            r = _find_rl(v, depth + 1)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_rl(v, depth + 1)
            if r:
                return r
    return None


def _iso_ts(s):
    try:
        import calendar
        return calendar.timegm(time.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return None


def _codex_win(j, base_ts, now):
    if not isinstance(j, dict):
        return None
    if j.get("resets_at") is not None:
        r = _num(j.get("resets_at"))
    elif j.get("resets_in_seconds") is not None and _num(j.get("resets_in_seconds")) is not None:
        r = base_ts + _num(j.get("resets_in_seconds"))
    else:
        return None
    return _janela(j.get("used_percent"), r, now)


def _codex(now):
    try:
        for mtime, path in _recent_files():
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                linhas = f.read().splitlines()[-200:]
            for linha in reversed(linhas):
                if "rate_limits" not in linha:
                    continue
                try:
                    obj = json.loads(linha)
                except ValueError:
                    continue
                rl = _find_rl(obj)
                if not rl:
                    continue
                ts = _iso_ts(obj.get("timestamp")) if isinstance(obj, dict) else None
                base_ts = ts if ts is not None else mtime
                out = {"five_hour": None, "weekly": None}
                for chave in ("primary", "secondary"):
                    j = rl.get(chave)
                    w = _codex_win(j, base_ts, now)
                    if not w:
                        continue
                    wm = _num(j.get("window_minutes"))
                    if wm is not None:
                        alvo = "five_hour" if abs(wm - 300) < abs(wm - 10080) else "weekly"
                    else:
                        alvo = "five_hour" if chave == "primary" else "weekly"
                    out[alvo] = out[alvo] or w
                if out["five_hour"] or out["weekly"]:
                    out.update(updated=int(base_ts), source="codex-log", tokens_today=None)
                    return out
    except Exception:
        pass
    return None


def status(now=None):
    now = int(now if now is not None else time.time())
    return {"claude": _claude(now), "codex": _codex(now), "grok": None}


# ------------------------------------------------------ ponte (instalar)
def _settings_path():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "settings.json")


def bridge_command():
    if paths.FROZEN:
        return '"%s" --ponte-claude' % sys.executable
    return '"%s" "%s"' % (sys.executable, os.path.join(paths.PKG_DIR, "ponte_claude.py"))


def _is_bridge(sl):
    cmd = sl.get("command") if isinstance(sl, dict) else None
    return isinstance(cmd, str) and ("ponte_claude" in cmd or "--ponte-claude" in cmd)


def _read_settings():
    p = _settings_path()
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict):
        raise ValueError("settings.json inesperado")
    return d


def bridge_installed():
    try:
        return _is_bridge(_read_settings().get("statusLine"))
    except Exception:
        return False


def install_bridge():
    p = _settings_path()
    try:
        cfg = _read_settings()
    except Exception as e:      # JSON quebrado: nao mexe
        return {"ok": False, "error": "nao foi possivel ler %s: %s" % (p, e)}
    prev = cfg.get("statusLine")
    if not _is_bridge(prev):
        storage.write_json(os.path.join(_ia_dir(), ANTERIOR_NOME), {"statusLine": prev})
        if os.path.exists(p):
            try:
                import shutil
                shutil.copy2(p, p + ".streamdeck.bak")
            except OSError:
                pass
    new = dict(prev) if isinstance(prev, dict) else {}
    new.update({"type": "command", "command": bridge_command()})
    cfg["statusLine"] = new
    os.makedirs(os.path.dirname(p), exist_ok=True)
    storage.write_json(p, cfg)
    return {"ok": True, "installed": True, "settings": p}


def uninstall_bridge():
    p = _settings_path()
    try:
        cfg = _read_settings()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if _is_bridge(cfg.get("statusLine")):
        prev = None
        try:
            with open(os.path.join(_ia_dir(), ANTERIOR_NOME), "r", encoding="utf-8") as f:
                prev = json.load(f).get("statusLine")
        except Exception:
            pass
        if prev:
            cfg["statusLine"] = prev
        else:
            cfg.pop("statusLine", None)
        storage.write_json(p, cfg)
    return {"ok": True, "installed": False}
