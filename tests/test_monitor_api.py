# -*- coding: utf-8 -*-
"""API do monitor e das IAs: /api/state (pc, ia), /api/monitor, kill com permissao,
ajustes locais e o esquema (live novos, kind monitor)."""
import copy
import json
import unittest

import apoio
from streamdeck import httpd, monitor, schema, security, state, storage
from test_http import call


def remoto(method, path, body=None):
    tok = storage.token()
    sep = "&" if "?" in path else "?"
    data = json.dumps(body).encode("utf-8") if body is not None else b""
    return apoio.fake_request(method, "%s%sk=%s" % (path, sep, tok), body=data,
                              headers={"Content-Type": "application/json"})


class MonitorApiTest(unittest.TestCase):
    def setUp(self):
        self._q = apoio.quiet()
        self._q.__enter__()
        apoio.write_config(apoio.base_config())
        state._TOGGLES.clear()
        security.FAILS.clear()
        httpd._IA_CACHE.update(t=0.0, val=None)
        s = storage.load_settings()
        s.pop("allow_kill", None)
        storage.save_settings(s)

    def tearDown(self):
        self._q.__exit__(None, None, None)

    def test_state_ocioso_nao_ativa_monitor(self):
        monitor._STATE["polled"] = 0.0
        st, _, r = call("GET", "/api/state")
        self.assertEqual(st, 200)
        self.assertNotIn("pc", r)
        self.assertNotIn("ia", r)
        self.assertFalse(monitor._active())

    def test_state_pc_rapido_sem_prime(self):
        import time
        orig = (monitor._prime, monitor._refresh)
        chamados = []
        monitor._prime = lambda: chamados.append("prime")
        monitor._refresh = lambda *a: chamados.append("refresh")
        monitor._STATE["snap"] = None
        try:
            t0 = time.time()
            st, _, r = call("GET", "/api/state?pc=1")
            dt = time.time() - t0
        finally:
            monitor._prime, monitor._refresh = orig
        self.assertEqual(st, 200)
        self.assertIn("cpu", r["pc"])
        self.assertEqual(chamados, [])
        self.assertLess(dt, 1.0)
        self.assertTrue(monitor._active())

    def test_kill_pai_protegido(self):
        import os
        orig = monitor.SIM_PROCS
        monitor.SIM_PROCS = orig + [{"pid": os.getppid() + 100000, "name": "x.exe", "cpu": 0, "mem": 0},
                                    {"pid": os.getppid(), "name": "pai.exe", "cpu": 0, "mem": 0}]
        try:
            with self.assertRaises(ValueError):
                monitor.kill(os.getppid())
            for nome in ("dwm.exe", "svchost.exe", "Registry", "MsMpEng.exe", "fontdrvhost.exe",
                         "sihost.exe", "ctfmon.exe"):
                monitor.SIM_PROCS = orig + [{"pid": 777, "name": nome, "cpu": 0, "mem": 0}]
                with self.assertRaises(ValueError):
                    monitor.kill(777)
        finally:
            monitor.SIM_PROCS = orig

    def test_kill_remoto_protegido_400(self):
        storage.save_settings(dict(storage.load_settings(), allow_kill=True))
        st, _, _ = remoto("POST", "/api/monitor/kill", {"pid": 4})
        self.assertEqual(st, 400)

    def test_kill_sem_cabecalho_403(self):
        st, _, _ = apoio.fake_request("POST", "/api/monitor/kill", headers={"X-StreamDeck": None},
                                      body=b'{"pid":1200}')
        self.assertEqual(st, 403)

    def test_kill_erro_inesperado_500(self):
        orig = monitor.kill
        def boom(pid):
            raise RuntimeError("segredo interno")
        monitor.kill = boom
        try:
            st, _, r = call("POST", "/api/monitor/kill", {"pid": 1200})
        finally:
            monitor.kill = orig
        self.assertEqual(st, 500)
        self.assertEqual(r["error"], "falha ao encerrar")

    def test_settings_kill_remoto_nao_altera(self):
        remoto("POST", "/api/local/settings_kill", {"allow": True})
        self.assertIsNot(storage.load_settings().get("allow_kill"), True)

    def test_state_traz_pc_e_ia(self):
        st, _, r = call("GET", "/api/state?pc=1&ia=1")
        self.assertEqual(st, 200)
        for k in ("cpu", "mem_pct", "gpu", "temp_cpu", "down_bps", "up_bps"):
            self.assertIn(k, r["pc"])
        self.assertEqual(set(r["ia"]), {"claude", "codex", "grok"})

    def test_ia_em_cache(self):
        from streamdeck import ia
        n = []
        orig = ia.status
        ia.status = lambda *a, **k: n.append(1) or {"claude": None, "codex": None, "grok": None}
        try:
            call("GET", "/api/state?ia=1")
            call("GET", "/api/state?ia=1")
        finally:
            ia.status = orig
        self.assertEqual(len(n), 1)

    def test_monitor_formato(self):
        st, _, r = call("GET", "/api/monitor?sort=mem")
        self.assertEqual(st, 200)
        self.assertTrue(r["ok"])
        self.assertIn("cpu", r["snapshot"])
        mems = [p["mem"] for p in r["processes"]]
        self.assertEqual(mems, sorted(mems, reverse=True))
        self.assertTrue(r["processes"])

    def test_kill_remoto_recusado_por_padrao(self):
        st, _, body = remoto("POST", "/api/monitor/kill", {"pid": 1200})
        self.assertEqual(st, 403)

    def test_kill_remoto_permitido(self):
        storage.save_settings(dict(storage.load_settings(), allow_kill=True))
        st, _, body = remoto("POST", "/api/monitor/kill", {"pid": 1200})
        self.assertEqual(st, 200)

    def test_kill_remoto_sem_codigo(self):
        storage.save_settings(dict(storage.load_settings(), allow_kill=True))
        st, _, _ = apoio.fake_request("POST", "/api/monitor/kill", body=b'{"pid":1200}')
        self.assertEqual(st, 403)

    def test_kill_local_sempre(self):
        st, _, r = call("POST", "/api/monitor/kill", {"pid": 1200})
        self.assertEqual((st, r["ok"]), (200, True))

    def test_kill_protegido_ou_invalido(self):
        for pid in (4, 999999, "x"):
            st, _, r = call("POST", "/api/monitor/kill", {"pid": pid})
            self.assertEqual(st, 400, pid)
            self.assertFalse(r["ok"])

    def test_settings_kill_so_local(self):
        st, _, r = call("POST", "/api/local/settings_kill", {"allow": True})
        self.assertEqual((st, r["allow_kill"]), (200, True))
        self.assertIs(storage.load_settings()["allow_kill"], True)
        st, _, _ = remoto("POST", "/api/local/settings_kill", {"allow": False})
        self.assertEqual(st, 403)
        st, _, _ = call("POST", "/api/local/settings_kill", {"allow": "sim"})
        self.assertEqual(st, 400)

    def test_ia_local(self):
        st, _, r = call("GET", "/api/local/ia")
        self.assertEqual(st, 200)
        for k in ("bridge_installed", "claude_updated", "codex_found"):
            self.assertIn(k, r)
        st, _, _ = remoto("GET", "/api/local/ia")
        self.assertEqual(st, 403)
        st, _, _ = call("POST", "/api/local/ia", {"install": "x"})
        self.assertEqual(st, 400)


class EsquemaMonitorTest(unittest.TestCase):
    def _cfg(self, btn):
        cfg = apoio.base_config()
        cfg["pages"][1]["buttons"].append(btn)
        return cfg

    def test_live_novos(self):
        for v in ("pc:cpu", "pc:mem", "pc:gpu", "pc:temp_cpu", "pc:temp_gpu", "pc:net", "pc:disk:C",
                  "ia:claude:5h", "ia:claude:week", "ia:codex:5h", "ia:codex:week"):
            schema.validate_config(self._cfg({"label": "x", "live": v}))

    def test_live_invalidos(self):
        for v in ("pc:disk:C\n", "pc:disk:CC", "pc:disk:c", "pc:disk:", "pc:disk:1", "pc:xyz", "ia:grok:5h"):
            with self.assertRaises(ValueError):
                schema.validate_config(self._cfg({"label": "x", "live": v}))

    def test_kind_monitor(self):
        schema.validate_config(self._cfg({"kind": "monitor", "label": "PC", "icon": "chart", "w": 2, "h": 2}))
        cfg = self._cfg({"kind": "folder", "label": "P", "buttons": [{"kind": "monitor"}]})
        schema.validate_config(cfg)
        with self.assertRaises(ValueError):
            schema.validate_config(self._cfg({"kind": "monitor", "w": 9}))


if __name__ == "__main__":
    unittest.main()
