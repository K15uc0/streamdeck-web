# Grade por página (2.10) — plano

Spec: `docs/superpowers/specs/2026-11-26-grade-por-pagina-2-10-design.md`

### Task 1: esquema e servidor
- `streamdeck/schema.py`: validar `page.grid` opcional (mesmos limites e mensagens da grade global, prefixo "pagina N"); capacidade/overflow (função perto da linha 377) usa a grade da página quando houver.
- `streamdeck/templates.py`: modelo "monitor" com `"grid": {"columns": 5, "rows": 4}`; `check()` confere que cabe.
- Testes em `tests/` (schema aceita/recusa; modelo válido).

### Task 2: celular
- `web/js/deck.js`: `dims()` usa `SD.gridDims(pageGridOrCfg, portrait)` da página atual (pasta aberta segue a página dona). `renderGrid` já refaz quando cols/rows mudam.
- `web/js/core.js` se houver helper compartilhado (ex.: `SD.pageGrid(cfg, pageIndex)`).
- e2e: página com grid própria renderiza cols×rows corretos.

### Task 3: editor
- `web/js/editar.js`: controle "Grade: Geral/Própria" por página, seletores próprios; `dimsFor` (linha ~104) passa a usar a grade da página; prévia e posicionamento usam ela. Mudar a geral não toca páginas com grade própria.
- Prints Playwright 1440x900 do editor; celular 640x288 e 390x844 com a página Monitor.

### Task 4: versão e docs
- VERSION 2.10.0, CHANGELOG, LEIA-ME/README (como usar), ARQUITETURA.
- Rodar unittest, flow.test.js, smoke; revisão; PR; merge só com pedido do usuário.
