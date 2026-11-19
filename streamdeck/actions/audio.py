# -*- coding: utf-8 -*-
"""Acoes de som: tocar efeito, parar efeitos e ligar/desligar mudo."""
import os

from . import action, Field, current_key
from .. import audio, paths


@action("sound", "Tocar efeito sonoro", group="Rádio", icon="sound",
        help="Coloque os arquivos MP3 ou WAV na pasta sons, dentro da pasta StreamDeck do PC; "
             "eles aparecem na lista. Também aceita um caminho completo.",
        fields=[Field("file", "Arquivo", "sound", required=True,
                      placeholder="vinheta.mp3 ou C:\\Sons\\aplausos.wav"),
                Field("volume", "Volume (%)", "number", min=0, max=200, step=1, default=100,
                      help="Acima de 100% o som é amplificado (pode distorcer)."),
                Field("exclusive", "Parar os outros sons antes de tocar este", "bool", default=False),
                Field("fade_in", "Entrada suave (ms)", "number", min=0, max=5000, step=100, default=0,
                      help="0 = começa no volume cheio.")])
def sound(a):
    if paths.is_unc(a["file"]):
        raise ValueError("caminho de rede nao permitido para sons")
    path = audio.sound_path(a["file"])
    if not os.path.isfile(path):
        raise ValueError("arquivo de som nao encontrado: %s" % a["file"])
    audio.PLAYER.play(path, a.get("volume", 100), bool(a.get("exclusive")),
                      key=current_key(), fade_in=a.get("fade_in", 0))


@action("stopsound", "Parar efeitos sonoros", group="Rádio", icon="stop",
        help="Para todos os efeitos sonoros tocados pelo Stream Deck (na hora ou abaixando aos poucos).",
        fields=[Field("fade", "Saída suave (ms)", "number", min=0, max=5000, step=100, default=0,
                      help="0 = para na hora.")])
def stopsound(a):
    audio.PLAYER.stop_all(a.get("fade", 0))


@action("mute", "Ligar/desligar mudo", group="Rádio", icon="mute",
        fields=[Field("target", "O que silenciar", "select", default="master",
                      options=[("master", "Som do PC (master)"), ("effects", "Efeitos sonoros"),
                               ("mic", "Microfone")])])
def mute(a):
    audio.set_level(a.get("target", "master"), toggle_mute=True)
