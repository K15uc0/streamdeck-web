# -*- coding: utf-8 -*-
"""Atualizacao: tipo de instalacao e escolha do arquivo da release."""
import os
import unittest
from unittest import mock

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
        achou = lambda pat: [pat.replace("*", "001")] if pat.endswith("unins*.exe") else []
        self.assertEqual(updates.install_kind(exe, exists=lambda p: False, globber=achou), "instalado")

    def test_com_marcador(self):
        exe = os.path.abspath(os.path.join("x", "StreamDeck.exe"))
        vistos = {os.path.join(os.path.dirname(exe), "instalado.txt")}
        self.assertEqual(updates.install_kind(exe, exists=lambda p: p in vistos, globber=lambda p: []), "instalado")

    def test_portatil(self):
        self.assertEqual(updates.install_kind("/x/Downloads/StreamDeck.exe", exists=lambda p: False,
                                              globber=lambda p: []), "portatil")

    def test_desinstalador_de_verdade(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "StreamDeck.exe")
            self.assertEqual(updates.install_kind(exe), "portatil")
            open(os.path.join(d, "unins001.exe"), "w").close()
            self.assertEqual(updates.install_kind(exe), "instalado")


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
        env = {"LOCALAPPDATA": os.path.abspath("lad"), "USERPROFILE": os.path.abspath("perfil")}
        pasta = os.path.join(env["LOCALAPPDATA"], "Programs", "StreamDeck")
        cmd = updates.installer_command("C:\\t\\i.exe", pasta, "C:\\t\\instalador.log", env=env)
        self.assertEqual(cmd[0], "C:\\t\\i.exe")
        for arg in ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/RESTARTAPP=1"):
            self.assertIn(arg, cmd)
        self.assertIn("/DIR=" + pasta, cmd)
        self.assertIn("/LOG=C:\\t\\instalador.log", cmd)

    def test_comando_no_perfil(self):
        env = {"USERPROFILE": os.path.abspath("perfil")}
        cmd = updates.installer_command("i.exe", os.path.join(env["USERPROFILE"], "Apps", "SD"), env=env)
        self.assertIn("/CURRENTUSER", cmd)

    def test_comando_fora_do_perfil(self):
        env = {"LOCALAPPDATA": os.path.abspath("lad"), "USERPROFILE": os.path.abspath("perfil")}
        cmd = updates.installer_command("i.exe", os.path.abspath("ProgramFiles") + os.sep + "SD", env=env)
        self.assertNotIn("/CURRENTUSER", cmd)
        # prefixo parecido nao conta
        cmd = updates.installer_command("i.exe", os.path.abspath("perfil2"), env=env)
        self.assertNotIn("/CURRENTUSER", cmd)
        self.assertFalse(any(a.startswith("/LOG=") for a in cmd))


class AplicarInstalador(unittest.TestCase):
    def setUp(self):
        self.antes = dict(updates.UPDATE)
        updates.UPDATE.update(available=True, latest="9.9.9", asset="https://x/i.exe", state="idle", error=None)

    def tearDown(self):
        updates.UPDATE.clear()
        updates.UPDATE.update(self.antes)

    def _rodar(self, poll):
        proc = mock.Mock()
        proc.poll.return_value = poll
        with mock.patch.object(updates.paths, "EXE_PATH", os.path.abspath(os.path.join("app", "StreamDeck.exe"))), \
                mock.patch.object(updates, "_download"), \
                mock.patch.object(updates.subprocess, "Popen", return_value=proc) as popen, \
                mock.patch.object(updates.time, "sleep"), \
                mock.patch.object(updates, "_stop_tray"), \
                mock.patch.object(updates.os, "_exit", side_effect=SystemExit) as sair:
            try:
                updates.apply_installer_update()
            except SystemExit:
                pass
        return popen, sair

    def test_instalador_saiu_logo(self):
        popen, sair = self._rodar(poll=2)
        sair.assert_not_called()
        self.assertEqual(updates.UPDATE["state"], "error")
        self.assertIn("2", updates.UPDATE["error"])
        self.assertTrue(any(a.startswith("/LOG=") and a.endswith("instalador.log") for a in popen.call_args[0][0]))

    def test_instalador_rodando(self):
        _, sair = self._rodar(poll=None)
        sair.assert_called_once_with(0)
        self.assertEqual(updates.UPDATE["state"], "restarting")


class LimpezaDoInstalador(unittest.TestCase):
    def test_tenta_de_novo_e_avisa(self):
        esperas = []
        with mock.patch.object(updates, "_remove_installer_folder", return_value=False):
            self.assertFalse(updates.cleanup_installer(tries=3, delay=2.0, sleep=esperas.append))
        self.assertEqual(esperas, [2.0, 2.0])

    def test_consegue_depois(self):
        res = iter([False, True])
        with mock.patch.object(updates, "_remove_installer_folder", side_effect=lambda f: next(res)):
            self.assertTrue(updates.cleanup_installer(sleep=lambda s: None))


if __name__ == "__main__":
    unittest.main()
