# -*- coding: utf-8 -*-
"""Avisos (2.12): fila e since, regras (IA, temperatura, CPU, OBS),
ajustes por tipo e entrega pelo /api/state (Windows so para Controle total)."""
import json
import os
import time
import unittest
from unittest import mock

import apoio
from streamdeck import avisos, devices, paths, security, storage
from test_aparelhos_http import pedir, cookie_de


def ajustes(**kw):
    s = storage.load_settings()
    s["avisos"] = kw
    storage.save_settings(s)
    avisos._drop_cache()


class FilaTest(unittest.TestCase):
    def test_ids_crescentes_e_maximo_50(self):
        f = avisos.Fila(start=1000)
        ids = [f.push("ia", "t%d" % i) for i in range(60)]
        self.assertEqual(ids, list(range(1001, 1061)))
        todos = f.since(0)
        self.assertEqual(len(todos), 50)
        self.assertEqual(todos[0]["id"], 1011)
        self.assertEqual(todos[-1]["title"], "t59")

    def test_since_devolve_so_os_novos(self):
        f = avisos.Fila(start=0)
        f.push("ia", "a")
        f.push("obs", "b")
        f.push("cpu", "c")
        self.assertEqual([i["title"] for i in f.since(1)], ["b", "c"])
        self.assertEqual(f.since(3), [])
        items, last = f.poll(3)
        self.assertEqual((items, last), ([], 3))

    def test_since_maior_que_o_ultimo_devolve_tudo(self):
        f = avisos.Fila(start=0)
        f.push("ia", "a")
        self.assertEqual(len(f.since(999)), 1)

    def test_so_full_ve_windows(self):
        f = avisos.Fila(start=0)
        f.push("ia", "a")
        f.push("windows", "segredo", "texto", full_only=True, app="Teams")
        self.assertEqual([i["title"] for i in f.since(0, full=False)], ["a"])
        com = f.since(0, full=True)
        self.assertEqual([i["title"] for i in com], ["a", "segredo"])
        self.assertNotIn("full", com[1])
        self.assertEqual(com[1]["app"], "Teams")


class RegrasTest(unittest.TestCase):
    def setUp(self):
        self.fila = avisos.Fila(start=0)
        p = mock.patch.object(avisos, "FILA", self.fila)
        p.start()
        self.addCleanup(p.stop)
        ajustes()
        self.r = avisos.Regras()

    def titulos(self):
        return [i["title"] for i in self.fila.since(0)]

    def test_ia_80_e_95_uma_vez_por_janela(self):
        now = 1000000
        st = lambda u, reset: {"claude": {"five_hour": {"used": u, "resets_at": reset}, "weekly": None}, "codex": None}  # noqa: E731
        self.r.check_ia(st(50, now + 3600), now)
        self.assertEqual(self.titulos(), [])
        self.r.check_ia(st(81, now + 3600), now)
        self.r.check_ia(st(85, now + 3600), now)
        self.assertEqual(len(self.titulos()), 1)
        self.assertIn("81%", self.titulos()[0])
        self.r.check_ia(st(96, now + 3600), now)
        self.r.check_ia(st(99, now + 3600), now)
        self.assertEqual(len(self.titulos()), 2)
        self.assertEqual(self.fila.since(0)[-1]["level"], "crit")
        # janela nova (outro resets_at): avisa de novo
        self.r.check_ia(st(82, now + 7200), now)
        self.assertEqual(len(self.titulos()), 3)

    def test_ia_pula_80_se_ja_em_95(self):
        st = {"codex": {"weekly": {"used": 97, "resets_at": 5000}}}
        self.r.check_ia(st, 1000)
        self.r.check_ia(st, 1000)
        self.assertEqual(len(self.titulos()), 1)
        self.assertIn("Codex", self.titulos()[0])

    def test_temperatura_com_intervalo_de_5_min(self):
        snap = lambda t, now: {"cpu": 10, "temps": {"cpu": t, "gpu": None}, "ts": now}  # noqa: E731
        self.r.check_pc(snap(89, 100), 100)
        self.assertEqual(self.titulos(), [])
        self.r.check_pc(snap(93, 101), 101)
        self.r.check_pc(snap(95, 200), 200)
        self.assertEqual(len(self.titulos()), 1)
        self.r.check_pc(snap(95, 402), 402)
        self.assertEqual(len(self.titulos()), 2)

    def test_limite_de_temperatura_dos_ajustes(self):
        ajustes(temp_limit=70)
        self.r.check_pc({"temps": {"gpu": 75}, "ts": 10}, 10)
        self.assertEqual(self.titulos(), ["GPU a 75 °C"])

    def test_amostra_velha_nao_conta(self):
        self.r.check_pc({"temps": {"cpu": 99}, "cpu": 99, "ts": 10}, 100)
        self.assertEqual(self.titulos(), [])

    def test_cpu_acima_de_95_por_1_min(self):
        for t in range(0, 59, 2):
            self.r.check_pc({"cpu": 99, "temps": {}, "ts": t}, t)
        self.assertEqual(self.titulos(), [])
        for t in range(60, 100, 2):
            self.r.check_pc({"cpu": 99, "temps": {}, "ts": t}, t)
        self.assertEqual(len(self.titulos()), 1)
        self.r.check_pc({"cpu": 20, "temps": {}, "ts": 102}, 102)    # baixou: rearma
        for t in range(104, 170, 2):
            self.r.check_pc({"cpu": 99, "temps": {}, "ts": t}, t)
        self.assertEqual(len(self.titulos()), 2)

    def test_cpu_buraco_nas_amostras_recomeca(self):
        self.r.check_pc({"cpu": 99, "temps": {}, "ts": 0}, 0)
        self.r.check_pc({"cpu": 99, "temps": {}, "ts": 70}, 70)    # 70 s sem amostras
        self.assertEqual(self.titulos(), [])

    def test_obs_desconectou_e_voltou(self):
        self.r.check_obs(None)
        self.r.check_obs({"ok": True})
        self.assertEqual(self.titulos(), [])
        self.r.check_obs({"ok": False})
        self.r.check_obs({"ok": False})
        self.r.check_obs({"ok": True})
        self.assertEqual(self.titulos(), ["OBS desconectado", "OBS conectado de novo"])

    def test_tipo_desligado_nao_entra(self):
        ajustes(types={"obs": False})
        self.r.check_obs({"ok": True})
        self.r.check_obs({"ok": False})
        self.assertEqual(self.titulos(), [])

    def test_agendamento_desligado_por_padrao(self):
        avisos.schedule_ran("Backup")
        self.assertEqual(self.titulos(), [])
        ajustes(types={"schedule": True})
        avisos.schedule_ran("Backup")
        self.assertEqual(self.titulos(), ["Agendamento executado"])


class AjustesTest(unittest.TestCase):
    def setUp(self):
        ajustes()

    def test_padroes(self):
        s = avisos.settings()
        self.assertTrue(s["types"]["ia"])
        self.assertFalse(s["types"]["windows"])
        self.assertFalse(s["types"]["schedule"])
        self.assertEqual(s["temp_limit"], 90)

    def test_salvar_parcial_e_validar(self):
        s = avisos.save_settings({"types": {"windows": True}, "ignored_apps": [" Teams ", ""]})
        self.assertTrue(s["types"]["windows"])
        self.assertTrue(s["types"]["ia"])
        self.assertEqual(s["ignored_apps"], ["Teams"])
        self.assertEqual(storage.load_settings()["avisos"]["types"]["windows"], True)
        for bad in ({"types": {"x": True}}, {"types": {"ia": 1}}, {"temp_limit": 200},
                    {"temp_limit": True}, {"ignored_apps": "Teams"}, []):
            with self.assertRaises(ValueError):
                avisos.save_settings(bad)


class AvisosHttpTest(unittest.TestCase):
    def setUp(self):
        self._popen = mock.patch("streamdeck.actions.system.subprocess.Popen")
        self._popen.start()
        self.addCleanup(self._popen.stop)
        self._q = apoio.quiet()
        self._q.__enter__()
        self.addCleanup(self._q.__exit__, None, None, None)
        apoio.write_config(apoio.base_config())
        security.FAILS.clear()
        if os.path.exists(paths.DEVICES_PATH):
            os.remove(paths.DEVICES_PATH)
        devices.reset()
        ajustes(types={"windows": True})
        self.fila = avisos.Fila(start=0)
        p = mock.patch.object(avisos, "FILA", self.fila)
        p.start()
        self.addCleanup(p.stop)

    def novo(self):
        st, h, _ = pedir("GET", "/?k=" + storage.token())
        self.assertEqual(st, 302)
        return cookie_de(h)

    def test_since_pelo_state_e_windows_so_com_controle_total(self):
        key = self.novo()                      # cadastro gera aviso "aparelho novo"
        st, _, r = pedir("GET", "/api/state", key)
        self.assertEqual(st, 200)
        self.assertNotIn("alerts", r)          # sem since: so o ultimo id
        base = r["alert_id"]
        self.assertEqual(base, 1)
        self.fila.push("obs", "OBS desconectado")
        self.fila.push("windows", "Mensagem", "oi", full_only=True, app="Teams")
        st, _, r = pedir("GET", "/api/state?since=%d" % base, key)
        self.assertEqual([a["title"] for a in r["alerts"]], ["OBS desconectado"])
        self.assertEqual(r["alert_id"], 3)
        st, _, r = pedir("GET", "/api/avisos", key)
        self.assertNotIn("Mensagem", json.dumps(r))
        # com Controle total o aparelho recebe a notificacao do Windows
        devices.set_full(devices.list_public()[0]["id"], True)
        st, _, r = pedir("GET", "/api/state?since=%d" % base, key)
        self.assertEqual([a["title"] for a in r["alerts"]], ["OBS desconectado", "Mensagem"])

    def test_aparelho_novo_gera_aviso(self):
        self.novo()
        self.assertEqual([a["title"] for a in self.fila.since(0)], ["Aparelho novo conectado"])

    def test_ajustes_so_no_pc(self):
        key = self.novo()
        st, _, _ = pedir("POST", "/api/local/avisos", key, body={"types": {"ia": False}})
        self.assertEqual(st, 403)
        st, _, r = pedir("POST", "/api/local/avisos", ip="127.0.0.1", body={"types": {"ia": False}, "temp_limit": 85})
        self.assertEqual(st, 200, r)
        self.assertFalse(r["types"]["ia"])
        self.assertEqual(r["temp_limit"], 85)
        self.assertIn("windows_status", r)
        st, _, r = pedir("POST", "/api/local/avisos", ip="127.0.0.1", body={"temp_limit": 5})
        self.assertEqual(st, 400)


if __name__ == "__main__":
    unittest.main()
