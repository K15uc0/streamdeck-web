# -*- coding: utf-8 -*-
"""Musica tocando agora, pelo titulo das janelas de players conhecidos.

parse(exe, titulo) -> {title, artist, app} ou None (funcao pura, testada).
Uma thread confere a cada ~3 s, mas so quando alguma pagina usa
live "nowplaying*" ou algum aparelho consultou /api/state no ultimo minuto.
Prioridade: Spotify > players dedicados > sites de musica no navegador."""
import re
import threading
import time

from . import windows

INTERVAL = 3.0
ACTIVE_FOR = 60.0     # segundos depois do ultimo /api/state

BROWSERS = ("chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe")
# sufixo que o navegador poe no titulo da aba
BROWSER_SUFFIX = re.compile(
    r"\s+[-–—]\s+(?:Google Chrome|Mozilla Firefox|Microsoft​?\s?Edge|Opera|Brave)$")
EDGE_MORE = re.compile(r"\s+(?:and|e) \d+ (?:more|outras?|mais) (?:pages?|páginas?)$")
PROFILE = re.compile(r"\s+-\s+(?:Personal|Work|Pessoal|Trabalho|Profile \d+|Perfil \d+)$")
NOTIF = re.compile(r"^\(\d+\+?\)\s+")
PLAY_MARK = re.compile(r"^[▶►]︎?️?\s*")
SPOTIFY_IDLE = re.compile(r"^Spotify(?: (?:Premium|Free|Family|Duo))?$", re.I)
EXTENSION = re.compile(r"\.(?:mp3|flac|wav|ogg|m4a|aac|wma|opus|mp4|mkv|avi|webm|mov)$", re.I)


def _np(title, artist, app):
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        return None
    return {"title": title, "artist": artist, "app": app}


def _artist_title(body, app, strip_ext=False):
    """"Artista - Musica" (ou so "Musica")."""
    body = body.strip()
    if strip_ext:
        body = EXTENSION.sub("", body)
    if " - " in body:
        artist, title = body.split(" - ", 1)
        if artist.strip() and title.strip():
            return _np(title, artist, app)
    return _np(body, "", app)


def _spotify(title):
    t = title.strip()
    if SPOTIFY_IDLE.match(t) or " - " not in t:
        return None
    artist, song = t.split(" - ", 1)
    return _np(song, artist, "Spotify")


def _vlc(title):
    t = title.strip()
    suf = " - VLC media player"
    if not t.endswith(suf):
        return None
    return _artist_title(t[:-len(suf)], "VLC", strip_ext=True)


FOOBAR = re.compile(r"^(.*?)\s*\[foobar2000(?: v?[\d.]+(?: \w+)?)?\]$")


def _foobar(title):
    t = title.strip()
    m = FOOBAR.match(t)
    if not m:
        return None       # "foobar2000" / "foobar2000 v2.1" = parado
    body = m.group(1).strip()
    if not body:
        return None
    artist = ""
    if " - " in body:
        artist, body = body.split(" - ", 1)
    body = re.sub(r"^\[[^\]]*\]\s*", "", body)   # [Album CD1 #03]
    body = body.split(" // ", 1)[0]
    return _np(body, artist, "foobar2000")


def _suffix_app(title, names, app):
    """Players que mostram "Artista - Musica - App" e so "App" parado."""
    t = title.strip()
    for n in names:
        if re.match(r"^%s(?: v?[\d.]+)?$" % re.escape(n), t, re.I):
            return None
        for sep in (" - ", " – "):
            if t.endswith(sep + n):
                t = t[:-len(sep + n)]
                break
    if t.lower() in [n.lower() for n in names]:
        return None
    return _artist_title(t, app)


def _winamp(title):
    t = title.strip()
    if re.search(r"\[(?:Paused|Stopped|Pausado|Parado)\]$", t):
        return None
    t = re.sub(r"^\d+\.\s+", "", t)
    return _suffix_app(t, ("Winamp",), "Winamp")


def _apple(title):
    t = title.strip()
    if t.lower() in ("itunes", "apple music", "music", "música", "mini player", "minijogador"):
        return None
    if " - " not in t and " — " not in t:
        return None
    t = t.replace(" — ", " - ")
    return _artist_title(t, "Apple Music")


def _browser(title):
    t = title.strip()
    t = BROWSER_SUFFIX.sub("", t)
    t = PROFILE.sub("", t)
    t = EDGE_MORE.sub("", t)
    t = NOTIF.sub("", t).strip()
    if not t:
        return None
    # YouTube Music
    for suf in (" - YouTube Music", " – YouTube Music"):
        if t.endswith(suf):
            body = t[:-len(suf)].strip()
            return _bullets(body, "YouTube Music") if body else None
    if t == "YouTube Music":
        return None
    # YouTube
    if t.endswith(" - YouTube"):
        body = NOTIF.sub("", t[:-len(" - YouTube")]).strip()
        return _np(body, "", "YouTube") if body else None
    # Deezer: "Musica - Artista - Deezer"
    if t.endswith(" - Deezer") or t.endswith(" | Deezer"):
        body = t[:-len(" - Deezer")].strip()
        if " - " not in body:
            return None
        song, artist = body.rsplit(" - ", 1)
        return _np(song, artist, "Deezer")
    # SoundCloud: tocando, a aba fica "▶ Musica by Artista"
    if PLAY_MARK.match(t):
        body = PLAY_MARK.sub("", t).strip()
        body = re.sub(r"\s*\|\s*.*SoundCloud.*$", "", body)
        if " by " in body:
            song, artist = body.rsplit(" by ", 1)
            return _np(song, artist, "SoundCloud")
        return None
    # Spotify Web: "Musica • Artista" (sem sufixo de site)
    parts = t.split(" • ")
    if len(parts) == 2 and parts[0].strip() and parts[1].strip() and " - " not in t:
        return _np(parts[0], parts[1], "Spotify Web")
    return None


def _bullets(body, app):
    parts = [p.strip() for p in body.split(" • ")]
    if len(parts) >= 2 and parts[0]:
        return _np(parts[0], parts[1], app)
    return _artist_title(body, app) if " - " in body else _np(body, "", app)


PLAYERS = {
    "vlc.exe": _vlc,
    "foobar2000.exe": _foobar,
    "aimp.exe": lambda t: _suffix_app(t, ("AIMP", "AIMP3", "AIMP2"), "AIMP"),
    "aimp3.exe": lambda t: _suffix_app(t, ("AIMP", "AIMP3"), "AIMP"),
    "winamp.exe": _winamp,
    "musicbee.exe": lambda t: _suffix_app(t, ("MusicBee",), "MusicBee"),
    "itunes.exe": _apple,
    "applemusic.exe": _apple,
}


def rank(exe):
    """0 = Spotify, 1 = players, 2 = navegador, None = desconhecido."""
    exe = (exe or "").lower()
    if exe == "spotify.exe":
        return 0
    if exe in PLAYERS:
        return 1
    if exe in BROWSERS:
        return 2
    return None


def parse(exe, title):
    """{title, artist, app} pelo titulo da janela, ou None."""
    if not isinstance(title, str) or not title.strip():
        return None
    exe = (exe or "").lower()
    if exe == "spotify.exe":
        return _spotify(title)
    if exe in PLAYERS:
        return PLAYERS[exe](title)
    if exe in BROWSERS:
        return _browser(title)
    return None


def pick(wins):
    """Melhor musica entre as janelas [{exe, title}] (pela prioridade)."""
    best = None
    for w in wins:
        r = rank(w.get("exe"))
        if r is None or (best is not None and r >= best[0]):
            continue
        np = parse(w.get("exe"), w.get("title"))
        if np:
            best = (r, np)
    return best[1] if best else None


# ------------------------------------------------------------------ thread ---
_LOCK = threading.Lock()
_STATE = {"np": None, "polled": 0.0}
_STOP = threading.Event()
_THREAD = [None]


def touch():
    """Chamado pelo /api/state: algum aparelho esta olhando."""
    _STATE["polled"] = time.time()


def current():
    with _LOCK:
        np = _STATE["np"]
        return dict(np) if np else None


def _uses_live(cfg):
    def scan(btns):
        for b in btns if isinstance(btns, list) else []:
            if not isinstance(b, dict):
                continue
            live = b.get("live")
            if isinstance(live, str) and live.startswith("nowplaying"):
                return True
            if scan(b.get("buttons")):
                return True
        return False
    for pg in (cfg or {}).get("pages") or []:
        if isinstance(pg, dict) and scan(pg.get("buttons")):
            return True
    return False


def _active():
    if time.time() - _STATE["polled"] < ACTIVE_FOR:
        return True
    try:
        from . import storage
        return _uses_live(storage.load_config())
    except Exception:
        return False


def refresh():
    try:
        np = pick(windows.list_windows())
    except Exception:
        np = None
    with _LOCK:
        _STATE["np"] = np
    return np


def _loop():
    while not _STOP.is_set():
        if _active():
            refresh()
        _STOP.wait(INTERVAL)


def start():
    if not windows.IS_WINDOWS or (_THREAD[0] and _THREAD[0].is_alive()):
        return
    _STOP.clear()
    _THREAD[0] = threading.Thread(target=_loop, name="tocando", daemon=True)
    _THREAD[0].start()


def stop():
    _STOP.set()
    if _THREAD[0]:
        _THREAD[0].join(2.0)
    _THREAD[0] = None
