# -*- coding: utf-8 -*-
"""Validacao e migracao do config.json (v1 -> v2). Formato em docs/ARQUITETURA.md."""
import copy
import json
import re

from . import actions
from .audio import TARGETS as FADER_TARGETS

CONFIG_VERSION = 2
MAX_PAGES = 50
MAX_BUTTONS = 120          # por pagina
MAX_LABEL = 60             # texto do botao
MAX_NAME = 60              # nome da pagina
MAX_TITLE = 80
MAX_SHORT = 40             # icone, cor
KINDS = ("button", "fader", "folder")
FOLDER_KINDS = ("button", "fader")   # pasta dentro de pasta nao
MAX_FOLDER = 60            # botoes dentro de uma pasta
MAX_APPS = 20              # apps por pagina (troca automatica)
LIVE = ("clock", "date", "volume:master", "volume:effects", "volume:mic", "timer")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()\-]{0,99}$")
# nome de executavel: letras/digitos (inclusive acentos), espaco e pontuacao
# comum; sem pastas nem caracteres de controle; termina em .exe
EXE_RE = re.compile(r"^(?=.{1,80}$)[^\W_](?:[\w ._()+\-'&,!]*)\.[eE][xX][eE]$")


# --------------------------------------------------------------- validacao ---
def _opt_str(obj, key, limit, where):
    v = obj.get(key)
    if v is None:
        return
    if not isinstance(v, str):
        raise ValueError("%s: %s invalido" % (where, key))
    if len(v) > limit:
        raise ValueError("%s: %s muito longo (maximo %d caracteres)" % (where, key, limit))


def _opt_hex(obj, key, where):
    v = obj.get(key)
    if v is None or v == "":
        return
    if not isinstance(v, str) or not HEX_RE.match(v):
        raise ValueError("%s: %s deve ser uma cor #rrggbb" % (where, key))


def safe_image_name(v):
    """Nome simples de arquivo (sem pastas), como os de imagens/."""
    return isinstance(v, str) and bool(IMAGE_RE.match(v)) and ".." not in v


def _opt_image(obj, key, where):
    v = obj.get(key)
    if v is None or v == "":
        return
    if not safe_image_name(v):
        raise ValueError("%s: nome de imagem invalido" % where)


def _looks(b, where):
    """Campos de aparencia (do botao e do "on")."""
    _opt_str(b, "label", MAX_LABEL, where)
    _opt_str(b, "icon", MAX_SHORT, where)
    _opt_str(b, "color", MAX_SHORT, where)
    _opt_hex(b, "textColor", where)
    _opt_image(b, "image", where)


def validate_button(b, n_pages, where, kinds=KINDS):
    if not isinstance(b, dict):
        raise ValueError(where + ": invalido")
    kind = b.get("kind", "button")
    if kind not in kinds:
        raise ValueError("%s: tipo deve ser %s" % (where, " ou ".join(kinds)))
    _looks(b, where)
    for key in ("w", "h"):
        if key in b:
            v = b[key]
            if not isinstance(v, int) or isinstance(v, bool) or not (1 <= v <= 4):
                raise ValueError("%s: %s deve ficar entre 1 e 4" % (where, key))
    if "toggle" in b and not isinstance(b["toggle"], bool):
        raise ValueError("%s: toggle deve ser true ou false" % where)
    on = b.get("on")
    if on is not None:
        if not isinstance(on, dict):
            raise ValueError("%s: aparencia ligado invalida" % where)
        for k in on:
            if k not in ("label", "icon", "color", "textColor", "image"):
                raise ValueError("%s: campo desconhecido em on: %s" % (where, k))
        _looks(on, where + " (ligado)")
    live = b.get("live")
    if live not in (None, "") and live not in LIVE:
        raise ValueError("%s: texto ao vivo invalido" % where)
    if kind == "folder":
        inner = b.get("buttons")
        if not isinstance(inner, list):
            raise ValueError("%s: pasta sem lista de botoes" % where)
        if len(inner) > MAX_FOLDER:
            raise ValueError("%s: pasta com botoes demais (maximo %d)" % (where, MAX_FOLDER))
        for i, x in enumerate(inner):
            validate_button(x, n_pages, "%s, item %d" % (where, i + 1), FOLDER_KINDS)
    elif kind == "fader":
        if b.get("target") not in FADER_TARGETS:
            raise ValueError("%s: o fader deve controlar %s" % (where, ", ".join(FADER_TARGETS)))
    else:
        actions.validate(b.get("action", {"type": "none"}), n_pages, where)


def validate_config(cfg):
    if not isinstance(cfg, dict):
        raise ValueError("configuracao invalida")
    if cfg.get("version") != CONFIG_VERSION:
        raise ValueError("versao da configuracao invalida (esperado %d)" % CONFIG_VERSION)
    _opt_str(cfg, "title", MAX_TITLE, "configuracao")
    for key, lo, hi in (("columns", 1, 10), ("rows", 1, 8)):
        v = cfg.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or not (lo <= v <= hi):
            raise ValueError("%s deve ficar entre %d e %d" % (key, lo, hi))
    por = cfg.get("portrait")
    if por is not None:
        if not isinstance(por, dict):
            raise ValueError("portrait invalido")
        for key, lo, hi in (("columns", 1, 10), ("rows", 1, 8)):
            v = por.get(key)
            if not isinstance(v, int) or isinstance(v, bool) or not (lo <= v <= hi):
                raise ValueError("vertical: %s deve ficar entre %d e %d" % (key, lo, hi))
    pages = cfg.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("precisa ter ao menos uma pagina")
    if len(pages) > MAX_PAGES:
        raise ValueError("no maximo %d paginas" % MAX_PAGES)
    for pi, pg in enumerate(pages):
        if not isinstance(pg, dict) or not isinstance(pg.get("buttons"), list):
            raise ValueError("pagina %d invalida" % (pi + 1))
        if pg.get("layout", "grid") != "grid":
            raise ValueError("pagina %d: layout invalido" % (pi + 1))
        _opt_str(pg, "name", MAX_NAME, "pagina %d" % (pi + 1))
        apps = pg.get("apps")
        if apps is not None:
            if not isinstance(apps, list) or len(apps) > MAX_APPS:
                raise ValueError("pagina %d: lista de apps invalida (maximo %d)" % (pi + 1, MAX_APPS))
            for x in apps:
                if not isinstance(x, str) or not EXE_RE.match(x):
                    raise ValueError("pagina %d: nome de app invalido: %s" % (pi + 1, str(x)[:40]))
        if len(pg["buttons"]) > MAX_BUTTONS:
            raise ValueError("pagina %d: botoes demais (maximo %d)" % (pi + 1, MAX_BUTTONS))
        for bi, b in enumerate(pg["buttons"]):
            validate_button(b, len(pages), "Pagina %d, botao %d" % (pi + 1, bi + 1))


# ---------------------------------------------------------------- migracao ---
def migrate(cfg):
    """Devolve (config na versao atual, mudou?). Nao altera o original."""
    if not isinstance(cfg, dict):
        return cfg, False
    ver = cfg.get("version")
    if isinstance(ver, int) and not isinstance(ver, bool) and ver >= CONFIG_VERSION:
        return cfg, False
    return migrate_v1(cfg), True


def _empty_button():
    return {"label": "", "icon": "", "color": "", "action": {"type": "none"}}


def _used(b):
    if not isinstance(b, dict):
        return False
    a = b.get("action") or {}
    return a.get("type", "none") != "none" or bool(str(b.get("label", "")).strip())


def _nav(label, icon, section):
    """Botao de navegacao; o destino (secao) e resolvido depois."""
    return {"label": label, "icon": icon, "color": "#0a3069",
            "action": {"type": "page", "to": 0, "_goto": section}}


def _fader(label, icon, color, target):
    return {"kind": "fader", "label": label, "icon": icon, "color": color, "target": target}


def _arrange(faders, onair, mutes, rest, nav_count, cols, cap):
    """Pagina principal do radio: com 4+ colunas, faders na 1a linha e cada
    mudo logo abaixo do seu fader; o resto ocupa os espacos livres."""
    items = faders + onair + mutes + rest
    if cols < 4 or len(items) + nav_count > cap or cols + len(mutes) > cap:
        return items
    grid = [None] * cap
    for i, x in enumerate(faders + onair):
        grid[i] = x
    for i, x in enumerate(mutes):
        grid[cols + i] = x
    free = [i for i, x in enumerate(grid) if x is None]
    for i, x in zip(free, rest):
        grid[i] = x
    while grid and grid[-1] is None:
        grid.pop()
    return [x if x is not None else _empty_button() for x in grid]


def _mixer_sections(pg, cols, cap):
    """Pagina "mixer" da 1.x (48 posicoes fixas):
    0-5 Deck A | 6-37 pads (4 bancos x 8) | 38-41 chat | 42 ON AIR
    43-45 mudo master/efeitos/mic | 46-47 disco (subir/descer na lista).
    Vira secoes [(chave, nome, itens, navegacao)], cada uma uma ou mais paginas."""
    src = [copy.deepcopy(b) for b in pg.get("buttons", [])[:48]]
    b = src + [_empty_button() for _ in range(48 - len(src))]
    name = str(pg.get("name") or "Rádio")

    def fill_icon(btn, icon):
        if not btn.get("icon"):
            btn["icon"] = icon
        return btn

    faders = [_fader("Master", "sound", "#0a84ff", "master"),
              _fader("Efeitos", "music", "#ff9f0a", "effects"),
              _fader("Mic", "mic", "#30d158", "mic")]
    onair = []
    if _used(b[42]):
        onair = [b[42]]
        b[42]["toggle"] = True
        if not str(b[42].get("label", "")).strip():
            b[42]["label"] = "ON AIR"
    mutes = []
    mute_names = {"master": ("Mudo PC", "mute"), "effects": ("Mudo efeitos", "mute"), "mic": ("Mudo mic", "mic")}
    for i in (43, 44, 45):
        if _used(b[i]):
            m = b[i]
            target = (m.get("action") or {}).get("target", "master")
            label, icon = mute_names.get(target, ("Mudo", "mute"))
            if str(m.get("label", "")).strip().upper() in ("", "MUDO", "MUTE"):
                m["label"] = label
            mutes.append(fill_icon(m, icon))
    rest = [x for x in b[0:6] if _used(x)]
    rest += [fill_icon(x, "updown") for x in b[46:48] if _used(x)]

    # os 4 bancos viram uma pagina so; botoes repetidos (ex.: "Parar sons" em
    # todos os bancos) entram uma vez
    pads, seen = [], set()
    for x in b[6:38]:
        if _used(x):
            sig = json.dumps([x.get("label"), x.get("action")], sort_keys=True, ensure_ascii=False)
            if sig not in seen:
                seen.add(sig)
                pads.append(x)
    chat = [fill_icon(x, "chat") for x in b[38:42] if _used(x)]

    main_nav = []
    if pads:
        main_nav.append(("Pads", "music", "pads"))
    if chat:
        main_nav.append(("Chat", "chat", "chat"))
    main = _arrange(faders, onair, mutes, rest, len(main_nav), cols, cap)
    sections = [("main", name, main, main_nav)]
    if pads:
        sections.append(("pads", "%s · Pads" % name, pads, [("Voltar", "back", "main")]))
    if chat:
        sections.append(("chat", "%s · Chat" % name, chat, [("Voltar", "back", "main")]))
    return sections


def _pack(key, name, items, nav, cap):
    """Distribui os itens em paginas de cap posicoes. Se nao couber, a ultima
    posicao vira "Mais" (proxima parte). Navegacao entra so se sobrar espaco."""
    out = []
    if len(items) <= cap:
        chunks = [items]
    else:
        per = max(1, cap - 1)
        chunks = [items[i:i + per] for i in range(0, len(items), per)]
    for ci, chunk in enumerate(chunks):
        btns = list(chunk)
        last = ci == len(chunks) - 1
        if not last and cap > 1:
            btns.append(_nav("Mais", "forward", (key, ci + 1)))
        if last:
            for label, icon, target in nav:
                if len(btns) < cap:
                    btns.append(_nav(label, icon, (target, 0)))
        out.append(((key, ci), {"name": name if ci == 0 else "%s (%d)" % (name, ci + 1), "buttons": btns}))
    return out


def migrate_v1(cfg):
    """Config da 1.x -> v2: paginas "grid" ficam iguais (sem "layout"); pagina
    "mixer" vira paginas comuns (faders, ON AIR liga/desliga, pads, chat).
    Acoes de pagina ("to") sao remapeadas para os novos indices."""
    cfg = copy.deepcopy(cfg)
    cols = cfg.get("columns") if isinstance(cfg.get("columns"), int) else 5
    rows = cfg.get("rows") if isinstance(cfg.get("rows"), int) else 3
    cols, rows = max(1, min(10, cols)), max(1, min(8, rows))
    cap = cols * rows
    groups = []    # por pagina antiga: [((secao, parte), pagina)]
    for pg in cfg.get("pages") or []:
        if isinstance(pg, dict) and pg.get("layout") == "mixer":
            parts = []
            for key, name, items, nav in _mixer_sections(pg, cols, cap):
                parts += _pack(key, name, items, nav, cap)
            groups.append(parts)
        else:
            if isinstance(pg, dict):
                pg = dict(pg)
                pg.pop("layout", None)
            groups.append([(None, pg)])

    first, pages = [], []
    for parts in groups:
        first.append(len(pages))
        index = {}
        for ref, page in parts:
            if ref is not None:
                index[ref] = len(pages)
            pages.append(page)
        for ref, page in parts:   # resolve a navegacao criada aqui
            for btn in page.get("buttons", []) if isinstance(page, dict) else []:
                a = btn.get("action") if isinstance(btn, dict) else None
                if isinstance(a, dict) and "_goto" in a:
                    a["to"] = index.get(a.pop("_goto"), index.get(("main", 0), 0))
                    a["_new"] = True

    def remap(a):
        if not isinstance(a, dict):
            return
        if a.get("type") == "page":
            if a.pop("_new", False):
                return
            to = a.get("to")
            ok = isinstance(to, int) and not isinstance(to, bool) and 0 <= to < len(first)
            a["to"] = first[to] if ok else 0
        steps = a.get("steps")
        for s in steps if isinstance(steps, list) else []:
            remap(s)

    for page in pages:
        for btn in page.get("buttons", []) if isinstance(page, dict) else []:
            if isinstance(btn, dict):
                remap(btn.get("action"))

    out = {"version": CONFIG_VERSION}
    for k, v in cfg.items():
        if k not in ("version", "pages"):
            out[k] = v
    out["pages"] = pages
    return out
