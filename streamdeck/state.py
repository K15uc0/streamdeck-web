# -*- coding: utf-8 -*-
"""Estado em memoria: botoes liga/desliga (toggle) e porta em uso.
O estado dos botoes vale para todos os aparelhos e some ao reiniciar."""
import threading

PORT = [None]          # porta em que o servidor esta escutando

_LOCK = threading.Lock()
_TOGGLES = {}          # "pagina:botao" -> True (so os ligados)


def _key(p, b):
    return "%d:%d" % (p, b)


def flip(p, b):
    """Inverte o botao p:b e devolve o novo estado."""
    with _LOCK:
        k = _key(p, b)
        on = not _TOGGLES.get(k, False)
        if on:
            _TOGGLES[k] = True
        else:
            _TOGGLES.pop(k, None)
        return on


def toggles(cfg=None):
    """Botoes ligados {"p:b": true}. Com cfg, descarta os que deixaram de
    existir ou de ser liga/desliga (botoes movidos ou editados)."""
    with _LOCK:
        if cfg is not None:
            pages = cfg.get("pages") or []
            for k in list(_TOGGLES):
                p, b = (int(x) for x in k.split(":"))
                try:
                    btn = pages[p]["buttons"][b]
                    keep = isinstance(btn, dict) and btn.get("toggle") is True
                except (IndexError, KeyError, TypeError):
                    keep = False
                if not keep:
                    _TOGGLES.pop(k, None)
        return dict(_TOGGLES)
