# Stream Deck caseiro

Transforma qualquer tablet ou celular (inclusive Android antigo) em um painel de botões para o PC com Windows. O PC roda um pequeno servidor em Python e o tablet abre a página pelo navegador. Não precisa instalar app.

- Atalhos de teclado, teclas de mídia, abrir sites e programas, rodar comandos e sequências de ações
- Várias páginas, ícones e cores
- Editor no próprio app (botão "Editar")
- Sem dependências: só Python 3.7+
- Acesso protegido por código (gerado em `token.txt` na primeira execução)

## Uso

1. Instale o Python (python.org), marcando "Add python.exe to PATH".
2. Execute `Iniciar Stream Deck.bat` e permita o acesso em "Redes privadas" no firewall.
3. Abra no tablet o endereço mostrado na janela (`http://IP-DO-PC:8765/?k=...`).

Detalhes e formato do `config.json` em [LEIA-ME.txt](LEIA-ME.txt).
