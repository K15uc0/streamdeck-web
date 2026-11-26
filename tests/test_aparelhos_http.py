# -*- coding: utf-8 -*-
"""Aparelhos (2.11) pela API: primeiro acesso cria o aparelho, cookie antigo
vira chave nova, aparelho removido perde o acesso, paginas liberadas,
Controle total para acoes sensiveis, PC sempre pode e lista sem chaves."""
import json
import os
import re
import unittest

import apoio
from streamdeck import devices, monitor, paths, security, state, storage
from test_http import Servidor, call

IP = "192.168.0.77"
UA = "Mozilla/5.0 (Linux; Android 13) Teste"


def cookie_de(h):
    m = re.search(r"sdk=([^;]*)", h.get("set-cookie", ""))
    return m.group(1) if m else None


def pedir(method, path, key=None, ip=IP, body=None, headers=None):
    hd = {"User-Agent": UA}
    if key is not None:
        hd["Cookie"] = "sdk=" + key
    if body is not None:
        hd["Content-Type"] = "application/json"
    hd.update(headers or {})
    data = json.dumps(body).encode("utf-8") if body is not None else b""
    st, h, payload = apoio.fake_request(method, path, ip=ip, headers=hd, body=data)
    try:
        payload = json.loads(payload.decode("utf-8"))
    except ValueError:
        pass
    return st, h, payload


def config_teste():
    cfg = apoio.base_config()
    cfg["pages"][0]["buttons"].append(
        {"label": "Desligar", "action": {"type": "command", "command": "shutdown /s /t 0"}})
    cfg["pages"][0]["buttons"].append(
        {"label": "Site", "action": {"type": "open", "target": "https://exemplo.com"}})
    return cfg


SHUTDOWN_B = 6
SITE_B = 7


class AparelhosHttpTest(unittest.TestCase):
    def setUp(self):
        self._q = apoio.quiet()
        self._q.__enter__()
        Servidor.start()
        apoio.write_config(config_teste())
        state._TOGGLES.clear()
        security.FAILS.clear()
        for p in (paths.DEVICES_PATH,):
            if os.path.exists(p):
                os.remove(p)
        devices.reset()
        s = storage.load_settings()
        s.pop("allow_kill", None)
        storage.save_settings(s)

    def tearDown(self):
        self._q.__exit__(None, None, None)

    def novo(self, ip=IP):
        st, h, _ = pedir("GET", "/?k=" + storage.token(), ip=ip)
        self.assertEqual(st, 302)
        return cookie_de(h)

    # ------------------------------------------------------ primeiro acesso ---
    def test_primeiro_acesso_cria_aparelho_e_cookie(self):
        st, h, _ = pedir("GET", "/?k=" + storage.token() + "&sync=abc")
        self.assertEqual(st, 302)
        self.assertEqual(h["location"], "/#sync=abc")
        key = cookie_de(h)
        self.assertTrue(re.match(r"^[0-9a-f]{32}$", key))
        self.assertNotEqual(key, storage.token())
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(flag, h["set-cookie"])
        lst = devices.list_public()
        self.assertEqual(len(lst), 1)
        self.assertEqual(lst[0]["last_ip"], IP)
        st, _, r = pedir("GET", "/api/state", key)
        self.assertEqual(st, 200)
        self.assertEqual(r["device"], {"name": lst[0]["name"], "pages": None, "full": False})
        self.assertNotIn("set-cookie", pedir("GET", "/api/state", key)[1])

    def test_primeiro_acesso_de_novo_reaproveita_o_aparelho(self):
        key = self.novo()
        st, h, _ = pedir("GET", "/?k=" + storage.token(), key)
        self.assertEqual(cookie_de(h), key)
        self.assertEqual(len(devices.list_public()), 1)

    def test_primeiro_acesso_codigo_errado(self):
        st, _, _ = pedir("GET", "/?k=errado")
        self.assertEqual(st, 403)
        self.assertEqual(devices.list_public(), [])
        self.assertEqual(len(security.FAILS.get(IP, [])), 1)

    def test_chave_nao_vale_no_endereco(self):
        key = self.novo()
        st, _, _ = pedir("GET", "/api/state?k=" + key)
        self.assertEqual(st, 403)
        st, _, _ = pedir("GET", "/?k=" + key)
        self.assertEqual(st, 403)

    def test_chave_errada_conta_tentativa(self):
        self.novo()
        st, _, _ = pedir("GET", "/api/state", "0" * 32)
        self.assertEqual(st, 403)
        self.assertEqual(len(security.FAILS.get(IP, [])), 1)

    # --------------------------------------------------------- cookie antigo ---
    def test_cookie_antigo_vira_chave_nova_no_mesmo_pedido(self):
        st, h, r = pedir("GET", "/api/state", storage.token())
        self.assertEqual(st, 200)
        self.assertTrue(r["ok"])
        key = cookie_de(h)
        self.assertTrue(re.match(r"^[0-9a-f]{32}$", key))
        self.assertIn("HttpOnly", h["set-cookie"])
        self.assertEqual(len(devices.list_public()), 1)
        # pedidos juntos com o cookie antigo: o mesmo aparelho
        st, h2, _ = pedir("GET", "/api/config", storage.token())
        self.assertEqual((st, cookie_de(h2)), (200, key))
        self.assertEqual(len(devices.list_public()), 1)
        # e a chave nova funciona
        self.assertEqual(pedir("GET", "/api/state", key)[0], 200)

    def test_cookie_antigo_em_post(self):
        st, h, _ = pedir("POST", "/api/tabs", storage.token(), body=[])
        self.assertEqual(st, 200)
        self.assertTrue(cookie_de(h))

    def test_cookie_antigo_em_imagem(self):
        os.makedirs(paths.IMAGES_DIR, exist_ok=True)
        with open(os.path.join(paths.IMAGES_DIR, "ap.png"), "wb") as f:
            f.write(apoio.PNG)
        st, h, _ = pedir("GET", "/img/ap.png", storage.token())
        self.assertEqual(st, 200)
        self.assertTrue(cookie_de(h))

    def test_codigo_trocado_cookie_antigo_cai_aparelho_continua(self):
        key = self.novo()
        velho = storage.token()
        try:
            call("POST", "/api/local/newcode", {})
            self.assertEqual(pedir("GET", "/api/state", velho, ip="192.168.0.78")[0], 403)
            self.assertEqual(pedir("GET", "/api/state", key)[0], 200)
        finally:
            security.FAILS.clear()

    # --------------------------------------------------------------- remover ---
    def test_aparelho_removido_403_na_hora(self):
        key = self.novo()
        self.assertEqual(pedir("GET", "/api/state", key)[0], 200)
        dev = devices.list_public()[0]
        st, _, r = call("POST", "/api/local/devices", {"id": dev["id"], "op": "remove"})
        self.assertEqual((st, r["ok"]), (200, True))
        st, _, r = pedir("GET", "/api/state", key)
        self.assertEqual(st, 403)
        self.assertEqual(r["error"], "codigo de acesso invalido")
        self.assertEqual(pedir("GET", "/api/press?p=0&b=1", key)[0], 403)

    # --------------------------------------------------------------- paginas ---
    def test_pagina_nao_liberada_403(self):
        key = self.novo()
        dev = devices.list_public()[0]
        call("POST", "/api/local/devices", {"id": dev["id"], "op": "pages", "value": [0]})
        st, _, r = pedir("GET", "/api/state", key)
        self.assertEqual(r["device"]["pages"], [0])
        st, h, _ = pedir("GET", "/api/config", key)
        self.assertEqual(h["x-device-pages"], "0")
        self.assertEqual(pedir("GET", "/api/config", self.novo(ip="192.168.0.82"), ip="192.168.0.82")[1]
                         ["x-device-pages"], "*")
        st, _, r = pedir("GET", "/api/press?p=1&b=0", key)
        self.assertEqual(st, 403)
        self.assertIn("pagina", r["error"])
        self.assertEqual(r["reason"], "page")
        st, _, r = pedir("GET", "/api/press?p=0&b=1", key)
        self.assertEqual(st, 200, r)
        # 403 de pagina nao conta como codigo errado
        self.assertEqual(security.FAILS.get(IP, []), [])

    def test_pagina_limitada_pasta(self):
        key = self.novo()
        dev = devices.list_public()[0]
        call("POST", "/api/local/devices", {"id": dev["id"], "op": "pages", "value": [1]})
        self.assertEqual(pedir("GET", "/api/press?p=0&b=3&f=1", key)[0], 403)

    # -------------------------------------------------------- controle total ---
    def test_acao_sensivel_sem_controle_total_403(self):
        key = self.novo()
        st, _, r = pedir("GET", "/api/press?p=0&b=%d" % SHUTDOWN_B, key)
        self.assertEqual(st, 403)
        self.assertIn("Controle total", r["error"])
        self.assertEqual(r["reason"], "full")
        # site (http) nao e sensivel
        self.assertEqual(pedir("GET", "/api/press?p=0&b=%d" % SITE_B, key)[0], 200)

    def test_acao_sensivel_com_controle_total(self):
        key = self.novo()
        dev = devices.list_public()[0]
        call("POST", "/api/local/devices", {"id": dev["id"], "op": "full", "value": True})
        st, _, r = pedir("GET", "/api/press?p=0&b=%d" % SHUTDOWN_B, key)
        self.assertEqual(st, 200, r)

    def test_codigo_geral_no_endereco_nao_tem_controle_total(self):
        st, _, _ = pedir("GET", "/api/press?p=0&b=%d&k=%s" % (SHUTDOWN_B, storage.token()))
        self.assertEqual(st, 403)

    def test_encerrar_processo_exige_controle_total(self):
        key = self.novo()
        st, _, r = pedir("GET", "/api/monitor", key)
        self.assertIs(r["allow_kill"], False)
        self.assertEqual(pedir("POST", "/api/monitor/kill", key, body={"pid": 1200})[0], 403)
        dev = devices.list_public()[0]
        call("POST", "/api/local/devices", {"id": dev["id"], "op": "full", "value": True})
        st, _, r = pedir("GET", "/api/monitor", key)
        self.assertIs(r["allow_kill"], True)
        st, _, r = pedir("POST", "/api/monitor/kill", key, body={"pid": 1200})
        self.assertEqual(st, 200, r)

    def test_pc_local_sempre_pode(self):
        st, _, r = call("GET", "/api/press?p=0&b=%d" % SHUTDOWN_B)
        self.assertEqual(st, 200, r)
        st, _, r = call("GET", "/api/press?p=1&b=0")
        self.assertEqual(st, 200, r)
        st, _, r = call("GET", "/api/state")
        self.assertEqual(r["device"], {"name": "Este PC", "pages": None, "full": True})
        self.assertEqual(call("POST", "/api/monitor/kill", {"pid": 1200})[0], 200)
        self.assertEqual(devices.list_public(), [])

    # -------------------------------------------------------- lista (no PC) ---
    def test_lista_sem_chaves(self):
        k1 = self.novo()
        k2 = self.novo(ip="192.168.0.79")
        st, _, raw = call("GET", "/api/local/devices", raw=True)
        self.assertEqual(st, 200)
        text = raw.decode("utf-8")
        self.assertNotIn(k1, text)
        self.assertNotIn(k2, text)
        self.assertNotIn(storage.token(), text)
        r = json.loads(text)
        self.assertEqual(len(r["devices"]), 2)
        for d in r["devices"]:
            self.assertNotIn("key", d)
        self.assertEqual([p["name"] for p in r["pages"]], ["Um", "Dois"])

    def test_lista_e_alteracoes_so_no_pc(self):
        key = self.novo()
        dev = devices.list_public()[0]
        self.assertEqual(pedir("GET", "/api/local/devices", key)[0], 403)
        st, _, _ = pedir("POST", "/api/local/devices", key, body={"id": dev["id"], "op": "full", "value": True})
        self.assertEqual(st, 403)
        self.assertIs(devices.get(dev["id"])["full"], False)

    def test_alteracoes(self):
        self.novo()
        dev = devices.list_public()[0]
        st, _, r = call("POST", "/api/local/devices", {"id": dev["id"], "op": "rename", "value": "Tablet"})
        self.assertEqual((st, r["device"]["name"]), (200, "Tablet"))
        self.assertNotIn("key", r["device"])
        for body in ({"id": dev["id"], "op": "rename", "value": ""},
                     {"id": dev["id"], "op": "pages", "value": [-1]},
                     {"id": dev["id"], "op": "full", "value": "sim"},
                     {"id": dev["id"], "op": "explodir"}):
            self.assertEqual(call("POST", "/api/local/devices", body)[0], 400, body)
        self.assertEqual(call("POST", "/api/local/devices", {"id": "nada", "op": "remove"})[0], 404)

    def test_info_remota_sem_codigo(self):
        key = self.novo()
        st, _, raw = pedir("GET", "/api/info", key)
        self.assertEqual(st, 200)
        self.assertNotIn("code", raw)
        self.assertNotIn(storage.token(), json.dumps(raw))
        self.assertNotIn(key, json.dumps(raw))
        self.assertEqual(call("GET", "/api/info")[2]["code"], storage.token())

    # --------------------------------------------------------------- migracao ---
    def test_migracao_allow_kill(self):
        storage.save_settings(dict(storage.load_settings(), allow_kill=True))
        st, h, _ = pedir("GET", "/api/state", storage.token())
        self.assertEqual(st, 200)
        key = cookie_de(h)
        self.assertNotIn("allow_kill", storage.load_settings())
        self.assertIs(pedir("GET", "/api/state", key)[2]["device"]["full"], True)
        self.assertEqual(pedir("POST", "/api/monitor/kill", key, body={"pid": 1200})[0], 200)
        # aparelho novo pelo QR nao herda
        k2 = self.novo(ip="192.168.0.81")
        self.assertIs(pedir("GET", "/api/state", k2, ip="192.168.0.81")[2]["device"]["full"], False)

    def test_settings_kill_saiu(self):
        self.assertEqual(call("POST", "/api/local/settings_kill", {"allow": True})[0], 404)


if __name__ == "__main__":
    unittest.main()
