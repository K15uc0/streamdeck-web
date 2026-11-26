# -*- coding: utf-8 -*-
"""Consumo das IAs (2.9): Claude (ponte) e Codex (logs)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from unittest import mock

import apoio  # noqa: F401
from streamdeck import ia, paths

FIX = apoio.FIXTURES
NOW = 1738400000


def _claude_json(ts):
    with open(os.path.join(FIX, "claude_status.json"), "r", encoding="utf-8") as f:
        d = json.load(f)
    os.makedirs(os.path.join(paths.BASE, "ia"), exist_ok=True)
    with open(os.path.join(paths.BASE, "ia", "claude.json"), "w", encoding="utf-8") as f:
        json.dump({"rate_limits": d["rate_limits"], "ts": ts}, f)


class IaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sd-ia-")
        self.old = {k: os.environ.get(k) for k in ("CODEX_HOME", "CLAUDE_CONFIG_DIR")}
        os.environ["CODEX_HOME"] = os.path.join(self.tmp, "codex")
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.tmp, "claude")
        os.makedirs(os.path.join(self.tmp, "claude"))
        ia._CX.update(key=None, val=None, t=0.0)
        cj = os.path.join(paths.BASE, "ia", "claude.json")
        if os.path.exists(cj):
            os.remove(cj)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, True)

    def _codex_file(self, src="codex_session.jsonl"):
        d = os.path.join(self.tmp, "codex", "sessions", "2025", "02", "01")
        os.makedirs(d)
        shutil.copy(os.path.join(FIX, src), os.path.join(d, "rollout-1.jsonl"))
        return os.path.join(d, "rollout-1.jsonl")

    def test_claude_parse(self):
        _claude_json(NOW)
        c = ia.status(now=NOW)["claude"]
        self.assertEqual(c["five_hour"], {"used": 23.5, "left": 76.5, "resets_at": 1738425600})
        self.assertEqual(c["weekly"]["used"], 41.2)
        self.assertEqual(c["source"], "statusline")
        self.assertIsNone(ia.status(now=NOW)["grok"])

    def test_claude_janela_passada(self):
        _claude_json(NOW)
        c = ia.status(now=1738425601)["claude"]
        self.assertEqual((c["five_hour"]["used"], c["five_hour"]["left"]), (0.0, 100.0))
        self.assertIsNone(c["five_hour"]["resets_at"])       # ja passou: celular esconde "reinicia"
        self.assertEqual(c["weekly"]["used"], 41.2)

    def test_claude_velho(self):
        _claude_json(NOW - 86400)
        c = ia.status(now=NOW)["claude"]
        self.assertEqual(c["five_hour"]["used"], 23.5)
        self.assertEqual(c["updated"], NOW - 86400)

    def test_claude_sem_arquivo(self):
        self.assertIsNone(ia.status(now=NOW)["claude"])

    def test_codex_parse(self):
        self._codex_file()
        c = ia.status(now=NOW)["codex"]
        # ultima linha: primary 12.5 (resets_in 3600 desde 10:01:00Z), secondary 33
        self.assertEqual(c["five_hour"]["used"], 12.5)
        self.assertEqual(c["weekly"]["used"], 33.0)
        self.assertEqual(c["weekly"]["resets_at"], 1738857600)
        self.assertEqual(c["source"], "codex-log")

    def test_codex_resets_in_relativo(self):
        self._codex_file()
        c = ia.status(now=1738400000)["codex"]
        # 2025-02-01T10:01:00Z = 1738404060
        self.assertEqual(c["five_hour"]["resets_at"], 1738404060 + 3600)

    def test_codex_formato_desconhecido(self):
        d = os.path.join(self.tmp, "codex", "sessions")
        os.makedirs(d)
        with open(os.path.join(d, "x.jsonl"), "w") as f:
            f.write('{"a": 1}\nnao e json\n{"rate_limits": {"foo": 1}}\n')
        self.assertIsNone(ia.status(now=NOW)["codex"])

    def test_install_preserva_statusline(self):
        sp = os.path.join(self.tmp, "claude", "settings.json")
        prev = {"type": "command", "command": "echo OI", "padding": 2}
        with open(sp, "w") as f:
            json.dump({"model": "opus", "statusLine": prev}, f)
        self.assertFalse(ia.bridge_installed())
        self.assertTrue(ia.install_bridge()["ok"])
        self.assertTrue(ia.bridge_installed())
        with open(sp) as f:
            cfg = json.load(f)
        self.assertEqual(cfg["model"], "opus")
        self.assertEqual(cfg["statusLine"]["padding"], 2)
        self.assertIn("ponte_claude", cfg["statusLine"]["command"])
        with open(os.path.join(paths.BASE, "ia", "statusline_anterior.json")) as f:
            self.assertEqual(json.load(f)["statusLine"], prev)
        ia.install_bridge()    # idempotente: nao sobrescreve o backup
        ia.uninstall_bridge()
        self.assertFalse(ia.bridge_installed())
        with open(sp) as f:
            self.assertEqual(json.load(f), {"model": "opus", "statusLine": prev})

    def test_uninstall_sem_anterior(self):
        ia.install_bridge()
        ia.uninstall_bridge()
        with open(os.path.join(self.tmp, "claude", "settings.json")) as f:
            self.assertNotIn("statusLine", json.load(f))

    def test_ponte_repassa(self):
        os.makedirs(os.path.join(paths.BASE, "ia"), exist_ok=True)
        with open(os.path.join(paths.BASE, "ia", "statusline_anterior.json"), "w") as f:
            json.dump({"statusLine": {"type": "command", "command": "echo OI"}}, f)
        script = os.path.join(paths.PKG_DIR, "ponte_claude.py")
        with open(os.path.join(FIX, "claude_status.json"), "rb") as f:
            entrada = f.read()
        r = subprocess.run([sys.executable, script], input=entrada, stdout=subprocess.PIPE,
                           env=dict(os.environ), timeout=10)
        self.assertIn(b"OI", r.stdout)
        with open(os.path.join(paths.BASE, "ia", "claude.json")) as f:
            self.assertEqual(json.load(f)["rate_limits"]["five_hour"]["used_percentage"], 23.5)
        os.remove(os.path.join(paths.BASE, "ia", "statusline_anterior.json"))
        r = subprocess.run([sys.executable, script], input=entrada, stdout=subprocess.PIPE,
                           env=dict(os.environ), timeout=10)
        self.assertIn("5h 24%".encode(), r.stdout)

    def test_ponte_sem_sys_std(self):
        """Estilo .exe sem console: sys.stdout/stdin None, so descritores."""
        code = ("import sys; sys.stdin = None; sys.stdout = None; sys.stderr = None\n"
                "from streamdeck import ponte_claude; ponte_claude.main()")
        with open(os.path.join(FIX, "claude_status.json"), "rb") as f:
            entrada = f.read()
        r = subprocess.run([sys.executable, "-c", code], input=entrada, stdout=subprocess.PIPE,
                           cwd=apoio.ROOT, env=dict(os.environ), timeout=10)
        self.assertIn("5h 24%".encode(), r.stdout)
        self.assertTrue(os.path.exists(os.path.join(paths.BASE, "ia", "claude.json")))

    def test_settings_com_bom(self):
        sp = os.path.join(self.tmp, "claude", "settings.json")
        with open(sp, "wb") as f:
            f.write(b"\xef\xbb\xbf" + json.dumps({"model": "x"}).encode())
        self.assertTrue(ia.install_bridge()["ok"])
        with open(sp, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["model"], "x")
        self.assertTrue(ia.bridge_installed())

    def test_install_falha_atomica(self):
        sp = os.path.join(self.tmp, "claude", "settings.json")
        with open(sp, "w") as f:
            json.dump({"model": "x"}, f)
        with mock.patch("streamdeck.ia.os.replace", side_effect=PermissionError("preso")):
            r = ia.install_bridge()
        self.assertFalse(r["ok"])
        with open(sp) as f:
            self.assertEqual(json.load(f), {"model": "x"})
        self.assertEqual([n for n in os.listdir(os.path.dirname(sp)) if n.endswith(".tmp")], [])

    def test_backup_primeiro_e_mantido(self):
        sp = os.path.join(self.tmp, "claude", "settings.json")
        with open(sp, "w") as f:
            json.dump({"model": "original"}, f)
        ia.install_bridge()
        ia.uninstall_bridge()
        with open(sp, "w") as f:
            json.dump({"model": "outro"}, f)
        ia.install_bridge()
        with open(sp + ".streamdeck.bak") as f:
            self.assertEqual(json.load(f)["model"], "original")

    def test_frozen_extrai_e_reaponta(self):
        from streamdeck import VERSION
        zp = os.path.join(self.tmp, "ponte.zip")
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr("StreamDeckPonte.exe", "x")
        ia_dir = os.path.join(paths.BASE, "ia")
        shutil.rmtree(ia_dir, True)
        velha = os.path.join(ia_dir, "ponte-0.0.1")
        legado = os.path.join(ia_dir, "ponte")
        for d in (velha, legado):
            os.makedirs(d)
        pasta = os.path.join(ia_dir, "ponte-" + VERSION)
        with mock.patch.object(paths, "FROZEN", True), mock.patch.object(ia, "_ponte_zip", return_value=zp):
            self.assertTrue(ia.install_bridge()["ok"])
            with open(os.path.join(self.tmp, "claude", "settings.json")) as f:
                cmd = json.load(f)["statusLine"]["command"]
            self.assertTrue(cmd.startswith('"') and "\\" not in cmd and cmd.endswith('StreamDeckPonte.exe"'))
            self.assertIn("ponte-" + VERSION + "/", cmd)
            exe = os.path.join(pasta, "StreamDeckPonte.exe")
            self.assertTrue(os.path.exists(exe))
            self.assertFalse(os.path.exists(velha))      # versoes velhas apagadas
            self.assertFalse(os.path.exists(legado))
            self.assertFalse(ia.refresh_bridge())      # em dia
            # pasta da versao atual ja existe com version.txt certo: reaproveita
            with open(exe, "w") as f:
                f.write("mexido")
            os.makedirs(velha)
            with open(os.path.join(self.tmp, "claude", "settings.json"), "w") as f:
                json.dump({"statusLine": {"type": "command", "command": '"%s"' % os.path.join(
                    velha, "StreamDeckPonte.exe").replace("\\", "/")}}, f)
            self.assertTrue(ia.refresh_bridge())       # apontava para versao velha
            with open(exe) as f:
                self.assertEqual(f.read(), "mexido")
            self.assertFalse(os.path.exists(velha))
            with open(os.path.join(pasta, "version.txt"), "w") as f:
                f.write("0.0.1")
            os.remove(exe)
            self.assertTrue(ia.refresh_bridge())       # version.txt errado: extrai de novo
            self.assertTrue(os.path.exists(exe))

    def test_ponte_shell_windows(self):
        from streamdeck import ponte_claude as pc
        with mock.patch.object(pc.sys, "platform", "win32"):
            with mock.patch.object(pc, "_acha_bash", return_value="C:/Git/bin/bash.exe"):
                self.assertEqual(pc._argv("echo a"), ["C:/Git/bin/bash.exe", "-c", "echo a"])
            with mock.patch.object(pc, "_acha_bash", return_value=None):
                self.assertEqual(pc._argv("echo a"), "echo a")      # cai no cmd (shell=True)
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_GIT_BASH_PATH": __file__}):
                self.assertEqual(pc._acha_bash(), __file__)
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_GIT_BASH_PATH": ""}), \
                    mock.patch.object(pc.os.path, "isfile", return_value=False), \
                    mock.patch.object(pc.shutil, "which", return_value="D:/bash.exe"):
                self.assertEqual(pc._acha_bash(), "D:/bash.exe")
        with mock.patch.object(pc.sys, "platform", "linux"):
            self.assertEqual(pc._argv("echo a"), ["/bin/sh", "-c", "echo a"])

    def test_ponte_lixo(self):
        script = os.path.join(paths.PKG_DIR, "ponte_claude.py")
        r = subprocess.run([sys.executable, script], input=b"\xff nao json", stdout=subprocess.PIPE,
                           env=dict(os.environ), timeout=10)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.strip())


if __name__ == "__main__":
    unittest.main()
