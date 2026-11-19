# -*- coding: utf-8 -*-
"""2.6: campos novos do botao (hold, double, confirm, live, lit), /api/press
com g=tap|hold|double, sons tocando no /api/state e rotas do OBS."""
import os
import time
import unittest
import wave

import apoio
from streamdeck import audio, obs, paths, schema, storage
from test_http import call


def botao(**extra):
    b = {"label": "B", "action": {"type": "none"}}
    b.update(extra)
    return b


class SchemaTest(unittest.TestCase):
    def ok(self, b, n=2):
        schema.validate_button(b, n, "W")

    def ruim(self, b, trecho="", n=2):
        with self.assertRaises(ValueError) as cm:
            schema.validate_button(b, n, "W")
        self.assertIn(trecho, str(cm.exception))

    def test_hold_double(self):
        self.ok(botao(hold={"type": "hotkey", "keys": ["a"]}, double={"type": "page", "to": 1}))
        self.ok(botao(hold=None))
        self.ruim(botao(hold={"type": "hotkey", "keys": []}), "segurar")
        self.ruim(botao(double={"type": "xyz"}), "duplo")
        self.ruim(botao(double={"type": "page", "to": 5}), "pagina")
        self.ruim(botao(hold="hotkey"), "tipo de acao")

    def test_confirm(self):
        self.ok(botao(confirm=True))
        self.ok(botao(confirm=False))
        self.ruim(botao(confirm="sim"), "confirm")

    def test_live(self):
        for v in ("obs:stream", "obs:record", "obs:scene", "sound", "clock", ""):
            self.ok(botao(live=v))
        self.ruim(botao(live="obs:mute"), "ao vivo")

    def test_lit(self):
        for v in ("obs:stream", "obs:record", "obs:scene=Cena 1", "obs:mute=Mic/Aux", "obs:scene=Á é", ""):
            self.ok(botao(lit=v))
        for v in ("obs:scene=", "obs:x", "obs:mute=a\nb", "obs:scene=" + "x" * 111, 5, "obs:stream "):
            self.ruim(botao(lit=v), "OBS")

    def test_dentro_de_pasta(self):
        pasta = {"kind": "folder", "label": "P", "buttons": [botao(hold={"type": "stopsound"}, confirm=True,
                                                                   lit="obs:record", live="sound")]}
        self.ok(pasta)
        pasta["buttons"][0]["double"] = {"type": "nada"}
        self.ruim(pasta, "item 1")

    def test_config_inteiro(self):
        cfg = apoio.base_config()
        cfg["pages"][0]["buttons"][1]["hold"] = {"type": "obs_stream", "mode": "stop"}
        cfg["pages"][0]["buttons"][1]["lit"] = "obs:stream"
        schema.validate_config(cfg)


def _wav(nome, segundos):
    os.makedirs(paths.SOUNDS_DIR, exist_ok=True)
    caminho = os.path.join(paths.SOUNDS_DIR, nome)
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * segundos))
    return caminho


class PressTest(unittest.TestCase):
    def setUp(self):
        _wav("dois.wav", 2.0)
        cfg = apoio.base_config()
        b = cfg["pages"][0]["buttons"]
        b[0]["hold"] = {"type": "text", "text": "segurou"}
        b[0]["double"] = {"type": "text", "text": "duplo"}
        b[2] = {"label": "Som", "action": {"type": "sound", "file": "dois.wav", "fade_in": 200}}
        b[3]["buttons"][1]["hold"] = {"type": "sound", "file": "dois.wav"}
        apoio.write_config(cfg)
        audio.PLAYER.stop_all()
        del apoio.KEYS[:]

    def tearDown(self):
        audio.PLAYER.stop_all()
        apoio.write_config(apoio.base_config())

    def test_gestos(self):
        with apoio.quiet():
            st, _, r = call("GET", "/api/state")
            ligado = "0:0" in r["toggles"]
            st, _, r = call("GET", "/api/press?p=0&b=0&g=hold")
            self.assertEqual(st, 200, r)
            st, _, r = call("GET", "/api/press?p=0&b=0&g=double")
            self.assertEqual(st, 200, r)
            # toggle so muda no toque simples
            self.assertEqual("0:0" in r["toggles"], ligado)
            st, _, r = call("GET", "/api/press?p=0&b=0&g=tap")
            self.assertNotEqual("0:0" in r["toggles"], ligado)
            st, _, r = call("GET", "/api/press?p=0&b=0")
            self.assertEqual("0:0" in r["toggles"], ligado)
            st, _, r = call("GET", "/api/press?p=0&b=0&g=triplo")
            self.assertEqual(st, 400)
            st, _, r = call("GET", "/api/press?p=0&b=1&g=hold")   # sem acao ao segurar
            self.assertEqual(st, 400)
            self.assertIn("segurar", r["error"])
        self.assertEqual(apoio.KEYS, [("text", "segurou", False), ("text", "duplo", False)])

    def test_sons_no_state(self):
        with apoio.quiet():
            st, _, r = call("GET", "/api/press?p=0&b=2")
            self.assertEqual(st, 200, r)
            st, _, r = call("GET", "/api/press?p=0&b=3&f=1&g=hold")
            self.assertEqual(st, 200, r)
            st, _, r = call("GET", "/api/state")
        sons = r["sounds"]
        self.assertEqual([s["key"] for s in sons], ["0:2", "0:3:1"])
        for s in sons:
            self.assertEqual(s["file"], "dois.wav")
            self.assertAlmostEqual(s["dur"], 2.0, places=2)
            self.assertTrue(0 <= s["pos"] <= 2.0)
        with apoio.quiet():
            call("GET", "/api/press?p=0&b=0")    # outro botao nao mexe nos sons
            audio.PLAYER.stop_all(1000)          # simulado: para na hora
            st, _, r = call("GET", "/api/state")
        self.assertEqual(r["sounds"], [])

    def test_som_termina_sai_da_lista(self):
        caminho = _wav("curto.wav", 0.05)
        audio.PLAYER.play(caminho, key="9:9")
        self.assertEqual(len(audio.PLAYER.sounds()), 1)
        time.sleep(0.5)
        self.assertEqual(audio.PLAYER.sounds(), [])

    def test_exclusivo_tira_os_outros(self):
        caminho = _wav("dois.wav", 2.0)
        audio.PLAYER.play(caminho, key="1:1")
        audio.PLAYER.play(caminho, key="1:2", exclusive=True)
        self.assertEqual([s["key"] for s in audio.PLAYER.sounds()], ["1:2"])

    def test_duracao_simulada_sem_wav(self):
        os.makedirs(paths.SOUNDS_DIR, exist_ok=True)
        caminho = os.path.join(paths.SOUNDS_DIR, "x.mp3")
        with open(caminho, "wb") as f:
            f.write(b"\x00" * 100)
        audio.PLAYER.play(caminho, key="2:2")
        self.assertEqual(audio.PLAYER.sounds()[0]["dur"], 3.0)


class FadeTest(unittest.TestCase):
    """Saida suave age so no retrato do inicio; fader respeita o fator."""

    def setUp(self):
        self.p = audio.SoundPlayer.__new__(audio.SoundPlayer)
        self.p.playing, self.p.pcm = [], []
        import threading
        self.p.pcm_lock = self.p.tracks_lock = threading.Lock()
        self.p.tracks, self.p.level, self.p.muted = [], 100, False
        self.rampas = []
        self.p._ramp = lambda ms, make: self.rampas.append(make)
        self.velho = audio.IS_WINDOWS

    def tearDown(self):
        audio.IS_WINDOWS = self.velho

    def test_retrato(self):
        t1 = {"done": False}
        self.p.playing.append(["a1", 100, t1, 1.0, False])
        audio.IS_WINDOWS = True
        vols = []
        self.p._mci_vol = lambda alias, v, f=1.0: vols.append((alias, f))
        self.p._close = lambda alias: None
        self.p._handle(("stop", 500))
        make = self.rampas[0]
        t2 = {"done": False}
        self.p.playing.append(["a2", 100, t2, 1.0, False])   # comecou durante a saida
        self.p._handle(make(5))
        self.assertEqual(self.p.playing[0][3], 0.5)
        self.assertEqual(self.p.playing[1][3], 1.0)
        # fader mexeu no meio: mantem o fator
        vols[:] = []
        self.p._handle(("vol",))
        self.assertEqual(vols, [("a1", 0.5), ("a2", 1.0)])
        self.p._handle(make(audio.FADE_STEPS))
        self.assertEqual([e[0] for e in self.p.playing], ["a2"])
        self.assertTrue(t1["done"])
        self.assertFalse(t2["done"])

    def test_play_poda(self):
        self.p.q = type("Q", (), {"put": lambda s, x: None})()
        for i in range(50):
            self.p.play("/x/nao.wav", key="k%d" % i, exclusive=True)
        self.assertEqual(len(self.p.tracks), 1)


class ObsRotasTest(unittest.TestCase):
    def tearDown(self):
        data = storage.load_settings()
        data.pop("obs", None)
        storage.save_settings(data)
        obs.CLIENT.stop()
        if obs.CLIENT.thread is not None:
            obs.CLIENT.thread.join(5)
        obs.CLIENT.stopped = False
        obs.CLIENT.thread = None

    def test_sem_obs_no_state(self):
        with apoio.quiet():
            st, _, r = call("GET", "/api/state")
        self.assertNotIn("obs", r)

    def test_ajustes(self):
        with apoio.quiet():
            st, _, r = call("GET", "/api/local/obs")
            self.assertEqual((r["host"], r["port"], r["has_password"], r["connected"]), ("127.0.0.1", 4455, False, False))
            st, _, r = call("POST", "/api/local/obs", {"host": "127.0.0.1", "port": 9, "password": "abc"})
            self.assertEqual(st, 200, r)
            self.assertTrue(r["has_password"])
            self.assertNotIn("password", r)
            self.assertNotIn("abc", str(r))
            # sem senha no corpo: mantem a anterior
            st, _, r = call("POST", "/api/local/obs", {"host": "127.0.0.1", "port": 9})
            self.assertTrue(r["has_password"])
            self.assertEqual(storage.load_settings()["obs"]["password"], "abc")
            st, _, r = call("POST", "/api/local/obs", {"host": "a b", "port": 9})
            self.assertEqual(st, 400)
            st, _, r = call("POST", "/api/local/obs", {"port": 70000})
            self.assertEqual(st, 400)
            st, _, r = call("GET", "/api/local/obs/scenes")
            self.assertFalse(r["ok"])
            self.assertIn("conectado", r["error"])
            st, _, r = call("GET", "/api/state")
            self.assertEqual(r["obs"]["ok"], False)

    def test_so_no_pc(self):
        for metodo, rota in (("GET", "/api/local/obs"), ("GET", "/api/local/obs/scenes"),
                             ("POST", "/api/local/obs")):
            with apoio.quiet():
                st, _, _ = apoio.fake_request(metodo, rota, body=b"{}" if metodo == "POST" else b"")
            self.assertEqual(st, 403, rota)


if __name__ == "__main__":
    unittest.main()
