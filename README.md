# Stream Deck

Transforma qualquer celular ou tablet, inclusive Android antigo, num painel de botões para o PC com Windows. Funciona pelo navegador e não precisa instalar app no aparelho.

## Como usar

1. **Baixe o [StreamDeck.exe](https://github.com/K15uc0/streamdeck-web/releases/latest/download/StreamDeck.exe)** e abra.
   - Se aparecer *"O Windows protegeu o computador"*: **Mais informações → Executar assim mesmo**.
   - Na pergunta do firewall: marque **Redes privadas e Redes públicas** → **Permitir**.
2. Abre no PC a tela **Conectar um aparelho** com um QR code. Aponte a câmera do celular ou tablet (no mesmo Wi-Fi) e abra o link.
3. Pronto. Toque em **✎ Editar** para personalizar os botões.

Deixe a janela do Stream Deck aberta (pode minimizar) ou marque **Iniciar junto com o Windows** na tela de conexão (`http://127.0.0.1:8765/conectar` no PC).

## O que dá para fazer

- Atalhos de teclado, teclas de mídia, abrir sites e programas, rodar comandos, sequências de ações
- Funções para rádio: efeitos sonoros (MP3/WAV), parar sons, mensagens no chat e chamadas à API do programa
- Várias páginas, ícones e cores, tudo editável no próprio app
- Abas para vários PCs (casa, trabalho…); só a aba aberta controla o PC dela
- **Atualizações**: o app avisa quando sai versão nova e atualiza com um toque, mantendo botões, abas e sons

Seus dados ficam em `Documentos\StreamDeck`. As novidades de cada versão estão no [CHANGELOG](CHANGELOG.md). Mais detalhes no [LEIA-ME](LEIA-ME.txt).

## Para desenvolvedores

- Rodar pelo código: Python 3.8+, `python server.py` (sem dependências).
- Publicar versão: altere `VERSION` em `server.py`, adicione a seção no `CHANGELOG.md` e envie a tag (`git tag v1.1.0 && git push origin v1.1.0`). O GitHub Actions gera o `StreamDeck.exe` e publica a release; os programas instalados avisam os usuários.
