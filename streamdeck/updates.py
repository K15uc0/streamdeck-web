# -*- coding: utf-8 -*-
"""Verificacao e aplicacao de atualizacoes (releases do GitHub)."""
import hashlib
import json
import os
import subprocess
import time
import urllib.request

from . import VERSION, REPO, paths

INSTALLER_NAME = "StreamDeck-Instalador.exe"   # programa instalado (pasta com _internal)
PORTABLE_NAME = "StreamDeck.exe"               # arquivo unico (portatil)

UPDATE = {"available": False, "latest": None, "notes": "", "page": None, "asset": None, "digest": None,
          "error": None, "checked": None, "state": "idle"}


def parse_ver(v):
    out = []
    for part in str(v).lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out + [0] * (3 - len(out)))


def install_kind(exe_path, exists=os.path.exists):
    """'instalado' (instalador: pasta com _internal ou unins000.exe ao lado do .exe),
    'portatil' (StreamDeck.exe de arquivo unico) ou None (rodando pelo codigo)."""
    if not exe_path:
        return None
    folder = os.path.dirname(os.path.abspath(exe_path))
    if exists(os.path.join(folder, "_internal")) or exists(os.path.join(folder, "unins000.exe")):
        return "instalado"
    return "portatil"


def current_kind():
    return install_kind(paths.EXE_PATH if paths.FROZEN else None)


def pick_asset(assets, kind, repo=REPO):
    """Escolhe o arquivo da release pelo nome (nao mais 'o ultimo .exe').
    Devolve (link, sha256 ou None) ou (None, None)."""
    want = INSTALLER_NAME if kind == "instalado" else PORTABLE_NAME
    prefix = "https://github.com/%s/releases/download/" % repo
    for a in assets or []:
        link = a.get("browser_download_url") or ""
        if str(a.get("name", "")).lower() == want.lower() and link.startswith(prefix):
            dg = str(a.get("digest") or "")
            return link, (dg[7:].lower() if dg.lower().startswith("sha256:") else None)
    return None, None


def check_updates():
    url = os.environ.get("STREAMDECK_UPDATE_URL") or "https://api.github.com/repos/%s/releases/latest" % REPO
    req = urllib.request.Request(url, headers={"User-Agent": "StreamDeck/" + VERSION,
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        asset, digest = pick_asset(data.get("assets", []), current_kind())
        was = UPDATE["available"]
        UPDATE.update(latest=tag.lstrip("vV"), notes=data.get("body") or "", page=data.get("html_url"),
                      asset=asset, digest=digest, error=None, checked=time.strftime("%d/%m %H:%M"),
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
    if current_kind() == "instalado":
        cleanup_installer()
        return
    part = paths.EXE_PATH + ".download"
    if os.path.exists(part):
        try:
            os.remove(part)
        except OSError:
            pass
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


def _download(url, dest, min_size=1000000):
    """Baixa url em dest conferindo o MZ, o tamanho e o SHA-256 da release."""
    sha = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "StreamDeck/" + VERSION})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
            sha.update(chunk)
    with open(dest, "rb") as f:
        head = f.read(2)
    if head != b"MZ" or os.path.getsize(dest) < min_size:
        os.remove(dest)
        raise RuntimeError("arquivo baixado invalido")
    if UPDATE.get("digest"):
        if sha.hexdigest().lower() != UPDATE["digest"]:
            os.remove(dest)
            raise RuntimeError("SHA-256 do arquivo baixado nao confere com o da versao publicada")
        print("* SHA-256 conferido: %s" % UPDATE["digest"])


INSTALLER_ARGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/RESTARTAPP=1"]


def installer_command(installer, app_dir):
    """Linha de comando do instalador silencioso (reinstala na mesma pasta)."""
    return [installer] + INSTALLER_ARGS + ['/DIR=%s' % app_dir]


def apply_installer_update():
    """Programa instalado: baixa o instalador novo para Documentos\\StreamDeck\\atualizacao,
    roda em silencio (ele fecha este app pelo /api/local/quit, troca os arquivos
    e abre a versao nova) e sai."""
    folder = os.path.join(paths.BASE, "atualizacao")
    try:
        UPDATE["state"] = "downloading"
        print("* baixando instalador da versao %s..." % UPDATE["latest"])
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, INSTALLER_NAME)
        if os.path.exists(dest):
            os.remove(dest)
        _download(UPDATE["asset"], dest)
        UPDATE["state"] = "restarting"
        print("* instalando %s, o programa reabre sozinho..." % UPDATE["latest"])
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: o instalador sobrevive a este processo
        subprocess.Popen(installer_command(dest, os.path.dirname(paths.EXE_PATH)), cwd=folder,
                         creationflags=0x00000008 | 0x00000200, close_fds=True)
        time.sleep(1.5)
        os._exit(0)
    except Exception as e:
        UPDATE["state"] = "error"
        UPDATE["error"] = "falha ao atualizar: %s" % e
        print("! " + UPDATE["error"])


def cleanup_installer():
    folder = os.path.join(paths.BASE, "atualizacao")
    try:
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                os.remove(os.path.join(folder, name))
            os.rmdir(folder)
    except OSError:
        pass


def apply_update():
    if current_kind() == "instalado":
        return apply_installer_update()
    return apply_portable_update()


def apply_portable_update():
    """Baixa o novo StreamDeck.exe, troca pelo atual e reinicia.
    Os dados (Documentos\\StreamDeck) nao sao tocados."""
    exe = paths.EXE_PATH
    try:
        UPDATE["state"] = "downloading"
        print("* baixando versao %s..." % UPDATE["latest"])
        new = exe + ".download"
        _download(UPDATE["asset"], new)
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
        try:
            if os.path.exists(exe + ".download"):
                os.remove(exe + ".download")
        except OSError:
            pass
        UPDATE["state"] = "error"
        UPDATE["error"] = "falha ao atualizar: %s" % e
        print("! " + UPDATE["error"])


def update_status():
    st = dict(UPDATE)
    st.update(ok=True, version=VERSION, auto=bool(paths.FROZEN and UPDATE["asset"]), kind=current_kind())
    return st
