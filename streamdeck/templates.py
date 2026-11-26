# -*- coding: utf-8 -*-
"""Modelos de pagina prontos (GET /api/templates). Cada modelo e uma pagina
inteira ({name, buttons}) que cabe na grade 5x3 (15 posicoes). O editor
insere uma copia como nova pagina. Reaproveita itens da biblioteca."""
import copy

from . import library as L

MAX_SLOTS = 15


def _lib(group, name, **extra):
    """Copia de um item da biblioteca (sem o texto de ajuda)."""
    for g in L.LIBRARY:
        if g["name"] == group:
            for it in g["items"]:
                if it["label"] == name:
                    b = dict((k, v) for k, v in copy.deepcopy(it).items() if k != "help")
                    b.update(extra)
                    return b
    raise KeyError("%s / %s" % (group, name))


def _btn(label, icon, color, action, **extra):
    b = {"label": label, "icon": icon, "color": color, "action": action}
    b.update(extra)
    return b


def _hk(label, icon, color, keys):
    return _btn(label, icon, color, {"type": "hotkey", "keys": keys.split("+")})


def _fader(label, icon, color, target):
    return {"kind": "fader", "label": label, "icon": icon, "color": color, "target": target}


def _sound(label, icon, color, f):
    return _btn(label, icon, color, {"type": "sound", "file": f, "volume": 100})


def _empty():
    return {"label": "", "icon": "", "color": "", "action": {"type": "none"}}


TEMPLATES = [
    {"id": "radio", "name": "Rádio", "icon": "radio",
     "desc": "Faders de som e microfone, ON AIR, vinhetas e mudos para quem faz rádio ao vivo.",
     "page": {"name": "Rádio", "buttons": [
         _fader("Master", "sound", L.BLUE, "master"),
         _fader("Efeitos", "music", L.PURPLE, "effects"),
         _fader("Mic", "mic", L.GREEN, "mic"),
         _lib("Rádio", "ON AIR"),
         _btn("Relógio", "clock", L.GRAY, {"type": "none"}, live="clock"),
         _lib("Rádio", "Mudo efeitos"),
         _lib("Rádio", "Mudo mic"),
         _lib("Rádio", "Parar sons"),
         _sound("Vinheta", "megaphone", L.ORANGE, "vinheta.mp3"),
         _sound("Aplausos", "hand", L.YELLOW, "aplausos.mp3"),
         _sound("Risadas", "smile", L.PINK, "risadas.mp3"),
         _sound("Suspense", "alert", L.INDIGO, "suspense.mp3"),
         _sound("Fundo", "waveform", L.TEAL, "fundo.mp3"),
         _btn("Cronômetro", "timer", L.GRAY, {"type": "none"}, live="timer"),
         _btn("Mensagem", "chat", L.BLUE, {"type": "text", "text": "Estamos no ar!", "enter": True}),
     ]}},
    {"id": "obs", "name": "OBS", "icon": "broadcast",
     "desc": "Transmissão, gravação, cenas e mudo pelo WebSocket do OBS 28+.",
     "page": {"name": "OBS", "buttons": [
         _lib("OBS (WebSocket)", "Transmissão", icon="broadcast"),
         _lib("OBS (WebSocket)", "Gravação"),
         _lib("OBS (WebSocket)", "Mudo do mic (OBS)", label="Mudo mic"),
         _btn("Cena atual", "scene", L.GRAY, {"type": "none"}, live="obs:scene"),
         _lib("Rádio", "Parar sons"),
         _lib("OBS (WebSocket)", "Cena 1", icon="num1"),
         _lib("OBS (WebSocket)", "Cena 2", icon="num2"),
         _btn("Cena 3", "num3", L.INDIGO, {"type": "obs_scene", "scene": "Cena 3"}, lit="obs:scene=Cena 3"),
         _btn("Câmera", "webcam", L.TEAL, {"type": "obs_scene", "scene": "Câmera"}, lit="obs:scene=Câmera"),
         _btn("Tela", "screen", L.BLUE, {"type": "obs_scene", "scene": "Tela"}, lit="obs:scene=Tela"),
         _btn("Pausa", "coffee", L.ORANGE, {"type": "obs_scene", "scene": "Pausa"}, lit="obs:scene=Pausa"),
         _btn("Mudo áudio PC", "mute", L.GRAY,
              {"type": "obs_mute", "input": "Áudio do desktop", "mode": "toggle"},
              lit="obs:mute=Áudio do desktop"),
         _fader("Mic", "mic", L.GREEN, "mic"),
         _fader("Master", "sound", L.BLUE, "master"),
         _btn("Início", "home", "#0a3069", {"type": "page", "to": 0}),
     ]}},
    {"id": "reuniao", "name": "Reunião", "icon": "users",
     "desc": "Mudo e câmera no Teams, Zoom e Discord, mais o mudo geral do microfone.",
     "page": {"name": "Reunião", "buttons": [
         _lib("Teams", "Mutar (Teams)", label="Mudo Teams"),
         _lib("Teams", "Câmera (Teams)", label="Câmera Teams"),
         _btn("Mão Teams", "hand", L.PURPLE,
              {"type": "apphotkey", "app": "ms-teams.exe", "keys": ["ctrl", "shift", "k"], "back": True}),
         _btn("Sair Teams", "callend", L.RED,
              {"type": "apphotkey", "app": "ms-teams.exe", "keys": ["ctrl", "shift", "h"], "back": True}),
         _lib("Rádio", "Mudo mic", label="Mudo mic (PC)", icon="micoff"),
         _lib("Zoom", "Mutar (Zoom)", label="Mudo Zoom"),
         _lib("Zoom", "Câmera (Zoom)", label="Câmera Zoom"),
         _btn("Tela Zoom", "screen", L.BLUE,
              {"type": "apphotkey", "app": "zoom.exe", "keys": ["alt", "s"], "back": True}),
         _btn("Sair Zoom", "callend", L.RED,
              {"type": "apphotkey", "app": "zoom.exe", "keys": ["alt", "q"], "back": True}),
         _fader("Mic", "mic", L.GREEN, "mic"),
         _lib("Discord", "Mutar (Discord)", label="Mudo Discord"),
         _lib("Discord", "Ensurdecer (Discord)", label="Surdo Discord", icon="headset"),
         _empty(),
         _empty(),
         _fader("Volume", "sound", L.BLUE, "master"),
     ]}},
    {"id": "midia", "name": "Mídia", "icon": "music",
     "desc": "Controles de música e vídeo do Windows, com faders do PC e dos efeitos.",
     "page": {"name": "Mídia", "buttons": [
         _lib("Mídia", "Anterior"),
         _lib("Mídia", "Play/Pausa"),
         _lib("Mídia", "Próxima"),
         _fader("Master", "sound", L.BLUE, "master"),
         _fader("Efeitos", "music", L.PURPLE, "effects"),
         _lib("Mídia", "Parar"),
         _lib("Mídia", "Mudo"),
         _btn("Volume", "volmid", L.GRAY, {"type": "none"}, live="volume:master"),
         _lib("Mídia", "Volume -"),
         _lib("Mídia", "Volume +"),
         _btn("Spotify", "music", L.GREEN, {"type": "app", "target": "spotify.exe"}),
         _lib("Spotify", "Anterior (Spotify)", label="Spotify ◀"),
         _lib("Spotify", "Play/Pausa (Spotify)", label="Spotify ⏯"),
         _lib("Spotify", "Próxima (Spotify)", label="Spotify ▶"),
         _lib("Navegador", "YouTube"),
     ]}},
    {"id": "monitor", "name": "Monitor do PC", "icon": "cpu",
     "desc": "CPU, memória, GPU, temperatura e rede ao vivo, tela de processos e o consumo do Claude e do Codex.",
     "page": {"name": "Monitor", "grid": {"columns": 5, "rows": 4}, "buttons": [
         _btn("CPU", "cpu", L.BLUE, {"type": "none"}, live="pc:cpu", w=2),
         _btn("Memória", "layers", L.PURPLE, {"type": "none"}, live="pc:mem"),
         _btn("GPU", "chart", L.GREEN, {"type": "none"}, live="pc:gpu"),
         {"kind": "monitor", "label": "Monitor", "icon": "monitor", "color": L.INDIGO, "w": 2, "h": 2},
         _btn("CPU °C", "bolt", L.ORANGE, {"type": "none"}, live="pc:temp_cpu"),
         _btn("Rede", "wifi", L.TEAL, {"type": "none"}, live="pc:net", w=2),
         _btn("Claude 5 h", "sparkles", L.ORANGE, {"type": "none"}, live="ia:claude:5h"),
         _btn("Claude sem", "sparkles", L.ORANGE, {"type": "none"}, live="ia:claude:week"),
         _btn("Codex 5 h", "sparkles", L.GRAY, {"type": "none"}, live="ia:codex:5h"),
     ]}},
    {"id": "windows", "name": "Atalhos do Windows", "icon": "windows",
     "desc": "Bloquear, captura de tela, área de trabalho, gerenciador de tarefas e energia.",
     "page": {"name": "Windows", "buttons": [
         _lib("Windows", "Bloquear PC", label="Bloquear"),
         _lib("Windows", "Captura de tela"),
         _lib("Windows", "Área de trabalho", label="Desktop"),
         _lib("Windows", "Trocar janela"),
         _lib("Windows", "Fechar janela", icon="xcircle"),
         _lib("Windows", "Explorador de arquivos", label="Arquivos"),
         _lib("Windows", "Gerenciador de Tarefas", label="Tarefas", icon="cpu"),
         _lib("Windows", "Configurações"),
         _lib("Windows", "Área de transferência", label="Histórico", icon="clipboard"),
         _lib("Windows", "Emojis"),
         _hk("Ditado", "mic", L.TEAL, "win+h"),
         _hk("Projetar", "cast", L.INDIGO, "win+p"),
         _lib("Windows", "Suspender", icon="sleep"),
         _lib("Windows", "Reiniciar PC (na hora)", label="Reiniciar", icon="restart"),
         _lib("Windows", "Desligar PC (na hora)", label="Desligar"),
     ]}},
    {"id": "navegador", "name": "Navegador", "icon": "globe",
     "desc": "Abas, voltar/avançar, zoom, busca e sites favoritos.",
     "page": {"name": "Navegador", "buttons": [
         _hk("Voltar", "left", L.BLUE, "alt+left"),
         _hk("Avançar", "right", L.BLUE, "alt+right"),
         _lib("Navegador", "Recarregar", icon="refresh"),
         _lib("Navegador", "Nova aba"),
         _lib("Navegador", "Fechar aba"),
         _lib("Navegador", "Aba anterior"),
         _lib("Navegador", "Próxima aba"),
         _lib("Navegador", "Reabrir aba"),
         _hk("Buscar", "search", L.TEAL, "ctrl+f"),
         _lib("Navegador", "Tela cheia", icon="fullscreen"),
         _hk("Mais zoom", "zoomin", L.INDIGO, "ctrl+="),
         _hk("Menos zoom", "zoomout", L.INDIGO, "ctrl+-"),
         _hk("Favoritar", "bookmark", L.YELLOW, "ctrl+d"),
         _lib("Navegador", "Google"),
         _lib("Navegador", "YouTube"),
     ]}},
]


def check():
    """Valida todas as paginas pelo schema. Levanta ValueError no primeiro problema."""
    from . import schema
    for t in TEMPLATES:
        btns = t["page"]["buttons"]
        if len(btns) > MAX_SLOTS:
            raise ValueError("Modelo %s: botoes demais" % t["name"])
        for i, b in enumerate(btns):
            schema.validate_button(b, 1, "Modelo %s, botao %d" % (t["name"], i + 1))
        if "grid" in t["page"]:
            schema.validate_config({"version": schema.CONFIG_VERSION, "columns": 5, "rows": 3,
                                    "pages": [t["page"]]})


def templates():
    return copy.deepcopy(TEMPLATES)
