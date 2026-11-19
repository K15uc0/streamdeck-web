# Stream Deck

Transforma qualquer celular ou tablet, inclusive Android antigo, num painel de botões para o PC com Windows. Funciona pelo navegador e não precisa instalar app no aparelho.

## Como usar

1. **Baixe o [StreamDeck.exe](https://github.com/K15uc0/streamdeck-web/releases/latest/download/StreamDeck.exe)** e abra.
   - Se aparecer *"O Windows protegeu o computador"*: **Mais informações → Executar assim mesmo**.
   - Na pergunta do firewall: marque **Redes privadas e Redes públicas** → **Permitir**.
2. Abre no PC a tela **Conectar um aparelho** com um QR code. Aponte a câmera do celular ou tablet (no mesmo Wi-Fi) e abra o link.
3. Pronto. Para personalizar os botões, clique em **Editar botões** na tela Conectar do PC. O celular fica só para usar (com tela cheia e orientação nos Ajustes).

Deixe a janela do Stream Deck aberta (pode minimizar) ou marque **Iniciar junto com o Windows** na tela de conexão (`http://127.0.0.1:8765/conectar` no PC).

## Windows bloqueou o programa?

O StreamDeck.exe é gratuito e não tem assinatura digital paga, por isso o Windows às vezes desconfia dele.

- **SmartScreen** (*"O Windows protegeu o computador"*): clique em **Mais informações → Executar assim mesmo**.
- **Microsoft Defender apagou ou colocou em quarentena**: abra **Segurança do Windows → Proteção contra vírus e ameaças → Histórico de proteção**, clique no item do StreamDeck.exe e escolha **Restaurar** (ou **Ações → Permitir no dispositivo**).
- **Confira se o arquivo é o original**: as notas de cada versão em [Releases](https://github.com/K15uc0/streamdeck-web/releases) trazem o SHA-256 do StreamDeck.exe. No PowerShell: `Get-FileHash .\StreamDeck.exe` — o valor tem de ser igual.
- **Avise a Microsoft do falso positivo**: envie o arquivo em <https://www.microsoft.com/wdsi/filesubmission> (escolha *Software developer* ou *Home customer* e marque *Incorrectly detected*). Depois da análise, o bloqueio costuma sumir para todo mundo.

O programa só abre a porta local, não se instala em lugar nenhum além do registro de "iniciar com o Windows" (se você marcar) e não mexe em outros programas.

## O que dá para fazer

- Atalhos de teclado, teclas de mídia, abrir sites e programas, rodar comandos, sequências de ações
- Funções para rádio: efeitos sonoros (MP3/WAV), parar sons, mensagens no chat e chamadas à API do programa
- Várias páginas, pastas, botões de até 4x4, ícones, imagens próprias e cores, tudo editável no PC
- Apps e sites: trazer/abrir programas, atalho dentro de um programa, abrir site (navegador, perfil, modo app), ir para uma aba; troca de página conforme o app em foco
- Biblioteca de comandos prontos (Windows, mídia, OBS, Discord, Spotify, Teams, Zoom…) e efeitos sonoros até 200%
- Cópia de segurança: exportar/importar um .zip com botões, imagens e sons
- Abas para vários PCs (casa, trabalho…); só a aba aberta controla o PC dela
- **Atualizações**: o app avisa quando sai versão nova e atualiza com um toque, mantendo botões, abas e sons

Seus dados ficam em `Documentos\StreamDeck`. As novidades de cada versão estão no [CHANGELOG](CHANGELOG.md). Mais detalhes no [LEIA-ME](LEIA-ME.txt).

## Para desenvolvedores

- Rodar pelo código: Python 3.8+, `python server.py` (sem dependências). O código do servidor fica no pacote `streamdeck/`; `server.py` só chama `streamdeck.app.main()`.
- Arquitetura, formato do `config.json` (v2) e API: [docs/ARQUITETURA.md](docs/ARQUITETURA.md).
- Nova função para os botões: um arquivo em `streamdeck/actions/` com `@action(...)` e o import em `_load()` (exemplo em [docs/ARQUITETURA.md](docs/ARQUITETURA.md#como-adicionar-uma-função)). O editor monta o formulário sozinho a partir de `/api/actions`.
- Testar fora do Windows: `STREAMDECK_DATA=/tmp/sd python3 server.py` (as ações são simuladas e aparecem como `[simulado]` na janela).
- Testes (rodam sozinhos no GitHub Actions em cada pull request, pelo `.github/workflows/testes.yml`, e antes de publicar uma versão):
  - Python, sem instalar nada: `python -m unittest discover -s tests` (validação e migração do config, ações, biblioteca, segurança e a API com o servidor de verdade numa porta livre; os dados ficam numa pasta temporária e nenhuma tecla é enviada de verdade).
  - JavaScript do núcleo (`SD.flow`, `SD.geometry`...), só com Node: `node tests/js/flow.test.js`.
  - No navegador (celular 390x844, tablet 1180x820 e editor do PC): `npm install --no-save playwright@1.48.2`, `npx playwright install chromium` e `node tests/e2e/smoke.js` (sobe o `server.py` sozinho; falha com qualquer erro no console).
  - `.exe` (Windows, pwsh): depois de gerar com o PyInstaller, `./tests/exe_smoke.ps1 -Exe dist/StreamDeck.exe` abre o programa, confere a API e fecha.
  - Ação nova: acrescente um exemplo válido e alguns inválidos em `EXEMPLOS` de `tests/test_acoes.py` (o teste avisa se faltar).
- Publicar versão: altere `VERSION` em `streamdeck/__init__.py`, adicione a seção no `CHANGELOG.md` e envie para a `main`. O GitHub Actions gera o `StreamDeck.exe` e publica a release; os programas instalados avisam os usuários.
