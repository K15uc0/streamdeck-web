# -*- coding: utf-8 -*-
"""Validacao do config v2 e migracao v1 -> v2."""
import copy
import json
import unittest

import apoio
from streamdeck import schema


class ValidacaoTest(unittest.TestCase):
    def ok(self, cfg):
        schema.validate_config(cfg)

    def ruim(self, cfg, trecho=None):
        with self.assertRaises(ValueError) as cm:
            schema.validate_config(cfg)
        if trecho:
            self.assertIn(trecho, str(cm.exception))

    def test_config_base_valido(self):
        self.ok(apoio.base_config())

    def test_config_padrao_do_programa_valido(self):
        with open(apoio.ROOT + "/config.padrao.json", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg, _ = schema.migrate(cfg)
        self.ok(cfg)

    def test_versao(self):
        c = apoio.base_config()
        c["version"] = 1
        self.ruim(c, "versao")
        del c["version"]
        self.ruim(c, "versao")
        self.ruim([], "invalida")

    def test_grade(self):
        for key, bad in (("columns", 0), ("columns", 11), ("rows", 9), ("rows", True), ("columns", "5")):
            c = apoio.base_config()
            c[key] = bad
            self.ruim(c, key)
        c = apoio.base_config()
        c["portrait"] = {"columns": 3, "rows": 5}
        self.ok(c)
        c["portrait"] = {"columns": 3, "rows": 9}
        self.ruim(c, "vertical")
        c["portrait"] = "x"
        self.ruim(c, "portrait")

    def test_paginas(self):
        c = apoio.base_config()
        c["pages"] = []
        self.ruim(c, "pagina")
        c = apoio.base_config()
        c["pages"] = [{"name": "x", "buttons": []}] * (schema.MAX_PAGES + 1)
        self.ruim(c, "maximo")
        c = apoio.base_config()
        c["pages"][0]["layout"] = "mixer"
        self.ruim(c, "layout")
        c = apoio.base_config()
        c["pages"][0]["buttons"] = [{"action": {"type": "none"}}] * (schema.MAX_BUTTONS + 1)
        self.ruim(c, "botoes demais")
        c = apoio.base_config()
        c["pages"][0]["name"] = "x" * (schema.MAX_NAME + 1)
        self.ruim(c, "longo")

    def test_apps_da_pagina(self):
        c = apoio.base_config()
        c["pages"][0]["apps"] = ["obs64.exe", "Spotify.EXE", "Música (2).exe"]
        self.ok(c)
        for bad in ("..\\x.exe", "c:/a.exe", "obs64", "", "a\nb.exe", 5):
            c["pages"][0]["apps"] = [bad]
            self.ruim(c, "app")
        c["pages"][0]["apps"] = ["a.exe"] * (schema.MAX_APPS + 1)
        self.ruim(c, "apps")

    def botao(self, **kw):
        c = apoio.base_config()
        c["pages"][0]["buttons"][1].update(kw)
        return c

    def test_campos_do_botao(self):
        self.ok(self.botao(w=2, h=4, textColor="#ffffff", image="logo.png", live="clock",
                           on={"label": "NO AR", "color": "#ff0000", "image": ""}))
        self.ruim(self.botao(w=5), "entre 1 e 4")
        self.ruim(self.botao(h=0), "entre 1 e 4")
        self.ruim(self.botao(w=True), "entre 1 e 4")
        self.ruim(self.botao(textColor="red"), "#rrggbb")
        self.ruim(self.botao(image="../x.png"), "imagem")
        self.ruim(self.botao(image="a/b.png"), "imagem")
        self.ruim(self.botao(live="tempo"), "ao vivo")
        self.ruim(self.botao(toggle="sim"), "toggle")
        self.ruim(self.botao(on={"action": {}}), "on")
        self.ruim(self.botao(on="x"), "ligado")
        self.ruim(self.botao(label="x" * (schema.MAX_LABEL + 1)), "longo")
        self.ruim(self.botao(kind="slider"), "tipo")

    def test_fader(self):
        c = apoio.base_config()
        c["pages"][0]["buttons"][4]["target"] = "bass"
        self.ruim(c, "fader")

    def test_pasta(self):
        c = apoio.base_config()
        pasta = c["pages"][0]["buttons"][3]
        pasta["buttons"].append({"kind": "folder", "buttons": []})
        self.ruim(c, "item 3")
        c = apoio.base_config()
        c["pages"][0]["buttons"][3]["buttons"] = "x"
        self.ruim(c, "pasta")
        c = apoio.base_config()
        c["pages"][0]["buttons"][3]["buttons"] = [{"action": {"type": "none"}}] * (schema.MAX_FOLDER + 1)
        self.ruim(c, "maximo")

    def test_acao_invalida_no_botao(self):
        self.ruim(self.botao(action={"type": "explodir"}), "tipo de acao")
        self.ruim(self.botao(action={"type": "page", "to": 5}), "pagina")

    def test_nome_de_imagem(self):
        for good in ("a.png", "Logo (1).jpg", "x-y_z.webp"):
            self.assertTrue(schema.safe_image_name(good), good)
        for bad in ("", ".png", "../a.png", "a/b.png", "a\\b.png", "a..png", None, 3, "x" * 101):
            self.assertFalse(schema.safe_image_name(bad), bad)


class MigracaoTest(unittest.TestCase):
    def setUp(self):
        self.v1 = apoio.fixture("config_v1.json")

    def test_fixture_e_v1_com_mixer(self):
        self.assertNotIn("version", self.v1)
        self.assertIn("mixer", [p.get("layout") for p in self.v1["pages"]])

    def test_migra_e_valida(self):
        orig = copy.deepcopy(self.v1)
        new, changed = schema.migrate(self.v1)
        self.assertTrue(changed)
        self.assertEqual(self.v1, orig, "migrate nao pode alterar o original")
        self.assertEqual(new["version"], 2)
        schema.validate_config(new)
        for pg in new["pages"]:
            self.assertNotIn("layout", pg)
        # paginas grid ficam iguais (sem layout)
        for i, pg in enumerate(self.v1["pages"]):
            if pg.get("layout", "grid") == "grid":
                self.assertEqual(new["pages"][i]["buttons"], pg["buttons"])

    def test_mixer_vira_paginas_comuns(self):
        new, _ = schema.migrate(self.v1)
        mi = [p.get("layout") for p in self.v1["pages"]].index("mixer")
        nome = self.v1["pages"][mi].get("name") or "Rádio"
        radio = new["pages"][mi]
        self.assertEqual(radio["name"], nome)
        faders = [b for b in radio["buttons"] if b.get("kind") == "fader"]
        self.assertEqual([f["target"] for f in faders], ["master", "effects", "mic"])
        nomes = [p["name"] for p in new["pages"]]
        self.assertIn("%s · Pads" % nome, nomes)
        # ON AIR (posicao 42) virou liga/desliga, se usado
        if any(b.get("toggle") for b in radio["buttons"]):
            self.assertTrue(any(b.get("toggle") is True for b in radio["buttons"]))

    def test_acoes_de_pagina_remapeadas(self):
        new, _ = schema.migrate(self.v1)
        n = len(new["pages"])

        def pages_of(a):
            if not isinstance(a, dict):
                return
            if a.get("type") == "page":
                yield a["to"]
            for s in a.get("steps") or []:
                for x in pages_of(s):
                    yield x
        alvos = []
        for pg in new["pages"]:
            for b in pg["buttons"]:
                alvos += list(pages_of(b.get("action")))
        self.assertTrue(alvos)
        for t in alvos:
            self.assertTrue(0 <= t < n)
        # "Voltar" das paginas novas leva a pagina principal do radio
        mi = [p.get("layout") for p in self.v1["pages"]].index("mixer")
        for pg in new["pages"][mi + 1:]:
            for b in pg["buttons"]:
                if b.get("label") == "Voltar":
                    self.assertEqual(b["action"]["to"], mi)
        # nada de chaves internas
        self.assertNotIn("_goto", json.dumps(new))
        self.assertNotIn("_new", json.dumps(new))

    def test_remapeia_destino_depois_do_mixer(self):
        v1 = {"columns": 5, "rows": 3, "pages": [
            {"name": "A", "layout": "mixer", "buttons": [
                {"label": "Pad", "action": {"type": "hotkey", "keys": ["f1"]}}] * 10},
            {"name": "B", "buttons": [{"label": "Ir A", "action": {"type": "page", "to": 0}},
                                      {"label": "Ir B", "action": {"type": "multi", "steps": [
                                          {"type": "page", "to": 1}]}},
                                      {"label": "Ir ?", "action": {"type": "page", "to": 9}}]}]}
        new, _ = schema.migrate(v1)
        b = new["pages"][-1]["buttons"]
        self.assertEqual(new["pages"][-1]["name"], "B")
        self.assertEqual(b[0]["action"]["to"], 0)
        self.assertEqual(b[1]["action"]["steps"][0]["to"], len(new["pages"]) - 1)
        self.assertEqual(b[2]["action"]["to"], 0)

    def test_v2_nao_muda(self):
        c = apoio.base_config()
        new, changed = schema.migrate(c)
        self.assertFalse(changed)
        self.assertIs(new, c)
        self.assertEqual(schema.migrate("x"), ("x", False))


if __name__ == "__main__":
    unittest.main()
