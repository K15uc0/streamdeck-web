# -*- coding: utf-8 -*-
"""Icone na bandeja: partes que rodam sem Win32 (modelo do menu, avisos, Tee)."""
import io
import os
import tempfile
import unittest

import apoio  # noqa: F401
from streamdeck import app, tray


def ids(items):
    return [i[0] for i in items]


class MenuTest(unittest.TestCase):
    def test_basico(self):
        m = tray.build_menu({})
        self.assertEqual(ids(m), [tray.ID_CONECTAR, tray.ID_EDITAR, tray.ID_PASTA, tray.ID_LOG, None,
                                  tray.ID_AUTOSTART, None, tray.ID_SAIR])
        self.assertEqual(m[0][1], "Conectar um aparelho")
        self.assertEqual(m[-1], (tray.ID_SAIR, "Sair", False, True))
        for i in m:
            self.assertEqual(len(i), 4)

    def test_autostart_marcado(self):
        item = [i for i in tray.build_menu({"autostart": True}) if i[0] == tray.ID_AUTOSTART][0]
        self.assertEqual(item, (tray.ID_AUTOSTART, "Iniciar com o Windows", True, True))
        item = [i for i in tray.build_menu({"autostart_ok": False}) if i[0] == tray.ID_AUTOSTART][0]
        self.assertFalse(item[3])

    def test_atualizacao_e_console(self):
        m = tray.build_menu({"update_latest": "2.6.0", "has_console": True, "console_visible": True})
        labels = dict((i[0], i) for i in m if i[0])
        self.assertEqual(labels[tray.ID_UPDATE][1], "Atualização disponível: 2.6.0")
        self.assertEqual(labels[tray.ID_CONSOLE], (tray.ID_CONSOLE, "Mostrar janela do log", True, True))
        self.assertNotIn(tray.ID_CONSOLE, ids(tray.build_menu({"has_console": False})))

    def test_aviso_atualizacao_uma_vez(self):
        shown = set()
        self.assertIsNone(tray.update_balloon({"available": False, "latest": "9"}, shown))
        msg = tray.update_balloon({"available": True, "latest": "2.6.0"}, shown)
        self.assertIn("2.6.0", msg[1])
        self.assertIsNone(tray.update_balloon({"available": True, "latest": "2.6.0"}, shown))
        self.assertIsNotNone(tray.update_balloon({"available": True, "latest": "2.7.0"}, shown))

    def test_tooltip(self):
        self.assertEqual(tray.tooltip(8765), "Stream Deck — porta 8765")
        self.assertLessEqual(len(tray.tooltip(8765, "x" * 300)), 127)

    @unittest.skipIf(tray.IS_WINDOWS, "so fora do Windows")
    def test_start_fora_do_windows(self):
        self.assertFalse(tray.start(8765, None))
        tray.stop()
        self.assertEqual(tray.console_hwnd(), 0)
        self.assertFalse(tray.show_console(True))


class CliqueTest(unittest.TestCase):
    def test_clique_simples_abre_menu(self):
        st = {}
        self.assertEqual(tray.click_event(st, "up"), "start_timer")
        self.assertEqual(tray.click_event(st, "timer"), "menu")

    def test_duplo_clique_ignora_up_seguinte(self):
        st = {}
        self.assertEqual(tray.click_event(st, "up"), "start_timer")
        self.assertEqual(tray.click_event(st, "dbl"), "open")
        self.assertIsNone(tray.click_event(st, "up"))       # nao reinicia o timer
        self.assertIsNone(tray.click_event(st, "timer"))    # timer atrasado: sem menu
        # proximo clique simples volta a abrir o menu
        self.assertEqual(tray.click_event(st, "up"), "start_timer")
        self.assertEqual(tray.click_event(st, "timer"), "menu")


class DicaParaParar(unittest.TestCase):
    def test_textos(self):
        self.assertIn("Sair", app.stop_hint(True, True))
        self.assertIn("Ctrl+C", app.stop_hint(False, True))
        t = app.stop_hint(False, False)
        self.assertIn("Gerenciador de Tarefas", t)
        self.assertIn("Conectar", t)


class TeeTest(unittest.TestCase):
    def test_sem_console(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "log.txt")
            t = app.Tee(None, p)
            t.write("ola\n")
            t.flush()
            t.f.close()
            with open(p, encoding="utf-8") as f:
                self.assertEqual(f.read(), "ola\n")

    def test_com_console(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            t = app.Tee(buf, os.path.join(d, "l.txt"))
            t.write("x")
            t.f.close()
            self.assertEqual(buf.getvalue(), "x")


if __name__ == "__main__":
    unittest.main()
