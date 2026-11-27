# -*- coding: utf-8 -*-
"""Navegador (2.12): pareamento da extensao, regras de Origin, abas, long-poll
de comandos, atalhos quando a extensao nao esta ligada, acao browser e bloco."""
import json
import os
import threading
import time
import unittest
from unittest import mock

import apoio
from streamdeck import actions, navegador, paths, schema, security, storage
from test_http import Servidor, call
from test_aparelhos_http import pedir, cookie_de

EXT = "abcdefghijklmnopabcdefghijklmnop"
ORIGIN = "chrome-extension://" + EXT
IP = "192.168.0.88"


def ext(method, path, body=None, key=None, origin=ORIGIN):
    h = {"Origin": origin, "X-StreamDeck": None}
    if key:
        h["X-StreamDeck-Ext"] = key
    return call(method, path, body=body, headers=h)


class Base(unittest.TestCase):
    def setUp(self):
        self._q = apoio.quiet()
        self._q.__enter__()
        Servidor.start()
        security.FAILS.clear()
        navegador.PONTE.unpair()
        del apoio.KEYS[:]
        self._open = mock.patch.object(navegador, "_open_default")
        self.opened = self._open.start()
        self._fg = mock.patch.object(navegador, "_foreground_exe", return_value="chrome.exe")
        self._fg.start()

    def tearDown(self):
        self._open.stop()
        self._fg.stop()
        navegador.PONTE.unpair()
        self._q.__exit__(None, None, None)

    def parear(self):
        st, _, d = call("POST", "/api/local/navegador", {"op": "pair"})
        self.assertEqual(st, 200)
        code = d["code"]
        self.assertEqual(len(code), navegador.CODE_LEN)
        st, _, d = ext("POST", "/api/browser/pair", {"code": code.lower()})
        self.assertEqual(st, 200, d)
        return d["key"]


class PareamentoTest(Base):
    def test_parear_e_desparear(self):
        key = self.parear()
        self.assertEqual(len(key), 64)
        st, _, d = call("GET", "/api/local/navegador")
        self.assertTrue(d["paired"])
        self.assertEqual(d["ext_id"], EXT)
        self.assertIsNone(d["code"])            # codigo e de uso unico
        self.assertNotIn("key", json.dumps(d))   # chave nunca sai para o Conectar
        with open(navegador.STATE_PATH, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["ext_id"], EXT)
        st, _, d = ext("POST", "/api/browser/hello", key=key)
        self.assertTrue(d["paired"])
        call("POST", "/api/local/navegador", {"op": "unpair"})
        self.assertFalse(os.path.exists(navegador.STATE_PATH))
        st, _, d = ext("POST", "/api/browser/tabs", {"tabs": []}, key=key)
        self.assertEqual(st, 401)

    def test_codigo_errado_morre_depois_de_5(self):
        call("POST", "/api/local/navegador", {"op": "pair"})
        code = navegador.PONTE.code
        for _ in range(navegador.CODE_TRIES):
            st, _, d = ext("POST", "/api/browser/pair", {"code": "ZZZZZZ"})
            self.assertEqual(st, 400)
        st, _, d = ext("POST", "/api/browser/pair", {"code": code})
        self.assertEqual(st, 400)
        self.assertIn("vencido", d["error"])
        self.assertFalse(security.fail_blocked("127.0.0.1"))   # o PC nao fica bloqueado

    def test_codigo_vencido(self):
        call("POST", "/api/local/navegador", {"op": "pair"})
        code = navegador.PONTE.code
        navegador.PONTE.code_until = time.time() - 1
        st, _, d = ext("POST", "/api/browser/pair", {"code": code})
        self.assertEqual(st, 400)

    def test_novo_codigo_repareia_e_invalida_chave_velha(self):
        k1 = self.parear()
        k2 = self.parear()
        self.assertNotEqual(k1, k2)
        self.assertEqual(ext("POST", "/api/browser/commands?wait=0", key=k1)[0], 401)
        self.assertEqual(ext("POST", "/api/browser/commands?wait=0", key=k2)[0], 200)


class OrigemTest(Base):
    def test_outros_origins_recusados(self):
        key = self.parear()
        for origin in (None, "http://127.0.0.1:8765", "https://evil.com", "chrome-extension://" + "a" * 32,
                       "chrome-extension://" + EXT + ".evil.com", "moz-extension://" + EXT, "null"):
            st, _, _ = ext("POST", "/api/browser/tabs", {"tabs": []}, key=key, origin=origin)
            self.assertIn(st, (401, 403), origin)
        # id certo, chave errada
        st, _, _ = ext("POST", "/api/browser/tabs", {"tabs": []}, key="0" * 64)
        self.assertEqual(st, 401)
        st, _, _ = ext("POST", "/api/browser/tabs", {"tabs": []})
        self.assertEqual(st, 401)

    def test_ip_remoto_recusado(self):
        key = self.parear()
        for path, method in (("/api/browser/hello", "POST"), ("/api/browser/pair", "POST"),
                             ("/api/browser/tabs", "POST"), ("/api/browser/commands", "POST"),
                             ("/api/browser/commands", "GET")):
            st, _, _ = pedir(method, path, ip=IP, body={"tabs": [], "code": "X"},
                             headers={"Origin": ORIGIN, "X-StreamDeck-Ext": key, "X-StreamDeck": "1"})
            self.assertEqual(st, 403, path)

    def test_extensao_nao_entra_no_resto_da_api(self):
        key = self.parear()
        for path in ("/api/local/info", "/api/config", "/api/local/navegador", "/api/state"):
            st, _, _ = call("GET", path, headers={"Origin": ORIGIN, "X-StreamDeck-Ext": key})
            self.assertEqual(st, 403, path)

    def test_get_nunca_vale(self):
        """O Chrome nao manda Origin no GET; o servidor so aceita POST."""
        key = self.parear()
        for path in ("/api/browser/hello", "/api/browser/commands"):
            st, _, _ = ext("GET", path, key=key)
            self.assertEqual(st, 404, path)
            st, _, _ = ext("GET", path, key=key, origin=None)
            self.assertEqual(st, 403, path)

    def test_hello_para_achar_a_porta(self):
        st, _, d = ext("POST", "/api/browser/hello")
        self.assertEqual(st, 200)
        self.assertEqual(d["app"], "streamdeck")
        self.assertFalse(d["paired"])


class AbasEComandosTest(Base):
    def test_abas_viram_host_sem_url(self):
        key = self.parear()
        tabs = [{"id": 5, "window": 1, "title": "Video", "url": "https://www.youtube.com/watch?v=x", "active": True,
                 "audible": True},
                {"id": 6, "window": 1, "title": "Arquivo", "url": "file:///C:/segredo.txt"},
                {"id": "x"}, "lixo"]
        st, _, d = ext("POST", "/api/browser/tabs", {"tabs": tabs}, key=key)
        self.assertEqual(d["n"], 2)
        st, _, d = call("GET", "/api/navegador")
        self.assertTrue(d["connected"])
        self.assertEqual(d["tabs"][0]["host"], "youtube.com")
        self.assertTrue(d["tabs"][0]["yt"])
        self.assertEqual(d["tabs"][1]["host"], "")
        self.assertNotIn("segredo", json.dumps(d))
        self.assertNotIn("watch", json.dumps(d))

    def test_rolar_fora_do_youtube_vira_atalho(self):
        key = self.parear()
        ext("POST", "/api/browser/tabs", {"tabs": [{"id": 1, "url": "https://g1.globo.com/", "active": True,
                                                    "current": True}]}, key=key)
        st, _, d = call("POST", "/api/navegador", {"op": "scroll", "dir": "down"})
        self.assertEqual(d["via"], "keys")
        st, _, d = call("POST", "/api/navegador", {"op": "yt_toggle"})
        self.assertEqual(d["via"], "keys")
        st, _, d = call("POST", "/api/navegador", {"op": "reload"})
        self.assertEqual(d["via"], "ext")
        self.assertEqual(apoio.KEYS, [("keys", ["pagedown"]), ("keys", ["k"])])

    def test_long_poll_recebe_comando(self):
        key = self.parear()
        ext("POST", "/api/browser/tabs", {"tabs": [{"id": 1, "url": "https://www.youtube.com/watch?v=1",
                                                    "active": True, "current": True}]}, key=key)
        out = {}

        def poll():
            out["r"] = ext("POST", "/api/browser/commands?wait=5", key=key)
        t = threading.Thread(target=poll)
        t.start()
        for _ in range(100):
            if navegador.PONTE.polls:
                break
            time.sleep(0.02)
        t0 = time.time()
        st, _, d = call("POST", "/api/navegador", {"op": "scroll", "dir": "down"})
        self.assertEqual(d["via"], "ext")
        t.join(5)
        self.assertLess(time.time() - t0, 3)
        self.assertEqual(out["r"][2]["commands"], [{"op": "scroll", "dir": "down"}])
        self.assertEqual(apoio.KEYS, [])     # nada de teclas com a extensao ligada

    def test_long_poll_vazio_e_limite(self):
        key = self.parear()
        t0 = time.time()
        st, _, d = ext("POST", "/api/browser/commands?wait=0.2", key=key)
        self.assertEqual(d["commands"], [])
        self.assertGreaterEqual(time.time() - t0, 0.15)
        res = []
        ths = [threading.Thread(target=lambda: res.append(ext("POST", "/api/browser/commands?wait=2", key=key)))
               for _ in range(2)]
        for th in ths:
            th.start()
        for _ in range(100):
            if navegador.PONTE.polls == 2:
                break
            time.sleep(0.02)
        t0 = time.time()
        st, _, d = ext("POST", "/api/browser/commands?wait=2", key=key)   # terceiro: volta na hora
        self.assertTrue(d.get("busy"))
        self.assertLess(time.time() - t0, 1)
        # outros pedidos nao ficam presos atras dos long-polls
        t0 = time.time()
        self.assertEqual(call("GET", "/api/local/navegador")[0], 200)
        self.assertLess(time.time() - t0, 1)
        navegador.PONTE.unpair()     # acorda quem espera
        for th in ths:
            th.join(5)
        self.assertEqual(navegador.PONTE.polls, 0)

    def test_permissoes_da_folha(self):
        """Aparelho sem Controle total: fechar aba e endereco digitado recusados."""
        cfg = apoio.base_config()
        cfg["pages"][0]["buttons"].append({"kind": "browser", "label": "Navegador"})
        apoio.write_config(cfg)
        st, h, _ = pedir("GET", "/?k=" + storage.token())
        key = cookie_de(h)
        st, _, d = pedir("POST", "/api/navegador", key=key, body={"op": "close_tab"})
        self.assertEqual(st, 403)
        self.assertEqual(d["reason"], "full")
        st, _, d = pedir("POST", "/api/navegador", key=key, body={"op": "open_url", "url": "https://a.com"})
        self.assertEqual(st, 403)
        st, _, d = pedir("POST", "/api/navegador", key=key, body={"op": "reload"})
        self.assertEqual(st, 200)
        self.assertEqual(apoio.KEYS[-1], ("keys", ["f5"]))
        st, _, d = pedir("GET", "/api/navegador", key=key)
        self.assertEqual(st, 200)
        self.assertFalse(d["full"])

    def test_aparelho_sem_pagina_com_bloco(self):
        from streamdeck import devices
        cfg = apoio.base_config()
        cfg["pages"].append({"name": "Nav", "id": "c9c9", "grid": {"columns": 4, "rows": 2},
                             "buttons": [{"kind": "browser"}]})
        apoio.write_config(cfg)
        st, h, _ = pedir("GET", "/?k=" + storage.token())
        key = cookie_de(h)
        dev = devices.find(key)
        devices.set_pages(dev["id"], ["a1a1"])
        st, _, d = pedir("GET", "/api/navegador", key=key)
        self.assertEqual(st, 403)
        st, _, d = pedir("POST", "/api/navegador", key=key, body={"op": "reload"})
        self.assertEqual(st, 403)
        devices.set_pages(dev["id"], ["c9c9"])
        self.assertEqual(pedir("GET", "/api/navegador", key=key)[0], 200)

    def test_comando_invalido(self):
        for body in ({"op": "x"}, {"op": "open_url", "url": "javascript:alert(1)"},
                     {"op": "open_url", "url": "file:///c:/"}, {"op": "scroll", "dir": "lado"},
                     {"op": "activate"}, {"op": "activate", "tab": True}):
            st, _, d = call("POST", "/api/navegador", body)
            self.assertEqual(st, 400, body)


class AtalhosTest(Base):
    """Sem extensao ligada: atalhos de teclado (nunca teclas de verdade nos testes)."""

    def run_op(self, **cmd):
        del apoio.KEYS[:]
        self.assertEqual(navegador.execute(cmd), "keys")
        return list(apoio.KEYS)

    def test_mapa(self):
        self.assertEqual(self.run_op(op="tab_next"), [("keys", ["ctrl", "tab"])])
        self.assertEqual(self.run_op(op="tab_prev"), [("keys", ["ctrl", "shift", "tab"])])
        self.assertEqual(self.run_op(op="yt_toggle"), [("keys", ["k"])])
        self.assertEqual(self.run_op(op="back"), [("keys", ["alt", "left"])])
        self.assertEqual(self.run_op(op="forward"), [("keys", ["alt", "right"])])
        self.assertEqual(self.run_op(op="reload"), [("keys", ["f5"])])
        self.assertEqual(self.run_op(op="close_tab"), [("keys", ["ctrl", "w"])])
        for d, k in (("down", "pagedown"), ("up", "pageup"), ("top", "home"), ("bottom", "end")):
            self.assertEqual(self.run_op(op="scroll", dir=d), [("keys", [k])])

    def test_abrir_site(self):
        self.assertEqual(self.run_op(op="open_url", url="https://exemplo.com/"),
                         [("keys", ["ctrl", "l"]), ("text", "https://exemplo.com/", True)])
        with mock.patch.object(navegador, "_foreground_exe", return_value="notepad.exe"):
            self.assertEqual(self.run_op(op="open_url", url="https://exemplo.com/"), [])
        self.opened.assert_called_once_with("https://exemplo.com/")

    def test_ativar_aba_sem_extensao(self):
        with self.assertRaises(navegador.BrowserError):
            navegador.execute({"op": "activate", "tab": 1})

    def test_extensao_parada_ha_mais_de_30s_usa_atalho(self):
        self.parear()
        navegador.PONTE.seen = time.time() - navegador.ONLINE_S - 1
        self.assertEqual(self.run_op(op="reload"), [("keys", ["f5"])])


class ExtensaoArquivosTest(unittest.TestCase):
    def test_manifesto_minimo(self):
        with open(os.path.join(apoio.ROOT, "extensao", "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["manifest_version"], 3)
        self.assertEqual(sorted(m["permissions"]), ["scripting", "storage", "tabs"])
        self.assertEqual(m["host_permissions"], ["http://127.0.0.1/*", "*://*.youtube.com/*"])
        self.assertNotIn("content_scripts", m)

    def test_pasta_da_extensao(self):
        self.assertEqual(navegador.ext_folder(), navegador.EXT_SRC)
        with mock.patch.object(paths, "FROZEN", True):
            if os.path.isdir(navegador.EXT_COPY):
                import shutil
                shutil.rmtree(navegador.EXT_COPY)
            self.assertEqual(navegador.ext_folder(), navegador.EXT_COPY)
            self.assertTrue(os.path.isfile(os.path.join(navegador.EXT_COPY, "sw.js")))
        with mock.patch.object(navegador.winapi, "open_folder") as of:
            st, _, d = call("POST", "/api/local/navegador", {"op": "folder"})
            self.assertTrue(d["folder_ok"])
            of.assert_called_once_with(navegador.EXT_SRC)
        st, _, d = call("POST", "/api/local/navegador", {"op": "x"})
        self.assertEqual(st, 400)

    def test_portas_iguais_as_do_programa(self):
        with open(os.path.join(apoio.ROOT, "extensao", "ponte.js"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("var PORTS = [%s];" % ", ".join(str(p) for p in paths.PORTS), src)


class AcaoEBlocoTest(Base):
    def test_validacao(self):
        ok = [{"type": "browser", "op": "tab_next"}, {"type": "browser", "op": "scroll", "dir": "top"},
              {"type": "browser", "op": "open_url", "url": "https://youtube.com"}]
        for a in ok:
            actions.validate(a, 1, "B")
        for a in ({"type": "browser", "op": "nada"}, {"type": "browser"},
                  {"type": "browser", "op": "open_url", "url": "ftp://x"},
                  {"type": "browser", "op": "open_url"}, {"type": "browser", "op": "activate", "tab": 1}):
            with self.assertRaises(ValueError):
                actions.validate(a, 1, "B")

    def test_acao_pelo_botao(self):
        actions.run({"type": "browser", "op": "back"})
        self.assertEqual(apoio.KEYS, [("keys", ["alt", "left"])])

    def test_bloco_navegador_no_schema(self):
        cfg = apoio.base_config()
        cfg["pages"][0]["buttons"].append({"kind": "browser", "label": "Abas", "icon": "globe"})
        cfg["pages"][0]["buttons"][3]["buttons"].append({"kind": "browser"})
        schema.validate_config(cfg)

    def test_modelo_navegador(self):
        from streamdeck import templates
        t = [x for x in templates.templates() if x["id"] == "navegador"][0]
        cfg = apoio.base_config()
        cfg["pages"] = [dict(t["page"], id="c3c3")]
        schema.validate_config(cfg)
        self.assertTrue(any(b.get("kind") == "browser" for b in t["page"]["buttons"]))


if __name__ == "__main__":
    unittest.main()
