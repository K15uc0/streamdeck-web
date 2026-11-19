# -*- coding: utf-8 -*-
"""Acoes de sistema: abrir site/arquivo/programa e rodar comando."""
import os
import subprocess
import webbrowser

from . import action, Field
from ..paths import IS_WINDOWS


def _is_web(target):
    return str(target).startswith(("http://", "https://"))


@action("open", "Abrir site, arquivo ou programa", group="Sistema", icon="globe",
        help="Sites (http/https) abrem no navegador do PC; caminhos abrem o arquivo ou programa.",
        fields=[Field("target", "Endereço ou caminho", "text", required=True,
                      placeholder="https://… ou C:\\Pasta\\programa.exe")])
def open_(a):
    target = a["target"]
    if _is_web(target):
        webbrowser.open(target)
    elif IS_WINDOWS:
        os.startfile(target)
    else:
        print("  [simulado] abrir:", target)


@action("command", "Rodar comando", group="Sistema", icon="code",
        help="Roda um comando do Windows (como no Executar).",
        fields=[Field("command", "Comando do Windows", "text", required=True, placeholder="notepad")])
def command(a):
    if IS_WINDOWS:
        subprocess.Popen(a["command"], shell=True,
                         creationflags=0x08000000)  # sem janela de console
    else:
        print("  [simulado] comando:", a["command"])
