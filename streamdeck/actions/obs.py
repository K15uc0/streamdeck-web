# -*- coding: utf-8 -*-
"""Acoes do OBS pelo obs-websocket v5 (OBS 28+): cena, transmissao,
gravacao e mudo de fonte. No OBS: Ferramentas > Configuracoes do WebSocket."""
from . import action, Field
from .. import obs

HELP = ("Usa o WebSocket do OBS (OBS 28 ou mais novo). No OBS, abra Ferramentas > Configurações do "
        "WebSocket, marque \"Ativar servidor WebSocket\" e, se usar senha, informe-a na tela Conectar do PC.")
MODES = [("toggle", "Alternar"), ("start", "Iniciar"), ("stop", "Parar")]
MUTE_MODES = [("toggle", "Alternar"), ("mute", "Silenciar"), ("unmute", "Ativar som")]


def _mode(a):
    return a.get("mode") or "toggle"


@action("obs_scene", "OBS: trocar de cena", group="OBS", icon="scene", help=HELP,
        fields=[Field("scene", "Cena", "obs_scene", required=True, placeholder="Nome da cena")])
def obs_scene(a):
    obs.request("SetCurrentProgramScene", {"sceneName": str(a["scene"])})


@action("obs_stream", "OBS: transmissão", group="OBS", icon="onair", help=HELP,
        fields=[Field("mode", "O que fazer", "select", default="toggle", options=MODES)])
def obs_stream(a):
    obs.request({"toggle": "ToggleStream", "start": "StartStream", "stop": "StopStream"}[_mode(a)])


@action("obs_record", "OBS: gravação", group="OBS", icon="record", help=HELP,
        fields=[Field("mode", "O que fazer", "select", default="toggle", options=MODES)])
def obs_record(a):
    obs.request({"toggle": "ToggleRecord", "start": "StartRecord", "stop": "StopRecord"}[_mode(a)])


@action("obs_mute", "OBS: mudo de uma fonte", group="OBS", icon="micoff", help=HELP,
        fields=[Field("input", "Fonte de áudio", "obs_input", required=True, placeholder="Mic/Aux"),
                Field("mode", "O que fazer", "select", default="toggle", options=MUTE_MODES)])
def obs_mute(a):
    name = str(a["input"])
    if _mode(a) == "toggle":
        obs.request("ToggleInputMute", {"inputName": name})
    else:
        obs.request("SetInputMute", {"inputName": name, "inputMuted": _mode(a) == "mute"})
