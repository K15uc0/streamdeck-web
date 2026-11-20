# Novidades

## 2.9.0

- Monitor do PC no celular: toque no ícone de gráfico na barra (ou num botão com a ação "Abrir monitor do PC") para acompanhar ao vivo o uso de CPU (total e por núcleo), memória, placa de vídeo (uso e memória de vídeo), rede (recebendo e enviando), disco (atividade, leitura/gravação e espaço livre de cada unidade), tempo ligado e bateria. Gráficos do último minuto e meio; toque e arraste no gráfico para ver o valor de cada momento.
- Texto ao vivo nos botões: "CPU 23%", "RAM 41%", "GPU 12%", "Disco 3%", rede recebendo/enviando e tempo ligado.
- Temperatura não aparece: o Windows só a entrega com programas do fabricante ou como administrador.

## 2.8.1

- Ao abrir o Stream Deck pelo atalho ou pelo .exe, a tela Conectar abre no navegador (desde a 2.5 o programa não tem janela e parecia que não tinha aberto). O ícone fica perto do relógio.
- Se algo impedir o programa de abrir, aparece uma mensagem com o motivo, também gravada em Documentos\StreamDeck\erro-ao-abrir.txt.

## 2.8.0

- Agendamentos (editor do PC > Automação > Agendamentos): disparar qualquer ação todo dia num horário, a cada N minutos (alinhado ao relógio, com faixa de horário opcional) ou uma vez numa data. Escolha os dias da semana, veja a próxima execução e teste na hora.
- Música tocando agora: botão com texto ao vivo "Música — Artista" (ou só um dos dois), rolando quando não cabe. Funciona com Spotify (app), YouTube/YouTube Music, Deezer e SoundCloud no navegador, VLC, foobar2000, AIMP, Winamp e MusicBee (lido do título da janela do player).

## 2.7.0

- 176 ícones (antes 56) com busca em português e ícones recentes; agora também dá para usar qualquer emoji como ícone.
- Modelos de página prontos no editor: Rádio, OBS, Reunião (Teams/Zoom/Discord), Mídia, Atalhos do Windows e Navegador (Nova página > A partir de um modelo).
- Duplicar página e mover para cima/baixo; botão direito num botão: copiar, mover ou duplicar para outra página (Ctrl+Z desfaz).
- Tema claro no celular (Ajustes > Aparência) e no editor do PC: Automático, Escuro ou Claro.

## 2.6.0

- OBS direto pelo WebSocket (OBS 28 ou mais novo): trocar de cena pelo nome, iniciar/parar transmissão e gravação, mutar fontes. Configure em Conectar > OBS (no OBS: Ferramentas > Configurações do WebSocket).
- Botões acendem conforme o OBS (ao vivo, gravando, cena atual, fonte mutada) e podem mostrar "AO VIVO", "Gravando" ou o nome da cena.
- Toque longo e toque duplo: cada botão pode ter até 3 ações (tocar, segurar, tocar duas vezes).
- Confirmação: botões perigosos (desligar, reiniciar) pedem "Toque de novo para confirmar".
- Sons: barra de progresso e tempo restante no botão enquanto toca, entrada suave (fade in) e "parar sons" com fade.

## 2.5.0

- Instalador: baixe o StreamDeck-Instalador.exe (recomendado). Instala só para o seu usuário, sem pedir administrador, com atalho no Menu Iniciar e desinstalador (seus botões em Documentos\StreamDeck nunca são apagados). Abre mais rápido, porque não precisa se extrair a cada vez.
- Ícone na bandeja (perto do relógio) no lugar da janela preta: Conectar um aparelho, Editar botões, pasta de dados, log, Iniciar com o Windows, aviso de atualização e Sair.
- A versão avulsa (StreamDeck.exe) continua disponível e se atualiza sozinha como antes.

## 2.4.0

- Versões anteriores: o programa guarda até 20 versões dos botões (no máximo uma a cada 10 minutos de edição, com o estado de antes de você começar a mexer). No editor, Backup > "Versões anteriores…" mostra cada uma e restaura com um clique (a versão substituída também fica guardada).
- Diagnóstico na tela Conectar: endereços, aparelhos conectados, últimos erros, "Abrir log" e "Copiar diagnóstico".
- Botão liga/desliga sem ação (como o ON AIR) volta a acender no celular.
- Importar backup funciona também rodando pelo código em Python 3.8 a 3.10.
- Testes automáticos antes de cada versão: a versão só é publicada se o StreamDeck.exe gerado abrir e responder.

## 2.3.1

- Menos chances de o Windows ou o antivírus bloquear o programa:
  - ao abrir de novo, a cópia antiga é avisada e fecha sozinha (sem forçar o encerramento de processos);
  - "Iniciar junto com o Windows" agora usa o registro do usuário (quem já tinha marcado é migrado sozinho) e abre minimizado;
  - a atualização automática confere o SHA-256 do arquivo baixado com o da versão publicada;
  - envio de teclas pelo método atual do Windows (SendInput);
  - o StreamDeck.exe agora traz informações de versão e o SHA-256 aparece nas notas de cada versão.

## 2.3.0

- Os botões agora esticam para preencher toda a tela do celular e do tablet, em pé e deitado, sem sobras nas bordas.
- Editor do PC: escolha o aparelho (celular ou tablet, em pé ou deitado, ou tamanho personalizado) e veja a prévia exatamente como vai ficar na tela.

## 2.2.0

- Botões maiores: cada botão pode ocupar até 4x4 espaços (estique pela alça no editor).
- Cores: roda de cores, cores recentes, cor do texto/ícone e aplicar em vários botões de uma vez.
- Imagem própria no botão (PNG/JPG) e aparência diferente quando o botão liga/desliga está ligado.
- Texto ao vivo no botão: relógio, data, volume e cronômetro (ex.: tempo no ar).
- Pastas: um botão abre um grupo de botões por cima da página.
- Novas ações: ir para um app (traz a janela se já estiver aberta, senão abre), atalho em um app específico, abrir site num navegador/perfil e ir para uma aba pelo título.
- Troca de página sozinha conforme o app em uso no PC (ex.: abriu o OBS, vai para a página OBS).
- Biblioteca de comandos prontos com busca e "Gravar atalho" pelo teclado do PC.
- Efeitos sonoros até 200%.
- Enviar sons e imagens pelo editor; exportar e importar tudo (backup).
- Celular vibra ao tocar (Android).

## 2.1.0

Edição pelo PC e celular só para uso:
- Novo editor no PC: na tela Conectar, toque em "Editar botões". Páginas à esquerda, grade no centro e o botão selecionado à direita; arraste para mover, Ctrl+Z para desfazer, botão "Testar" e salvamento automático.
- O celular não edita mais: fica só com os botões, sem risco de mudar algo sem querer.
- Grade separada para o celular em pé (ex.: 3x5 em pé e 5x3 deitado), definida no editor do PC.
- Tela cheia pelo botão no topo e opção "Abrir sempre em tela cheia".
- Orientação por aparelho: Automática, Vertical ou Horizontal (nos Ajustes do celular).
- Dá para adicionar à tela de início como um app (no iPhone, é assim que fica em tela cheia).

## 2.0.0

Visual novo no estilo iOS e programa reorganizado:
- Botões como os blocos do app Atalhos; página atual no topo e pontinhos embaixo; deslize para trocar de página.
- Modo edição como a tela de início do iPhone: segure um botão ou toque em Editar; os botões tremem, arraste para trocar de lugar, "−" para remover, "+" para criar.
- Editor em folha que sobe de baixo, com prévia do botão, ícones, cores do iOS e lista de ações por grupo.
- Novos tipos de botão: Liga/desliga (fica aceso em todos os aparelhos, como o ON AIR) e Fader (controle de volume do PC, efeitos ou microfone, como na Central de Controle).
- A página Mixer de DJ foi convertida sozinha em páginas comuns (Rádio, Pads com os 4 bancos juntos, Chat); a configuração antiga fica salva em config.v1.bak.json.
- Tela Conectar no PC com o mesmo visual.
- Para quem programa: cada ação é um arquivo em streamdeck/actions e o editor monta o formulário sozinho (veja docs/ARQUITETURA.md).

## 1.3.0

Novo layout Mixer de DJ (página "Rádio"):
- Deck A (playlist): disco giratório para rolar a lista, tocar/pausar, anterior, próxima, parar, CUE e AUTO DJ.
- Mixer: faders de volume do PC (master), dos efeitos e do microfone, com medidor de LED e botões de mudo; botão ON AIR que acende em todos os aparelhos.
- Deck B (efeitos): 4 bancos com 8 pads cada e mensagens rápidas para o chat.
- No celular em pé, vira três abas: Pads, Deck e Mixer.
- Tudo editável no modo Editar. Para criar outra página assim: Editar > + Página > Mixer.
- Nova ação "Rádio: ligar/desligar mudo".

## 1.2.0

Mais fluido e adaptado a qualquer aparelho:
- O botão responde na hora ao toque; se a ação falhar, pisca em vermelho e mostra o motivo.
- Segurar Volume +/− ou as setas repete a ação.
- Arrastar o dedo para fora do botão cancela o toque.
- Celular em pé: a grade se reorganiza sozinha para os botões ficarem maiores.
- Em telas estreitas, as abas e os botões de edição quebram linha em vez de sumir.
- Abre na hora com os botões guardados, mesmo antes de o PC responder.
- Edições feitas em um aparelho aparecem sozinhas nos outros em poucos segundos.
- Opção "Tela cheia" no modo de edição.
- Servidor mais rápido: respostas sem atraso de rede, configuração em memória e consultas mais leves.

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
