# -*- coding: utf-8 -*-
"""Atualizacao: tipo de instalacao e escolha do arquivo da release."""
import os
import unittest

import apoio  # noqa: F401  (pasta de dados temporaria)
from streamdeck import REPO, updates

BASE = "https://github.com/%s/releases/download/v2.5.0/" % REPO


def asset(name, digest=None, base=BASE):
    a = {"name": name, "browser_download_url": base + name}
    if digest:
        a["digest"] = digest
    return a


class TipoDeInstalacao(unittest.TestCase):
    def test_pelo_codigo(self):
        self.assertIsNone(updates.install_kind(None))

    def test_onedir_com_internal(self):
        exe = os.path.join("C:", os.sep, "Prog", "StreamDeck", "StreamDeck.exe")
        pasta = os.path.dirname(os.path.abspath(exe))
        vistos = {os.path.join(pasta, "_internal")}
        self.assertEqual(updates.install_kind(exe, exists=lambda p: p in vistos), "instalado")

    def test_com_desinstalador(self):
        exe = os.path.abspath(os.path.join("x", "StreamDeck.exe"))
        vistos = {os.path.join(os.path.dirname(exe), "unins000.exe")}
        self.assertEqual(updates.install_kind(exe, exists=lambda p: p in vistos), "instalado")

    def test_portatil(self):
        self.assertEqual(updates.install_kind("/x/Downloads/StreamDeck.exe", exists=lambda p: False), "portatil")


class EscolhaDoArquivo(unittest.TestCase):
    # ordem da API = ordem de envio: instalador primeiro, portatil por ultimo
    ASSETS = [asset("StreamDeck-Instalador.exe", "sha256:AA"), asset("StreamDeck.exe", "sha256:BB")]

    def test_instalado_pega_instalador(self):
        self.assertEqual(updates.pick_asset(self.ASSETS, "instalado"),
                         (BASE + "StreamDeck-Instalador.exe", "aa"))

    def test_portatil_pega_exe_unico(self):
        self.assertEqual(updates.pick_asset(self.ASSETS, "portatil"), (BASE + "StreamDeck.exe", "bb"))
        # independente da ordem
        self.assertEqual(updates.pick_asset(self.ASSETS[::-1], "portatil"), (BASE + "StreamDeck.exe", "bb"))

    def test_sem_arquivo_certo(self):
        self.assertEqual(updates.pick_asset([asset("StreamDeck.exe")], "instalado"), (None, None))
        self.assertEqual(updates.pick_asset([], "portatil"), (None, None))

    def test_link_de_outro_repositorio(self):
        a = [asset("StreamDeck.exe", base="https://github.com/outro/repo/releases/download/v1/")]
        self.assertEqual(updates.pick_asset(a, "portatil"), (None, None))

    def test_sem_digest(self):
        self.assertEqual(updates.pick_asset([asset("StreamDeck.exe")], "portatil"), (BASE + "StreamDeck.exe", None))

    def test_compat_clientes_antigos(self):
        # ate a 2.4.0 o app pega o ULTIMO .exe: tem de ser o portatil
        ultimo = [a for a in self.ASSETS if a["name"].lower().endswith(".exe")][-1]
        self.assertEqual(ultimo["name"], "StreamDeck.exe")

    def test_comando_do_instalador(self):
        cmd = updates.installer_command("C:\\t\\i.exe", "C:\\Prog\\StreamDeck")
        self.assertEqual(cmd[0], "C:\\t\\i.exe")
        for arg in ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/RESTARTAPP=1"):
            self.assertIn(arg, cmd)
        self.assertIn("/DIR=C:\\Prog\\StreamDeck", cmd)


if __name__ == "__main__":
    unittest.main()
