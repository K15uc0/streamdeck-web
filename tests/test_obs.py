# -*- coding: utf-8 -*-
"""Cliente do OBS: quadros WebSocket, handshake, autenticacao e um servidor
obs-websocket falso (numa thread) para testar conexao, pedidos, eventos,
estado em cache e reconexao."""
import base64
import hashlib
import json
import socketserver
import struct
import threading
import time
import unittest

import apoio  # noqa: F401  (STREAMDECK_DATA antes de importar streamdeck)
from streamdeck import actions, obs


def esperar(cond, limite=3.0):
    fim = time.time() + limite
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


class QuadrosTest(unittest.TestCase):
    def test_ida_e_volta_tamanhos(self):
        for n in (0, 5, 125, 126, 300, 65535, 65536, 70000):
            dado = bytes(i % 251 for i in range(n))
            for mask in (True, False):
                q = obs.encode_frame(obs.OP_TEXT, dado, mask=mask)
                fin, op, payload, resto = obs.decode_frame(q + b"xy")
                self.assertTrue(fin)
                self.assertEqual(op, obs.OP_TEXT)
                self.assertEqual(payload, dado)
                self.assertEqual(resto, b"xy")

    def test_mascara_conhecida(self):
        # exemplo da RFC 6455 (5.7): "Hello" mascarado com 37 fa 21 3d
        q = obs.encode_frame(obs.OP_TEXT, b"Hello", mask_key=b"\x37\xfa\x21\x3d")
        self.assertEqual(q, bytes([0x81, 0x85, 0x37, 0xfa, 0x21, 0x3d, 0x7f, 0x9f, 0x4d, 0x51, 0x58]))
        self.assertEqual(obs.decode_frame(q)[2], b"Hello")
        # sem mascara (servidor)
        self.assertEqual(obs.encode_frame(obs.OP_TEXT, b"Hello", mask=False), b"\x81\x05Hello")

    def test_fragmento_e_controle(self):
        q = obs.encode_frame(obs.OP_TEXT, b"Hel", fin=False, mask=False)
        fin, op, p, _ = obs.decode_frame(q)
        self.assertEqual((fin, op, p), (False, obs.OP_TEXT, b"Hel"))
        fin, op, p, _ = obs.decode_frame(obs.encode_frame(obs.OP_PING, b"x"))
        self.assertEqual((fin, op, p), (True, obs.OP_PING, b"x"))

    def test_quadro_incompleto(self):
        with self.assertRaises(ValueError):
            obs.decode_frame(b"\x81\x05He")

    def test_accept_rfc(self):
        # exemplo da RFC 6455 (1.3)
        self.assertEqual(obs.accept_key("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def test_autenticacao(self):
        senha, salt, desafio = "supersecretpassword", "lM1GncleQOaCu9lT1yeUZhFYnqhsLLP1G5lAGo3ixaI=", \
            "+IxH4CnCiqpX1rM9scsNynZzbOe4KhDeYcTNS3PDaeY="
        s1 = base64.b64encode(hashlib.sha256((senha + salt).encode()).digest())
        esperado = base64.b64encode(hashlib.sha256(s1 + desafio.encode()).digest()).decode()
        self.assertEqual(obs.auth_string(senha, salt, desafio), esperado)
        self.assertNotEqual(obs.auth_string("outra", salt, desafio), esperado)


# ------------------------------------------------------------ OBS falso ---
class FakeObs(object):
    """Servidor obs-websocket v5 minimo."""

    def __init__(self, password=None):
        self.password = password
        self.salt, self.challenge = "c2FsdA==", "ZGVzYWZpbw=="
        self.scene = "Cena 1"
        self.stream = self.record = False
        self.muted = {"Mic/Aux": False, "Desktop": True}
        self.requests = []
        self.conns = []
        self.identify = None
        self.mudo = False
        fake = self

        class H(socketserver.BaseRequestHandler):
            def handle(self):
                fake._serve(self.request)

        class S(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True
        self.srv = S(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.kick()

    def kick(self):
        for c in list(self.conns):
            try:
                c.shutdown(2)
                c.close()
            except OSError:
                pass

    def _send(self, sock, obj, fragment=False):
        data = json.dumps(obj).encode()
        if fragment and len(data) > 4:
            meio = len(data) // 2
            sock.sendall(obs.encode_frame(obs.OP_TEXT, data[:meio], mask=False, fin=False) +
                         obs.encode_frame(obs.OP_PING, b"p", mask=False) +
                         obs.encode_frame(obs.OP_CONT, data[meio:], mask=False))
        else:
            sock.sendall(obs.encode_frame(obs.OP_TEXT, data, mask=False))

    def event(self, kind, data):
        for c in list(self.conns):
            try:
                self._send(c, {"op": 5, "d": {"eventType": kind, "eventIntent": 1, "eventData": data}})
            except OSError:
                pass

    def _serve(self, sock):
        def recv(n):
            return obs._recv_exact(sock, n)
        head = b""
        while b"\r\n\r\n" not in head:
            c = sock.recv(1)
            if not c:
                return
            head += c
        key = [l.split(":", 1)[1].strip() for l in head.decode().split("\r\n")
               if l.lower().startswith("sec-websocket-key:")][0]
        sock.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      "Sec-WebSocket-Accept: %s\r\nSec-WebSocket-Protocol: obswebsocket.json\r\n\r\n"
                      % obs.accept_key(key)).encode())
        self.conns.append(sock)
        hello = {"obsWebSocketVersion": "5.0.0", "rpcVersion": 1}
        if self.password:
            hello["authentication"] = {"challenge": self.challenge, "salt": self.salt}
        self._send(sock, {"op": 0, "d": hello})
        try:
            while True:
                fin, op, data = obs.read_frame(recv)
                if op == obs.OP_CLOSE:
                    return
                if op != obs.OP_TEXT:
                    continue
                m = json.loads(data.decode())
                if m["op"] == 1:
                    self.identify = m["d"]
                    if self.password and m["d"].get("authentication") != obs.auth_string(
                            self.password, self.salt, self.challenge):
                        sock.sendall(obs.encode_frame(obs.OP_CLOSE, struct.pack("!H", 4009), mask=False))
                        return
                    self._send(sock, {"op": 2, "d": {"negotiatedRpcVersion": 1}})
                elif m["op"] == 6:
                    if self.mudo:
                        continue
                    self._request(sock, m["d"])
        except (ConnectionError, OSError, ValueError):
            return
        finally:
            if sock in self.conns:
                self.conns.remove(sock)

    def _request(self, sock, d):
        kind, data = d["requestType"], d.get("requestData") or {}
        self.requests.append((kind, data))
        out, ok, events = {}, True, []
        if kind == "GetCurrentProgramScene":
            out = {"currentProgramSceneName": self.scene, "sceneName": self.scene}
        elif kind == "GetStreamStatus":
            out = {"outputActive": self.stream}
        elif kind == "GetRecordStatus":
            out = {"outputActive": self.record}
        elif kind == "GetSceneList":
            out = {"currentProgramSceneName": self.scene,
                   "scenes": [{"sceneName": "Cena 2", "sceneIndex": 1}, {"sceneName": "Cena 1", "sceneIndex": 0}]}
        elif kind == "GetInputList":
            out = {"inputs": [{"inputName": "Mic/Aux", "inputKind": "wasapi_input_capture"},
                              {"inputName": "Desktop", "inputKind": "wasapi_output_capture"},
                              {"inputName": "Camera", "inputKind": "dshow_input"}]}
        elif kind == "GetInputMute":
            if data["inputName"] in self.muted:
                out = {"inputMuted": self.muted[data["inputName"]]}
            else:
                ok = False
        elif kind == "SetCurrentProgramScene":
            self.scene = data["sceneName"]
            events.append(("CurrentProgramSceneChanged", {"sceneName": self.scene}))
        elif kind == "ToggleStream":
            self.stream = not self.stream
            events.append(("StreamStateChanged", {"outputActive": self.stream, "outputState": "x"}))
        elif kind == "StartRecord":
            self.record = True
            events.append(("RecordStateChanged", {"outputActive": True}))
        elif kind == "ToggleInputMute":
            self.muted[data["inputName"]] = not self.muted[data["inputName"]]
            events.append(("InputMuteStateChanged", {"inputName": data["inputName"],
                                                     "inputMuted": self.muted[data["inputName"]]}))
        elif kind == "SetInputMute":
            self.muted[data["inputName"]] = data["inputMuted"]
        elif kind == "Lento":
            return    # nunca responde
        else:
            ok = False
        resp = {"op": 7, "d": {"requestType": kind, "requestId": d["requestId"],
                               "requestStatus": {"result": ok, "code": 100 if ok else 600,
                                                 "comment": None if ok else "nao existe"},
                               "responseData": out}}
        self._send(sock, resp, fragment=(kind == "GetSceneList"))
        for k, v in events:
            self.event(k, v)


class ClienteTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeObs()
        self.cfg = {"host": "127.0.0.1", "port": self.fake.port}
        self.cli = obs.ObsClient(lambda: self.cfg, lambda: ["Mic/Aux"])
        self.cli.retry = 0.1

    def tearDown(self):
        self.cli.stop()
        self.fake.stop()

    def conectar(self):
        self.cli.start()
        self.assertTrue(esperar(self.cli.connected), self.cli.error)

    def test_conecta_e_carrega_estado(self):
        self.conectar()
        self.assertEqual(self.fake.identify["eventSubscriptions"] & obs.SUB_OUTPUTS, obs.SUB_OUTPUTS)
        self.assertNotIn("authentication", self.fake.identify)
        self.assertTrue(esperar(lambda: self.cli.snapshot()["muted"].get("Desktop")))
        snap = self.cli.snapshot()
        self.assertEqual(snap, {"ok": True, "stream": False, "record": False, "scene": "Cena 1",
                                "muted": {"Mic/Aux": False, "Desktop": True}})
        self.assertEqual(self.cli.scenes, ["Cena 1", "Cena 2"])
        self.assertEqual(self.cli.inputs, ["Mic/Aux", "Desktop", "Camera"])

    def test_pedidos_e_eventos(self):
        self.conectar()
        self.cli.request("SetCurrentProgramScene", {"sceneName": "Cena 2"})
        self.cli.request("ToggleStream")
        self.cli.request("ToggleInputMute", {"inputName": "Mic/Aux"})
        self.assertTrue(esperar(lambda: self.cli.snapshot()["scene"] == "Cena 2"))
        self.assertTrue(esperar(lambda: self.cli.snapshot()["stream"]))
        self.assertTrue(esperar(lambda: self.cli.snapshot()["muted"].get("Mic/Aux")))
        with self.assertRaises(obs.ObsError) as cm:
            self.cli.request("NaoExiste")
        self.assertIn("nao existe", str(cm.exception))
        t0 = time.time()
        with self.assertRaises(obs.ObsError) as cm:
            self.cli.request("Lento", timeout=0.3)
        self.assertLess(time.time() - t0, 2)
        self.assertIn("tempo", str(cm.exception))

    def test_acoes_usam_o_cliente(self):
        self.conectar()
        velho = obs.CLIENT
        obs.CLIENT = self.cli
        try:
            actions.run({"type": "obs_scene", "scene": "Cena 2"})
            actions.run({"type": "obs_stream", "mode": "toggle"})
            actions.run({"type": "obs_record", "mode": "start"})
            actions.run({"type": "obs_mute", "input": "Desktop", "mode": "unmute"})
            actions.run({"type": "obs_mute", "input": "Mic/Aux"})
        finally:
            obs.CLIENT = velho
        feitos = [r for r in self.fake.requests if not r[0].startswith("Get")]
        self.assertEqual(feitos, [("SetCurrentProgramScene", {"sceneName": "Cena 2"}), ("ToggleStream", {}),
                                  ("StartRecord", {}),
                                  ("SetInputMute", {"inputName": "Desktop", "inputMuted": False}),
                                  ("ToggleInputMute", {"inputName": "Mic/Aux"})])

    def test_reconecta(self):
        self.conectar()
        self.fake.kick()
        self.assertTrue(esperar(lambda: not self.cli.connected()))
        self.assertTrue(esperar(self.cli.connected), self.cli.error)
        self.cli.request("ToggleStream")

    def test_sem_conexao_erro_claro(self):
        self.fake.stop()
        self.cli.start()
        self.assertTrue(esperar(lambda: self.cli.error))
        with self.assertRaises(obs.ObsError) as cm:
            self.cli.request("ToggleStream")
        self.assertIn("OBS nao esta conectado", str(cm.exception))
        self.assertEqual(self.cli.snapshot()["ok"], False)


class RobustezTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeObs()
        self.cfg = {"host": "127.0.0.1", "port": self.fake.port}
        self.cli = obs.ObsClient(lambda: self.cfg, lambda: [])
        self.cli.retry = 0.1

    def tearDown(self):
        self.cli.stop()
        self.fake.stop()

    def test_keepalive_e_queda_silenciosa(self):
        self.cli.idle = 0.3
        self.cli.start()
        self.assertTrue(esperar(self.cli.connected))
        self.assertTrue(esperar(lambda: any(r[0] == "GetVersion" for r in self.fake.requests)))
        self.assertTrue(self.cli.connected())     # respondeu: segue
        # OBS para de responder (sem fechar): cai e reconecta
        self.fake.mudo = True
        self.assertTrue(esperar(lambda: not self.cli.connected(), 3))
        self.fake.mudo = False
        self.assertTrue(esperar(self.cli.connected, 3))

    def test_reconnect_limpa_erro_e_nao_marca_erro(self):
        self.cli.start()
        self.assertTrue(esperar(self.cli.connected))
        self.cli.error = "velho"
        g = self.cli.gen
        self.cli.reconnect()
        self.assertEqual(self.cli.error, "")
        self.assertGreater(self.cli.gen, g)
        self.assertTrue(esperar(self.cli.connected))
        time.sleep(0.2)
        self.assertEqual(self.cli.error, "")

    def test_geracao_muda_no_handshake(self):
        def lento(sock):
            self.cli.gen += 1          # ajustes mudaram durante a negociacao
        velho = obs.WebSocket.__init__

        def init(ws, *a, **k):
            k.pop("on_sock", None)
            velho(ws, *a, on_sock=lento, **k)
        obs.WebSocket.__init__ = init
        try:
            self.cli._session(self.cli.gen)
        finally:
            obs.WebSocket.__init__ = velho
        self.assertIsNone(self.cli.ws)

    def test_mute_evento_mais_novo_vence(self):
        self.cli.state["muted"] = {"Desktop": True}
        self.cli.mute_ev["Mic/Aux"] = time.time() + 10
        self.cli.state["muted"]["Mic/Aux"] = True
        respostas = {"GetInputList": {"inputs": [{"inputName": "Mic/Aux", "inputKind": "wasapi"},
                                                 {"inputName": "Desktop", "inputKind": "wasapi"}]},
                     "GetInputMute": {"inputMuted": False}}
        self.cli.request = lambda kind, data=None: respostas[kind]
        self.cli._fetch_inputs()
        self.assertEqual(self.cli.state["muted"], {"Mic/Aux": True, "Desktop": False})

    def test_cache_de_ajustes(self):
        from streamdeck import storage
        data = storage.load_settings()
        data["obs"] = {"host": "h", "port": 1}
        storage.save_settings(data)
        self.assertEqual(obs.cached_settings()["host"], "h")
        data.pop("obs")
        storage.save_settings(data)
        self.assertEqual(obs.cached_settings(), {})


class SenhaTest(unittest.TestCase):
    def test_senha(self):
        fake = FakeObs(password="segredo")
        cfg = {"host": "127.0.0.1", "port": fake.port, "password": "errada"}
        cli = obs.ObsClient(lambda: cfg)
        cli.retry = 0.1
        try:
            cli.start()
            self.assertTrue(esperar(lambda: "senha" in cli.error), cli.error)
            self.assertFalse(cli.connected())
            cfg["password"] = "segredo"
            cli.reconnect()
            self.assertTrue(esperar(cli.connected), cli.error)
            self.assertEqual(fake.identify["authentication"], obs.auth_string("segredo", fake.salt, fake.challenge))
            cfg["password"] = ""
            cli.reconnect()
            self.assertTrue(esperar(lambda: "informe a senha" in cli.error), cli.error)
        finally:
            cli.stop()
            fake.stop()


if __name__ == "__main__":
    unittest.main()
