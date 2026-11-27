# -*- coding: utf-8 -*-
"""Validacao e migracao do config.json (v1 -> v2). Formato em docs/ARQUITETURA.md."""
import copy
import json
import re
import secrets

from . import actions, agenda
from .audio import TARGETS as FADER_TARGETS

CONFIG_VERSION = 2
MAX_PAGES = 50
MAX_BUTTONS = 120          # por pagina
MAX_LABEL = 60             # texto do botao
MAX_NAME = 60              # nome da pagina
MAX_TITLE = 80
MAX_SHORT = 40             # icone, cor
KINDS = ("button", "fader", "folder", "monitor")
FOLDER_KINDS = ("button", "fader", "monitor")   # pasta dentro de pasta nao
MAX_FOLDER = 60            # botoes dentro de uma pasta
MAX_APPS = 20              # apps por pagina (troca automatica)
LIVE = ("clock", "date", "volume:master", "volume:effects", "volume:mic", "timer",
        "obs:stream", "obs:record", "obs:scene", "sound",
        "nowplaying", "nowplaying:title", "nowplaying:artist",
        "pc:cpu", "pc:mem", "pc:gpu", "pc:temp_cpu", "pc:temp_gpu", "pc:net",
        "ia:claude:5h", "ia:claude:week", "ia:codex:5h", "ia:codex:week")
DISK_LIVE_RE = re.compile(r"pc:disk:[A-Z]")   # uma letra de unidade, maiuscula


def valid_live(v):
    return v in LIVE or (isinstance(v, str) and bool(DISK_LIVE_RE.fullmatch(v)))
MAX_LIT = 130
# botao aceso pelo estado do OBS
LIT_RE = re.compile(r"^(obs:stream|obs:record|obs:(scene|mute)=[^\r\n]{1,120})$")
# icone: nome do conjunto (SD.ICONS em web/js/core.js) ou "emoji:<1..8 caracteres>"
ICON_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,39}")
MAX_EMOJI = 8
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


def valid_icon(v):
    """"" (sem icone), nome do conjunto ou emoji:<1..8 caracteres, sem
    caracteres de controle nem < > & ">."""
    if not isinstance(v, str):
        return False
    if v == "" or ICON_NAME_RE.fullmatch(v):
        return True
    if not v.startswith("emoji:"):
        return False
    t = v[6:]
    if not 1 <= len(t) <= MAX_EMOJI or t.strip() == "":
        return False
    for ch in t:
        o = ord(ch)
        if o < 32 or 0x7f <= o < 0xa0 or ch in '<>&"' or ch in "\u2028\u2029":
            return False
    return True


def _opt_icon(obj, key, where):
    v = obj.get(key)
    if v is None:
        return
    if not valid_icon(v):
        raise ValueError("%s: icone invalido (use um nome da lista ou emoji:<ate %d caracteres>)"
                         % (where, MAX_EMOJI))


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
    _opt_icon(b, "icon", where)
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
    if "confirm" in b and not isinstance(b["confirm"], bool):
        raise ValueError("%s: confirm deve ser true ou false" % where)
    lit = b.get("lit")
    if lit not in (None, ""):
        if not isinstance(lit, str) or len(lit) > MAX_LIT or not LIT_RE.match(lit):
            raise ValueError("%s: aceso pelo OBS invalido" % where)
    on = b.get("on")
    if on is not None:
        if not isinstance(on, dict):
            raise ValueError("%s: aparencia ligado invalida" % where)
        for k in on:
            if k not in ("label", "icon", "color", "textColor", "image"):
                raise ValueError("%s: campo desconhecido em on: %s" % (where, k))
        _looks(on, where + " (ligado)")
    live = b.get("live")
    if live not in (None, "") and not valid_live(live):
        raise ValueError("%s: texto ao vivo invalido" % where)
    if kind == "folder":
        inner = b.get("buttons")
        if not isinstance(inner, list):
            raise ValueError("%s: pasta sem lista de botoes" % where)
        if len(inner) > MAX_FOLDER:
            raise ValueError("%s: pasta com botoes demais (maximo %d)" % (where, MAX_FOLDER))
        for i, x in enumerate(inner):
            validate_button(x, n_pages, "%s, item %d" % (where, i + 1), FOLDER_KINDS)
    elif kind == "monitor":
        pass    # sem acao: o toque abre a tela de processos
    elif kind == "fader":
        if b.get("target") not in FADER_TARGETS:
            raise ValueError("%s: o fader deve controlar %s" % (where, ", ".join(FADER_TARGETS)))
    else:
        actions.validate(b.get("action", {"type": "none"}), n_pages, where)
        for key, name in (("hold", "ao segurar"), ("double", "no toque duplo")):
            if b.get(key) is not None:
                actions.validate(b[key], n_pages, "%s (%s)" % (where, name))


def _grid(g, prefix):
    """Valida colunas/linhas (e "portrait" opcional) de uma grade."""
    for key, lo, hi in (("columns", 1, 10), ("rows", 1, 8)):
        v = g.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or not (lo <= v <= hi):
            raise ValueError("%s%s deve ficar entre %d e %d" % (prefix, key, lo, hi))
    por = g.get("portrait")
    if por is not None:
        if not isinstance(por, dict):
            raise ValueError("%sportrait invalido" % prefix)
        for key, lo, hi in (("columns", 1, 10), ("rows", 1, 8)):
            v = por.get(key)
            if not isinstance(v, int) or isinstance(v, bool) or not (lo <= v <= hi):
                raise ValueError("%svertical: %s deve ficar entre %d e %d" % (prefix, key, lo, hi))


def validate_config(cfg):
    if not isinstance(cfg, dict):
        raise ValueError("configuracao invalida")
    if cfg.get("version") != CONFIG_VERSION:
        raise ValueError("versao da configuracao invalida (esperado %d)" % CONFIG_VERSION)
    _opt_str(cfg, "title", MAX_TITLE, "configuracao")
    _grid(cfg, "")
    pages = cfg.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("precisa ter ao menos uma pagina")
    if len(pages) > MAX_PAGES:
        raise ValueError("no maximo %d paginas" % MAX_PAGES)
    seen_ids = set()
    for pi, pg in enumerate(pages):
        if not isinstance(pg, dict) or not isinstance(pg.get("buttons"), list):
            raise ValueError("pagina %d invalida" % (pi + 1))
        if pg.get("layout", "grid") != "grid":
            raise ValueError("pagina %d: layout invalido" % (pi + 1))
        _opt_str(pg, "name", MAX_NAME, "pagina %d" % (pi + 1))
        if "id" in pg:
            pid = pg["id"]
            if not isinstance(pid, str) or not PAGE_ID_RE.match(pid):
                raise ValueError("pagina %d: id invalido" % (pi + 1))
            if pid in seen_ids:
                raise ValueError("pagina %d: id repetido" % (pi + 1))
            seen_ids.add(pid)
        grid = pg.get("grid")
        if grid is not None:
            if not isinstance(grid, dict):
                raise ValueError("pagina %d: grade invalida" % (pi + 1))
            _grid(grid, "pagina %d: " % (pi + 1))
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
    agenda.validate(cfg.get("schedules"), len(pages))


# ---------------------------------------------------------------- migracao ---
def migrate(cfg):
    """Devolve (config na versao atual, mudou?). Nao altera o original."""
    if not isinstance(cfg, dict):
        return cfg, False
    ver = cfg.get("version")
    if isinstance(ver, int) and not isinstance(ver, bool) and ver >= CONFIG_VERSION:
        if ver != CONFIG_VERSION:
            return cfg, False
        bad_icon = _has_bad_icon(cfg.get("pages"))
        if not bad_icon and not _needs_grid(cfg) and not _needs_ids(cfg):
            return cfg, False
        out = copy.deepcopy(cfg)
        for page in out["pages"]:
            for btn in page.get("buttons", []) if isinstance(page, dict) else []:
                if isinstance(btn, dict):
                    fix_icon(btn)
        add_page_grids(out)
        add_page_ids(out)
        return out, True
    out = migrate_v1(cfg)
    add_page_grids(out)
    add_page_ids(out)
    return out, True


# ------------------------------------------------- id fixo de cada pagina ---
PAGE_ID_RE = re.compile(r"^[0-9a-f]{4,16}$")


def _needs_ids(cfg):
    pages = cfg.get("pages")
    if not isinstance(pages, list):
        return False
    seen = set()
    for p in pages:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        if not isinstance(pid, str) or not PAGE_ID_RE.match(pid) or pid in seen:
            return True
        seen.add(pid)
    return False


def add_page_ids(cfg):
    """2.11: toda pagina tem um id fixo (os aparelhos guardam ids, nao
    posicoes, entao mover/apagar paginas nao troca o que cada um ve).
    Pagina sem id (ou com id repetido) ganha um novo. Devolve True se mudou."""
    pages = cfg.get("pages") if isinstance(cfg, dict) else None
    if not isinstance(pages, list):
        return False
    used, changed = set(), False
    for pg in pages:
        if isinstance(pg, dict) and isinstance(pg.get("id"), str) and PAGE_ID_RE.match(pg["id"]) \
                and pg["id"] not in used:
            used.add(pg["id"])
            continue
        if not isinstance(pg, dict):
            continue
        pid = secrets.token_hex(4)
        while pid in used:
            pid = secrets.token_hex(4)
        used.add(pid)
        pg["id"] = pid
        changed = True
    return changed


def page_ids(cfg):
    """[id de cada pagina] na ordem atual (None onde faltar)."""
    pages = cfg.get("pages") if isinstance(cfg, dict) else None
    return [p.get("id") if isinstance(p, dict) else None for p in (pages or [])]


# ------------------------------------------------- grade de cada pagina ---
def _int_in(v, lo, hi, default):
    if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi:
        return v
    return default


def flow(buttons, cols, rows):
    """Mesma regra de SD.flow (web/js/core.js): cada botao ocupa w x h (1..4,
    limitado a grade) na primeira posicao livre, linha a linha. Devolve
    [(i, x, y, w, h)] dos que couberam."""
    used = [False] * (cols * rows)
    out = []

    def free(x0, y0, w0, h0):
        if x0 + w0 > cols or y0 + h0 > rows:
            return False
        for yy in range(y0, y0 + h0):
            for xx in range(x0, x0 + w0):
                if used[yy * cols + xx]:
                    return False
        return True

    def size(v, lim):
        try:
            n = int(v) if not isinstance(v, bool) else 1
        except (TypeError, ValueError, OverflowError):
            n = 1
        return max(1, min(lim, n or 1))

    for i, b in enumerate(buttons or []):
        b = b if isinstance(b, dict) else {}
        w, h = size(b.get("w"), cols), size(b.get("h"), rows)
        done = False
        for y in range(rows):
            for x in range(cols):
                if free(x, y, w, h):
                    for yy in range(y, y + h):
                        for xx in range(x, x + w):
                            used[yy * cols + xx] = True
                    out.append((i, x, y, w, h))
                    done = True
                    break
            if done:
                break
    return out


def _real(b):
    """Botao que conta para caber (botoes vazios no fim da lista nao contam)."""
    return isinstance(b, dict) and (b.get("kind") in ("folder", "monitor") or _used(b)
                                    or bool(b.get("icon")) or bool(b.get("image")))


def fit_grid(buttons, cols, rows):
    """Menor grade >= cols x rows (ate 10 x 8) onde todos os botoes cabem.
    Empate: proporcao mais perto da original, depois menos linhas (cresce
    primeiro em colunas). Se nada couber em tudo, a que cabe mais."""
    bs = list(buttons or [])
    while bs and not _real(bs[-1]):
        bs.pop()
    if len(flow(bs, cols, rows)) == len(bs):
        return cols, rows
    ratio = float(cols) / rows
    best = None
    for c in range(cols, 11):
        for r in range(rows, 9):
            n = len(flow(bs, c, r))
            key = (-n, c * r, abs(float(c) / r - ratio), r)
            if best is None or key < best[0]:
                best = (key, c, r)
    return best[1], best[2]


def _needs_grid(cfg):
    pages = cfg.get("pages")
    return isinstance(pages, list) and any(isinstance(p, dict) and not isinstance(p.get("grid"), dict)
                                           for p in pages)


def add_page_grids(cfg):
    """2.10.1: toda pagina tem a sua grade. Pagina sem "grid" ganha uma copia
    da geral (columns/rows/portrait), crescida se os botoes nao couberem.
    Devolve True se mudou algo."""
    pages = cfg.get("pages") if isinstance(cfg, dict) else None
    if not isinstance(pages, list):
        return False
    cols = _int_in(cfg.get("columns"), 1, 10, 5)
    rows = _int_in(cfg.get("rows"), 1, 8, 3)
    por = cfg.get("portrait")
    changed = False
    for pg in pages:
        if not isinstance(pg, dict) or isinstance(pg.get("grid"), dict):
            continue
        c, r = fit_grid(pg.get("buttons") if isinstance(pg.get("buttons"), list) else [], cols, rows)
        g = {"columns": c, "rows": r}
        if isinstance(por, dict):
            g["portrait"] = {"columns": _int_in(por.get("columns"), 1, 10, r),
                             "rows": _int_in(por.get("rows"), 1, 8, c)}
        pg["grid"] = g
        changed = True
    return changed


def fix_icon(btn):
    """Icone antigo fora do formato atual vira "" (sem icone). Devolve True se mudou."""
    changed = False
    for o in (btn, btn.get("on")):
        if isinstance(o, dict) and "icon" in o and not valid_icon(o["icon"]):
            o["icon"] = ""
            changed = True
    for x in btn.get("buttons") if isinstance(btn.get("buttons"), list) else []:
        if isinstance(x, dict) and fix_icon(x):
            changed = True
    return changed


def _has_bad_icon(pages):
    """Ha algum icone invalido (sem alterar a config)?"""
    if not isinstance(pages, list):
        return False
    for page in pages:
        for btn in page.get("buttons", []) if isinstance(page, dict) else []:
            if isinstance(btn, dict) and fix_icon(copy.deepcopy(btn)):
                return True
    return False


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
                fix_icon(btn)

    out = {"version": CONFIG_VERSION}
    for k, v in cfg.items():
        if k not in ("version", "pages"):
            out[k] = v
    out["pages"] = pages
    return out
