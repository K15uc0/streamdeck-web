# -*- coding: utf-8 -*-
"""Acoes de apps e sites: trazer/abrir programa, atalho num programa,
abrir site (navegador, perfil, modo app) e ir para uma aba pelo titulo."""
import os
import subprocess
import time
import webbrowser

from . import action, Field
from .. import windows, winapi
from ..paths import IS_WINDOWS

GROUP = "Apps e sites"

BROWSERS = {
    # nome -> (exe, caminhos relativos a ProgramFiles/ProgramFiles(x86)/LOCALAPPDATA, familia)
    "chrome": ("chrome.exe", [r"Google\Chrome\Application\chrome.exe"], "chromium"),
    "edge": ("msedge.exe", [r"Microsoft\Edge\Application\msedge.exe"], "chromium"),
    "brave": ("brave.exe", [r"BraveSoftware\Brave-Browser\Application\brave.exe"], "chromium"),
    "firefox": ("firefox.exe", [r"Mozilla Firefox\firefox.exe"], "firefox"),
}
BROWSER_OPTIONS = [("default", "Navegador padrão"), ("chrome", "Google Chrome"),
                   ("edge", "Microsoft Edge"), ("firefox", "Firefox"), ("brave", "Brave")]
PROGIDS = (("chromehtml", "chrome"), ("msedgehtm", "edge"), ("bravehtml", "brave"),
           ("firefoxurl", "firefox"))


def _exe_name(target):
    t = os.path.basename(str(target).strip().strip('"').replace("/", "\\").split("\\")[-1]).lower()
    if t and not t.endswith(".exe"):
        t += ".exe"
    return t


def _app_path(exe):
    """Caminho de um .exe registrado em "App Paths" (como o Executar acha)."""
    if not IS_WINDOWS:
        return None
    import winreg
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s" % exe) as k:
                v = winreg.QueryValue(k, None)
                if v and os.path.isfile(v.strip('"')):
                    return v.strip('"')
        except OSError:
            pass
    return None


def default_browser():
    """chrome/edge/firefox/brave conforme o navegador padrao do Windows (ou None)."""
    if not IS_WINDOWS:
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations"
                            r"\UrlAssociations\https\UserChoice") as k:
            prog = str(winreg.QueryValueEx(k, "ProgId")[0]).lower()
    except OSError:
        return None
    for prefix, name in PROGIDS:
        if prog.startswith(prefix):
            return name
    return None


def browser_path(name):
    exe, rels, _fam = BROWSERS[name]
    found = _app_path(exe)
    if found:
        return found
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "ProgramW6432"):
        base = os.environ.get(env)
        for rel in rels:
            if base and os.path.isfile(os.path.join(base, rel)):
                return os.path.join(base, rel)
    return None


def launch(target):
    """Abre um programa (caminho completo ou nome como obs64.exe)."""
    target = str(target).strip().strip('"')
    if not IS_WINDOWS:
        print("  [simulado] abrir programa:", target)
        return
    if os.path.isabs(target) and os.path.isfile(target) and target.lower().endswith(".exe"):
        # alguns programas (OBS) precisam rodar de dentro da propria pasta
        subprocess.Popen([target], cwd=os.path.dirname(target), creationflags=0x00000008)  # DETACHED
        return
    path = _app_path(_exe_name(target)) if not os.path.isabs(target) else None
    if path:
        subprocess.Popen([path], cwd=os.path.dirname(path), creationflags=0x00000008)
        return
    os.startfile(target)


def bring(target):
    """Traz a janela do programa para a frente; devolve True se achou."""
    hwnd = windows.find_window(_exe_name(target))
    if hwnd:
        windows.focus(hwnd)
        return True
    return False


def _focused(hwnd):
    """Foca e confere: so manda teclas se a janela ficou mesmo na frente."""
    windows.focus(hwnd)
    fg = windows.foreground_hwnd()
    return fg is None or fg == getattr(hwnd, "value", hwnd)


def _no_unc(a):
    from ..paths import is_unc
    for key in ("target", "app"):
        if a.get(key) and is_unc(a[key]):
            raise ValueError("caminho de rede nao permitido")


@action("app", "Abrir ou trazer programa", group=GROUP, icon="apps", validate=_no_unc,
        help="Se o programa já estiver aberto, a janela dele vem para a frente; senão, ele é aberto. "
             "Escolha entre as janelas abertas ou digite o nome do .exe ou o caminho completo.",
        fields=[Field("target", "Programa", "app", required=True,
                      placeholder="obs64.exe ou C:\\Programas\\app.exe")])
def app(a):
    if not IS_WINDOWS:
        print("  [simulado] trazer/abrir programa:", a["target"])
        return
    if not bring(a["target"]):
        launch(a["target"])


@action("apphotkey", "Atalho num programa", group=GROUP, icon="keyboard", validate=_no_unc,
        help="Traz o programa para a frente, aperta as teclas e (se marcado) volta para a janela "
             "em que você estava. O programa precisa estar aberto.",
        fields=[Field("app", "Programa", "app", required=True, placeholder="discord.exe"),
                Field("keys", "Teclas", "keys", required=True, placeholder="ctrl+shift+m"),
                Field("back", "Voltar para a janela anterior depois", "bool", default=True)])
def apphotkey(a):
    if not IS_WINDOWS:
        print("  [simulado] atalho em %s: %s%s" % (a["app"], "+".join(a["keys"]),
                                                    " (e volta)" if a.get("back", True) else ""))
        return
    prev = windows.foreground_hwnd()
    hwnd = windows.find_window(_exe_name(a["app"]))
    if not hwnd:
        raise ValueError("o programa %s nao esta aberto" % _exe_name(a["app"]))
    if not _focused(hwnd):
        raise ValueError("nao consegui trazer %s para a frente" % _exe_name(a["app"]))
    time.sleep(0.08)
    winapi.send_keys(a["keys"])
    if a.get("back", True) and prev and prev != hwnd:
        time.sleep(0.1)
        windows.focus(prev)


def _validate_site(a):
    if not str(a.get("url", "")).startswith(("http://", "https://")):
        raise ValueError("o endereco deve comecar com http:// ou https://")
    prof = str(a.get("profile") or "")
    if len(prof) > 80 or any(c in prof for c in '"\r\n'):
        raise ValueError("perfil invalido")


@action("site", "Abrir site", group=GROUP, icon="globe", validate=_validate_site,
        help="Abre o endereço no navegador escolhido. Perfil: no Chrome/Edge/Brave é o nome da pasta "
             "do perfil (ex.: Default, Profile 1); no Firefox, o nome do perfil. “Modo app” abre numa "
             "janela própria, sem abas (Chrome, Edge e Brave).",
        fields=[Field("url", "Endereço", "text", required=True, placeholder="https://…"),
                Field("browser", "Navegador", "select", default="default", options=BROWSER_OPTIONS),
                Field("profile", "Perfil (opcional)", "text", placeholder="Profile 1"),
                Field("appmode", "Modo app (janela sem abas)", "bool", default=False)])
def site(a):
    url, name = a["url"], a.get("browser") or "default"
    profile, appmode = str(a.get("profile") or "").strip(), bool(a.get("appmode"))
    if name == "default":
        if not (profile or appmode):
            if IS_WINDOWS:
                webbrowser.open(url)
            else:
                print("  [simulado] abrir site:", url)
            return
        name = default_browser() or "edge"
    if not IS_WINDOWS:
        print("  [simulado] abrir site em %s: %s%s%s" % (name, url, " perfil " + profile if profile else "",
                                                          " (modo app)" if appmode else ""))
        return
    exe = browser_path(name)
    if not exe:
        raise ValueError("navegador %s nao encontrado" % name)
    fam = BROWSERS[name][2]
    args = [exe]
    if fam == "chromium":
        if profile:
            args.append("--profile-directory=%s" % profile)
        args.append("--app=%s" % url if appmode else url)
    else:
        if profile:
            args += ["-P", profile]
        args.append(url)
    subprocess.Popen(args, creationflags=0x00000008)


@action("tab", "Ir para aba do navegador", group=GROUP, icon="page",
        help="Traz o navegador para a frente e passa as abas (Ctrl+Tab) até achar uma cujo título "
             "contenha o texto. Funciona na janela do navegador que estiver na frente.",
        fields=[Field("browser", "Navegador", "select", default="default", options=BROWSER_OPTIONS),
                Field("title", "Título da aba contém", "text", required=True, placeholder="YouTube")])
def tab(a):
    want = str(a["title"]).strip().lower()
    name = a.get("browser") or "default"
    if not IS_WINDOWS:
        print("  [simulado] ir para aba '%s' (%s)" % (want, name))
        return
    names = [name] if name != "default" else [default_browser()] + [n for n in BROWSERS]
    hwnd = None
    for n in names:
        if n and not hwnd:
            hwnd = windows.find_window(BROWSERS[n][0])
    if not hwnd:
        raise ValueError("navegador nao esta aberto")
    if not _focused(hwnd):
        raise ValueError("nao consegui trazer o navegador para a frente")
    time.sleep(0.1)
    for _ in range(30):
        fg = windows.foreground_hwnd()
        if want in windows.window_title(fg).lower():
            return
        winapi.send_keys(["ctrl", "tab"])
        time.sleep(0.15)
    raise ValueError("aba nao encontrada: %s" % a["title"])
