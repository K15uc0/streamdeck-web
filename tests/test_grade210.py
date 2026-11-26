import copy
import unittest

from streamdeck import schema, templates


def cfg(**page):
    p = {"name": "P", "buttons": []}
    p.update(page)
    return {"version": schema.CONFIG_VERSION, "columns": 4, "rows": 3, "pages": [p]}


class GradePorPagina(unittest.TestCase):
    def test_sem_grade_continua_valido(self):
        schema.validate_config(cfg())

    def test_grade_propria_valida(self):
        schema.validate_config(cfg(grid={"columns": 5, "rows": 4}))
        schema.validate_config(cfg(grid={"columns": 10, "rows": 8, "portrait": {"columns": 3, "rows": 6}}))

    def test_grade_propria_invalida(self):
        for g in ({"columns": 11, "rows": 4}, {"columns": 5, "rows": 0}, {"columns": True, "rows": 2},
                  {"rows": 2}, "5x4", [5, 4], {"columns": 5, "rows": 4, "portrait": {"columns": 2}},
                  {"columns": 5, "rows": 4, "portrait": "x"}):
            with self.assertRaises(ValueError) as cm:
                schema.validate_config(cfg(grid=g))
            self.assertIn("pagina 1", str(cm.exception))

    def test_modelo_monitor_tem_grade_5x4(self):
        t = [x for x in templates.templates() if x["id"] == "monitor"][0]
        self.assertEqual(t["page"]["grid"], {"columns": 5, "rows": 4})
        templates.check()
        schema.validate_config(cfg(**copy.deepcopy(t["page"])))


if __name__ == "__main__":
    unittest.main()
