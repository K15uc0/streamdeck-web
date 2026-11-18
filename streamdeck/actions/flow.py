# -*- coding: utf-8 -*-
"""Acoes de fluxo: nada (espaco vazio), ir para pagina e sequencia."""
import time

from . import action, Field, run, is_dangerous


@action("none", "Nada (espaço vazio)", group="Geral", icon="")
def none(a):
    pass   # botao vazio ou so liga/desliga (toggle)


@action("page", "Ir para outra página", group="Geral", icon="forward",
        help="Troca a página mostrada neste aparelho.",
        fields=[Field("to", "Página", "page", required=True)])
def page(a):
    pass   # a troca de pagina acontece no aparelho


def _multi_dangerous(a):
    return any(is_dangerous(x) for x in a.get("steps") or [])


@action("multi", "Sequência de ações (avançado)", group="Geral", icon="bolt",
        help="Executa várias ações em ordem, com uma pausa entre elas.",
        dangerous=_multi_dangerous, warn=False,
        fields=[Field("steps", "Passos", "steps", required=True,
                      help='Cada passo é uma ação: {"type":"hotkey","keys":["ctrl","c"]}, '
                           '{"type":"sound","file":"vinheta.mp3"}, {"type":"text","text":"Olá!","enter":true}, '
                           '{"type":"open","target":"…"} ou {"type":"command","command":"…"}.'),
                Field("delay", "Pausa entre passos (segundos)", "number", min=0, max=60, step=0.1, default=0.2)])
def multi(a):
    for step in a["steps"]:
        run(step)
        time.sleep(a.get("delay", 0.1))
