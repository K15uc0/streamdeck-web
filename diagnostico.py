# -*- coding: utf-8 -*-
"""Diagnostico de rede do Stream Deck (somente leitura).
Gera diagnostico.txt com: IPs do PC, perfil da rede (Publica/Privada),
regras de firewall do Python, portas em uso e um teste de acesso ao servidor."""
import os
import socket
import subprocess
import sys
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "diagnostico.txt")
NOWIN = 0x08000000


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30, creationflags=NOWIN, shell=isinstance(cmd, str))
        raw = r.stdout + r.stderr
        for enc in ("utf-8", "cp850", "cp1252"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("latin-1")
    except Exception as e:
        return "ERRO: %s" % e


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    lines = []
    w = lines.append
    w("Python: %s" % sys.executable)
    w("IP detectado: %s" % lan_ip())
    w("")
    w("== Perfil da rede ==")
    w(run(["powershell", "-NoProfile", "-Command",
           "Get-NetConnectionProfile | Format-List Name,InterfaceAlias,NetworkCategory,IPv4Connectivity"]))
    w("== Firewall: estado dos perfis ==")
    w(run(["netsh", "advfirewall", "show", "allprofiles", "state"]))
    w("== Firewall: regras de entrada do Python ==")
    rules = run(["netsh", "advfirewall", "firewall", "show", "rule", "name=all", "dir=in", "verbose"])
    blocks = [b for b in rules.replace("\r", "").split("\n\n") if "python" in b.lower()]
    w("\n\n".join(blocks) if blocks else "(nenhuma regra encontrada para Python)")
    w("")
    w("== Portas 8765-8767 ==")
    w("\n".join(l for l in run(["netstat", "-ano", "-p", "TCP"]).splitlines() if ":876" in l) or "(nenhuma)")
    w("")
    w("== ipconfig ==")
    w(run(["ipconfig"]))
    w("== Teste de acesso ao servidor ==")
    for host in ("127.0.0.1", lan_ip()):
        url = "http://%s:8765/ping.gif" % host
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                w("%s -> OK (%d)" % (url, r.status))
        except Exception as e:
            w("%s -> FALHOU: %s" % (url, e))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Diagnostico salvo em", OUT)


if __name__ == "__main__":
    main()
