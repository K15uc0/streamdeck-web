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


OBS_HELP = ("Usa o WebSocket do OBS (OBS 28 ou mais novo): no OBS, abra Ferramentas > Configurações do "
            "WebSocket e marque \"Ativar servidor WebSocket\". Se usar senha, informe-a na tela Conectar do PC. "
            "Troque o nome da cena/fonte pelo do seu OBS.")


def _obs(label, icon, color, action, lit=None, live=None):
    it = {"label": label, "icon": icon, "color": color, "action": action, "help": OBS_HELP}
    if lit:
        it["lit"] = lit
    if live:
        it["live"] = live
    return it


def _confirm(it):
    it["confirm"] = True
    return it


LIBRARY = [
    {"name": "Windows", "items": [
        _cmd("Bloquear PC", "lock", GRAY, "rundll32.exe user32.dll,LockWorkStation"),
        _confirm(_cmd("Desligar PC (na hora)", "power", RED, "shutdown /s /t 0",
                      help="Desliga o PC imediatamente. O celular pede um segundo toque para confirmar.")),
        _confirm(_cmd("Reiniciar PC (na hora)", "power", ORANGE, "shutdown /r /t 0",
                      help="Reinicia o PC imediatamente. O celular pede um segundo toque para confirmar.")),
        _confirm(_cmd("Suspender", "power", INDIGO, "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                      help="Se a hibernação estiver ligada no Windows, o PC hiberna em vez de suspender.")),
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
    {"name": "OBS (WebSocket)", "items": [
        _obs("Transmissão", "onair", RED, {"type": "obs_stream", "mode": "toggle"},
             lit="obs:stream", live="obs:stream"),
        _obs("Gravação", "record", RED, {"type": "obs_record", "mode": "toggle"},
             lit="obs:record", live="obs:record"),
        _obs("Cena 1", "scene", INDIGO, {"type": "obs_scene", "scene": "Cena 1"}, lit="obs:scene=Cena 1"),
        _obs("Cena 2", "scene", INDIGO, {"type": "obs_scene", "scene": "Cena 2"}, lit="obs:scene=Cena 2"),
        _obs("Mudo do mic (OBS)", "micoff", GRAY, {"type": "obs_mute", "input": "Mic/Aux", "mode": "toggle"},
             lit="obs:mute=Mic/Aux"),
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
