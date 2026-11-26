# -*- coding: utf-8 -*-
"""Ponte da status line do Claude Code (2.9). O Claude Code chama este programa
a cada atualizacao e manda um JSON no stdin; aqui guardamos o consumo
(rate_limits) em Documentos\\StreamDeck\\ia\\claude.json e repassamos o mesmo
stdin para a status line que o usuario ja tinha. Rapido, so biblioteca padrao,
e nunca derruba o Claude Code: qualquer erro vira uma linha de texto."""
import json
import os
import shutil
import subprocess
import sys
import time

ORCAMENTO = 1.8     # segundos para a status line anterior


def _ia_dir():
    base = os.environ.get("STREAMDECK_DATA")
    if not base:
        try:
            aqui = os.path.dirname(os.path.abspath(__file__))
            if os.path.dirname(aqui) not in sys.path:
                sys.path.insert(0, os.path.dirname(aqui))
            from streamdeck import paths
            base = paths.BASE
        except Exception:
            base = os.path.join(os.path.expanduser("~"), "Documents", "StreamDeck")
    return os.path.join(base, "ia")


def _grava(caminho, dados):
    tmp = "%s.%d.tmp" % (caminho, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f)
        os.replace(tmp, caminho)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _ler_stdin():
    """Le o stdin sem usar sys.stdin (no .exe sem console ele pode ser None)."""
    partes = []
    try:
        while True:
            b = os.read(0, 65536)
            if not b:
                break
            partes.append(b)
    except Exception:
        if not partes and sys.platform.startswith("win"):
            try:
                import ctypes
                from ctypes import wintypes
                k = ctypes.windll.kernel32
                k.GetStdHandle.restype = wintypes.HANDLE
                h = k.GetStdHandle(-10)
                buf = ctypes.create_string_buffer(65536)
                n = wintypes.DWORD(0)
                while k.ReadFile(h, buf, 65536, ctypes.byref(n), None) and n.value:
                    partes.append(buf.raw[:n.value])
            except Exception:
                pass
    return b"".join(partes).decode("utf-8-sig", "replace")


def _escrever(texto):
    """Escreve no stdout pelo descritor 1 (sem sys.stdout)."""
    dados = (texto + "\n").encode("utf-8", "replace")
    try:
        while dados:
            n = os.write(1, dados)
            dados = dados[n:]
        return
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            k.GetStdHandle.restype = wintypes.HANDLE
            h = k.GetStdHandle(-11)
            n = wintypes.DWORD(0)
            k.WriteFile(h, dados, len(dados), ctypes.byref(n), None)
        except Exception:
            pass


def _padrao(dados):
    """Linha curta quando nao ha status line anterior."""
    try:
        rl = dados.get("rate_limits") or {}
        partes = []
        for chave, nome in (("five_hour", "5h"), ("seven_day", "semana")):
            j = rl.get(chave)
            if isinstance(j, dict) and j.get("used_percentage") is not None:
                partes.append("%s %d%%" % (nome, round(float(j["used_percentage"]))))
        return " \u00b7 ".join(partes) or "Claude"
    except Exception:
        return "Claude"


def _anterior(pasta):
    try:
        with open(os.path.join(pasta, "statusline_anterior.json"), "r", encoding="utf-8-sig") as f:
            sl = json.load(f).get("statusLine")
        cmd = sl.get("command") if isinstance(sl, dict) else None
        if cmd and "ponte_claude" not in cmd and "--ponte-claude" not in cmd \
                and "StreamDeckPonte" not in cmd:
            return cmd
    except Exception:
        pass
    return None


GIT_BASH_PADRAO = "C:\\Program Files\\Git\\bin\\bash.exe"


def _acha_bash():
    """bash.exe como o Claude Code no Windows: CLAUDE_CODE_GIT_BASH_PATH,
    o Git for Windows padrao, depois o PATH. None se nao achar."""
    env = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if env and os.path.isfile(env):
        return env
    if os.path.isfile(GIT_BASH_PADRAO):
        return GIT_BASH_PADRAO
    return shutil.which("bash")


def _argv(cmd):
    """Lista para Popen (bash -c / sh -c) ou o texto (cmd, shell=True)."""
    if sys.platform.startswith("win"):
        bash = _acha_bash()
        return [bash, "-c", cmd] if bash else cmd
    return ["/bin/sh", "-c", cmd]


def _executa(cmd, texto, limite):
    """Roda a status line anterior com o mesmo stdin; None se falhar/estourar."""
    kw = {}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x08000000      # CREATE_NO_WINDOW
    argv = _argv(cmd)
    p = subprocess.Popen(argv, shell=isinstance(argv, str), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **kw)
    try:
        out, _ = p.communicate(texto.encode("utf-8"), timeout=limite)
    except subprocess.TimeoutExpired:
        if sys.platform.startswith("win"):
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], creationflags=0x08000000,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            except Exception:
                pass
        try:
            p.kill()
        except Exception:
            pass
        return None
    return out.decode("utf-8", "replace").rstrip("\r\n")


def main(texto=None):
    t0 = time.time()
    saida = "Claude"
    try:
        if texto is None:
            texto = _ler_stdin()
        dados = {}
        try:
            dados = json.loads(texto)
            if not isinstance(dados, dict):
                dados = {}
        except Exception:
            dados = {}
        saida = _padrao(dados)
        pasta = _ia_dir()
        try:
            os.makedirs(pasta, exist_ok=True)
            if isinstance(dados.get("rate_limits"), dict):
                _grava(os.path.join(pasta, "claude.json"),
                       {"rate_limits": dados["rate_limits"], "ts": int(time.time())})
        except Exception:
            pass
        cmd = _anterior(pasta)
        if cmd:
            try:
                out = _executa(cmd, texto, max(0.2, min(1.5, ORCAMENTO - (time.time() - t0))))
                if out:
                    saida = out
            except Exception:
                pass
    except BaseException:
        pass
    _escrever(saida)


if __name__ == "__main__":
    main()
