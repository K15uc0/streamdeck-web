# Avisos, notificações e navegador (2.12) — desenho (aprovado pelo usuário)

## Intenção
Ver no celular avisos do Stream Deck e (experimental) as notificações do Windows, e controlar o navegador do PC: ver abas, trocar, abrir site, pausar YouTube, rolar.

## Decidido
### 1. Avisos do Stream Deck
- Fontes: limite do Claude/Codex (≥ 80% e ≥ 95%, por janela, uma vez por janela), temperatura CPU/GPU acima de limite (padrão 90 °C, 5 min de intervalo), CPU > 95% por 1 min, OBS desconectou/voltou, agendamento executado (opcional), aparelho novo conectado.
- Servidor guarda fila curta (últimos 50) com id crescente; `/api/state?since=<id>` devolve os novos. Celular mostra faixa iOS no topo (4 s), vibra (respeita preferência), e uma "central" (folha) com o histórico.
- Liga/desliga por tipo em Conectar > Avisos. Só com a página aberta (sem Web Push: exige HTTPS).

### 2. Notificações do Windows (experimental)
- Lê `%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db` com `sqlite3` (somente leitura, `mode=ro` URI, cópia se travado), extrai app + título + texto dos toasts novos (XML do payload). Formato não documentado: falha → desliga sozinho e mostra "indisponível nesta versão do Windows".
- Desligado por padrão; liga em Conectar. Só vai para aparelhos com **Controle total** (2.11). Lista de apps ignorados.

### 3. Navegador
- **Extensão "Stream Deck" (Chrome/Edge, Manifest V3)** em `extensao/` no repo e empacotada no app (Conectar mostra "Abrir pasta da extensão" + passo a passo do modo desenvolvedor).
  - Service worker conecta em `http://127.0.0.1:<porta>/api/browser/*` (host_permissions só 127.0.0.1 nas portas do app), pareada por uma chave mostrada em Conectar ("Parear extensão"), guardada em `chrome.storage.local`. O servidor aceita Origin `chrome-extension://<id pareado>` só nesses endpoints.
  - Envia lista de abas (id, título, url, ativa, tocando áudio, janela) quando muda; recebe comandos por long-poll (≤ 25 s): ativar aba, fechar aba, abrir URL (nova aba), play/pause na aba do YouTube (via `chrome.scripting` clicando/usando `video.paused`), rolar (cima/baixo/topo/fim) na aba ativa, voltar/avançar, recarregar.
  - Permissões mínimas: `tabs`, `scripting`, `storage`, host 127.0.0.1 + `*://*.youtube.com/*` para o play/pause. Nada de ler conteúdo de outras páginas.
- **Sem extensão**: as mesmas ações viram atalhos de teclado na janela em primeiro plano (Ctrl+Tab, Ctrl+Shift+Tab, Ctrl+L + URL + Enter → abrir site, K/espaço → pausar, PageDown/PageUp/Home/End). Lista de abas mostra "Instale a extensão".
- **Celular**: tipo de bloco novo "Navegador" (abre folha com abas: tocar = ativar, deslizar = fechar; botões rolar/pausar/abrir site) + ações novas `browser` (`tab_next`, `tab_prev`, `open_url`, `yt_toggle`, `scroll`, `back`, `forward`, `reload`) usáveis em qualquer botão; modelo de página "Navegador".
- Fechar aba e abrir URL arbitrária pelo celular: exige Controle total? Decisão: abrir sites salvos no botão = qualquer aparelho com a página; fechar aba/URL digitada = Controle total.

## Não objetivos
Web Push/HTTPS; Firefox (fica para depois); ler conteúdo de páginas; publicar na Chrome Web Store.

## Anti-objetivos
Extensão com acesso a todos os sites; notificações do Windows indo para aparelho sem Controle total; qualquer site conseguindo falar com a API do navegador.

## Abordagens
Navegador: extensão + atalhos (escolhida) / só atalhos / porta de depuração do Chrome (recusada: insegura, exige abrir o Chrome com flag). Notificações Windows: banco local (escolhida, experimental) / WinRT UserNotificationListener (exige app empacotado, inviável).
