import copy
import unittest

from streamdeck import schema, templates


def b(**kw):
    x = {"label": "X", "action": {"type": "none"}}
    x.update(kw)
    return x


def v2(pages, **kw):
    c = {"version": schema.CONFIG_VERSION, "columns": 4, "rows": 3, "pages": pages}
    c.update(kw)
    return c


class GradeDeCadaPagina(unittest.TestCase):
    def test_copia_a_grade_geral(self):
        c = v2([{"name": "A", "buttons": [b()]}, {"name": "B", "grid": {"columns": 2, "rows": 2}, "buttons": []}])
        new, changed = schema.migrate(c)
        self.assertTrue(changed)
        self.assertEqual(new["pages"][0]["grid"], {"columns": 4, "rows": 3})
        self.assertEqual(new["pages"][1]["grid"], {"columns": 2, "rows": 2})
        self.assertNotIn("grid", c["pages"][0], "nao altera o original")
        self.assertEqual((new["columns"], new["rows"]), (4, 3), "geral continua")
        schema.validate_config(new)

    def test_copia_vertical(self):
        c = v2([{"name": "A", "buttons": []}], portrait={"columns": 2, "rows": 5})
        new, _ = schema.migrate(c)
        self.assertEqual(new["pages"][0]["grid"], {"columns": 4, "rows": 3, "portrait": {"columns": 2, "rows": 5}})
        new["pages"][0]["grid"]["portrait"]["rows"] = 6
        self.assertEqual(new["portrait"]["rows"], 5, "copia, nao referencia")

    def test_idempotente(self):
        c = v2([{"name": "A", "buttons": [b()] * 20}])
        new, changed = schema.migrate(c)
        self.assertTrue(changed)
        again, changed2 = schema.migrate(new)
        self.assertFalse(changed2)
        self.assertIs(again, new)

    def test_cresce_em_colunas_primeiro(self):
        new, _ = schema.migrate(v2([{"name": "A", "buttons": [b()] * 14}]))
        self.assertEqual(new["pages"][0]["grid"], {"columns": 5, "rows": 3})

    def test_cresce_linhas_depois_de_10_colunas(self):
        new, _ = schema.migrate(v2([{"name": "A", "buttons": [b()] * 35}]))
        g = new["pages"][0]["grid"]
        self.assertGreaterEqual(g["columns"] * g["rows"], 35)
        self.assertEqual(len(schema.flow([b()] * 35, g["columns"], g["rows"])), 35)

    def test_vazios_no_fim_nao_contam(self):
        vazio = {"label": "", "icon": "", "color": "", "action": {"type": "none"}}
        new, _ = schema.migrate(v2([{"name": "A", "buttons": [b()] * 3 + [vazio] * 20}]))
        self.assertEqual(new["pages"][0]["grid"], {"columns": 4, "rows": 3})

    def test_nao_cabe_nem_no_maximo(self):
        new, _ = schema.migrate(v2([{"name": "A", "buttons": [b()] * 120}]))
        self.assertEqual(new["pages"][0]["grid"], {"columns": 10, "rows": 8})

    def test_monitor_sem_grade_cresce(self):
        t = [x for x in templates.templates() if x["id"] == "monitor"][0]
        pg = copy.deepcopy(t["page"])
        del pg["grid"]
        new, _ = schema.migrate(v2([pg]))
        g = new["pages"][0]["grid"]
        self.assertEqual(len(schema.flow(pg["buttons"], g["columns"], g["rows"])), len(pg["buttons"]))
        self.assertLessEqual(g["columns"] * g["rows"], 20)
        schema.validate_config(new)

    def test_v1_ganha_grade(self):
        new, _ = schema.migrate({"columns": 3, "rows": 2, "pages": [{"name": "A", "buttons": [b()]}]})
        self.assertEqual(new["pages"][0]["grid"], {"columns": 3, "rows": 2})

    def test_flow_igual_ao_js(self):
        bs = [b(w=2, h=2), b(), b(w=9), b(h=2)]
        self.assertEqual(schema.flow(bs, 4, 3), [(0, 0, 0, 2, 2), (1, 2, 0, 1, 1), (2, 0, 2, 4, 1), (3, 3, 0, 1, 2)])
        self.assertEqual(schema.flow([b()] * 3, 1, 2), [(0, 0, 0, 1, 1), (1, 0, 1, 1, 1)])


if __name__ == "__main__":
    unittest.main()
