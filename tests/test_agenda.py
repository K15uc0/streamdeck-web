# -*- coding: utf-8 -*-
"""Agendamentos (2.8): next_run/due, validacao, execucao e API local."""
import json
import threading
import unittest
from datetime import datetime as D

import apoio  # noqa: F401  (antes do pacote)
from streamdeck import actions, agenda, schema, storage


def item(when, sid="a1", enabled=True, action=None):
    return {"id": sid, "name": "Teste", "enabled": enabled, "when": when,
            "action": action or {"type": "none"}}


# 2026-11-20 e sexta (5); 2026-11-22 domingo (0)
class NextRun(unittest.TestCase):
    def test_daily(self):
        it = item({"type": "daily", "time": "08:00"})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 7, 59, 30)), D(2026, 11, 20, 8, 0))
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 8, 0, 40)), D(2026, 11, 20, 8, 0))
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 8, 1)), D(2026, 11, 21, 8, 0))

    def test_daily_days(self):
        it = item({"type": "daily", "time": "08:00", "days": [1, 2, 3, 4, 5]})
        # sexta 9h -> segunda
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 9, 0)), D(2026, 11, 23, 8, 0))
        it = item({"type": "daily", "time": "10:00", "days": [0]})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 9, 0)), D(2026, 11, 22, 10, 0))

    def test_every_aligned(self):
        it = item({"type": "every", "minutes": 15})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 9, 1)), D(2026, 11, 20, 9, 15))
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 9, 30, 59)), D(2026, 11, 20, 9, 30))
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 23, 50)), D(2026, 11, 21, 0, 0))
        it = item({"type": "every", "minutes": 60})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 9, 1)), D(2026, 11, 20, 10, 0))
        it = item({"type": "every", "minutes": 1440})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 9, 1)), D(2026, 11, 21, 0, 0))
        it = item({"type": "every", "minutes": 7})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 23, 56)), D(2026, 11, 21, 0, 0))

    def test_every_window(self):
        it = item({"type": "every", "minutes": 30, "from": "09:00", "to": "18:00"})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 6, 0)), D(2026, 11, 20, 9, 0))
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 17, 31)), D(2026, 11, 21, 9, 0))  # 18:00 fora
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 17, 29)), D(2026, 11, 20, 17, 30))

    def test_every_window_midnight(self):
        it = item({"type": "every", "minutes": 60, "from": "22:00", "to": "02:00"})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 12, 0)), D(2026, 11, 20, 22, 0))
        self.assertEqual(agenda.next_run(it, D(2026, 11, 21, 0, 30)), D(2026, 11, 21, 1, 0))
        self.assertEqual(agenda.next_run(it, D(2026, 11, 21, 1, 30)), D(2026, 11, 21, 22, 0))
        # so sexta: sabado 01:00 conta como a noite de sexta
        it = item({"type": "every", "minutes": 60, "from": "22:00", "to": "02:00", "days": [5]})
        self.assertTrue(agenda.matches(it["when"], D(2026, 11, 21, 1, 0)))
        self.assertFalse(agenda.matches(it["when"], D(2026, 11, 20, 1, 0)))  # quinta a noite
        self.assertEqual(agenda.next_run(it, D(2026, 11, 21, 2, 0)), D(2026, 11, 27, 22, 0))

    def test_every_from_only_to_only(self):
        it = item({"type": "every", "minutes": 60, "from": "20:00"})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 21, 1)), D(2026, 11, 20, 22, 0))
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 23, 1)), D(2026, 11, 21, 20, 0))
        it = item({"type": "every", "minutes": 60, "to": "03:00"})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 2, 1)), D(2026, 11, 21, 0, 0))

    def test_once(self):
        it = item({"type": "once", "at": "2026-12-01T10:30"})
        self.assertEqual(agenda.next_run(it, D(2026, 11, 20, 0, 0)), D(2026, 12, 1, 10, 30))
        self.assertIsNone(agenda.next_run(it, D(2026, 12, 1, 10, 31)))
        it["enabled"] = False
        self.assertIsNone(agenda.next_run(it, D(2026, 11, 20)))

    def test_dst_agnostic(self):
        # hora local ingenua: dia de mudanca de horario nao altera a conta
        it = item({"type": "daily", "time": "02:30"})
        self.assertEqual(agenda.next_run(it, D(2026, 3, 29, 1, 0)), D(2026, 3, 29, 2, 30))


class Due(unittest.TestCase):
    def test_once_per_minute(self):
        it = item({"type": "every", "minutes": 15})
        now = D(2026, 11, 20, 9, 15, 3)
        self.assertTrue(agenda.due(it, None, now))
        self.assertFalse(agenda.due(it, D(2026, 11, 20, 9, 15), D(2026, 11, 20, 9, 15, 50)))
        self.assertFalse(agenda.due(it, None, D(2026, 11, 20, 9, 16)))
        self.assertTrue(agenda.due(it, D(2026, 11, 20, 9, 15), D(2026, 11, 20, 9, 30)))

    def test_disabled_and_days(self):
        it = item({"type": "daily", "time": "08:00", "days": [6]}, enabled=False)
        self.assertFalse(agenda.due(it, None, D(2026, 11, 21, 8, 0)))
        it["enabled"] = True
        self.assertTrue(agenda.due(it, None, D(2026, 11, 21, 8, 0)))
        self.assertFalse(agenda.due(it, None, D(2026, 11, 20, 8, 0)))

    def test_once_due(self):
        it = item({"type": "once", "at": "2026-11-20T10:00"})
        self.assertTrue(agenda.due(it, None, D(2026, 11, 20, 10, 0, 9)))
        self.assertFalse(agenda.due(it, None, D(2026, 11, 20, 10, 1)))   # nao recupera atrasados


class Runner(unittest.TestCase):
    def setUp(self):
        self.ran = []
        self.cfg = {"schedules": []}
        self.ag = agenda.Agenda(get_config=lambda: self.cfg)
        self.orig = actions.run
        actions.run = lambda a, key=None: self.ran.append((a, key))

    def tearDown(self):
        actions.run = self.orig

    def tick(self, now):
        with apoio.quiet():
            for t in self.ag.tick(now):
                t.join(5)

    def test_tick_and_clock_back(self):
        self.cfg["schedules"] = [item({"type": "every", "minutes": 1}, sid="x")]
        self.tick(D(2026, 11, 20, 9, 0, 1))
        self.tick(D(2026, 11, 20, 9, 0, 11))
        self.tick(D(2026, 11, 20, 9, 0, 5))     # relogio voltou
        self.assertEqual(len(self.ran), 1)
        self.assertEqual(self.ran[0][1], "agenda:x")
        self.tick(D(2026, 11, 20, 9, 1, 1))
        self.assertEqual(len(self.ran), 2)
        st = self.ag.status(D(2026, 11, 20, 9, 1, 30))
        self.assertTrue(st["ok"])
        self.assertEqual(st["items"][0]["next"], "2026-11-20T09:01:00")
        self.assertIsNotNone(st["items"][0]["last"])
        self.assertIsNone(st["items"][0]["last_error"])

    def test_error_recorded(self):
        def boom(a, key=None):
            raise RuntimeError("falhou")
        actions.run = boom
        self.cfg["schedules"] = [item({"type": "daily", "time": "09:00"}, sid="e")]
        self.tick(D(2026, 11, 20, 9, 0))
        self.assertEqual(self.ag.status(D(2026, 11, 20, 9, 0))["items"][0]["last_error"], "falhou")


class OnceDisables(unittest.TestCase):
    def test_once_disables_in_config(self):
        cfg = apoio.base_config()
        cfg["schedules"] = [item({"type": "once", "at": "2026-11-20T10:00"}, sid="o1")]
        apoio.write_config(cfg)
        orig = actions.run
        actions.run = lambda a, key=None: None
        try:
            ag = agenda.Agenda()
            with apoio.quiet():
                for t in ag.tick(D(2026, 11, 20, 10, 0, 2)):
                    t.join(5)
        finally:
            actions.run = orig
        storage.CONFIG_CACHE["key"] = None
        self.assertIs(storage.load_config()["schedules"][0]["enabled"], False)


class Schema(unittest.TestCase):
    def cfg(self, scheds):
        c = apoio.base_config()
        c["schedules"] = scheds
        return c

    def ok(self, scheds):
        schema.validate_config(self.cfg(scheds))

    def bad(self, scheds):
        with self.assertRaises(ValueError):
            schema.validate_config(self.cfg(scheds))

    def test_accept(self):
        self.ok([])
        self.ok([item({"type": "daily", "time": "08:00", "days": [1, 2, 3, 4, 5]}),
                 item({"type": "every", "minutes": 15, "from": "22:00", "to": "02:00", "days": []}, sid="b"),
                 item({"type": "once", "at": "2026-12-31T23:59"}, sid="c",
                      action={"type": "hotkey", "keys": ["ctrl", "c"]})])
        schema.validate_config(apoio.base_config())   # sem schedules

    def test_reject(self):
        self.bad({})
        self.bad([item({"type": "daily", "time": "8:00"})])
        self.bad([item({"type": "daily", "time": "24:00"})])
        self.bad([item({"type": "daily", "time": "08:00", "days": [7]})])
        self.bad([item({"type": "daily", "time": "08:00", "days": [1, 1]})])
        self.bad([item({"type": "every", "minutes": 0})])
        self.bad([item({"type": "every", "minutes": 1441})])
        self.bad([item({"type": "every", "minutes": True})])
        self.bad([item({"type": "every", "minutes": 5, "from": "25:00"})])
        self.bad([item({"type": "once", "at": "2026-02-30T10:00"})])
        self.bad([item({"type": "once", "at": "2026-02-01 10:00"})])
        self.bad([item({"type": "weekly"})])
        self.bad([item({"type": "daily", "time": "08:00", "extra": 1})])
        self.bad([item({"type": "daily", "time": "08:00"}, sid="A1")])
        self.bad([item({"type": "daily", "time": "08:00"}, sid="x" * 17)])
        self.bad([item({"type": "daily", "time": "08:00"}), item({"type": "daily", "time": "09:00"})])
        self.bad([item({"type": "daily", "time": "08:00"}, enabled="sim")])
        self.bad([item({"type": "daily", "time": "08:00"}, action={"type": "page", "to": 0})])
        self.bad([item({"type": "daily", "time": "08:00"}, action={"type": "inexistente"})])
        x = item({"type": "daily", "time": "08:00"})
        x["name"] = "n" * 61
        self.bad([x])
        self.bad([item({"type": "every", "minutes": 5}, sid="s%d" % i) for i in range(51)])

    def test_live_nowplaying(self):
        for live in ("nowplaying", "nowplaying:title", "nowplaying:artist"):
            c = apoio.base_config()
            c["pages"][0]["buttons"][1]["live"] = live
            schema.validate_config(c)
        c["pages"][0]["buttons"][1]["live"] = "nowplaying:album"
        with self.assertRaises(ValueError):
            schema.validate_config(c)


class Api(unittest.TestCase):
    def setUp(self):
        cfg = apoio.base_config()
        cfg["schedules"] = [item({"type": "daily", "time": "08:00"}, sid="v1",
                                 action={"type": "hotkey", "keys": ["f5"]})]
        apoio.write_config(cfg)

    def req(self, method, path, ip="127.0.0.1", body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        h = {"Content-Type": "application/json"} if body is not None else None
        with apoio.quiet():
            st, _h, out = apoio.fake_request(method, path, ip=ip, headers=h, body=raw)
        try:
            return st, json.loads(out.decode("utf-8") or "{}")
        except ValueError:
            return st, {}

    def test_list(self):
        st, js = self.req("GET", "/api/local/schedules")
        self.assertEqual(st, 200)
        self.assertTrue(js["ok"])
        self.assertIn("T", js["now"])
        self.assertEqual(js["items"][0]["id"], "v1")
        self.assertTrue(js["items"][0]["next"].endswith("T08:00:00"))

    def test_run(self):
        n = len(apoio.KEYS)
        st, js = self.req("POST", "/api/local/schedules/run", body={"id": "v1"})
        self.assertEqual((st, js.get("ok")), (200, True))
        self.assertEqual(apoio.KEYS[n:], [("keys", ["f5"])])
        st, _ = self.req("POST", "/api/local/schedules/run", body={"id": "nao"})
        self.assertEqual(st, 404)
        st, _ = self.req("POST", "/api/local/schedules/run", body={"id": "../x"})
        self.assertEqual(st, 400)
        st, js = self.req("GET", "/api/local/schedules")
        self.assertIsNotNone(js["items"][0]["last"])

    def test_remote_refused(self):
        st, _ = self.req("GET", "/api/local/schedules", ip="192.168.0.50")
        self.assertEqual(st, 403)
        st, _ = self.req("POST", "/api/local/schedules/run", ip="192.168.0.50", body={"id": "v1"})
        self.assertEqual(st, 403)


class StartStop(unittest.TestCase):
    def test_thread(self):
        ag = agenda.Agenda(get_config=lambda: {})
        ag.start()
        self.assertTrue(any(t.name == "agenda" for t in threading.enumerate()))
        ag.stop()
        self.assertIsNone(ag._thread)


if __name__ == "__main__":
    unittest.main()
