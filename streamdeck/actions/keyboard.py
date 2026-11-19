# -*- coding: utf-8 -*-
"""Acoes de teclado: atalho e digitar texto."""
from . import action, Field
from .. import winapi

KEYS_HELP = ("Separe as teclas com +. Letras, números, ctrl, shift, alt, win, enter, esc, tab, space, backspace, delete, "
             "home, end, pageup, pagedown, left, up, right, down, printscreen, f1…f24, playpause, "
             "next, prev, stop, mute, volumeup, volumedown, e . , - = ; /")


@action("hotkey", "Atalho de teclado", group="Geral", icon="keyboard",
        fields=[Field("keys", "Teclas", "keys", required=True,
                      placeholder="ctrl+shift+m", help=KEYS_HELP)])
def hotkey(a):
    winapi.send_keys(a["keys"])


@action("text", "Digitar mensagem no chat", group="Rádio", icon="chat",
        help="O texto é digitado onde o cursor estiver no PC. Deixe o campo de mensagem do chat selecionado.",
        fields=[Field("text", "Mensagem", "textarea", required=True),
                Field("enter", "Apertar Enter no final (enviar)", "bool", default=True)])
def text(a):
    winapi.type_text(a["text"], bool(a.get("enter")))
