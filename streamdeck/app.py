# -*- coding: utf-8 -*-
"""main(): log, config, copias antigas, porta e tela Conectar."""
import os
import subprocess
import sys
import threading
import time
import webbrowser

from . import VERSION, paths, state, storage, updates
from .httpd import Handler, Server
from .security import lan_ip

IS_WINDOWS = paths.IS_WINDOWS
PORTS = paths.PORTS


def stop_old_instances():
    """Encerra copias antigas do Stream Deck que ainda estejam escutando nas
    nossas portas (so processos nessas portas, nada mais)."""
    if not IS_WINDOWS:
        return
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             timeout=10, creationflags=0x08000000).stdout
    except Exception as e:
        print("  aviso: nao consegui verificar copias antigas (%s)" % e)
        return
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].upper() in ("LISTENING", "ESCUTANDO"):
            port = parts[1].rsplit(":", 1)[-1]
            if port.isdigit() and int(port) in PORTS and parts[4].isdigit():
                pid = int(parts[4])
                if pid != os.getpid():
                    pids.add(pid)
    killed = 0
    for pid in pids:
        try:
            info = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
                                  capture_output=True, text=True, timeout=10,
                                  creationflags=0x08000000).stdout.lower()
        except Exception:
            continue
        # so encerra se for o proprio Stream Deck (python ou StreamDeck.exe)
        if "python" not in info and "streamdeck" not in info:
            print("  aviso: porta ocupada por outro programa (PID %d), nao foi encerrado" % pid)
            continue
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True,
                       creationflags=0x08000000)
        print("  copia antiga encerrada (PID %d)" % pid)
        killed += 1
    if killed:
        time.sleep(1)


class Tee:
    """Mostra na janela e grava em streamdeck.log."""

    def __init__(self, stream, path):
        self.stream = stream
        try:
            self.f = open(path, "w", encoding="utf-8", buffering=1)
        except OSError:
            self.f = None

    def write(self, text):
        try:
            self.stream.write(text)
            self.stream.flush()
        except Exception:
            pass
        if self.f:
            try:
                self.f.write(text)
            except Exception:
                pass

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass


def main():
    sys.stdout = Tee(sys.stdout, paths.LOG_PATH)
    sys.stderr = sys.stdout
    print("Iniciando em %s" % time.strftime("%d/%m/%Y %H:%M:%S"))
    print("Stream Deck %s | dados em %s" % (VERSION, paths.BASE))
    first_run = storage.ensure_config()
    storage.load_config()  # valida o JSON (e migra config antigo) antes de subir
    os.makedirs(paths.SOUNDS_DIR, exist_ok=True)
    os.makedirs(paths.IMAGES_DIR, exist_ok=True)
    token = storage.token()
    stop_old_instances()
    srv = port = None
    for port in PORTS:
        try:
            srv = Server(("0.0.0.0", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        print("Nenhuma porta livre (%s)." % ", ".join(map(str, PORTS)))
        sys.exit(1)
    state.PORT[0] = port
    base = "http://%s%s" % (lan_ip(), "" if port == 80 else ":%d" % port)
    print("=" * 56)
    print(" Stream Deck rodando.")
    print()
    print(" Primeiro acesso no tablet (so uma vez):")
    print("   %s/?k=%s" % (base, token))
    print()
    print(" Depois disso, basta abrir:")
    print("   %s" % base)
    print()
    print(" Tela de conexao com QR code (neste PC):")
    print("   http://127.0.0.1:%d/conectar" % port)
    print()
    print(" Deixe esta janela aberta. Ctrl+C para parar.")
    print("=" * 56)
    threading.Thread(target=updates.update_loop, daemon=True).start()
    threading.Thread(target=updates.cleanup_old_exe, daemon=True).start()
    if first_run or "--conectar" in sys.argv:
        threading.Timer(1.0, webbrowser.open, ["http://127.0.0.1:%d/conectar" % port]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
