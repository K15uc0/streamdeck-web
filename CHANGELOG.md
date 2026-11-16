# Novidades

## 1.1.0

Segurança reforçada:
- Só aceita aparelhos da rede local; acessos vindos da internet são recusados, mesmo com porta aberta no roteador.
- Bloqueia sites maliciosos que tentem usar o navegador do celular ou do PC para acionar botões ou mudar a configuração (CSRF e DNS rebinding).
- Limite de tentativas: após 10 códigos errados, o aparelho fica bloqueado por 10 minutos.
- Código de acesso mais forte nas instalações novas, com opção "Gerar novo código" na tela Conectar.
- Botões que rodam comandos, abrem programas/arquivos ou chamam APIs só podem ser criados no próprio PC (pode ser liberado em Conectar > Segurança).
- Sons só da pasta "sons"; caminhos de rede bloqueados.
- Cabeçalhos de proteção nas páginas e cookie restrito ao próprio site.
- Ao iniciar, só encerra cópias antigas do próprio Stream Deck (nunca outros programas).

## 1.0.0

- Programa único para Windows (StreamDeck.exe): não precisa instalar Python.
- Tela de conexão no PC com QR code para conectar o celular ou tablet.
- Aba "Atualizações": avisa quando sai versão nova e atualiza com um toque, mantendo botões, abas e sons.
- Abas para vários PCs (casa, trabalho...).
- Funções para rádio: efeitos sonoros, parar sons, mensagem no chat e API do programa.
- Editor de botões no próprio app.
- Opção de iniciar junto com o Windows.
