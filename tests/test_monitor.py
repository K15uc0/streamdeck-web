# -*- coding: utf-8 -*-
"""Monitor do PC (2.9): coletor de metricas (simulado fora do Windows)."""
import os
import socket
import sys
import time
import unittest

import apoio  # noqa: F401  (antes do pacote)
from streamdeck import monitor

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "lhm.json")


class MonitorTests(unittest.TestCase):
    def test_snapshot_shape(self):
        s = monitor.snapshot()
        self.assertIsInstance(s["cpu"], float)
        self.assertTrue(0 <= s["cpu"] <= 100)
        for k in ("used", "total"):
            self.assertIsInstance(s["mem"][k], int)
        self.assertIsInstance(s["mem"]["pct"], float)
        self.assertTrue(s["disk"])
        d = s["disk"][0]
        self.assertTrue(d["drive"].endswith(":"))
        self.assertIsInstance(d["used"], int)
        self.assertIsInstance(d["total"], int)
        self.assertIsInstance(d["pct"], float)
        self.assertIsInstance(s["net"]["down_bps"], float)
        self.assertIsInstance(s["net"]["up_bps"], float)
        self.assertTrue(s["gpu"] is None or isinstance(s["gpu"], float))
        self.assertEqual(set(s["temps"]), {"cpu", "gpu"})
        self.assertIsInstance(s["ts"], float)

    def test_cpu_delta(self):
        # kernel inclui idle: total = 100, idle = 75 -> 25%
        self.assertEqual(monitor.cpu_pct((0, 0, 0), (75, 100, 0)), 25.0)
        self.assertEqual(monitor.cpu_pct((10, 10, 10), (10, 10, 10)), 0.0)

    def test_net_rate(self):
        self.assertEqual(monitor.rate(1000, 3000, 2.0), 1000.0)
        self.assertEqual(monitor.rate(3000, 1000, 2.0), 0.0)   # contador reiniciou
        self.assertEqual(monitor.rate(0, 10, 0), 0.0)

    def test_lhm_parse(self):
        with open(FIX, encoding="utf-8") as f:
            data = f.read()
        t = monitor.parse_lhm(data)
        self.assertEqual(t, {"cpu": 54.0, "gpu": 61.0})

    def test_lhm_offline_rapido(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        t0 = time.time()
        t = monitor.lhm_temps("http://127.0.0.1:%d/data.json" % port, timeout=0.4)
        self.assertLess(time.time() - t0, 0.6)
        self.assertEqual(t, {"cpu": None, "gpu": None})

    def test_kill_protegidos(self):
        for pid in (0, 4, os.getpid()):
            with self.assertRaises(ValueError):
                monitor.kill(pid)
        # lista simulada (no Windows real o lsass nem aparece para o usuario comum)
        velho = monitor.IS_WINDOWS
        monitor.IS_WINDOWS = False
        try:
            lsass = [p["pid"] for p in monitor.processes(limit=100) if p["name"] == "lsass.exe"]
            self.assertTrue(lsass)
            with self.assertRaises(ValueError):
                monitor.kill(lsass[0])
        finally:
            monitor.IS_WINDOWS = velho
        with self.assertRaises(ValueError):
            monitor.kill(999999)

    def test_processes(self):
        for sort in ("cpu", "mem"):
            ps = monitor.processes(limit=3, sort=sort)
            self.assertLessEqual(len(ps), 3)
            self.assertEqual(set(ps[0]), {"pid", "name", "cpu", "mem"})
            vals = [p[sort] for p in ps]
            self.assertEqual(vals, sorted(vals, reverse=True))

    def test_snapshot_nao_bloqueia_no_lhm(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        old = monitor.LHM_URL
        monitor.LHM_URL = "http://127.0.0.1:%d/data.json" % port
        monitor._STATE["snap"] = None
        try:
            monitor.touch()
            monitor.snapshot()                  # primeira leitura
            t0 = time.time()
            monitor.snapshot()
            self.assertLess(time.time() - t0, 0.05)
        finally:
            monitor.LHM_URL = old

    def test_snapshot_devolve_copia(self):
        a = monitor.snapshot()
        a["mem"]["used"] = -1
        self.assertNotEqual(monitor.snapshot()["mem"]["used"], -1)


@unittest.skipUnless(sys.platform.startswith("win"), "so no Windows")
class MonitorWindowsTests(unittest.TestCase):
    def test_if_row2_tamanho(self):
        w = monitor._win()
        self.assertEqual(w["ctypes"].sizeof(w["IFROW2"]), 1352)

    def test_roda_sem_excecao(self):
        monitor.touch()
        self.assertIn("cpu", monitor.snapshot())
        self.assertTrue(monitor.processes(limit=5))


if __name__ == "__main__":
    unittest.main()
