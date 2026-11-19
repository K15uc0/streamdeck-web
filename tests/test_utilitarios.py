# -*- coding: utf-8 -*-
"""Funcoes pequenas: nomes de arquivos, seguranca, estado liga/desliga, versoes."""
import io
import os
import time
import unittest
import zipfile

import apoio
from streamdeck import httpd, media, paths, security, state, updates


class NomesTest(unittest.TestCase):
    def test_clean_name(self):
        casos = {
            ("logo.png", ".png"): "logo.png",
            ("C:\\Users\\x\\Minha Foto!.jpeg", ".jpg"): "Minha Foto.jpg",
            ("../../etc/passwd", ".png"): "passwd.png",
            ("-logo", ".png"): "logo.png",
            ("(1) foto", ".png"): "1) foto.png",
            ("", ".gif"): "arquivo.gif",
            (None, ".gif"): "arquivo.gif",
            ("...", ".png"): "arquivo.png",
            ("ação.png", ".png"): "a__o.png",
        }
        for (name, ext), want in casos.items():
            self.assertEqual(media.clean_name(name, ext), want, name)
        longo = media.clean_name("a" * 300, ".png")
        self.assertLessEqual(len(longo), 84)
        for name in ("a" * 300, "x/../y", "con:", "a b  .png"):
            self.assertTrue(apoio_safe(media.clean_name(name, ".png")), name)

    def test_image_type(self):
        self.assertEqual(media.image_type(apoio.PNG), ".png")
        self.assertEqual(media.image_type(b"\xff\xd8\xff\xe0abc"), ".jpg")
        self.assertEqual(media.image_type(b"GIF89a..."), ".gif")
        self.assertEqual(media.image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 "), ".webp")
        self.assertIsNone(media.image_type(b"<svg></svg>"))
        self.assertIsNone(media.image_type(b""))

    def test_safe_member(self):
        self.assertEqual(media._safe_member("imagens/a.png"), ("imagens", ["a.png"]))
        self.assertEqual(media._safe_member("sons/pasta/x.mp3"), ("sons", ["pasta", "x.mp3"]))
        for bad in ("../x.png", "/imagens/a.png", "imagens/../a.png", "imagens/a/b.png", "imagens/a.svg",
                    "sons/x.exe", "c:/sons/a.mp3", "outros/a.png", "imagens/", "sons/./a.mp3",
                    "sons/a/b/c/d.mp3"):
            self.assertIsNone(media._safe_member(bad), bad)


def apoio_safe(name):
    from streamdeck import schema
    return schema.safe_image_name(name)


class MidiaTest(unittest.TestCase):
    def test_save_image(self):
        n1 = media.save_image("Meu Logo.png", apoio.PNG)
        self.assertEqual(n1, "Meu Logo.png")
        n2 = media.save_image("Meu Logo.png", apoio.PNG)
        self.assertEqual(n2, "Meu Logo-2.png")
        n3 = media.save_image("foto.jpg", apoio.PNG)   # extensao pelo conteudo
        self.assertEqual(n3, "foto.png")
        self.assertIn(n1, media.list_images())
        full, mime = media.image_file(n1)
        self.assertTrue(paths.inside(full, paths.IMAGES_DIR))
        self.assertEqual(mime, "image/png")
        self.assertIsNone(media.image_file("../config.json"))
        self.assertIsNone(media.image_file("nao-existe.png"))
        for data, trecho in ((b"", "vazio"), (b"texto", "formato"),
                             (apoio.PNG + b"0" * media.MAX_IMAGE, "grande")):
            with self.assertRaises(ValueError) as cm:
                media.save_image("x.png", data)
            self.assertIn(trecho, str(cm.exception))

    def test_save_sound(self):
        self.assertEqual(media.save_sound("../Vinheta.MP3", b"ID3xx"), "Vinheta.mp3")
        for name, data in (("a.exe", b"x"), ("a.mp3", b""), ("semext", b"x")):
            with self.assertRaises(ValueError):
                media.save_sound(name, data)

    def test_import_zip_recusa_ruins(self):
        def zipa(files):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                for k, v in files.items():
                    z.writestr(k, v)
            buf.seek(0)
            return buf
        with self.assertRaises(ValueError) as cm:
            media.import_zip(zipa({"a.txt": "x"}))
        self.assertIn("config.json", str(cm.exception))
        with self.assertRaises(ValueError) as cm:
            media.import_zip(zipa({"config.json": "{\"version\": 2}"}))
        self.assertIn("columns", str(cm.exception))
        with self.assertRaises(ValueError):
            media.import_zip(io.BytesIO(b"nao e zip"))


class SegurancaTest(unittest.TestCase):
    def test_ip_allowed(self):
        for ip in ("127.0.0.1", "::1", "192.168.0.10", "10.1.2.3", "172.16.5.5", "169.254.1.1",
                   "100.64.0.1", "100.127.255.254", "::ffff:192.168.1.2", "fe80::1%eth0", "fd00::1"):
            self.assertTrue(security.ip_allowed(ip), ip)
        for ip in ("8.8.8.8", "1.1.1.1", "100.128.0.1", "::ffff:8.8.8.8", "2001:4860::8888", "x", ""):
            self.assertFalse(security.ip_allowed(ip), ip)

    def test_host_allowed(self):
        for h in ("127.0.0.1", "127.0.0.1:8765", "localhost:8766", "LOCALHOST", "[::1]:8765",
                  "%s:8765" % security.lan_ip()):
            self.assertTrue(security.host_allowed(h), h)
        for h in ("", None, "evil.com", "evil.com:8765", "127.0.0.1.evil.com", "[::2]:8765",
                  "localhost.evil.com:80"):
            self.assertFalse(security.host_allowed(h), h)

    def test_is_local_only(self):
        for p in ("/conectar", "/CONECTAR", "/editar", "/editar.html", "//editar", "/x/../editar",
                  "/api/local/info", "/api/local", "/API/Local/quit", "/js/editar.js", "/css/editar.css",
                  "\\editar", "/./js/./editar.js"):
            self.assertTrue(httpd.is_local_only(p), p)
        for p in ("/", "/index.html", "/js/core.js", "/api/config", "/api/localx", "/img/a.png"):
            self.assertFalse(httpd.is_local_only(p), p)
        full = os.path.join(paths.WEB_DIR, "js", "editar.js")
        self.assertTrue(httpd.is_local_only("/qualquer", full))

    def test_norm_path(self):
        self.assertEqual(httpd._norm_path("//a//b/../c"), "/a/c")
        self.assertEqual(httpd._norm_path(""), "/")
        self.assertEqual(httpd._norm_path("x\\Y"), "/x/y")

    def test_inside_e_unc(self):
        self.assertTrue(paths.inside(os.path.join(paths.BASE, "a", "b"), paths.BASE))
        self.assertFalse(paths.inside(os.path.join(paths.BASE, "..", "x"), paths.BASE))
        self.assertTrue(paths.is_unc("\\\\srv\\pasta"))
        self.assertTrue(paths.is_unc(' "//srv/x" '))
        self.assertFalse(paths.is_unc("C:\\x"))

    def test_token_e_tentativas(self):
        tok = __import__("streamdeck.storage", fromlist=["x"]).token()
        self.assertTrue(security.same_token(tok))
        self.assertFalse(security.same_token(""))
        self.assertFalse(security.same_token(tok + "x"))
        ip = "10.9.9.9"
        security.FAILS.pop(ip, None)
        for _ in range(security.MAX_FAILS - 1):
            security.note_fail(ip)
        self.assertFalse(security.fail_blocked(ip))
        with apoio.quiet():
            security.note_fail(ip)
        self.assertTrue(security.fail_blocked(ip))
        security.FAILS.pop(ip, None)


class EstadoTest(unittest.TestCase):
    def setUp(self):
        state._TOGGLES.clear()

    def test_flip_toggles_since(self):
        self.assertEqual(state.key(1, 2), "1:2")
        self.assertEqual(state.key(1, 2, 0), "1:2:0")
        t0 = int(time.time())
        self.assertTrue(state.flip(0, 0))
        self.assertTrue(state.flip(0, 3, 0))
        self.assertEqual(state.toggles(), {"0:0": True, "0:3:0": True})
        s = state.since()
        self.assertGreaterEqual(s["0:0"], t0)
        self.assertFalse(state.flip(0, 0))
        self.assertEqual(state.toggles(), {"0:3:0": True})

    def test_prune(self):
        cfg = apoio.base_config()
        state.flip(0, 0)        # toggle de verdade
        state.flip(0, 3, 0)     # toggle dentro da pasta
        state.flip(0, 1)        # nao e toggle
        state.flip(0, 3, 1)     # item da pasta que nao e toggle
        state.flip(9, 0)        # pagina inexistente
        state.flip(0, 4, 0)     # fader nao e pasta
        self.assertEqual(state.toggles(cfg), {"0:0": True, "0:3:0": True})
        cfg["pages"][0]["buttons"][0]["toggle"] = False
        self.assertEqual(set(state.since(cfg)), {"0:3:0"})


class VersaoTest(unittest.TestCase):
    def test_parse_ver(self):
        self.assertEqual(updates.parse_ver("2.3.1"), (2, 3, 1))
        self.assertEqual(updates.parse_ver("v2.4"), (2, 4, 0))
        self.assertEqual(updates.parse_ver("V10"), (10, 0, 0))
        self.assertEqual(updates.parse_ver(""), (0, 0, 0))
        self.assertGreater(updates.parse_ver("v2.10.0"), updates.parse_ver("2.9.9"))
        self.assertGreater(updates.parse_ver("3"), updates.parse_ver("2.99"))
        from streamdeck import VERSION
        self.assertEqual(len(updates.parse_ver(VERSION)), 3)


if __name__ == "__main__":
    unittest.main()
