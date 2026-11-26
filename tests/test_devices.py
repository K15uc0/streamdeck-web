# -*- coding: utf-8 -*-
"""Aparelhos (2.11): arquivo aparelhos.json, chave por aparelho, permissoes,
remocao, ultimo acesso com gravacao limitada e migracao do allow_kill."""
import json
import os
import re
import unittest

import apoio
from streamdeck import devices, paths, storage


def limpar(allow_kill=None):
    """Sem aparelhos e sem a marca de migracao (como uma instalacao antiga)."""
    for p in (paths.DEVICES_PATH, paths.DEVICES_PATH + ".tmp"):
        if os.path.exists(p):
            os.remove(p)
    devices.reset()
    s = storage.load_settings()
    s.pop("allow_kill", None)
    if allow_kill is not None:
        s["allow_kill"] = allow_kill
    storage.save_settings(s)


class DevicesTest(unittest.TestCase):
    def setUp(self):
        self._q = apoio.quiet()
        self._q.__enter__()
        limpar()

    def tearDown(self):
        self._q.__exit__(None, None, None)

    def test_criar_e_achar_pela_chave(self):
        d = devices.create(ua="Mozilla/5.0 (Linux; Android 13)", ip="192.168.0.50")
        self.assertTrue(re.match(r"^[0-9a-f]{32}$", d["key"]))
        self.assertEqual(d["name"], "Android 1")
        self.assertIsNone(d["pages"])
        self.assertIs(d["full"], False)
        self.assertEqual(d["last_ip"], "192.168.0.50")
        achado = devices.find(d["key"])
        self.assertEqual(achado["id"], d["id"])
        self.assertNotIn("key", achado)
        self.assertIsNone(devices.find(d["key"][:-1] + "x"))
        self.assertIsNone(devices.find(""))
        self.assertIsNone(devices.find(None))
        with open(paths.DEVICES_PATH, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["devices"][0]["key"], d["key"])

    def test_nomes_numerados(self):
        a = devices.create(ua="iPhone")
        b = devices.create(ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)")
        c = devices.create(ua="")
        self.assertEqual((a["name"], b["name"], c["name"]), ("iPhone 1", "iPhone 2", "Aparelho 3"))

    def test_lista_sem_chaves(self):
        devices.create()
        devices.create()
        lst = devices.list_public()
        self.assertEqual(len(lst), 2)
        for d in lst:
            self.assertNotIn("key", d)
            self.assertEqual(set(d), {"id", "name", "created", "last_seen", "last_ip", "pages", "full"})
        self.assertNotIn(devices.create()["key"], json.dumps(devices.list_public()))

    def test_renomear(self):
        d = devices.create()
        devices.rename(d["id"], "  Tablet da sala  ")
        self.assertEqual(devices.find(d["key"])["name"], "Tablet da sala")
        for ruim in ("", "   ", "x" * 41, "a\nb", 5, None):
            with self.assertRaises(ValueError):
                devices.rename(d["id"], ruim)
        with self.assertRaises(KeyError):
            devices.rename("naoexiste", "Oi")

    def test_paginas(self):
        d = devices.create()
        devices.set_pages(d["id"], [2, 0, 2])
        self.assertEqual(devices.find(d["key"])["pages"], [0, 2])
        devices.set_pages(d["id"], None)
        self.assertIsNone(devices.find(d["key"])["pages"])
        devices.set_pages(d["id"], [])
        self.assertEqual(devices.find(d["key"])["pages"], [])
        for ruim in ([-1], [50], ["1"], [True], "0", {"a": 1}):
            with self.assertRaises(ValueError):
                devices.set_pages(d["id"], ruim)

    def test_controle_total(self):
        d = devices.create()
        devices.set_full(d["id"], True)
        self.assertIs(devices.find(d["key"])["full"], True)
        with self.assertRaises(ValueError):
            devices.set_full(d["id"], "sim")

    def test_remover_corta_na_hora(self):
        d = devices.create()
        self.assertTrue(devices.remove(d["id"]))
        self.assertIsNone(devices.find(d["key"]))
        self.assertFalse(devices.remove(d["id"]))
        devices.reset()      # relendo do disco tambem nao volta
        self.assertIsNone(devices.find(d["key"]))

    def test_ultimo_acesso_gravado_no_maximo_a_cada_60s(self):
        d = devices.create(ip="1.1.1.1")
        t = [1000.0]
        orig = devices._now
        devices._now = lambda: t[0]
        gravou = []
        orig_save = devices._save
        devices._save = lambda data: (gravou.append(1), orig_save(data))
        try:
            devices.touch(d["id"], "1.1.1.1")
            n0 = len(gravou)
            t[0] += 10
            devices.touch(d["id"], "1.1.1.1")
            self.assertEqual(len(gravou), n0)                      # nao gravou
            self.assertEqual(devices.find(d["key"])["last_seen"], 1010)   # mas a memoria sabe
            t[0] += 61
            devices.touch(d["id"], "1.1.1.1")
            self.assertEqual(len(gravou), n0 + 1)
        finally:
            devices._now = orig
            devices._save = orig_save

    def test_arquivo_atomico_sem_tmp(self):
        devices.create()
        self.assertFalse(os.path.exists(paths.DEVICES_PATH + ".tmp"))

    def test_arquivo_quebrado_nao_sobrescreve(self):
        with open(paths.DEVICES_PATH, "w") as f:
            f.write("{quebrado")
        devices.reset()
        self.assertIsNone(devices.find("0" * 32))
        with self.assertRaises(devices.DevicesError):
            devices.create()
        with open(paths.DEVICES_PATH) as f:
            self.assertEqual(f.read(), "{quebrado")

    def test_limite_de_aparelhos(self):
        for _ in range(devices.MAX_DEVICES):
            devices.create()
        with self.assertRaises(devices.DevicesError):
            devices.create()

    def test_migracao_allow_kill_ligado(self):
        limpar(allow_kill=True)
        devices.migrate()
        self.assertNotIn("allow_kill", storage.load_settings())
        # aparelhos que ja existiam (cookie antigo) ganham controle total
        d = devices.upgrade("192.168.0.9", "Android")
        self.assertIs(d["full"], True)
        # aparelho novo (QR) nao
        self.assertIs(devices.create()["full"], False)

    def test_migracao_automatica_no_primeiro_upgrade(self):
        limpar(allow_kill=True)
        self.assertIs(devices.upgrade("192.168.0.9", "Android")["full"], True)
        self.assertNotIn("allow_kill", storage.load_settings())

    def test_migracao_allow_kill_desligado(self):
        limpar(allow_kill=False)
        devices.migrate()
        self.assertNotIn("allow_kill", storage.load_settings())
        self.assertIs(devices.upgrade("192.168.0.9", "Android")["full"], False)

    def test_migracao_so_uma_vez(self):
        limpar(allow_kill=False)
        devices.migrate()
        storage.save_settings(dict(storage.load_settings(), allow_kill=True))
        devices.migrate()
        self.assertIs(devices.upgrade("192.168.0.9", "Android")["full"], False)

    def test_upgrade_reaproveita_o_mesmo_aparelho(self):
        a = devices.upgrade("192.168.0.9", "Android")
        b = devices.upgrade("192.168.0.9", "Android")
        c = devices.upgrade("192.168.0.10", "Android")
        self.assertEqual(a["key"], b["key"])
        self.assertNotEqual(a["key"], c["key"])
        devices.remove(a["id"])
        d = devices.upgrade("192.168.0.9", "Android")
        self.assertNotEqual(d["key"], a["key"])

    def test_pode_pagina_e_sensivel(self):
        self.assertTrue(devices.page_allowed(None, 3))
        self.assertTrue(devices.page_allowed([1, 3], 3))
        self.assertFalse(devices.page_allowed([1], 3))
        self.assertFalse(devices.page_allowed([], 0))
        sens = devices.sensitive
        self.assertTrue(sens({"type": "command", "command": "shutdown /s /t 0"}))
        self.assertFalse(sens({"type": "open", "target": "C:\\x.exe"}))
        self.assertTrue(sens({"type": "command", "command": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"}))
        self.assertFalse(sens({"type": "command", "command": "rundll32.exe user32.dll,LockWorkStation"}))
        self.assertFalse(sens({"type": "open", "target": "https://exemplo.com"}))
        self.assertFalse(sens({"type": "app", "target": "obs64.exe"}))
        self.assertFalse(sens({"type": "hotkey", "keys": ["f5"]}))
        self.assertFalse(sens(None))
        self.assertTrue(sens({"type": "multi", "steps": [{"type": "hotkey"}, {"type": "command", "command": "shutdown /r /t 0"}]}))
        self.assertFalse(sens({"type": "multi", "steps": [{"type": "hotkey"}]}))


if __name__ == "__main__":
    unittest.main()
