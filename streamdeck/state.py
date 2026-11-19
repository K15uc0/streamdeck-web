# -*- coding: utf-8 -*-
"""Estado em memoria: botoes liga/desliga (toggle) e porta em uso.
O estado dos botoes vale para todos os aparelhos e some ao reiniciar.
Chave: "pagina:botao" ou, dentro de uma pasta, "pagina:botao:item"."""
import threading
import time

PORT = [None]          # porta em que o servidor esta escutando

_LOCK = threading.Lock()
_TOGGLES = {}          # chave -> epoch (s) em que foi ligado (so os ligados)


def key(p, b, f=None):
    return "%d:%d" % (p, b) if f is None else "%d:%d:%d" % (p, b, f)


def flip(p, b, f=None):
    """Inverte o botao e devolve o novo estado."""
    with _LOCK:
        k = key(p, b, f)
        on = k not in _TOGGLES
        if on:
            _TOGGLES[k] = int(time.time())
        else:
            _TOGGLES.pop(k, None)
        return on


def _button(cfg, k):
    parts = [int(x) for x in k.split(":")]
    btn = cfg.get("pages")[parts[0]]["buttons"][parts[1]]
    if len(parts) == 3:
        if not isinstance(btn, dict) or btn.get("kind") != "folder":
            return None
        btn = btn["buttons"][parts[2]]
    return btn


def _prune(cfg):
    for k in list(_TOGGLES):
        try:
            btn = _button(cfg, k)
            keep = isinstance(btn, dict) and btn.get("toggle") is True
        except (IndexError, KeyError, TypeError, ValueError, AttributeError):
            keep = False
        if not keep:
            _TOGGLES.pop(k, None)


def toggles(cfg=None):
    """Botoes ligados {"p:b": true}. Com cfg, descarta os que deixaram de
    existir ou de ser liga/desliga (botoes movidos ou editados)."""
    with _LOCK:
        if cfg is not None:
            _prune(cfg)
        return dict((k, True) for k in _TOGGLES)


def since(cfg=None):
    """{"p:b": epoch_s} dos botoes ligados."""
    with _LOCK:
        if cfg is not None:
            _prune(cfg)
        return dict(_TOGGLES)
