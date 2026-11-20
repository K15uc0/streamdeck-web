# -*- coding: utf-8 -*-
"""Musica tocando agora (2.8): parse() pelo titulo da janela."""
import unittest

import apoio  # noqa: F401  (antes do pacote)
from streamdeck import schema, tocando

E = "Microsoft​ Edge"
CASES = [
    # Spotify
    ("Spotify.exe", "Daft Punk - Get Lucky", ("Get Lucky", "Daft Punk", "Spotify")),
    ("spotify.exe", "The Beatles - Let It Be - Remastered 2009",
     ("Let It Be - Remastered 2009", "The Beatles", "Spotify")),
    ("spotify.exe", "Spotify", None),
    ("spotify.exe", "Spotify Premium", None),
    ("spotify.exe", "Spotify Free", None),
    ("spotify.exe", "Anitta, Cardi B - Me Gusta", ("Me Gusta", "Anitta, Cardi B", "Spotify")),
    ("spotify.exe", "GDI+ Window (Spotify.exe)", None),
    # YouTube
    ("chrome.exe", "Rick Astley - Never Gonna Give You Up (Official Video) - YouTube - Google Chrome",
     ("Rick Astley - Never Gonna Give You Up (Official Video)", "", "YouTube")),
    ("chrome.exe", "(123) Lofi hip hop radio - YouTube - Google Chrome", ("Lofi hip hop radio", "", "YouTube")),
    ("msedge.exe", "Aula de violao - YouTube and 3 more pages - Personal - " + E,
     ("Aula de violao", "", "YouTube")),
    ("msedge.exe", "Aula de violao - YouTube - " + E, ("Aula de violao", "", "YouTube")),
    ("firefox.exe", "Bohemian Rhapsody - YouTube — Mozilla Firefox", ("Bohemian Rhapsody", "", "YouTube")),
    ("chrome.exe", "YouTube - Google Chrome", None),
    ("brave.exe", "(5) Musica boa - YouTube - Brave", ("Musica boa", "", "YouTube")),
    # YouTube Music
    ("chrome.exe", "Blinding Lights • The Weeknd - YouTube Music - Google Chrome",
     ("Blinding Lights", "The Weeknd", "YouTube Music")),
    ("chrome.exe", "Blinding Lights • The Weeknd • After Hours - YouTube Music - Google Chrome",
     ("Blinding Lights", "The Weeknd", "YouTube Music")),
    ("chrome.exe", "YouTube Music - Google Chrome", None),
    ("opera.exe", "Garota de Ipanema - YouTube Music - Opera", ("Garota de Ipanema", "", "YouTube Music")),
    # Deezer
    ("chrome.exe", "Evidencias - Chitaozinho & Xororo - Deezer - Google Chrome",
     ("Evidencias", "Chitaozinho & Xororo", "Deezer")),
    ("chrome.exe", "Deezer - Google Chrome", None),
    # SoundCloud
    ("firefox.exe", "▶ Midnight City by M83 — Mozilla Firefox", ("Midnight City", "M83", "SoundCloud")),
    ("chrome.exe", "▶︎ Track One by Some DJ | Listen online for free on SoundCloud - Google Chrome",
     ("Track One", "Some DJ", "SoundCloud")),
    # Spotify Web
    # (nao suportado: titulo sem sufixo do site, ambiguo)
    ("chrome.exe", "Get Lucky • Daft Punk - Google Chrome", None),
    ("chrome.exe", "Fulano (@fulano) • Instagram photos and videos - Google Chrome", None),
    ("msedge.exe", "Spotify - Web Player: Music for everyone - " + E, None),
    # outras abas
    ("chrome.exe", "Gmail - Caixa de entrada - Google Chrome", None),
    ("chrome.exe", "Nova guia - Google Chrome", None),
    # VLC
    ("vlc.exe", "Song Name - VLC media player", ("Song Name", "", "VLC")),
    ("vlc.exe", "Queen - Bohemian Rhapsody - VLC media player", ("Bohemian Rhapsody", "Queen", "VLC")),
    ("vlc.exe", "musica.mp3 - VLC media player", ("musica", "", "VLC")),
    ("vlc.exe", "VLC media player", None),
    # foobar2000
    ("foobar2000.exe", "Pink Floyd - [The Wall #03] Another Brick in the Wall  [foobar2000]",
     ("Another Brick in the Wall", "Pink Floyd", "foobar2000")),
    ("foobar2000.exe", "Pink Floyd - Time [foobar2000]", ("Time", "Pink Floyd", "foobar2000")),
    ("foobar2000.exe", "Various - [Hits CD1 #01] Song // Guest [foobar2000]", ("Song", "Various", "foobar2000")),
    ("foobar2000.exe", "foobar2000", None),
    ("foobar2000.exe", "foobar2000 v2.1.4", None),
    ("foobar2000.exe", "Artist - Song [foobar2000 v1.6.16]", ("Song", "Artist", "foobar2000")),
    # AIMP
    ("AIMP.exe", "Metallica - One", ("One", "Metallica", "AIMP")),
    ("aimp.exe", "AIMP", None),
    ("aimp.exe", "Metallica - One - AIMP", ("One", "Metallica", "AIMP")),
    # Winamp
    ("winamp.exe", "1. Nirvana - Smells Like Teen Spirit - Winamp", ("Smells Like Teen Spirit", "Nirvana", "Winamp")),
    ("winamp.exe", "12. Nirvana - Lithium - Winamp [Paused]", None),
    ("winamp.exe", "Winamp", None),
    ("winamp.exe", "Winamp 5.9", None),
    # MusicBee
    ("MusicBee.exe", "Adele - Hello - MusicBee", ("Hello", "Adele", "MusicBee")),
    ("musicbee.exe", "MusicBee", None),
    # iTunes / Apple Music
    ("iTunes.exe", "iTunes", None),
    ("AppleMusic.exe", "Apple Music", None),
    ("AppleMusic.exe", "Mini Player", None),
    # desconhecido / vazio
    ("notepad.exe", "Artista - Musica", None),
    ("spotify.exe", "", None),
    ("", "Artista - Musica", None),
]


class Parse(unittest.TestCase):
    def test_table(self):
        self.assertGreaterEqual(len(CASES), 30)
        for exe, title, want in CASES:
            got = tocando.parse(exe, title)
            if want is not None:
                want = {"title": want[0], "artist": want[1], "app": want[2]}
            self.assertEqual(got, want, "%s | %s" % (exe, title))

    def test_priority(self):
        wins = [{"exe": "chrome.exe", "title": "Video - YouTube - Google Chrome"},
                {"exe": "vlc.exe", "title": "A - B - VLC media player"},
                {"exe": "spotify.exe", "title": "Spotify Premium"}]
        self.assertEqual(tocando.pick(wins)["app"], "VLC")
        wins.append({"exe": "spotify.exe", "title": "X - Y"})
        self.assertEqual(tocando.pick(wins)["app"], "Spotify")
        self.assertEqual(tocando.pick(wins[:1])["app"], "YouTube")
        self.assertIsNone(tocando.pick([]))

    def test_uses_live(self):
        cfg = apoio.base_config()
        self.assertFalse(tocando._uses_live(cfg))
        cfg["pages"][0]["buttons"][3]["buttons"][1]["live"] = "nowplaying:title"
        self.assertTrue(tocando._uses_live(cfg))
        schema.validate_config(cfg)

    def test_state_has_nowplaying(self):
        import json
        apoio.write_config(apoio.base_config())
        with apoio.quiet():
            st, _h, out = apoio.fake_request("GET", "/api/state", ip="127.0.0.1")
        self.assertEqual(st, 200)
        js = json.loads(out.decode("utf-8"))
        self.assertIn("nowplaying", js)
        self.assertIsNone(js["nowplaying"])


if __name__ == "__main__":
    unittest.main()
