# -*- coding: utf-8 -*-
"""Consumo das IAs (2.9): limites do Claude (via ponte da status line) e do
Codex (logs de sessao). Nunca le credenciais."""
import json
import os
import shutil
import sys
import time
import zipfile

from . import VERSION, paths

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
    if resets_at <= now:        # janela ja virou: comecou outra
        return {"used": 0.0, "left": 100.0, "resets_at": None}
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
            d = os.path.join(os.path.expanduser(base), "sessions")
            if d not in dirs:
                dirs.append(d)
    return dirs


def _recent_files(limit=5):
    """Os .jsonl mais novos, andando por ano/mes/dia do mais novo para o mais
    antigo e parando ao juntar `limit` arquivos (nao varre o historico todo)."""
    achados = []

    def anda(d):
        if len(achados) >= limit:
            return
        try:
            nomes = os.listdir(d)
        except OSError:
            return
        arqs = []
        for n in nomes:
            p = os.path.join(d, n)
            if n.endswith(".jsonl") and os.path.isfile(p):
                try:
                    arqs.append((os.path.getmtime(p), p))
                except OSError:
                    pass
        for m, p in sorted(arqs, reverse=True):
            if len(achados) >= limit:
                return
            achados.append((m, p))
        for n in sorted(nomes, reverse=True):
            p = os.path.join(d, n)
            if os.path.isdir(p):
                anda(p)
    for d in _codex_dirs():
        anda(d)
    achados.sort(reverse=True)
    return achados[:limit]


def _tail_lines(path, max_bytes=256 * 1024, max_lines=200):
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - max_bytes))
        raw = f.read()
    linhas = raw.split(b"\n")
    if size > max_bytes:
        linhas = linhas[1:]          # primeira linha pode estar cortada
    return [l.decode("utf-8", "replace") for l in linhas[-max_lines:]]


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


def _codex_win(j, base_ts):
    """(used, resets_at) cru; a janela passada e tratada depois (depende do agora)."""
    if not isinstance(j, dict):
        return None
    if j.get("resets_at") is not None:
        r = _num(j.get("resets_at"))
    elif _num(j.get("resets_in_seconds")) is not None:
        r = base_ts + _num(j.get("resets_in_seconds"))
    else:
        return None
    u = _num(j.get("used_percent"))
    return None if r is None or u is None else (u, r)


_CX = {"key": None, "t": 0.0, "val": None}


def _codex_raw():
    arqs = _recent_files()
    key = tuple((p, m) for m, p in arqs)
    if _CX["key"] == key and time.time() - _CX["t"] < 5:
        return _CX["val"]
    val = None
    try:
        for mtime, path in arqs:
            for linha in reversed(_tail_lines(path)):
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
                out = {"five_hour": None, "weekly": None, "updated": int(base_ts)}
                for chave in ("primary", "secondary"):
                    j = rl.get(chave)
                    w = _codex_win(j, base_ts)
                    if not w:
                        continue
                    wm = _num(j.get("window_minutes"))
                    if wm is not None:
                        alvo = "five_hour" if abs(wm - 300) < abs(wm - 10080) else "weekly"
                    else:
                        alvo = "five_hour" if chave == "primary" else "weekly"
                    out[alvo] = out[alvo] or w
                if out["five_hour"] or out["weekly"]:
                    val = out
                    break
            if val:
                break
    except Exception:
        val = None
    _CX.update(key=key, t=time.time(), val=val)
    return val


def _codex(now):
    raw = _codex_raw()
    if not raw:
        return None
    out = {}
    for k in ("five_hour", "weekly"):
        out[k] = _janela(raw[k][0], raw[k][1], now) if raw[k] else None
    out.update(updated=raw["updated"], source="codex-log", tokens_today=None)
    return out


def status(now=None):
    now = int(now if now is not None else time.time())
    return {"claude": _claude(now), "codex": _codex(now), "grok": None}


# ------------------------------------------------------ ponte (instalar)
def _settings_path():
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    base = os.path.expanduser(base) if base else os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "settings.json")


def _ponte_dir():
    """Pasta versionada da ponte (ia/ponte-<versao>): sem troca no lugar."""
    return os.path.join(_ia_dir(), "ponte-" + VERSION)


def _fwd(p):
    return p.replace("\\", "/")


def bridge_command():
    if paths.FROZEN:
        return '"%s"' % _fwd(os.path.join(_ponte_dir(), "StreamDeckPonte.exe"))
    return '"%s" "%s"' % (_fwd(sys.executable), _fwd(os.path.join(paths.PKG_DIR, "ponte_claude.py")))


def _is_bridge(sl):
    cmd = sl.get("command") if isinstance(sl, dict) else None
    return isinstance(cmd, str) and ("ponte_claude" in cmd or "--ponte-claude" in cmd
                                     or "StreamDeckPonte" in cmd)


def _read_settings():
    p = _settings_path()
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8-sig") as f:
        d = json.load(f)
    if not isinstance(d, dict):
        raise ValueError("settings.json inesperado")
    return d


def _write_settings(cfg):
    """Atomico: arquivo temporario unico + os.replace (sem plano B por cima)."""
    p = _settings_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = "%s.%d.tmp" % (p, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(cfg, ensure_ascii=False, indent=2))
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _write_json(path, data):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _ponte_zip():
    exe_dir = os.path.dirname(sys.executable)
    for d in (paths.APP_DIR, os.path.join(exe_dir, "_internal"), exe_dir):
        z = os.path.join(d, "ponte.zip")
        if os.path.isfile(z):
            return z
    return None


def _ponte_version():
    try:
        with open(os.path.join(_ponte_dir(), "version.txt"), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _limpa_pontes_velhas(atual):
    """Apaga (best-effort) ia/ponte-* de outras versoes e a ia/ponte antiga."""
    base = _ia_dir()
    try:
        nomes = os.listdir(base)
    except OSError:
        return
    for n in nomes:
        d = os.path.join(base, n)
        if (n == "ponte" or n.startswith("ponte-")) and os.path.normcase(d) != os.path.normcase(atual) \
                and os.path.isdir(d):
            shutil.rmtree(d, True)       # em uso (exe aberto no Windows): fica para a proxima


def _extract_ponte():
    """Extrai ponte.zip em ia/ponte-<versao>; se ja existe com o version.txt
    certo, reaproveita. Erro devolve (False, msg)."""
    z = _ponte_zip()
    if not z:
        return False, "ponte.zip nao encontrado no programa"
    dest = _ponte_dir()
    if _ponte_version() == VERSION and os.path.isfile(os.path.join(dest, "StreamDeckPonte.exe")):
        return True, None
    novo = "%s.novo%d" % (dest, os.getpid())
    try:
        shutil.rmtree(novo, True)
        os.makedirs(novo)
        with zipfile.ZipFile(z) as zf:
            raiz = os.path.realpath(novo)
            for m in zf.namelist():
                alvo = os.path.realpath(os.path.join(novo, m))
                if alvo != raiz and not alvo.startswith(raiz + os.sep):
                    raise ValueError("zip com caminho invalido")
            zf.extractall(novo)
        with open(os.path.join(novo, "version.txt"), "w", encoding="utf-8") as f:
            f.write(VERSION)
        shutil.rmtree(dest, True)        # sobra incompleta da mesma versao
        os.rename(novo, dest)
        return True, None
    except Exception as e:
        shutil.rmtree(novo, True)
        return False, "nao foi possivel extrair a ponte: %s" % e


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
    try:
        if paths.FROZEN:
            ok, err = _extract_ponte()
            if not ok:
                return {"ok": False, "error": err}
        if not _is_bridge(cfg.get("statusLine")):
            _write_json(os.path.join(_ia_dir(), ANTERIOR_NOME), {"statusLine": cfg.get("statusLine")})
        bak = p + ".streamdeck.bak"
        if os.path.exists(p) and not os.path.exists(bak):     # guarda so o PRIMEIRO backup
            shutil.copy2(p, bak)
        cfg = _read_settings()           # le de novo logo antes de gravar
        prev = cfg.get("statusLine")
        new = dict(prev) if isinstance(prev, dict) else {}
        new.update({"type": "command", "command": bridge_command()})
        cfg["statusLine"] = new
        _write_settings(cfg)
        if paths.FROZEN:
            _limpa_pontes_velhas(_ponte_dir())
    except Exception as e:
        return {"ok": False, "error": "nao foi possivel gravar %s: %s" % (p, e)}
    return {"ok": True, "installed": True, "settings": p}


def uninstall_bridge():
    p = _settings_path()
    try:
        cfg = _read_settings()
        if _is_bridge(cfg.get("statusLine")):
            prev = None
            try:
                with open(os.path.join(_ia_dir(), ANTERIOR_NOME), "r", encoding="utf-8-sig") as f:
                    prev = json.load(f).get("statusLine")
            except Exception:
                pass
            if prev:
                cfg["statusLine"] = prev
            else:
                cfg.pop("statusLine", None)
            _write_settings(cfg)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "installed": False}


def refresh_bridge():
    """Na partida: se a ponte esta instalada mas a versao/caminho mudou
    (programa atualizado ou movido), extrai de novo e reaponta em silencio."""
    try:
        if not bridge_installed():
            return False
        cfg = _read_settings()
        atual = cfg["statusLine"].get("command")
        if atual == bridge_command() and (not paths.FROZEN or _ponte_version() == VERSION):
            return False
        r = install_bridge()
        print("Ponte do Claude Code atualizada: %s" % ("ok" if r.get("ok") else r.get("error")))
        return bool(r.get("ok"))
    except Exception as e:  # noqa: BLE001
        print("Aviso: ponte do Claude Code: %s" % e)
        return False
