# -*- coding: utf-8 -*-
"""Registro de acoes: schema e validate de todos os tipos, e biblioteca."""
import unittest

import apoio  # STREAMDECK_DATA antes de importar streamdeck
from streamdeck import actions, library, schema

# exemplo valido e exemplos invalidos (com trecho esperado do erro) por tipo.
# Acao nova sem exemplo aqui faz test_todo_tipo_tem_exemplo falhar.
EXEMPLOS = {
    "none": ({}, []),
    "hotkey": ({"keys": ["ctrl", "shift", "m"]},
               [({}, "Teclas"), ({"keys": "ctrl+c"}, "teclas"), ({"keys": ["ctrl", "tecla_que_nao_existe"]}, "")]),
    "open": ({"target": "https://example.com/"}, [({}, "preencha")]),
    "command": ({"command": "notepad.exe"}, [({"command": "  "}, "preencha")]),
    "page": ({"to": 1}, [({}, "escolha"), ({"to": 2}, "pagina"), ({"to": -1}, "pagina"), ({"to": True}, "pagina")]),
    "multi": ({"steps": [{"type": "hotkey", "keys": ["a"]}, {"type": "text", "text": "x"}], "delay": 0.5},
              [({"steps": []}, "preencha"), ({"steps": [{"type": "page", "to": 0}]}, "sequencia"),
               ({"steps": [{"type": "multi", "steps": [{"type": "none"}]}]}, "sequencia"),
               ({"steps": [{"type": "hotkey"}]}, "Teclas"),
               ({"steps": [{"type": "none"}], "delay": 61}, "entre")]),
    "sound": ({"file": "vinheta.mp3", "volume": 150, "exclusive": True, "fade_in": 500},
              [({"file": "a.mp3", "fade_in": 5001}, "entre"), ({}, "escolha"), ({"file": "a.mp3", "volume": 201}, "entre"),
               ({"file": "a.mp3", "volume": "alto"}, "numero"), ({"file": ["a"]}, "invalido")]),
    "stopsound": ({"fade": 800}, [({"fade": 6000}, "entre")]),
    "obs_scene": ({"scene": "Cena 1"}, [({}, "preencha"), ({"scene": "a\nb"}, "invalido"),
                                        ({"scene": 5}, "invalido")]),
    "obs_stream": ({"mode": "start"}, [({"mode": "pause"}, "invalido")]),
    "obs_record": ({"mode": "toggle"}, [({"mode": "x"}, "invalido")]),
    "obs_mute": ({"input": "Mic/Aux", "mode": "mute"}, [({}, "preencha"), ({"input": "Mic", "mode": "x"}, "invalido"),
                                                       ({"input": "x" * 121}, "invalido")]),
    "text": ({"text": "Ola!", "enter": False}, [({"text": ""}, "preencha")]),
    "http": ({"method": "POST", "url": "http://127.0.0.1:9000/x", "body": "{}"},
             [({"url": "ftp://x"}, "http"), ({"url": "http://x", "method": "PUT"}, "invalido"), ({}, "preencha")]),
    "mute": ({"target": "mic"}, [({"target": "bass"}, "invalido")]),
    "app": ({"target": "obs64.exe"}, [({}, "preencha"), ({"target": "\\\\srv\\x.exe"}, "rede"),
                                      ({"target": "a\nb"}, "invalido")]),
    "apphotkey": ({"app": "discord.exe", "keys": ["ctrl", "shift", "m"], "back": True},
                  [({"app": "discord.exe"}, "Teclas"), ({"keys": ["a"]}, "preencha")]),
    "site": ({"url": "https://www.youtube.com/", "browser": "chrome", "profile": "Profile 1", "appmode": True},
             [({"url": "www.x.com"}, "http"), ({"url": "https://x", "browser": "opera"}, "invalido"),
              ({"url": "https://x", "profile": 'a"b'}, "perfil")]),
    "browser": ({"op": "open_url", "url": "https://www.youtube.com/"},
                [({}, "escolha"), ({"op": "x"}, "invalido"), ({"op": "open_url", "url": "javascript:x"}, "http"),
                 ({"op": "scroll", "dir": "x"}, "invalido")]),
    "tab": ({"browser": "edge", "title": "YouTube"}, [({}, "preencha"), ({"title": "x", "browser": "x"}, "invalido")]),
}


class RegistroTest(unittest.TestCase):
    def test_todo_tipo_tem_exemplo(self):
        faltando = set(actions.REGISTRY) - set(EXEMPLOS)
        self.assertFalse(faltando, "acoes sem exemplo em tests/test_acoes.py: %s" % sorted(faltando))

    def test_schema(self):
        sch = actions.schema()
        tipos = [s["type"] for s in sch]
        self.assertEqual(len(tipos), len(set(tipos)))
        self.assertEqual(set(tipos), set(actions.REGISTRY))
        self.assertEqual(tipos[:len(actions.ORDER)], [t for t in actions.ORDER if t in actions.REGISTRY])
        for s in sch:
            for k in ("type", "label", "group", "icon", "help", "fields"):
                self.assertIn(k, s, s["type"])
            self.assertTrue(s["label"])
            chaves = [f["key"] for f in s["fields"]]
            self.assertEqual(len(chaves), len(set(chaves)), s["type"])
            for f in s["fields"]:
                self.assertIn(f["kind"], actions.FIELD_KINDS)
                self.assertTrue(f["label"])
                if f["kind"] == "select":
                    self.assertTrue(f["options"])
                    for o in f["options"]:
                        self.assertEqual(set(o), {"value", "label"})
                    if "default" in f:
                        self.assertIn(f["default"], [o["value"] for o in f["options"]])
                if f["kind"] == "number" and "default" in f:
                    self.assertTrue(f.get("min", f["default"]) <= f["default"] <= f.get("max", f["default"]))

    def test_validos(self):
        for t, (ok, _) in EXEMPLOS.items():
            if t not in actions.REGISTRY:
                continue
            a = dict(ok, type=t)
            actions.validate(a, 2, "teste %s" % t)

    def test_invalidos(self):
        for t, (_, ruins) in EXEMPLOS.items():
            if t not in actions.REGISTRY:
                continue
            for extra, trecho in ruins:
                a = dict(extra, type=t)
                with self.assertRaises(ValueError, msg="%s %r" % (t, extra)) as cm:
                    actions.validate(a, 2, "W")
                msg = str(cm.exception)
                self.assertTrue(msg.startswith("W"), msg)
                self.assertIn(trecho, msg, "%s %r" % (t, extra))

    def test_tipo_desconhecido(self):
        for a in ({"type": "x"}, {}, None, "hotkey"):
            with self.assertRaises(ValueError):
                actions.validate(a, 1, "W")
        with self.assertRaises(ValueError):
            actions.run({"type": "x"})

    def test_acao_repetida(self):
        with self.assertRaises(ValueError):
            actions.action("none", "de novo")(lambda a: None)

    def test_campo_de_tipo_desconhecido(self):
        with self.assertRaises(ValueError):
            actions.Field("x", "X", "cor")

    def test_run_simulado(self):
        # fora do Windows estas acoes so imprimem; none/page nao fazem nada
        actions.run({"type": "none"})
        actions.run({"type": "page", "to": 0})
        del apoio.KEYS[:]
        actions.run({"type": "hotkey", "keys": ["ctrl", "c"]})
        actions.run({"type": "text", "text": "oi", "enter": True})
        actions.run({"type": "multi", "steps": [{"type": "hotkey", "keys": ["a"]}, {"type": "none"}], "delay": 0})
        self.assertEqual(apoio.KEYS, [("keys", ["ctrl", "c"]), ("text", "oi", True), ("keys", ["a"])])


class BibliotecaTest(unittest.TestCase):
    def test_check(self):
        library.check()

    def test_grupos(self):
        gs = library.groups()
        self.assertTrue(gs)
        for g in gs:
            self.assertTrue(g["name"])
            self.assertTrue(g["items"])
            for it in g["items"]:
                self.assertTrue(it["label"])
                self.assertIn(it["action"]["type"], actions.REGISTRY)
        # copia: mexer no resultado nao altera a biblioteca
        gs[0]["items"][0]["label"] = "mudado"
        self.assertNotEqual(library.groups()[0]["items"][0]["label"], "mudado")

    def test_check_pega_item_ruim(self):
        ruim = {"name": "X", "items": [{"label": "ruim", "action": {"type": "hotkey", "keys": []}}]}
        library.LIBRARY.append(ruim)
        try:
            with self.assertRaises(ValueError):
                library.check()
        finally:
            library.LIBRARY.remove(ruim)

    def test_icones_existem_no_core_js(self):
        import re
        with open(apoio.ROOT + "/web/js/core.js", encoding="utf-8") as f:
            js = f.read()
        bloco = js[js.index("SD.ICONS = {"):]
        bloco = bloco[:bloco.index("\n  };")]
        nomes = set(re.findall(r"^\s{4}([a-z0-9_]+)\s*:", bloco, re.M))
        self.assertTrue(nomes)
        for g in library.groups():
            for it in g["items"]:
                self.assertIn(it["icon"], nomes, it["label"])


class BotaoDaBibliotecaNoSchemaTest(unittest.TestCase):
    def test_validate_button_aceita_item(self):
        it = library.groups()[0]["items"][0]
        it.pop("help", None)
        schema.validate_button(it, 1, "x")

if __name__ == "__main__":
    unittest.main()
