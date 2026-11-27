# -*- coding: utf-8 -*-
"""Notificacoes do Windows (2.12): banco de exemplo gerado no teste com o
esquema ASSUMIDO do wpndatabase.db (ver notif_windows.py), parser do XML,
apps ignorados, primeira leitura so marca a base, esquema diferente desliga
sem quebrar, so leitura."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

import apoio  # noqa: F401
from streamdeck import avisos, notif_windows as nw

TOAST = ('<toast launch="x"><visual><binding template="ToastGeneric">'
         '<text>%s</text><text>%s</text></binding></visual></toast>')


def criar_banco(path, schema="ok"):
    con = sqlite3.connect(path)
    if schema == "ok":
        con.execute("CREATE TABLE NotificationHandler (RecordId INTEGER PRIMARY KEY, PrimaryId TEXT, HandlerType TEXT)")
        con.execute("CREATE TABLE Notification (Id INTEGER PRIMARY KEY, HandlerId INTEGER, Type TEXT, "
                    "Payload BLOB, Tag TEXT, ArrivalTime INTEGER, ExpiryTime INTEGER)")
        con.executemany("INSERT INTO NotificationHandler VALUES (?,?,?)", [
            (1, "MSTeams_8wekyb3d8bbwe!MSTeams", "app:desktop"),
            (2, "Microsoft.Windows.Explorer", "app:desktop"),
            (3, "Chrome", "app:desktop")])
    else:
        con.execute("CREATE TABLE Notification (Id INTEGER PRIMARY KEY, Dados TEXT)")
    con.commit()
    return con


def add(con, nid, handler, title, text, typ="toast"):
    con.execute("INSERT INTO Notification (Id, HandlerId, Type, Payload, ArrivalTime) VALUES (?,?,?,?,?)",
                (nid, handler, typ, (TOAST % (title, text)).encode("utf-8"), 133000000000000000))
    con.commit()


class ParserTest(unittest.TestCase):
    def test_toast_generico(self):
        self.assertEqual(nw.parse_toast(TOAST % ("Ana", "Oi, tudo bem?")), ("Ana", "Oi, tudo bem?"))
        self.assertEqual(nw.parse_toast((TOAST % ("A", "B")).encode("utf-16")), ("A", "B"))

    def test_invalidos(self):
        for p in (None, b"", "nao e xml", "<tile><visual><text>x</text></visual></tile>",
                  '<!DOCTYPE x [<!ENTITY a "b">]><toast><text>&a;</text></toast>',
                  "<toast><visual/></toast>", b"\xff\xfe\x00"):
            self.assertIsNone(nw.parse_toast(p), p)

    def test_nome_do_app(self):
        self.assertEqual(nw.app_name("MSTeams_8wekyb3d8bbwe!MSTeams"), "MSTeams")
        self.assertEqual(nw.app_name("Microsoft.WindowsStore_8wekyb3d8bbwe!App"), "WindowsStore")
        self.assertEqual(nw.app_name("Microsoft.Windows.Explorer"), "Explorer")
        self.assertEqual(nw.app_name("C:\\Apps\\Zap.exe"), "Zap")
        self.assertEqual(nw.app_name(None), "Windows")

    def test_filetime(self):
        self.assertAlmostEqual(nw.filetime_to_epoch(116444736000000000), 0.0)
        self.assertIsNone(nw.filetime_to_epoch("x"))


class LeitorTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = os.path.join(self.dir, "wpndatabase.db")
        self.fila = avisos.Fila(start=0)

    def test_primeira_leitura_so_marca_base_depois_entrega(self):
        con = criar_banco(self.db)
        add(con, 1, 1, "Antiga", "nao aparece")
        lt = nw.Leitor(self.db, self.fila)
        self.assertEqual(lt.poll_once(), 0)
        self.assertEqual(lt.status, "ativo")
        add(con, 2, 1, "Ana", "Oi")
        add(con, 3, 2, "Download", "Pronto")
        add(con, 4, 3, "Bloco", "x", typ="tile")
        self.assertEqual(lt.poll_once(), 2)
        got = self.fila.since(0, full=True)
        self.assertEqual([(a["app"], a["title"], a["text"]) for a in got],
                         [("MSTeams", "Ana", "Oi"), ("Explorer", "Download", "Pronto")])
        self.assertEqual(self.fila.since(0, full=False), [])     # so Controle total
        self.assertEqual(lt.poll_once(), 0)
        con.close()

    def test_apps_ignorados(self):
        con = criar_banco(self.db)
        lt = nw.Leitor(self.db, self.fila)
        lt.poll_once()
        add(con, 1, 1, "Ana", "Oi")
        add(con, 2, 3, "Site", "Promo")
        self.assertEqual(lt.poll_once(["chrome"]), 1)
        self.assertEqual(self.fila.since(0, True)[0]["app"], "MSTeams")
        con.close()

    def test_esquema_diferente_desliga_sem_quebrar(self):
        criar_banco(self.db, schema="outro").close()
        lt = nw.Leitor(self.db, self.fila)
        self.assertEqual(lt.poll_once(), 0)
        self.assertTrue(lt.failed)
        self.assertEqual(lt.status, nw.UNAVAILABLE)

    def test_sem_banco(self):
        lt = nw.Leitor(os.path.join(self.dir, "nao.db"), self.fila)
        lt.poll_once()
        self.assertEqual(lt.status, nw.UNAVAILABLE)

    def test_somente_leitura(self):
        con = criar_banco(self.db)
        con.close()
        c = nw._connect(self.db)
        with self.assertRaises(sqlite3.OperationalError):
            c.execute("INSERT INTO Notification (Id) VALUES (9)")
        c.close()

    def test_travado_usa_copia(self):
        con = criar_banco(self.db)
        add(con, 1, 1, "A", "a")
        con.close()
        real = nw._connect
        calls = []

        def travado(path):
            calls.append(path)
            raise sqlite3.OperationalError("database is locked")
        with mock.patch.object(nw, "_connect", travado):
            self.assertEqual(nw._with_db(self.db, nw._max_id), 1)
        self.assertEqual(len(calls), 1)
        self.assertIs(nw._connect, real)

    def test_maybe_poll_respeita_ajuste_windows_e_intervalo(self):
        lt = nw.Leitor(self.db, self.fila)
        with mock.patch.object(avisos, "settings", lambda: {"types": {"windows": False}, "ignored_apps": []}):
            self.assertFalse(lt.maybe_poll(100))
        cfg = {"types": {"windows": True}, "ignored_apps": []}
        with mock.patch.object(avisos, "settings", lambda: cfg), \
                mock.patch.object(nw.paths, "IS_WINDOWS", True), \
                mock.patch.object(nw.threading, "Thread") as th:
            self.assertTrue(lt.maybe_poll(100))
            lt.busy = False
            self.assertFalse(lt.maybe_poll(103))      # menos de 5 s
            self.assertTrue(lt.maybe_poll(106))
            self.assertEqual(th.call_count, 2)
        with mock.patch.object(avisos, "settings", lambda: cfg), mock.patch.object(nw.paths, "IS_WINDOWS", False):
            self.assertFalse(lt.maybe_poll(200))
            self.assertEqual(lt.info(), "só no Windows")


if __name__ == "__main__":
    unittest.main()
