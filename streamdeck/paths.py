# -*- coding: utf-8 -*-
"""Pastas do programa e dos dados do usuario."""
import os
import sys

from .winapi import documents_dir

IS_WINDOWS = sys.platform.startswith("win")
FROZEN = getattr(sys, "frozen", False)   # True quando roda como StreamDeck.exe

# Arquivos do programa (pagina, config padrao): dentro do .exe ou ao lado do server.py
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = getattr(sys, "_MEIPASS", os.path.dirname(PKG_DIR))
WEB_DIR = os.path.join(APP_DIR, "web")
DEFAULT_CONFIG = os.path.join(APP_DIR, "config.padrao.json")
SCRIPT = os.path.join(APP_DIR, "server.py")   # ponto de entrada quando roda pelo codigo
EXE_PATH = sys.executable if FROZEN else None

# Dados do usuario (botoes, abas, codigo, sons): ficam fora do programa,
# por isso continuam intactos quando o programa e atualizado.
if os.environ.get("STREAMDECK_DATA"):
    BASE = os.environ["STREAMDECK_DATA"]
elif FROZEN:
    BASE = os.path.join(documents_dir(), "StreamDeck")
else:
    BASE = APP_DIR
os.makedirs(BASE, exist_ok=True)

CONFIG_PATH = os.path.join(BASE, "config.json")
CONFIG_BAK = os.path.join(BASE, "config.bak.json")
CONFIG_V1_BAK = os.path.join(BASE, "config.v1.bak.json")
TOKEN_PATH = os.path.join(BASE, "token.txt")
TABS_PATH = os.path.join(BASE, "abas.json")
SETTINGS_PATH = os.path.join(BASE, "seguranca.json")
LOG_PATH = os.path.join(BASE, "streamdeck.log")
SOUNDS_DIR = os.path.join(BASE, "sons")
SOUND_EXT = (".mp3", ".wav", ".wma", ".m4a")
PORTS = (8765, 8766, 8767)  # usa a primeira livre


def inside(path, folder):
    """path fica dentro de folder (resolvendo links e ..)?"""
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(folder)]) == os.path.realpath(folder)
    except ValueError:
        return False


def is_unc(path):
    """Caminho de rede (\\\\servidor\\pasta)."""
    p = str(path).strip().strip('"')
    return p.startswith("\\\\") or p.startswith("//")
