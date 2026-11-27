# -*- coding: utf-8 -*-
"""Acao browser (2.12): controlar o navegador do PC (pela extensao ou por atalhos)."""
from . import action, Field
from .. import navegador

OPS = [("tab_next", "Próxima aba"), ("tab_prev", "Aba anterior"), ("open_url", "Abrir site (nova aba)"),
       ("yt_toggle", "Pausar/continuar YouTube"), ("scroll", "Rolar a página"), ("back", "Voltar"),
       ("forward", "Avançar"), ("reload", "Recarregar"), ("close_tab", "Fechar aba atual")]
DIRS = [("down", "Para baixo"), ("up", "Para cima"), ("top", "Topo"), ("bottom", "Fim")]


def _cmd(a):
    c = {"op": a.get("op")}
    if c["op"] == "open_url":
        c["url"] = str(a.get("url") or "").strip()
    elif c["op"] == "scroll":
        c["dir"] = a.get("dir") or "down"
    return c


def _validate(a):
    if a.get("op") not in [o[0] for o in OPS]:
        raise ValueError("escolha o que fazer no navegador")
    try:
        navegador.check_cmd(_cmd(a))
    except navegador.BrowserError as e:
        raise ValueError(str(e))


@action("browser", "Navegador", group="Apps e sites", icon="globe", validate=_validate,
        help="Controla o navegador do PC. Com a extensão Stream Deck (Conectar > Navegador) funciona em "
             "qualquer janela; sem ela, vira atalho de teclado (Ctrl+Tab, Alt+←, F5…) no navegador que "
             "estiver na frente.",
        fields=[Field("op", "O que fazer", "select", required=True, default="tab_next", options=OPS),
                Field("url", "Endereço", "text", placeholder="https://…", when={"op": "open_url"}),
                Field("dir", "Direção", "select", default="down", options=DIRS, when={"op": "scroll"})])
def browser(a):
    how = navegador.execute(_cmd(a))
    print("  navegador: %s (%s)" % (a.get("op"), "extensao" if how == "ext" else "atalho"))
