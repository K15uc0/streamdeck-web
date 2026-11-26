# -*- coding: utf-8 -*-
"""main(): log, config, copias antigas, porta e tela Conectar."""
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from . import VERSION, agenda, diag, obs, paths, state, storage, tocando, updates, winapi
from .httpd import Handler, Server
from .security import lan_ip

IS_WINDOWS = paths.IS_WINDOWS
PORTS = paths.PORTS


def _local_call(port, path, method="GET", timeout=1.0):
    """Pedido ao Stream Deck que (talvez) esteja nesta porta do proprio PC."""
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), method=method,
                                 data=b"{}" if method == "POST" else None,
                                 headers={"X-StreamDeck": "1", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _port_busy(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def stop_old_instances():
    """Pede para copias antigas do Stream Deck (nas nossas portas) fecharem
    sozinhas, pela propria API local. Nunca mexe em outros programas."""
    for port in PORTS:
        try:
            hello = _local_call(port, "/api/local/hello", timeout=1.0)
        except Exception:
            # porta ocupada sem /hello: pode ser a versao anterior fechando
            # sozinha depois de se atualizar; espera ate 5 s antes de seguir
            if port == PORTS[0] and _port_busy(port):
                for _ in range(50):
                    time.sleep(0.1)
                    if not _port_busy(port):
                        break
            continue      # outro programa: nao mexe
        if not (isinstance(hello, dict) and hello.get("app") == "streamdeck"):
            continue
        if hello.get("pid") == os.getpid():
            continue
        try:
            _local_call(port, "/api/local/quit", method="POST", timeout=2.0)
        except Exception as e:
            print("  aviso: copia antiga na porta %d nao respondeu (%s)" % (port, e))
            continue
        for _ in range(30):     # espera ate 3 s a porta liberar
            if not _port_busy(port):
                break
            time.sleep(0.1)
        print("  copia antiga encerrada (porta %d, PID %s)" % (port, hello.get("pid")))


class Tee:
    """Mostra na janela (se houver) e grava em streamdeck.log.
    stream pode ser None (exe sem console): ai so grava no log e no diag."""

    def __init__(self, stream, path):
        self.stream = stream
        try:
            self.f = open(path, "w", encoding="utf-8", buffering=1)
        except OSError:
            self.f = None

    def write(self, text):
        if self.stream is not None:
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
        diag.feed(text)

    def flush(self):
        if self.stream is not None:
            try:
                self.stream.flush()
            except Exception:
                pass
        if self.f:
            try:
                self.f.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def _has_console():
    """True se ha uma janela/terminal onde Ctrl+C funciona."""
    if not IS_WINDOWS:
        return True
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:
        return False


def stop_hint(tray_on, has_console):
    """Como fechar o programa, conforme o que existe nesta execucao."""
    if tray_on:
        return "icone do Stream Deck perto do relogio > Sair."
    if has_console:
        return "Ctrl+C nesta janela (ou feche a janela)."
    return "feche pelo Gerenciador de Tarefas ou pela tela Conectar > Fechar o Stream Deck."


def main():
    sys.stdout = Tee(sys.stdout, paths.LOG_PATH)
    sys.stderr = sys.stdout
    print("Iniciando em %s" % time.strftime("%d/%m/%Y %H:%M:%S"))
    print("Stream Deck %s | dados em %s" % (VERSION, paths.BASE))
    storage.ensure_config()   # cria o config.json na primeira vez
    storage.load_config()  # valida o JSON (e migra config antigo) antes de subir
    try:
        from . import library
        library.check()
    except Exception as e:  # noqa: BLE001 - so avisa, nao impede de subir
        print("Aviso: biblioteca de comandos com problema: %s" % e)
    os.makedirs(paths.SOUNDS_DIR, exist_ok=True)
    os.makedirs(paths.IMAGES_DIR, exist_ok=True)
    token = storage.token()
    winapi.migrate_autostart()
    try:
        from . import ia
        ia.refresh_bridge()
    except Exception as e:  # noqa: BLE001
        print("Aviso: ponte do Claude Code: %s" % e)
    stop_old_instances()
    srv = port = None
    for port in PORTS:
        try:
            srv = Server(("0.0.0.0", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        # vira caixa de mensagem no server.py (o .exe nao tem janela)
        raise RuntimeError("nenhuma porta livre (%s): outro programa esta usando as portas do Stream Deck"
                           % ", ".join(map(str, PORTS)))
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
    print("=" * 56)
    threading.Thread(target=updates.update_loop, daemon=True).start()
    threading.Thread(target=updates.cleanup_old_exe, daemon=True).start()
    agenda.start()   # agendamentos (confere a cada ~10 s)
    tocando.start()  # musica tocando agora (so no Windows)
    obs.start()   # conexao com o OBS em segundo plano (tenta a cada 5 s)
    minimized = "--minimizado" in sys.argv
    tray_on = False
    if "--sem-bandeja" not in sys.argv:
        try:
            from . import tray
            tray_on = tray.start(port, srv, VERSION)
        except Exception as e:  # noqa: BLE001 - sem icone o servidor segue igual
            print("  aviso: icone na bandeja indisponivel (%s)" % e)
    if tray_on:
        print(" Icone na bandeja ativo (perto do relogio).")
    print(" Para parar: %s" % stop_hint(tray_on, _has_console()))
    if minimized:
        # com o icone, a janela some (volta pelo menu "Mostrar janela do log")
        if not (tray_on and tray.show_console(False)):
            winapi.minimize_console()
    # aberto pela pessoa (sem --minimizado): sempre mostra a tela Conectar,
    # senao o programa sem janela parece que "nao abriu"
    # (--sem-bandeja e o modo de teste/depuracao: nao abre navegador)
    if (not minimized and "--sem-bandeja" not in sys.argv) or "--conectar" in sys.argv:
        threading.Timer(1.0, webbrowser.open, ["http://127.0.0.1:%d/conectar" % port]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
