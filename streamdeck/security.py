# -*- coding: utf-8 -*-
"""Seguranca.
1) So aceita aparelhos da rede local (nunca da internet, mesmo com porta aberta
   no roteador). 2) So aceita o nome/IP deste PC no cabecalho Host (bloqueia
   "DNS rebinding"). 3) Toda chamada da API exige o cabecalho X-StreamDeck,
   que sites de terceiros nao conseguem enviar (bloqueia CSRF). 4) Limite de
   tentativas com codigo errado. 5) Botoes que rodam comandos, abrem programas
   ou chamam APIs so podem ser criados no proprio PC (a menos que liberado)."""
import hmac
import ipaddress
import json
import socket
import threading
import time

from . import actions, state, storage
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


# ------------------------------------------------------------ acoes perigosas ---
def is_dangerous(a):
    """Acoes que dao controle amplo sobre o PC (decidido pelo registro de acoes)."""
    return actions.is_dangerous(a)


def dangerous_actions(cfg):
    out = set()
    for pg in (cfg or {}).get("pages", []):
        for b in pg.get("buttons", []) if isinstance(pg, dict) else []:
            a = b.get("action") if isinstance(b, dict) else None
            if is_dangerous(a):
                out.add(json.dumps(a, sort_keys=True, ensure_ascii=False))
    return out


def check_remote_edit(new_cfg):
    """Vindo de um aparelho: nao deixa criar/alterar botoes perigosos,
    a nao ser que o dono tenha liberado na tela de conexao do PC."""
    if storage.load_settings().get("remote_admin"):
        return
    try:
        old = dangerous_actions(storage.load_config())
    except Exception:
        old = set()
    novos = dangerous_actions(new_cfg) - old
    if novos:
        raise PermissionError("Por seguranca, botoes que rodam comandos, abrem programas/arquivos ou "
                              "chamam APIs so podem ser criados ou alterados no proprio PC "
                              "(abra http://127.0.0.1:%s no PC) ou libere em Conectar > Seguranca."
                              % (state.PORT[0] or 8765))
