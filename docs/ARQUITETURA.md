# Arquitetura (2.0)

Referências de produto: Elgato Stream Deck (perfis, páginas, multi-ação, ações
como plugins), Touch Portal (botões com estado), Bitfocus Companion (módulos de
ação declarativos) e, na interface, a tela de início e o app Atalhos do iOS
(blocos coloridos, modo "tremer" para editar, folhas que sobem de baixo).

Princípio: **uma função nova = um arquivo Python**. O servidor descreve cada ação
(campos, rótulos, ajuda) em `/api/actions` e o editor do aparelho monta o
formulário sozinho, sem mudar o frontend.

## Pastas

```
server.py                 ponto de entrada (PyInstaller usa este arquivo)
streamdeck/
  __init__.py             VERSION, REPO
  paths.py                pastas do programa e dos dados do usuário
  storage.py              JSON atômico, config (cache, versão, migração), abas, ajustes, código
  schema.py               validação e migração do config (v1 -> v2)
  security.py             rede local, Host/Origin, limite de tentativas, ações perigosas
  audio.py                SoundPlayer, volume do Windows, níveis (master/effects/mic)
  winapi.py               SendInput, pasta Documentos, iniciar com o Windows, abrir pasta
  updates.py              verificação e aplicação de atualizações
  state.py                estado em memória (botões liga/desliga)
  httpd.py                servidor HTTP e tabela de rotas
  app.py                  main(): porta, log, cópias antigas, abrir tela Conectar
  actions/
    __init__.py           registro: @action(...), run(), validate(), schema()
    keyboard.py           hotkey, text
    system.py             open, command
    audio.py              sound, stopsound, mute
    web.py                http
    flow.py               none, page, multi
web/
  index.html              casca (HTML mínimo)
  conectar.html           tela do PC (QR code)
  editar.html             editor do PC (só no PC)
  manifest.json           "Adicionar à tela inicial"
  icons/                  ícones do manifest e apple-touch-icon
  css/app.css
  css/editar.css          estilos do editor do PC
  js/core.js              rede, utilidades, ícones, estado global SD
  js/deck.js              grade, toque, páginas, faders, liga/desliga
  js/editar.js            editor do PC: grade, formulário a partir do schema, autosave
  js/settings.js          ajustes, páginas, PCs (abas), atualizações
```

JavaScript em ES5 (sem módulos, sem `let`/`=>`), para funcionar em Android antigo.
Cada arquivo é um IIFE que pendura funções em `window.SD`.

## Config v2 (`Documentos\StreamDeck\config.json`)

```json
{
  "version": 2,
  "title": "Stream Deck",
  "columns": 5,
  "rows": 3,
  "pages": [
    { "name": "Principal", "buttons": [ Botão, ... ] }
  ]
}
```

Botão:

```json
{ "kind": "button", "label": "Play", "icon": "playpause", "color": "#0a84ff",
  "toggle": false, "action": { "type": "hotkey", "keys": ["playpause"] } }
```

- `kind`: `"button"` (padrão se ausente) ou `"fader"`.
- `toggle: true`: o botão guarda estado ligado/desligado (ex.: ON AIR). Cada
  toque executa a ação e inverte o estado; o estado aparece aceso em todos os aparelhos.
- Fader: `{ "kind": "fader", "label": "Master", "icon": "sound", "color": "#0a84ff", "target": "master" }`
  com `target` em `master | effects | mic`. Ocupa uma célula da grade e é desenhado
  como o controle de volume da Central de Controle do iOS (preenche de baixo para cima).
- Posição na lista = posição na grade (linha a linha). A lista pode ser menor que
  `columns*rows`; o que falta é vazio. Botão vazio: `action.type == "none"` e `kind` button.

Migração v1 -> v2 (automática ao carregar, com cópia `config.v1.bak.json`):
- sem `version` = v1. Páginas `layout: "grid"` ficam iguais (só remove `layout`).
- Página `layout: "mixer"` (48 posições fixas, ver `tools/pagina_mixer.py` no histórico)
  vira páginas comuns: "Rádio" (3 faders master/effects/mic, ON AIR como `toggle`,
  botões de mudo e controles do Deck A), "Rádio · Pads" (pads dos 4 bancos juntos, sem repetidos e
  não vazios) e "Rádio · Chat" (mensagens). Ações `page` (`to`) são remapeadas.

## API (todas exigem `X-StreamDeck: 1`; código via cookie `sdk` ou `?k=`)

| Método | Rota | Resposta |
|---|---|---|
| GET | `/api/config` | config v2; cabeçalho `X-Config-Version` |
| POST | `/api/config` | `{ok, v}`; 400 `{ok:false, error}`; 403 se ação perigosa vinda de fora do PC |
| GET | `/api/actions` | `{ok, actions:[ActionSchema]}` |
| GET | `/api/info` | `{ok, name, code, sounds, tabs, version, local, update}` |
| GET | `/api/press?p=&b=` | `{ok, toggles?}` ; erro `{ok:false, error}` |
| GET | `/api/state?levels=1` | `{ok, v, update, toggles:{"p:b":true}, levels?}` |
| GET | `/api/volume?c=master&v=40` ou `?c=mic&mute=toggle` | `{ok, levels:{master:{v,muted}, effects:{...}, mic:{...}}}` |
| POST | `/api/tabs` | lista de abas |
| GET/POST | `/api/update`, `/api/update/check`, `/api/update/apply` | iguais à 1.x |
| GET/POST | `/api/local/*` | só no próprio PC (tela Conectar), iguais à 1.x |
| GET | `/ping.gif` | sinal de vida para as abas |

ActionSchema:

```json
{
  "type": "sound",
  "label": "Tocar efeito sonoro",
  "group": "Rádio",
  "icon": "sound",
  "help": "Coloque MP3/WAV na pasta sons.",
  "fields": [
    { "key": "file", "label": "Arquivo", "kind": "sound", "required": true },
    { "key": "volume", "label": "Volume", "kind": "number", "min": 0, "max": 100, "default": 100 },
    { "key": "exclusive", "label": "Parar os outros sons antes", "kind": "bool", "default": false }
  ]
}
```

Tipos de campo (`kind`): `text`, `textarea`, `keys` (lista de teclas; editada como
`ctrl+shift+m`), `number` (`min`, `max`, `step`), `bool`, `select` (`options:
[{value, label}]`), `sound` (nome de arquivo; opções vêm de `/api/info.sounds`),
`page` (índice de página), `steps` (lista de ações, sem `page`/`multi`).
Opcionais em qualquer campo: `placeholder`, `help`, `default`, `required`.

## Como adicionar uma função

```python
# streamdeck/actions/minha.py
from . import action, Field

@action("beep", "Fazer um bipe", group="Sistema", icon="bell",
        fields=[Field("freq", "Frequência (Hz)", "number", min=100, max=5000, default=800)])
def beep(a):
    import winsound
    winsound.Beep(int(a.get("freq", 800)), 200)
```

e importar o módulo em `streamdeck/actions/__init__.py` (`_load()`). A validação
básica (obrigatórios, limites, opções) vem dos campos; validações extras vão em
`validate=func`.

## 2.1: edição só no PC, tela cheia e orientação

**Edição só no PC.** `POST /api/config` só é aceito do próprio PC (127.0.0.1/::1);
de outro aparelho responde 403 `{ok:false, error:"edite pelo PC"}`. A opção
`remote_admin` (Conectar > Segurança) e o bloqueio de "ações perigosas" vindas do
celular deixam de existir (o celular não salva mais nada). `/api/info` perde
`remote_admin`. `POST /api/tabs` continua aceito do celular (lista de PCs do aparelho).

**Editor do PC.** `GET /editar` (só no PC, como `/conectar`) serve `web/editar.html`
com `web/css/editar.css` e `web/js/editar.js`, que reutilizam `web/js/core.js`
(rede, ícones, cores). Rota extra só no PC: `POST /api/local/test` com corpo
`{action}` executa uma ação sem salvar (botão "Testar").

**Grade por orientação.** `columns`/`rows` = grade na horizontal. Opcional
`"portrait": {"columns": 3, "rows": 5}` = grade na vertical (1..10 x 1..8). Sem
`portrait`, a vertical é a horizontal transposta quando `columns > rows` (como hoje).
A mesma lista de botões é distribuída linha a linha em cada grade; se a grade
atual tiver menos posições que a lista, os excedentes não aparecem (o editor avisa).

**Celular (só uso).** Sem modo edição. Ajustes por aparelho em localStorage
(`sd_prefs`): `orientation` = `auto|portrait|landscape`, `autoFullscreen` bool.
Tela cheia pela barra; trava via `screen.orientation.lock` quando possível, senão
gira o conteúdo por CSS. `web/manifest.json` + ícones para "Adicionar à tela inicial".

## 2.2: botões maiores, apps/janelas, biblioteca, efeitos até 200%

**Botão (campos novos, todos opcionais):**
- `w`, `h`: 1..4 (padrão 1). Encaixe pela regra única `SD.flow(buttons, cols, rows)` em
  `web/js/core.js` (primeira posição livre, linha a linha; o que não couber fica de fora).
  O mesmo encaixe vale para as duas orientações.
- `textColor`: cor do texto e do ícone (`#rrggbb`).
- `image`: nome de arquivo em `Documentos\StreamDeck\imagens` (substitui o ícone; servido em `/img/<nome>`).
- `on`: `{label, icon, color, textColor, image}`: aparência quando um botão `toggle` está ligado.
- `live`: `clock | date | volume:master | volume:effects | volume:mic | timer`: texto ao vivo
  no lugar do rótulo (`timer` = tempo desde que este botão liga/desliga foi ligado).
- Pasta: `{kind:"folder", label, icon, color, w, h, buttons:[Botão...]}`; abre por cima da página
  com os botões de dentro e um "Voltar"; pasta dentro de pasta não é permitida.
**Página:** `apps: ["obs64.exe", ...]` (troca para esta página quando o app em foco no PC é um deles).
**Fader `effects`:** 0..200 (os outros 0..100). `levels[t]` passa a ter `max`.

**API nova/alterada:**
| Método | Rota | |
|---|---|---|
| GET | `/api/press?p=&b=&f=` | `f` = índice dentro da pasta `b` (opcional); chave de toggle `"p:b"` ou `"p:b:f"` |
| GET | `/api/state` | + `app` (exe em foco, minúsculo), `since: {"p:b": epoch_s}` dos toggles ligados |
| GET | `/api/library` | `{ok, groups:[{name, items:[{label, icon, color, action, help?}]}]}` comandos prontos |
| GET | `/api/images` | `{ok, images:[nome]}` ; GET `/img/<nome>` (com código, como a API) |
| GET | `/api/local/windows` | `{ok, windows:[{title, exe, path}]}` janelas abertas (só no PC) |
| POST | `/api/local/images?name=` | corpo = bytes PNG/JPG/GIF/WEBP (até 2 MB) -> `{ok, name}` |
| POST | `/api/local/sounds?name=` | corpo = bytes MP3/WAV (até 20 MB) -> `{ok, name}` |
| GET | `/api/local/export` | zip com config.json, imagens/ e sons/ |
| POST | `/api/local/import` | corpo = esse zip -> substitui config (com backup), adiciona imagens/sons |

**Ações novas:** `app` (`target` exe ou caminho; traz a janela se aberta, senão abre),
`apphotkey` (`app`, `keys`, `back` bool: volta para a janela anterior),
`site` (`url`, `browser`: default|chrome|edge|firefox|brave, `profile` opcional, `appmode` bool),
`tab` (`browser`, `title`: vai para o navegador e passa as abas com Ctrl+Tab até achar o título).
Tipos de campo novos: `app` (escolher entre janelas abertas ou digitar), `color`.

**Celular, ajustes por aparelho (`sd_prefs`):** `vibrate` (bool, padrão true), `autoPage` (bool, padrão true).

## 2.6: OBS, toque longo/duplo, confirmação, sons com progresso

**Botão (campos novos, opcionais):**
- `hold`: ação ao segurar (~500 ms). `double`: ação no toque duplo (janela ~300 ms).
  Quando `double` existe, o toque simples espera a janela antes de disparar.
  Botões com repetição ao segurar (volume, setas) não usam `hold`.
- `confirm`: bool. O celular pede "Toque de novo para confirmar" (3 s) antes de enviar.
  A biblioteca marca desligar/reiniciar/suspender com `confirm: true`.
- `live` ganha `obs:stream`, `obs:record`, `obs:scene` (nome da cena atual) e
  `sound` (progresso do som que este botão tocou).
- `lit`: `obs:stream | obs:record | obs:scene=<nome> | obs:mute=<fonte>`: o botão
  acende conforme o estado no OBS (independente de `toggle`).

**API:**
| Método | Rota | |
|---|---|---|
| GET | `/api/press?p=&b=&f=&g=` | `g` = `tap` (padrão) \| `hold` \| `double` |
| GET | `/api/state` | + `sounds: [{key:"p:b[:f]", file, pos, dur}]` (tocando agora, s) e `obs: {ok, stream, record, scene, muted:{fonte:bool}}` |
| GET | `/api/local/obs` | `{ok, host, port, has_password, connected, error}` |
| POST | `/api/local/obs` | `{host, port, password?}` salva em `seguranca.json` (senha nunca volta) e reconecta |
| GET | `/api/local/obs/scenes` | `{ok, scenes:[nome], inputs:[nome]}` |

**Ações novas (grupo "OBS"):** `obs_scene` (`scene`, campo `obs_scene`), `obs_stream` (`mode`: toggle\|start\|stop),
`obs_record` (idem), `obs_mute` (`input`, campo `obs_input`, `mode`). Tipos de campo novos: `obs_scene`, `obs_input`
(lista de `/api/local/obs/scenes`, com texto livre).
**Sons:** `sound` ganha `fade_in` (ms, 0–5000); `stopsound` ganha `fade` (ms, 0–5000).

OBS: obs-websocket v5 (vem no OBS 28+), porta 4455, cliente WebSocket próprio (stdlib),
autenticação SHA-256 (challenge/salt), reconexão automática a cada 5 s em segundo plano.

## 2.7: modelos, duplicar página, ícones e tema claro

**Ícones:** `icon` aceita um nome do conjunto (`SD.ICONS`) ou `emoji:<caractere(s)>`
(até 8 caracteres). `SD.iconHtml(icon, size, color)` desenha qualquer um dos dois
(SVG ou emoji em texto) e é o que celular e editor usam. `SD.ICON_META` =
`[{name, label, tags:[...]}]` em pt-BR para a busca. O conjunto cresce para ~150 ícones.
O servidor aceita `emoji:` na validação.

**Modelos de página:** `GET /api/templates` -> `{ok, templates:[{id, name, desc, icon, page:{name, buttons}}]}`
(Rádio, OBS, Reunião (Teams/Zoom/Discord), Mídia, Atalhos do Windows, Navegador).
O editor insere uma cópia como nova página (nomes repetidos ganham " (2)").

**Editor:** duplicar página; botão direito/menu do bloco: "Copiar para página…" e
"Mover para página…" (vai para a primeira posição livre; se não houver, cria no fim).

**Tema:** `sd_prefs.theme` no celular e `sd_ed_theme` no editor = `auto | escuro | claro`
(auto segue o aparelho). Os blocos coloridos mantêm suas cores nos dois temas.

## 2.8: agendamentos e música tocando agora

**Agendamentos** (no config, nível de cima): `schedules: [Agendamento]` (até 50).

```json
{ "id": "a1b2c3", "name": "Vinheta da hora certa", "enabled": true,
  "when": { "type": "daily", "time": "08:00", "days": [1,2,3,4,5] },
  "action": { "type": "sound", "file": "vinheta.mp3" } }
```

- `when.type`:
  - `daily`: `time` "HH:MM", `days` 0=domingo..6=sábado (vazio = todos);
  - `every`: `minutes` 1..1440, `from`/`to` "HH:MM" opcionais (janela do dia, as duas pontas
    inclusive: das 08:00 às 22:00 roda também às 22:00; pode cruzar a meia-noite), `days`; alinhado ao relógio
    (a cada 60 min = toda hora cheia; a cada 15 = :00 :15 :30 :45);
  - `once`: `at` "YYYY-MM-DDTHH:MM" (desliga sozinho depois de rodar).
- `action`: qualquer ação válida (exceto `page`). Horário do PC (hora local).
- Roda no máximo uma vez por minuto previsto; se o PC estava desligado, não recupera atrasados.
- Um agendamento malformado não atrapalha os outros (fica com `last_error: "agendamento invalido"`).
- Importar (`/api/local/import`) ou restaurar cópia chega com todos os agendamentos desligados; a resposta
  traz `schedules_disabled` (quantos foram desligados) para o usuário revisar e ligar.
- Um `once` que já rodou não volta ligado se o editor salvar uma cópia antiga dele.
- API (só no PC): `GET /api/local/schedules` -> `{ok, now, items:[{id, next, last, last_error}]}`;
  `POST /api/local/schedules/run {id}` testa agora.

**Música tocando agora:** `GET /api/state` ganha `nowplaying: {title, artist, app} | null`.
Fonte: título das janelas de players conhecidos (Spotify, YouTube/YouTube Music/Deezer/SoundCloud no
Chrome/Edge/Firefox/Opera/Brave, VLC, foobar2000, AIMP, Winamp, MusicBee, iTunes/Apple Music) com
regras por app (Spotify Web no navegador não é detectado: o título da aba, "Música • Artista", não
diz o site e se confunde com outros, como Instagram); atualizado a cada ~3 s em segundo plano. `live: "nowplaying"` mostra
"Música — Artista" (rolando se não couber); `live: "nowplaying:title"` / `"nowplaying:artist"` só um.
