# -*- coding: utf-8 -*-
"""Ponte da status line do Claude Code (2.9). O Claude Code chama este programa
a cada atualizacao e manda um JSON no stdin; aqui guardamos o consumo
(rate_limits) em Documentos\\StreamDeck\\ia\\claude.json e repassamos o mesmo
stdin para a status line que o usuario ja tinha. Rapido, so biblioteca padrao,
e nunca derruba o Claude Code: qualquer erro vira uma linha de texto."""
import json
import os
import subprocess
import sys
import time


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
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    os.replace(tmp, caminho)


def _padrao(dados):
    """Linha curta quando nao ha status line anterior."""
    try:
        rl = dados.get("rate_limits") or {}
        partes = []
        for chave, nome in (("five_hour", "5h"), ("seven_day", "semana")):
            j = rl.get(chave)
            if isinstance(j, dict) and j.get("used_percentage") is not None:
                partes.append("%s %d%%" % (nome, round(float(j["used_percentage"]))))
        return " · ".join(partes) or "Claude"
    except Exception:
        return "Claude"


def _anterior(pasta):
    try:
        with open(os.path.join(pasta, "statusline_anterior.json"), "r", encoding="utf-8") as f:
            sl = json.load(f).get("statusLine")
        cmd = sl.get("command") if isinstance(sl, dict) else None
        if cmd and "ponte_claude" not in cmd and "--ponte-claude" not in cmd:
            return cmd
    except Exception:
        pass
    return None


def main(texto=None):
    saida = "Claude"
    try:
        if texto is None:
            raw = sys.stdin.buffer.read()
            texto = raw.decode("utf-8", "replace")
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
                r = subprocess.run(cmd, shell=True, input=texto.encode("utf-8"),
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
                out = r.stdout.decode("utf-8", "replace").rstrip("\r\n")
                if out:
                    saida = out
            except Exception:
                pass
    except BaseException:
        pass
    try:
        sys.stdout.write(saida + "\n")
        sys.stdout.flush()
    except Exception:
        pass


if __name__ == "__main__":
    main()
