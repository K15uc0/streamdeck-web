# -*- coding: utf-8 -*-
"""Seguranca.
1) So aceita aparelhos da rede local (nunca da internet, mesmo com porta aberta
   no roteador). 2) So aceita o nome/IP deste PC no cabecalho Host (bloqueia
   "DNS rebinding"). 3) Toda chamada da API exige o cabecalho X-StreamDeck,
   que sites de terceiros nao conseguem enviar (bloqueia CSRF). 4) Limite de
   tentativas com codigo errado. 5) A configuracao dos botoes so pode ser
   salva no proprio PC (tela Editar); os aparelhos so usam."""
import hmac
import ipaddress
import socket
import threading
import time

from . import storage
from .paths import inside, is_unc  # noqa: F401  (reexportados)

CGNAT = ipaddress.ip_network("100.64.0.0/10")   # Tailscale e similares


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def ip_allowed(ip):
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return a.is_loopback or a.is_private or a.is_link_local or (a.version == 4 and a in CGNAT)


def local_addresses():
    names = {"127.0.0.1", "localhost", "::1", lan_ip()}
    try:
        host = socket.gethostname()
        names.add(host.lower())
        names.add(host.lower() + ".local")
        names.update(socket.gethostbyname_ex(host)[2])
    except OSError:
        pass
    return names


ALLOWED_HOSTS = {"cache": set(), "at": 0.0}


def host_allowed(host_header):
    if not host_header:
        return False
    h = host_header.strip().lower()
    if h.startswith("["):                      # [::1]:8765
        h = h[1:].split("]")[0]
    else:
        h = h.rsplit(":", 1)[0] if h.count(":") == 1 else h
    if time.time() - ALLOWED_HOSTS["at"] > 30:   # IP pode mudar (DHCP)
        ALLOWED_HOSTS["cache"] = local_addresses()
        ALLOWED_HOSTS["at"] = time.time()
    return h in ALLOWED_HOSTS["cache"]


# ------------------------------------------------- tentativas com codigo errado ---
FAILS = {}
FAILS_LOCK = threading.Lock()
MAX_FAILS, FAIL_WINDOW = 10, 600


def fail_blocked(ip):
    with FAILS_LOCK:
        now = time.time()
        recent = [t for t in FAILS.get(ip, []) if now - t < FAIL_WINDOW]
        FAILS[ip] = recent
        return len(recent) >= MAX_FAILS


def note_fail(ip):
    with FAILS_LOCK:
        FAILS.setdefault(ip, []).append(time.time())
        n = len(FAILS[ip])
    if n == MAX_FAILS:
        print("! %s bloqueado por 10 minutos: muitas tentativas com codigo errado" % ip)


def same_token(value):
    tok = storage.token()
    return bool(value) and hmac.compare_digest(str(value).encode("utf-8"), tok.encode("utf-8"))
