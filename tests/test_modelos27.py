# -*- coding: utf-8 -*-
"""2.7: icones (nome ou emoji:), modelos de pagina e GET /api/templates."""
import copy
import json
import re
import unittest

import apoio
from streamdeck import library, schema, storage, templates


def _nomes_core():
    with open(apoio.ROOT + "/web/js/core.js", encoding="utf-8") as f:
        js = f.read()
    bloco = js[js.index("SD.ICONS = {"):]
    bloco = bloco[:bloco.index("\n  };")]
    return js, set(re.findall(r"^\s{4}([a-z0-9_]+)\s*:", bloco, re.M))


def _btn(icon, on_icon=None):
    b = {"label": "x", "icon": icon, "action": {"type": "none"}}
    if on_icon is not None:
        b["on"] = {"icon": on_icon}
    return b


class IconeTest(unittest.TestCase):
    def test_aceitos(self):
        for ic in ("", "play", "num1", "emoji:🎙", "emoji:a", "emoji:12345678", "emoji:👨‍👩‍👧"):
            schema.validate_button(_btn(ic), 1, "t")
            schema.validate_button(_btn("play", ic), 1, "t")

    def test_recusados(self):
        for ic in ("emoji:", "emoji:123456789", "emoji:<b>", "emoji:a>b", "emoji:\x01", "emoji:a\nb",
                   "emoji:   ", "Play", "com espaco", "<svg>", "x" * 41, "emoji:&amp", 5):
            with self.assertRaises(ValueError, msg=repr(ic)):
                schema.validate_button(_btn(ic), 1, "t")
            with self.assertRaises(ValueError, msg=repr(ic)):
                schema.validate_button(_btn("play", ic), 1, "t")

    def test_migracao_limpa_icone_antigo_invalido(self):
        v1 = {"pages": [{"name": "A", "buttons": [{"label": "a", "icon": "<x>", "action": {"type": "none"}},
                                                  {"label": "b", "icon": "emoji:🔥", "action": {"type": "none"}}]}]}
        out = schema.migrate_v1(v1)
        self.assertEqual(out["pages"][0]["buttons"][0]["icon"], "")
        self.assertEqual(out["pages"][0]["buttons"][1]["icon"], "emoji:🔥")


class ConjuntoDeIconesTest(unittest.TestCase):
    def test_tamanho_e_meta(self):
        js, nomes = _nomes_core()
        self.assertGreaterEqual(len(nomes), 140)
        for n in nomes:
            self.assertTrue(schema.valid_icon(n), n)
        meta = js[js.index("SD.ICON_META = SD.ICON_META"):]
        meta = meta[:meta.index("]);")]
        linhas = re.findall(r'^\s{4}"([a-z0-9_]+)\|([^|"]+)\|([^"]+)"', meta, re.M)
        self.assertEqual(set(x[0] for x in linhas), nomes)
        self.assertEqual(len(linhas), len(nomes))

    def test_icones_usados_existem(self):
        _, nomes = _nomes_core()
        for t in templates.TEMPLATES:
            self.assertIn(t["icon"], nomes, t["id"])
            for b in t["page"]["buttons"]:
                for o in (b, b.get("on") or {}):
                    if o.get("icon"):
                        self.assertIn(o["icon"], nomes, "%s / %s" % (t["id"], b.get("label")))
        for g in library.groups():
            for it in g["items"]:
                self.assertIn(it["icon"], nomes, it["label"])


class ModelosTest(unittest.TestCase):
    def test_modelos_validos(self):
        templates.check()
        ids = [t["id"] for t in templates.TEMPLATES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 6)
        for t in templates.TEMPLATES:
            self.assertTrue(t["name"] and t["desc"] and t["page"]["name"])
            self.assertLessEqual(len(t["page"]["buttons"]), 15)

    def test_modelo_vira_config_valida(self):
        cfg = apoio.base_config()
        for t in templates.templates():
            cfg["pages"].append(copy.deepcopy(t["page"]))
        schema.validate_config(cfg)

    def test_copia_independente(self):
        a = templates.templates()
        a[0]["page"]["buttons"][0]["label"] = "mudou"
        self.assertNotEqual(templates.TEMPLATES[0]["page"]["buttons"][0]["label"], "mudou")


class RotaTemplatesTest(unittest.TestCase):
    def test_local(self):
        with apoio.quiet():
            st, _, body = apoio.fake_request("GET", "/api/templates", ip="127.0.0.1")
        self.assertEqual(st, 200)
        r = json.loads(body.decode("utf-8"))
        self.assertTrue(r["ok"])
        self.assertEqual([t["id"] for t in r["templates"]], [t["id"] for t in templates.TEMPLATES])
        for t in r["templates"]:
            self.assertEqual(set(t), {"id", "name", "desc", "icon", "page"})

    def test_rede_precisa_de_codigo(self):
        with apoio.quiet():
            st, _, _ = apoio.fake_request("GET", "/api/templates", ip="192.168.0.70")
            self.assertIn(st, (401, 403))
            st, _, _ = apoio.fake_request("GET", "/api/templates?k=" + storage.token(), ip="192.168.0.70")
        self.assertEqual(st, 200)


if __name__ == "__main__":
    unittest.main()
