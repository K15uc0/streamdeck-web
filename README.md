# Stream Deck

Transforma qualquer celular ou tablet, inclusive Android antigo, num painel de botões para o PC com Windows. Funciona pelo navegador e não precisa instalar app no aparelho.

## Como usar

1. **Baixe o [StreamDeck.exe](https://github.com/K15uc0/streamdeck-web/releases/latest/download/StreamDeck.exe)** e abra.
   - Se aparecer *"O Windows protegeu o computador"*: **Mais informações → Executar assim mesmo**.
   - Na pergunta do firewall: marque **Redes privadas e Redes públicas** → **Permitir**.
2. Abre no PC a tela **Conectar um aparelho** com um QR code. Aponte a câmera do celular ou tablet (no mesmo Wi-Fi) e abra o link.
3. Pronto. Para personalizar os botões, clique em **Editar botões** na tela Conectar do PC. O celular fica só para usar (com tela cheia e orientação nos Ajustes).

Deixe a janela do Stream Deck aberta (pode minimizar) ou marque **Iniciar junto com o Windows** na tela de conexão (`http://127.0.0.1:8765/conectar` no PC).

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
- Publicar versão: altere `VERSION` em `streamdeck/__init__.py`, adicione a seção no `CHANGELOG.md` e envie para a `main`. O GitHub Actions gera o `StreamDeck.exe` e publica a release; os programas instalados avisam os usuários.
