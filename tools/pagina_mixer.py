"""Gera a pagina padrao "Radio" no layout Mixer de DJ (48 posicoes fixas).
0-5 Deck A | 6-37 pads (4 bancos x 8) | 38-41 chat | 42 ON AIR
43-45 mudo master/efeitos/mic | 46-47 disco (esquerda/direita)."""
import json
import sys


def none():
    return {"label": "", "icon": "", "color": "", "action": {"type": "none"}}


def btn(label, icon, color, action):
    return {"label": label, "icon": icon, "color": color, "action": action}


def mixer_page(name="Rádio"):
    b = [none() for _ in range(48)]
    b[0] = btn("Anterior", "prev", "", {"type": "hotkey", "keys": ["prev"]})
    b[1] = btn("Play/Pausa", "playpause", "#ff8a3d", {"type": "hotkey", "keys": ["playpause"]})
    b[2] = btn("Próxima", "next", "", {"type": "hotkey", "keys": ["next"]})
    b[3] = btn("Parar", "stop", "", {"type": "hotkey", "keys": ["stop"]})
    b[4] = btn("CUE", "headphones", "", {"type": "hotkey", "keys": ["ctrl", "alt", "f10"]})
    b[5] = btn("AUTO DJ", "playlist", "", {"type": "hotkey", "keys": ["ctrl", "alt", "f11"]})
    for bank in range(4):
        b[6 + bank * 8 + 7] = btn("Parar sons", "stop", "#7f1d1d", {"type": "stopsound"})
    msgs = ["Bom dia, ouvintes!", "Peça sua música!", "Já volto!", "Obrigado pela audiência!"]
    for i, m in enumerate(msgs):
        b[38 + i] = btn(m, "", "", {"type": "text", "text": m, "enter": True})
    b[42] = btn("ON AIR", "", "#ef4444", {"type": "hotkey", "keys": ["ctrl", "alt", "f12"]})
    b[43] = btn("MUDO", "", "", {"type": "mute", "target": "master"})
    b[44] = btn("MUDO", "", "", {"type": "mute", "target": "effects"})
    b[45] = btn("MUTE", "", "", {"type": "mute", "target": "mic"})
    b[46] = btn("Subir na lista", "", "", {"type": "hotkey", "keys": ["up"]})
    b[47] = btn("Descer na lista", "", "", {"type": "hotkey", "keys": ["down"]})
    return {"name": name, "layout": "mixer", "buttons": b}


if __name__ == "__main__":
    path = sys.argv[1]
    cfg = json.load(open(path, encoding="utf-8"))
    if not any(p.get("layout") == "mixer" for p in cfg["pages"]):
        cfg["pages"].append(mixer_page())
    json.dump(cfg, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("paginas:", [p["name"] for p in cfg["pages"]])
