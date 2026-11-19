# -*- coding: utf-8 -*-
"""Integracao: o servidor de verdade (httpd.Server) numa thread, em porta livre,
com os dados numa pasta temporaria. Pedidos de "outro aparelho" (IP da rede)
usam apoio.fake_request, que chama o Handler com um endereco falso."""
import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import apoio
from streamdeck import httpd, security, state, storage


class Servidor(object):
    srv = None
    port = None

    @classmethod
    def start(cls):
        if cls.srv is None:
            apoio.write_config(apoio.base_config())
            cls.srv = httpd.Server(("127.0.0.1", 0), httpd.Handler)
            cls.port = cls.srv.server_address[1]
            state.PORT[0] = cls.port
            threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        return cls.port


def call(method, path, body=None, headers=None, raw=False):
    """Pedido ao servidor da thread (vem de 127.0.0.1, o proprio PC).
    Devolve (status, cabecalhos, json ou bytes)."""
    port = Servidor.start()
    h = {"X-StreamDeck": "1"}
    h.update(headers or {})
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    h = dict((k, v) for k, v in h.items() if v is not None)
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status, hdrs, payload = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        status, hdrs, payload = e.code, dict(e.headers), e.read()
    if raw:
        return status, hdrs, payload
    return status, hdrs, json.loads(payload.decode("utf-8"))


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with apoio.quiet():
            Servidor.start()

    def setUp(self):
        self._q = apoio.quiet()
        self._q.__enter__()
        apoio.write_config(apoio.base_config())
        state._TOGGLES.clear()
        security.FAILS.clear()

    def tearDown(self):
        self._q.__exit__(None, None, None)

    # -------------------------------------------------------------- config ---
    def test_get_config(self):
        st, h, cfg = call("GET", "/api/config")
        self.assertEqual(st, 200)
        self.assertEqual(cfg, apoio.base_config())
        self.assertTrue(h.get("X-Config-Version"))

    def test_post_config_valido(self):
        cfg = apoio.base_config()
        cfg["title"] = "Mudou"
        cfg["pages"][1]["buttons"].append({"label": "Novo", "action": {"type": "hotkey", "keys": ["f2"]}})
        st, _, r = call("POST", "/api/config", cfg)
        self.assertEqual((st, r["ok"]), (200, True))
        self.assertTrue(r["v"])
        self.assertEqual(call("GET", "/api/config")[2], cfg)
        self.assertEqual(r["v"], call("GET", "/api/state")[2]["v"])

    def test_post_config_invalido(self):
        for ruim in ({"version": 2}, {"version": 2, "columns": 4, "rows": 2, "pages": [
                {"buttons": [{"action": {"type": "explodir"}}]}]}, [1, 2]):
            st, _, r = call("POST", "/api/config", ruim)
            self.assertEqual(st, 400)
            self.assertFalse(r["ok"])
            self.assertTrue(r["error"])
        self.assertEqual(call("GET", "/api/config")[2], apoio.base_config())
        st, _, payload = call("POST", "/api/config", b"{nao e json", raw=True)
        self.assertEqual(st, 400)

    def test_post_config_v1_e_migrado(self):
        st, _, r = call("POST", "/api/config", apoio.fixture("config_v1.json"))
        self.assertEqual(st, 200, r)
        cfg = call("GET", "/api/config")[2]
        self.assertEqual(cfg["version"], 2)

    def test_post_config_de_outro_aparelho_recusado(self):
        tok = storage.token()
        body = json.dumps(apoio.base_config()).encode("utf-8")
        st, _, payload = apoio.fake_request("POST", "/api/config?k=" + tok, ip="192.168.0.50",
                                            headers={"Content-Type": "application/json"}, body=body)
        self.assertEqual(st, 403)
        self.assertEqual(json.loads(payload.decode("utf-8"))["error"], "edite pelo PC")
        # sem codigo: recusado antes
        st, _, _ = apoio.fake_request("POST", "/api/config", ip="192.168.0.51", body=body)
        self.assertEqual(st, 403)
        # do proprio PC pelo mesmo caminho: aceito
        st, _, payload = apoio.fake_request("POST", "/api/config", ip="127.0.0.1",
                                            headers={"Content-Type": "application/json"}, body=body)
        self.assertEqual(st, 200, payload)

    # --------------------------------------------------------- barreiras ---
    def test_cabecalho_obrigatorio(self):
        st, _, r = call("GET", "/api/config", headers={"X-StreamDeck": None})
        self.assertEqual(st, 403)
        st, _, r = call("GET", "/api/config", headers={"Origin": "http://evil.com"})
        self.assertEqual(st, 403)

    def test_host_estranho(self):
        st, _, _ = call("GET", "/api/config", headers={"Host": "evil.com"}, raw=True)
        self.assertEqual(st, 421)

    def test_outro_aparelho_precisa_de_codigo(self):
        st, _, _ = apoio.fake_request("GET", "/api/config", ip="192.168.0.60")
        self.assertEqual(st, 403)
        st, _, payload = apoio.fake_request("GET", "/api/config?k=" + storage.token(), ip="192.168.0.60")
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(payload.decode("utf-8"))["version"], 2)
        st, _, _ = apoio.fake_request("GET", "/api/config", ip="192.168.0.60",
                                      headers={"Cookie": "a=b; sdk=" + storage.token()})
        self.assertEqual(st, 200)
        st, _, _ = apoio.fake_request("GET", "/api/config", ip="8.8.8.8")
        self.assertEqual(st, 403)

    def test_paginas_so_do_pc(self):
        for p in ("/editar", "/conectar", "/js/editar.js", "/api/local/hello", "/api/local/info"):
            st, _, _ = apoio.fake_request("GET", p + "?k=" + storage.token(), ip="192.168.0.70")
            self.assertEqual(st, 403, p)
        st, _, _ = apoio.fake_request("POST", "/api/local/quit", ip="192.168.0.70")
        self.assertEqual(st, 403)
        st, _, body = call("GET", "/editar", raw=True)
        self.assertEqual(st, 200)
        self.assertIn(b"<html", body.lower())

    def test_primeiro_acesso_grava_cookie(self):
        st, h, _ = apoio.fake_request("GET", "/?k=" + storage.token(), ip="192.168.0.80")
        self.assertEqual(st, 302)
        self.assertIn("sdk=" + storage.token(), h["set-cookie"])
        st, _, _ = apoio.fake_request("GET", "/?k=errado", ip="192.168.0.80")
        self.assertEqual(st, 403)

    # ------------------------------------------------------------- acoes ---
    def test_actions(self):
        st, _, r = call("GET", "/api/actions")
        self.assertEqual(st, 200)
        tipos = [a["type"] for a in r["actions"]]
        for t in ("none", "hotkey", "page", "multi", "sound", "site"):
            self.assertIn(t, tipos)

    def test_info_e_hello(self):
        st, _, r = call("GET", "/api/local/hello")
        self.assertEqual((st, r["ok"], r["app"]), (200, True, "streamdeck"))
        st, _, r = call("GET", "/api/info")
        self.assertEqual(st, 200)
        self.assertTrue(r["local"])
        self.assertEqual(r["code"], storage.token())

    def test_press_simulado_e_toggles(self):
        del apoio.KEYS[:]
        st, _, r = call("GET", "/api/press?p=0&b=1")       # hotkey (teclas anotadas, nao enviadas)
        self.assertEqual((st, r["ok"]), (200, True), r)
        st, _, r = call("GET", "/api/press?p=0&b=2")       # texto
        self.assertTrue(r["ok"], r)
        self.assertEqual(apoio.KEYS, [("keys", ["ctrl", "c"]), ("text", "Ola!", True)])
        st, _, r = call("GET", "/api/press?p=0&b=0")       # ON AIR liga
        self.assertEqual(r["toggles"], {"0:0": True})
        st, _, s = call("GET", "/api/state")
        self.assertEqual(s["toggles"], {"0:0": True})
        self.assertIn("0:0", s["since"])
        self.assertIsInstance(s["since"]["0:0"], int)
        st, _, r = call("GET", "/api/press?p=0&b=3&f=0")   # toggle dentro da pasta
        self.assertEqual(r["toggles"], {"0:0": True, "0:3:0": True})
        st, _, r = call("GET", "/api/press?p=0&b=0")       # desliga
        self.assertEqual(r["toggles"], {"0:3:0": True})
        st, _, s = call("GET", "/api/state")
        self.assertNotIn("0:0", s["since"])
        # botao movido: estado some
        cfg = apoio.base_config()
        cfg["pages"][0]["buttons"][3]["buttons"][0]["toggle"] = False
        self.assertEqual(call("POST", "/api/config", cfg)[0], 200)
        self.assertEqual(call("GET", "/api/state")[2]["toggles"], {})

    def test_press_pasta_e_erros(self):
        st, _, r = call("GET", "/api/press?p=0&b=3")       # abrir pasta: so no aparelho
        self.assertEqual((st, r["ok"]), (200, True))
        for q in ("p=0&b=99", "p=5&b=0", "p=0&b=4", "p=0&b=1&f=0", "p=-1&b=0", "p=x&b=0", "b=1"):
            st, _, r = call("GET", "/api/press?" + q)
            self.assertEqual(st, 500, q)
            self.assertFalse(r["ok"], q)

    def test_library(self):
        st, _, r = call("GET", "/api/library")
        self.assertEqual(st, 200)
        self.assertTrue(r["groups"])
        self.assertTrue(r["groups"][0]["items"])

    # ------------------------------------------------------------ imagens ---
    def test_upload_imagem_e_img(self):
        st, _, r = call("POST", "/api/local/images?name=Botao%20Teste.png", apoio.PNG,
                        headers={"Content-Type": "application/octet-stream"})
        self.assertEqual((st, r["ok"]), (200, True), r)
        name = r["name"]
        self.assertIn(name, call("GET", "/api/images")[2]["images"])
        path = "/img/" + urllib.parse.quote(name)
        st, h, data = call("GET", path, raw=True)
        self.assertEqual((st, data), (200, apoio.PNG))
        self.assertEqual(h["Content-Type"], "image/png")
        # outro aparelho: sem codigo 403 (e nao conta tentativa), com codigo 200
        st, _, _ = apoio.fake_request("GET", path, ip="192.168.0.90")
        self.assertEqual(st, 403)
        self.assertFalse(security.FAILS.get("192.168.0.90"))
        st, _, data = apoio.fake_request("GET", path + "?k=" + storage.token(), ip="192.168.0.90")
        self.assertEqual((st, data), (200, apoio.PNG))
        st, _, _ = call("GET", "/img/..%2Fconfig.json", raw=True)
        self.assertEqual(st, 404)
        st, _, r = call("POST", "/api/local/images?name=x.png", b"nao e imagem",
                        headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(st, 400)
        # upload de outro aparelho: recusado
        st, _, _ = apoio.fake_request("POST", "/api/local/images?name=x.png&k=" + storage.token(),
                                      ip="192.168.0.91", body=apoio.PNG)
        self.assertEqual(st, 403)

    # -------------------------------------------------- exportar/importar ---
    def test_export_import(self):
        call("POST", "/api/local/images?name=roundtrip.png", apoio.PNG,
             headers={"Content-Type": "application/octet-stream"})
        orig = apoio.base_config()
        orig["title"] = "Original"
        orig["pages"][0]["buttons"][1]["image"] = "roundtrip.png"
        self.assertEqual(call("POST", "/api/config", orig)[0], 200)
        st, h, zdata = call("GET", "/api/local/export", raw=True)
        self.assertEqual(st, 200)
        self.assertEqual(h["Content-Type"], "application/zip")
        names = zipfile.ZipFile(io.BytesIO(zdata)).namelist()
        self.assertIn("config.json", names)
        self.assertIn("imagens/roundtrip.png", names)

        outro = apoio.base_config()
        outro["title"] = "Outro"
        self.assertEqual(call("POST", "/api/config", outro)[0], 200)
        st, _, r = call("POST", "/api/local/import", zdata, headers={"Content-Type": "application/zip"})
        self.assertEqual((st, r["ok"]), (200, True), r)
        self.assertGreaterEqual(r["images"], 1)
        self.assertEqual(call("GET", "/api/config")[2], orig)

        st, _, r = call("POST", "/api/local/import", b"PK nao e zip", headers={"Content-Type": "application/zip"})
        self.assertEqual(st, 400)
        self.assertEqual(call("GET", "/api/config")[2], orig)

    def test_local_test_nao_salva(self):
        st, _, r = call("POST", "/api/local/test", {"action": {"type": "hotkey", "keys": ["f1"]}})
        self.assertEqual((st, r["ok"]), (200, True))
        st, _, r = call("POST", "/api/local/test", {"action": {"type": "hotkey"}})
        self.assertFalse(r["ok"])

    def test_estaticos(self):
        st, h, body = call("GET", "/", raw=True)
        self.assertEqual(st, 200)
        self.assertIn("text/html", h["Content-Type"])
        self.assertIn("Content-Security-Policy", h)
        st, _, _ = call("GET", "/../config.padrao.json", raw=True)
        self.assertEqual(st, 404)
        st, _, _ = call("GET", "/ping.gif", raw=True, headers={"X-StreamDeck": None})
        self.assertEqual(st, 200)


if __name__ == "__main__":
    unittest.main()
