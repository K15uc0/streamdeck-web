# 2.12 — plano
Spec: docs/superpowers/specs/2026-11-26-avisos-e-navegador-2-12-design.md
Começa só depois do merge da 2.11 (usa Controle total).
1. `streamdeck/avisos.py`: fila, regras (IA, temperatura, CPU, OBS, aparelho novo), ajustes; `/api/state?since=`; testes.
2. Celular: faixa de aviso + central; Conectar > Avisos; e2e + prints.
3. `streamdeck/notif_windows.py`: leitura ro do wpndatabase.db, parser do XML, apps ignorados, entrega só a aparelhos full; testes com banco de exemplo (fixture sqlite gerada no teste).
4. `extensao/` MV3 + `streamdeck/navegador.py` + `/api/browser/*` (pareamento, Origin da extensão, abas, long-poll de comandos); testes HTTP; teste da extensão com Playwright carregando a extensão (Chromium headful/`--load-extension` se possível) ou testes unitários do service worker.
5. Ações `browser` + fallback de atalhos (`actions.py`), bloco "Navegador" e folha de abas no celular, modelo "Navegador", editor; build empacota `extensao/`.
6. VERSION 2.12.0, CHANGELOG, README (instalar a extensão), ARQUITETURA; revisão; PR.
