# -*- coding: utf-8 -*-
"""Historico de copias do config (storage) e rotas /api/local/backups e diag."""
import json
import os
import shutil
import time
import unittest
from unittest import mock

import apoio
from streamdeck import storage
from test_http import Servidor, call


class Relogio(object):
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _cfg(title):
    c = apoio.base_config()
    c["title"] = title
    return c


class BackupsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with apoio.quiet():
            Servidor.start()

    def setUp(self):
        self._q = apoio.quiet()
        self._q.__enter__()
        shutil.rmtree(storage.backups_dir(), True)
        storage._LAST["t"] = None
        self.clock = Relogio(time.time())
        self._p = mock.patch.object(storage, "_clock", self.clock)
        self._p.start()
        apoio.write_config(_cfg("inicio"))

    def tearDown(self):
        self._p.stop()
        storage._LAST["t"] = None
        self._q.__exit__(None, None, None)

    def names(self):
        return storage._backup_names()

    def test_regra_dos_10_minutos(self):
        storage.save_config(_cfg("a"))          # primeira: guarda "inicio"
        self.assertEqual(len(self.names()), 1)
        self.assertEqual(storage.read_backup(self.names()[0])["title"], "inicio")
        self.clock.t += 60
        storage.save_config(_cfg("b"))          # rajada do editor: nao guarda
        storage.save_config(_cfg("c"))
        self.assertEqual(len(self.names()), 1)
        self.clock.t += 601
        storage.save_config(_cfg("d"))          # guarda o estado anterior ("c")
        self.assertEqual(len(self.names()), 2)
        self.assertEqual(storage.read_backup(self.names()[0])["title"], "c")

    def test_dedupe(self):
        storage.backup_current()
        storage.backup_current()
        self.assertEqual(len(self.names()), 1)

    def test_limite_20(self):
        for i in range(25):
            storage.save_config(_cfg("v%d" % i), force=True)
        n = self.names()
        self.assertEqual(len(n), storage.BACKUP_KEEP)
        self.assertEqual(storage.read_backup(n[0])["title"], "v23")

    def test_ordem_com_relogio_para_tras(self):
        storage.save_config(_cfg("a"), force=True)    # guarda "inicio"
        self.clock.t -= 86400 * 3
        with mock.patch("time.localtime", lambda t=None: time.gmtime(self.clock.t)):
            storage.save_config(_cfg("b"), force=True)  # guarda "a" com data menor
        n = self.names()
        self.assertEqual(storage.read_backup(n[0])["title"], "a")
        self.assertEqual(storage.read_backup(n[1])["title"], "inicio")

    def test_nomes_antigos_vem_antes(self):
        os.makedirs(storage.backups_dir(), exist_ok=True)
        with open(os.path.join(storage.backups_dir(), "config-29991231-235959.json"), "w") as f:
            json.dump(_cfg("velho"), f)
        storage.save_config(_cfg("a"), force=True)
        n = self.names()
        self.assertEqual(n[1], "config-29991231-235959.json")
        self.assertTrue(n[0].startswith("config-000001-"))

    def test_api_lista_le_restaura(self):
        storage.save_config(_cfg("a"), force=True)    # copia de "inicio"
        st, _, d = call("GET", "/api/local/backups")
        self.assertEqual(st, 200)
        b = d["backups"]
        self.assertEqual(len(b), 1)
        self.assertFalse(b[0]["current"])
        self.assertGreater(b[0]["when"], 0)
        name = b[0]["name"]
        st, _, d = call("GET", "/api/local/backups/" + name)
        self.assertEqual(st, 200)
        self.assertEqual(d["title"], "inicio")
        self.assertEqual(d["version"], 2)
        st, _, d = call("POST", "/api/local/backups/restore", {"name": name})
        self.assertEqual(st, 200)
        self.assertEqual(storage.load_config()["title"], "inicio")
        st, _, d = call("GET", "/api/local/backups")
        cur = [x for x in d["backups"] if x["current"]]
        self.assertEqual(len(cur), 1)
        self.assertEqual(cur[0]["name"], name)
        # o estado de antes de restaurar ("a") ficou guardado
        self.assertEqual(storage.read_backup(d["backups"][0]["name"])["title"], "a")

    def test_nome_invalido_e_inexistente(self):
        st, _, _ = call("GET", "/api/local/backups/..%2Fconfig.json")
        self.assertEqual(st, 400)
        st, _, _ = call("POST", "/api/local/backups/restore", {"name": "x.json"})
        self.assertEqual(st, 400)
        st, _, _ = call("GET", "/api/local/backups/config-000099-20200101-000000.json")
        self.assertEqual(st, 404)

    def test_outro_aparelho_403(self):
        for m, p in (("GET", "/api/local/backups"), ("GET", "/api/local/diag"),
                     ("GET", "/api/local/backups/config-000001-20200101-000000.json")):
            st, _, _ = apoio.fake_request(m, p)
            self.assertEqual(st, 403, p)
        st, _, _ = apoio.fake_request("POST", "/api/local/backups/restore",
                                      headers={"Content-Type": "application/json"}, body=b'{"name":"x"}')
        self.assertEqual(st, 403)

    def test_diag(self):
        st, _, d = call("GET", "/api/local/diag")
        self.assertEqual(st, 200)
        for k in ("version", "python", "platform", "data_dir", "port", "addresses",
                  "uptime_s", "clients", "recent_errors", "log_path", "autostart", "update"):
            self.assertIn(k, d)
        self.assertIsInstance(d["addresses"], list)


if __name__ == "__main__":
    unittest.main()
