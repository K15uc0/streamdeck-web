# -*- coding: utf-8 -*-
"""Verificacao e aplicacao de atualizacoes (releases do GitHub)."""
import json
import os
import subprocess
import time
import urllib.request

from . import VERSION, REPO, paths

UPDATE = {"available": False, "latest": None, "notes": "", "page": None, "asset": None,
          "error": None, "checked": None, "state": "idle"}


def parse_ver(v):
    out = []
    for part in str(v).lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out + [0] * (3 - len(out)))


def check_updates():
    url = os.environ.get("STREAMDECK_UPDATE_URL") or "https://api.github.com/repos/%s/releases/latest" % REPO
    req = urllib.request.Request(url, headers={"User-Agent": "StreamDeck/" + VERSION,
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        asset = None
        for a in data.get("assets", []):
            link = a.get("browser_download_url") or ""
            if a.get("name", "").lower().endswith(".exe") and \
                    link.startswith("https://github.com/%s/releases/download/" % REPO):
                asset = link
        was = UPDATE["available"]
        UPDATE.update(latest=tag.lstrip("vV"), notes=data.get("body") or "", page=data.get("html_url"),
                      asset=asset, error=None, checked=time.strftime("%d/%m %H:%M"),
                      available=parse_ver(tag) > parse_ver(VERSION))
        if UPDATE["available"] and not was:
            print("* nova versao disponivel: %s (instalada: %s)" % (UPDATE["latest"], VERSION))
    except Exception as e:
        code = getattr(e, "code", None)
        UPDATE.update(error="nenhuma versao publicada ainda" if code == 404 else str(e),
                      checked=time.strftime("%d/%m %H:%M"))
    return UPDATE


def update_loop():
    time.sleep(3)
    while True:
        check_updates()
        time.sleep(6 * 3600)


def cleanup_old_exe():
    if not paths.FROZEN:
        return
    old = paths.EXE_PATH + ".old"
    for _ in range(30):
        if not os.path.exists(old):
            return
        try:
            os.remove(old)
            return
        except OSError:
            time.sleep(2)


def can_apply():
    return bool(paths.FROZEN and UPDATE["available"] and UPDATE["asset"])


def apply_update():
    """Baixa o novo StreamDeck.exe, troca pelo atual e reinicia.
    Os dados (Documentos\\StreamDeck) nao sao tocados."""
    exe = paths.EXE_PATH
    try:
        UPDATE["state"] = "downloading"
        print("* baixando versao %s..." % UPDATE["latest"])
        new = exe + ".new"
        req = urllib.request.Request(UPDATE["asset"], headers={"User-Agent": "StreamDeck/" + VERSION})
        with urllib.request.urlopen(req, timeout=120) as r, open(new, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
        with open(new, "rb") as f:
            head = f.read(2)
        if head != b"MZ" or os.path.getsize(new) < 1000000:
            os.remove(new)
            raise RuntimeError("arquivo baixado invalido")
        old = exe + ".old"
        if os.path.exists(old):
            os.remove(old)
        os.replace(exe, old)      # o Windows permite renomear o .exe em uso
        os.replace(new, exe)
        UPDATE["state"] = "restarting"
        print("* atualizado para %s, reiniciando..." % UPDATE["latest"])
        subprocess.Popen([exe], cwd=os.path.dirname(exe), creationflags=0x00000010)
        time.sleep(1.5)
        os._exit(0)
    except Exception as e:
        UPDATE["state"] = "error"
        UPDATE["error"] = "falha ao atualizar: %s" % e
        print("! " + UPDATE["error"])


def update_status():
    st = dict(UPDATE)
    st.update(ok=True, version=VERSION, auto=bool(paths.FROZEN and UPDATE["asset"]))
    return st
