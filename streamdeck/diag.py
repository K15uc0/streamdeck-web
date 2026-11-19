# -*- coding: utf-8 -*-
"""Diagnostico em memoria: inicio, aparelhos recentes e ultimos erros do log."""
import collections
import socket
import threading
import time

STARTED = time.time()
_LOCK = threading.Lock()
MAX_CLIENTS = 20
MAX_ERRORS = 30
_CLIENTS = collections.OrderedDict()   # ip -> {"ip", "last_seen", "user_agent"}
_ERRORS = collections.deque(maxlen=MAX_ERRORS)
_PARTIAL = [""]


def short_agent(ua):
    """Resumo curto do navegador do aparelho."""
    ua = (ua or "").strip()
    for key, name in (("iPad", "iPad"), ("iPhone", "iPhone"), ("Android", "Android"),
                      ("Windows", "Windows"), ("Macintosh", "Mac"), ("Linux", "Linux")):
        if key in ua:
            for b in ("Edg/", "Chrome/", "Firefox/", "Safari/"):
                if b in ua:
                    return "%s (%s)" % (name, b.rstrip("/").replace("Edg", "Edge"))
            return name
    return ua[:40]


def note_client(ip, user_agent):
    with _LOCK:
        _CLIENTS.pop(ip, None)
        _CLIENTS[ip] = {"ip": ip, "last_seen": int(time.time()), "user_agent": short_agent(user_agent)}
        while len(_CLIENTS) > MAX_CLIENTS:
            _CLIENTS.popitem(last=False)


def clients():
    with _LOCK:
        return list(reversed(list(_CLIENTS.values())))


def _is_error(line):
    low = line.lower()
    return line.lstrip().startswith("!") or "erro" in low or "falh" in low


def feed(text):
    """Chamado pelo Tee a cada escrita: guarda linhas que parecem erro."""
    try:
        with _LOCK:
            buf = _PARTIAL[0] + text
            lines = buf.split("\n")
            _PARTIAL[0] = lines.pop()[-2000:]
            for line in lines:
                line = line.rstrip("\r")
                if line.strip() and _is_error(line):
                    _ERRORS.append({"when": int(time.time()), "text": line.strip()[:300]})
    except Exception:  # noqa: BLE001 - o log nunca pode quebrar
        pass


def recent_errors():
    with _LOCK:
        return list(_ERRORS)


def ipv4_addresses():
    """Todos os IPv4 deste PC (sem 127.x)."""
    out = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in out and not ip.startswith("127."):
                out.append(ip)
    except OSError:
        pass
    try:
        from .security import lan_ip
        ip = lan_ip()
        if ip not in out and not ip.startswith("127."):
            out.insert(0, ip)
    except Exception:  # noqa: BLE001
        pass
    return out
