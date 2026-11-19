# -*- coding: utf-8 -*-
"""Biblioteca de comandos prontos (GET /api/library). Modulo Python (e nao
JSON) para o PyInstaller incluir sem configuracao extra. Cada item e um
botao pronto: label, icon (nomes de SD.ICONS em web/js/core.js), color,
action e, opcionais, toggle e help. check() valida tudo pelo registro de acoes."""
import copy

BLUE, GREEN, ORANGE, RED, PURPLE = "#0a84ff", "#30d158", "#ff9f0a", "#ff453a", "#bf5af2"
TEAL, INDIGO, PINK, GRAY, YELLOW = "#64d2ff", "#5e5ce6", "#ff375f", "#8e8e93", "#ffd60a"


def _hk(label, icon, color, keys, help=None):
    it = {"label": label, "icon": icon, "color": color, "action": {"type": "hotkey", "keys": keys.split("+")}}
    if help:
        it["help"] = help
    return it


def _cmd(label, icon, color, command, help=None):
    it = {"label": label, "icon": icon, "color": color, "action": {"type": "command", "command": command}}
    if help:
        it["help"] = help
    return it


def _app(label, icon, color, exe, keys, help=None, back=True):
    it = {"label": label, "icon": icon, "color": color,
          "action": {"type": "apphotkey", "app": exe, "keys": keys.split("+"), "back": back}}
    if help:
        it["help"] = help
    return it


def _site(label, icon, color, url):
    return {"label": label, "icon": icon, "color": color,
            "action": {"type": "site", "url": url, "browser": "default"}}


OBS_HELP = ("O OBS não vem com teclas de atalho prontas: em OBS > Configurações > Teclas de atalho, "
            "defina a mesma combinação deste botão (ou mude o botão para a sua).")

LIBRARY = [
    {"name": "Windows", "items": [
        _cmd("Bloquear PC", "lock", GRAY, "rundll32.exe user32.dll,LockWorkStation"),
        _cmd("Desligar PC (na hora)", "power", RED, "shutdown /s /t 0",
             help="Desliga o PC imediatamente, sem perguntar. Salve seu trabalho antes."),
        _cmd("Reiniciar PC (na hora)", "power", ORANGE, "shutdown /r /t 0",
             help="Reinicia o PC imediatamente, sem perguntar."),
        _cmd("Suspender", "power", INDIGO, "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
             help="Se a hibernação estiver ligada no Windows, o PC hiberna em vez de suspender."),
        _hk("Captura de tela", "camera", TEAL, "win+shift+s"),
        _hk("Área de trabalho", "desktop", BLUE, "win+d"),
        _hk("Minimizar tudo", "desktop", GRAY, "win+m"),
        _hk("Gerenciador de Tarefas", "chart", GREEN, "ctrl+shift+esc"),
        _hk("Configurações", "gear", GRAY, "win+i"),
        _hk("Explorador de arquivos", "folder", YELLOW, "win+e"),
        _hk("Emojis", "smile", YELLOW, "win+."),
        _hk("Área de transferência", "paste", PURPLE, "win+v"),
        _hk("Trocar janela", "apps", BLUE, "alt+tab"),
        _hk("Fechar janela", "close", RED, "alt+f4"),
    ]},
    {"name": "Mídia", "items": [
        _hk("Play/Pausa", "playpause", BLUE, "playpause"),
        _hk("Próxima", "next", BLUE, "next"),
        _hk("Anterior", "prev", BLUE, "prev"),
        _hk("Parar", "stop", RED, "stop"),
        _hk("Volume +", "volup", PURPLE, "volumeup"),
        _hk("Volume -", "voldown", PURPLE, "volumedown"),
        _hk("Mudo", "mute", GRAY, "mute"),
    ]},
    {"name": "Edição", "items": [
        _hk("Copiar", "copy", BLUE, "ctrl+c"),
        _hk("Colar", "paste", BLUE, "ctrl+v"),
        _hk("Recortar", "cut", BLUE, "ctrl+x"),
        _hk("Desfazer", "undo", ORANGE, "ctrl+z"),
        _hk("Refazer", "redo", ORANGE, "ctrl+y"),
        _hk("Salvar", "save", GREEN, "ctrl+s"),
        _hk("Selecionar tudo", "select", INDIGO, "ctrl+a"),
        _hk("Localizar", "text", TEAL, "ctrl+f"),
    ]},
    {"name": "Navegador", "items": [
        _hk("Nova aba", "plus", BLUE, "ctrl+t"),
        _hk("Fechar aba", "close", RED, "ctrl+w"),
        _hk("Reabrir aba", "undo", ORANGE, "ctrl+shift+t"),
        _hk("Próxima aba", "forward", INDIGO, "ctrl+tab"),
        _hk("Aba anterior", "back", INDIGO, "ctrl+shift+tab"),
        _hk("Recarregar", "updown", GREEN, "f5"),
        _hk("Tela cheia", "desktop", GRAY, "f11"),
        _site("YouTube", "play", RED, "https://www.youtube.com/"),
        _site("Google", "globe", BLUE, "https://www.google.com/"),
    ]},
    {"name": "OBS", "items": [
        _app("Iniciar/parar transmissão", "onair", RED, "obs64.exe", "ctrl+alt+shift+1", OBS_HELP),
        _app("Iniciar/parar gravação", "record", RED, "obs64.exe", "ctrl+alt+shift+2", OBS_HELP),
        _app("Cena 1", "scene", INDIGO, "obs64.exe", "ctrl+alt+shift+3", OBS_HELP),
        _app("Cena 2", "scene", INDIGO, "obs64.exe", "ctrl+alt+shift+4", OBS_HELP),
        _app("Mudo do mic (OBS)", "micoff", GRAY, "obs64.exe", "ctrl+alt+shift+5", OBS_HELP),
    ]},
    {"name": "Discord", "items": [
        _app("Mutar (Discord)", "micoff", INDIGO, "discord.exe", "ctrl+shift+m"),
        _app("Ensurdecer (Discord)", "headphones", INDIGO, "discord.exe", "ctrl+shift+d"),
    ]},
    {"name": "Spotify", "items": [
        _app("Play/Pausa (Spotify)", "playpause", GREEN, "spotify.exe", "space"),
        _app("Próxima (Spotify)", "next", GREEN, "spotify.exe", "ctrl+right"),
        _app("Anterior (Spotify)", "prev", GREEN, "spotify.exe", "ctrl+left"),
    ]},
    {"name": "Teams", "items": [
        _app("Mutar (Teams)", "micoff", PURPLE, "ms-teams.exe", "ctrl+shift+m",
             help="No Teams clássico o programa é Teams.exe: troque no campo Programa se precisar."),
        _app("Câmera (Teams)", "camera", PURPLE, "ms-teams.exe", "ctrl+shift+o",
             help="No Teams clássico o programa é Teams.exe: troque no campo Programa se precisar."),
    ]},
    {"name": "Zoom", "items": [
        _app("Mutar (Zoom)", "micoff", BLUE, "zoom.exe", "alt+a"),
        _app("Câmera (Zoom)", "camera", BLUE, "zoom.exe", "alt+v"),
    ]},
    {"name": "Rádio", "items": [
        {"label": "Parar sons", "icon": "stop", "color": RED, "action": {"type": "stopsound"}},
        {"label": "Mudo mic", "icon": "mic", "color": GREEN, "action": {"type": "mute", "target": "mic"}},
        {"label": "Mudo efeitos", "icon": "mute", "color": ORANGE, "action": {"type": "mute", "target": "effects"}},
        {"label": "ON AIR", "icon": "onair", "color": RED, "toggle": True, "action": {"type": "none"},
         "on": {"label": "NO AR", "color": "#ff0000"},
         "help": "Botão liga/desliga: fica aceso em todos os aparelhos enquanto estiver no ar."},
    ]},
]


def check():
    """Valida todos os itens (acoes pelo registro e o botao pelo schema).
    Levanta ValueError no primeiro problema."""
    from . import schema
    for g in LIBRARY:
        for it in g["items"]:
            btn = dict((k, v) for k, v in it.items() if k != "help")
            schema.validate_button(btn, 1, "Biblioteca %s / %s" % (g["name"], it["label"]))


def groups():
    return copy.deepcopy(LIBRARY)
