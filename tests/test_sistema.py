# -*- coding: utf-8 -*-
"""Monitor do PC: calculos puros, amostrador com backend falso e a API."""
import json
import unittest

import apoio  # noqa: F401  (antes do pacote)
from streamdeck import agenda, schema, sistema


class Puras(unittest.TestCase):
    def test_cpu_percent(self):
        prev = [(100, 1000), (50, 1000)]
        cur = [(150, 1100), (50, 1100)]   # nucleo 0: 50/100, nucleo 1: 0/100
        total, cores = sistema.cpu_percent(prev, cur)
        self.assertEqual(cores, [50.0, 0.0])
        self.assertEqual(total, 25.0)
        self.assertEqual(sistema.cpu_percent(None, cur), (None, []))
        self.assertEqual(sistema.cpu_percent(prev, cur[:1]), (None, []))   # numero de nucleos mudou
        self.assertEqual(sistema.cpu_percent([(0, 0)], [(0, 0)]), (0.0, [0.0]))

    def test_rate(self):
        self.assertEqual(sistema.rate(1000, 3000, 2.0), 1000.0)
        self.assertIsNone(sistema.rate(None, 3000, 2.0))
        self.assertIsNone(sistema.rate(5000, 3000, 2.0))   # contador reiniciou
        self.assertIsNone(sistema.rate(1000, 3000, 0))

    def test_gpu_engines(self):
        items = [("pid_1_luid_0x0_0x1_phys_0_eng_0_engtype_3D", 30.0),
                 ("pid_2_luid_0x0_0x1_phys_0_eng_0_engtype_3D", 25.5),
                 ("pid_2_luid_0x0_0x1_phys_0_eng_3_engtype_VideoDecode", 70.0),
                 ("pid_3_luid_0x0_0x2_phys_0_eng_0_engtype_3D", None)]
        self.assertEqual(sistema.gpu_from_engines(items), 70.0)
        self.assertEqual(sistema.gpu_from_engines(items[:2]), 55.5)
        self.assertIsNone(sistema.gpu_from_engines([]))
        self.assertEqual(sistema.gpu_from_engines([("x", 80.0), ("x", 60.0)]), 100.0)

    def test_human_bytes(self):
        self.assertEqual(sistema.human_bytes(None), "--")
        self.assertEqual(sistema.human_bytes(512), "512 B")
        self.assertEqual(sistema.human_bytes(1536), "1,5 KB")
        self.assertEqual(sistema.human_bytes(50 * 1024 * 1024), "50 MB")


class Falso(object):
    """Backend de mentira: CPU sobe 40% por amostra, rede 1000 B a cada leitura."""
    cpu_name = "CPU Teste"
    gpu_name = "GPU Teste"
    gpu_total = 4 * 1024 ** 3

    def __init__(self):
        self.n = 0

    def cpu_times(self):
        self.n += 1
        return [(40 * self.n, 100 * self.n), (0, 100 * self.n)]

    def memory(self):
        return 8 * 1024 ** 3, 2 * 1024 ** 3

    def counters(self):
        return {"rx": 1000 * self.n, "tx": 0, "dr": None, "dw": None}

    def rates(self):
        return {"gpu": 12.5, "vram": 1024 ** 3, "didle": 90.0}

    def disks(self):
        return [{"name": "C:", "total": 100, "used": 25}]

    def uptime(self):
        return 3600

    def battery(self):
        raise OSError("sem bateria")   # uma fonte com erro nao derruba as outras


class Amostrador(unittest.TestCase):
    def test_sample(self):
        m = sistema.Monitor(Falso())
        self.assertIsNone(m.compact())
        m.sample()
        self.assertIsNone(m.snap)          # primeira leitura so e base
        s = m.sample()
        self.assertEqual(s["cpu"]["pct"], 20.0)
        self.assertEqual(s["cpu"]["cores"], [40.0, 0.0])
        self.assertEqual(s["cpu"]["name"], "CPU Teste")
        self.assertEqual(s["ram"]["pct"], 25.0)
        self.assertEqual(s["gpu"]["pct"], 12.5)
        self.assertEqual(s["gpu"]["mem_total"], 4 * 1024 ** 3)
        self.assertEqual(s["disk"]["busy"], 10.0)
        self.assertEqual(s["disk"]["drives"][0]["pct"], 25.0)
        self.assertIsNotNone(s["net"]["rx"])
        self.assertIsNone(s["disk"]["read"])
        self.assertIsNone(s["battery"])
        self.assertEqual(s["uptime"], 3600)
        self.assertEqual(len(m.hist["cpu"]), 1)
        c = m.compact()
        self.assertEqual((c["cpu"], c["ram"], c["gpu"], c["disk"]), (20.0, 25.0, 12.5, 10.0))

    def test_full_sem_amostra(self):
        m = sistema.Monitor(Falso())
        out = m.full()
        self.assertTrue(out["ok"])
        self.assertEqual(out["hist"]["cpu"], [20.0])
        self.assertEqual(set(out["hist"]), set(sistema.HIST_KEYS))

    def test_historico_limitado(self):
        m = sistema.Monitor(Falso())
        for _ in range(sistema.HIST + 10):
            m.sample()
        self.assertEqual(len(m.hist["cpu"]), sistema.HIST)

    def test_backend_real(self):
        # Linux nos testes (/proc); no Windows, ctypes. Nao pode levantar erro.
        m = sistema.Monitor()
        m.sample()
        s = m.sample()
        self.assertIsNotNone(s)
        self.assertIn("cpu", s)


class Config(unittest.TestCase):
    def test_live_e_acao(self):
        cfg = apoio.base_config()
        b = cfg["pages"][0]["buttons"]
        b[1]["live"] = "sys:cpu"
        b[2]["action"] = {"type": "monitor"}
        schema.validate_config(cfg)
        b[1]["live"] = "sys:temperatura"
        with self.assertRaises(ValueError):
            schema.validate_config(cfg)

    def test_agendamento_nao_abre_monitor(self):
        cfg = apoio.base_config()
        cfg["schedules"] = [{"id": "a1", "name": "x", "enabled": True,
                             "when": {"type": "daily", "time": "08:00"}, "action": {"type": "monitor"}}]
        with self.assertRaises(ValueError):
            agenda.validate(cfg["schedules"], 2)


class Api(unittest.TestCase):
    def setUp(self):
        apoio.write_config(apoio.base_config())
        self._old = sistema.MONITOR
        sistema.MONITOR = sistema.Monitor(Falso())

    def tearDown(self):
        sistema.MONITOR.stop()
        sistema.MONITOR = self._old

    def test_api_sys(self):
        with apoio.quiet():
            st, _h, out = apoio.fake_request("GET", "/api/sys", ip="127.0.0.1")
        self.assertEqual(st, 200)
        js = json.loads(out.decode("utf-8"))
        self.assertTrue(js["ok"])
        self.assertIn("hist", js)
        self.assertIn("name", js)
        self.assertEqual(js["ram"]["pct"], 25.0)

    def test_state_sys(self):
        with apoio.quiet():
            _st, _h, out = apoio.fake_request("GET", "/api/state", ip="127.0.0.1")
        self.assertNotIn("sys", json.loads(out.decode("utf-8")))
        sistema.MONITOR.sample()
        sistema.MONITOR.sample()
        with apoio.quiet():
            _st, _h, out = apoio.fake_request("GET", "/api/state?sys=1", ip="127.0.0.1")
        self.assertEqual(json.loads(out.decode("utf-8"))["sys"]["ram"], 25.0)


if __name__ == "__main__":
    unittest.main()
