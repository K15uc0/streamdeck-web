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

## API (todas exigem `X-StreamDeck: 1`; chave do aparelho no cookie `sdk`, ver 2.11)

| Método | Rota | Resposta |
|---|---|---|
| GET | `/api/config` | config v2; cabeçalhos `X-Config-Version` e `X-Device-Pages` (2.11) |
| POST | `/api/config` | `{ok, v}`; 400 `{ok:false, error}`; 403 se ação perigosa vinda de fora do PC |
| GET | `/api/actions` | `{ok, actions:[ActionSchema]}` |
| GET | `/api/info` | `{ok, name, code (só no PC), sounds, tabs, version, local, update, device}` |
| GET | `/api/press?p=&b=` | `{ok, toggles?}` ; erro `{ok:false, error}`; 403 `{reason:"page"\|"full"}` (2.11) |
| GET | `/api/state?levels=1` | `{ok, v, update, toggles:{"p:b":true}, levels?, device}` |
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

**Grade por página (2.10).** Opcional em cada página:
`"grid": {"columns": 5, "rows": 4, "portrait": {"columns": 4, "rows": 5}}` (mesmos
limites; `portrait` opcional, com a mesma regra de transpor). Sem `grid`, a página usa
a grade geral. `SD.pageGrid(cfg, i)` (core.js) devolve a grade válida da página; o
celular e o editor usam a da página atual.

**Grade de cada página (2.10.1).** Toda página tem `grid`. A migração
(`schema.add_page_grids`, chamada por `schema.migrate` ao carregar o config, em
backups e no import) dá a cada página sem `grid` uma cópia da geral (`columns`,
`rows` e `portrait` se houver). Se os botões não couberem (mesma regra de
`SD.flow`, portada em `schema.flow`; botões vazios no fim da lista não contam), a
grade cresce para a menor que caiba (`schema.fit_grid`: até 10 × 8, primeiro em
colunas, proporção perto da geral). É idempotente. O `columns`/`rows` geral
continua obrigatório: serve de reserva para clientes antigos. No editor, Colunas e
Linhas (e a vertical) mudam só a página atual; página nova copia a grade da atual,
duplicada copia a da original, modelo usa a dele ou a da atual.

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

## 2.9: monitor do PC, consumo das IAs e ponte do Claude Code

**Módulos novos**

- `streamdeck/monitor.py`: CPU, memória, discos, rede, GPU (PDH "GPU Engine"), processos
  (Toolhelp32, GetProcessTimes, GetProcessMemoryInfo) e temperaturas do LibreHardwareMonitor
  (`http://127.0.0.1:8085/data.json`, cache de 5 s). Só coleta enquanto alguém olhou nos últimos
  60 s (`touch()`); `start()`/`stop()` controlam a thread. Fora do Windows devolve valores
  simulados (testes). `kill(pid)` recusa processos protegidos (`PROTECTED_NAMES`: csrss, winlogon,
  explorer, svchost etc.) e o próprio programa.
- `streamdeck/ia.py`: consumo das IAs. `status()` -> `{claude, codex, grok}`; `grok` é sempre `None`
  por enquanto. Claude vem de `ia/claude.json` (gravado pela ponte); Codex vem dos logs de sessão em
  `CODEX_HOME` ou `~/.codex/sessions` (nunca lê credenciais). Cada janela: `{used, left, resets_at}`;
  `resets_at` no passado zera o uso. Também instala/remove a ponte (`install_bridge`,
  `uninstall_bridge`, `bridge_installed`) e, na partida, reaponta a ponte se a versão ou o caminho mudou
  (`refresh_bridge`, em thread).
- `streamdeck/ponte_claude.py`: a status line do Claude Code chama a ponte com o JSON no stdin. Ela grava
  `rate_limits` e `ts` em `ia/claude.json` e repassa o mesmo stdin para a status line anterior
  (guardada em `ia/statusline_anterior.json`, com orçamento de 1,8 s). Erros viram uma linha de texto e
  nunca derrubam o Claude Code. Só biblioteca padrão.
- Exe da ponte: `ponte_entry.py` -> `StreamDeckPonte.exe` (PyInstaller `--console`, job "Gerar a ponte
  da status line" em `.github/workflows/release.yml`), comprimido em `ponte.zip` e embutido no
  `StreamDeck.exe`. Ao instalar, é extraído em `Documentos\StreamDeck\ia\ponte` (caminho estável entre
  atualizações). A status line grava `"command"` apontando para esse exe (ou para `ponte_claude.py`
  quando roda pelo código).
- Arquivos em `Documentos\StreamDeck\ia\`: `claude.json`, `statusline_anterior.json`, `ponte\`.
  O `settings.json` do Claude Code (`CLAUDE_CONFIG_DIR` ou `~/.claude`) recebe só a chave `statusLine`
  (backup `settings.json.streamdeck.bak`, só do primeiro).

**API**

- `GET /api/state?pc=1`: acrescenta `pc` (lido do cache; quem pediu chama `monitor.touch()`):
  `{cpu, mem_pct, mem_used, mem_total, gpu, temp_cpu, temp_gpu, down_bps, up_bps, disk:[...], ts}`.
- `GET /api/state?ia=1`: acrescenta `ia` = `{claude, codex, grok}`. Cada um é `null` ou
  `{five_hour, weekly, updated, source, tokens_today}`, onde as janelas são `{used, left, resets_at}`.
  O resultado fica em cache por 10 s (`IA_TTL`).
- `GET /api/monitor?sort=cpu|mem`: `{ok, snapshot, processes (até 15), allow_kill}` (2.11: `allow_kill`
  = quem pede tem Controle total).
- `POST /api/monitor/kill` `{pid}`: exige Controle total do aparelho (2.11; antes `allow_kill` nos ajustes).
  Protegido ou inexistente -> 400 com a mensagem.
- `GET /api/local/ia` (só no PC): `{ok, bridge_installed, claude_updated, codex_found}`.
- `POST /api/local/ia` (só no PC) `{install: true|false}`: instala ou remove a ponte; 400 se falhar.
- (2.11) `POST /api/local/settings_kill` saiu: virou Controle total por aparelho.

**Botões**

- Modelo de página "Monitor do PC" em `streamdeck/templates.py` (id `monitor`).
- `kind: "monitor"` (ao lado de `button`, `fader`, `folder`): sem ação; o toque abre a tela de processos.
  Pode ficar dentro de pasta (`FOLDER_KINDS`); pasta dentro de pasta continua não permitida.
- Valores ao vivo (`live`, validados por `schema.LIVE`): `pc:cpu`, `pc:mem`, `pc:gpu`, `pc:temp_cpu`,
  `pc:temp_gpu`, `pc:net`, `pc:disk:<letra A-Z>`, `ia:claude:5h`, `ia:claude:week`, `ia:codex:5h`,
  `ia:codex:week`. No cliente, `SD.pc` e `SD.ia` guardam a última resposta (`applyPc`/`applyIa` repintam
  os blocos com prefixo `pc:`/`ia:`).

## 2.11: aparelhos (chave por aparelho)

Antes, todo aparelho entrava com o mesmo código (`token.txt`, cookie `sdk` ou `?k=`). Agora o código geral
só **cadastra** aparelhos; cada aparelho entra com a chave dele.

**Arquivo** `Documentos\StreamDeck\aparelhos.json` (`paths.DEVICES_PATH`), módulo `streamdeck/devices.py`:
`{"devices": [{id, key, name, created, last_seen, last_ip, pages: null|[ids de página], full}], "legacy_full": bool}`.
Gravação atômica (`storage.write_json`: `.tmp` + `os.replace`) sob `devices.LOCK`; relido se o mtime mudar.
Arquivo ilegível: ninguém entra pela chave e nada é gravado por cima (`DevicesError`). Limite de 50 aparelhos.
`key` = `secrets.token_hex(16)`, comparada com `hmac.compare_digest` contra todos (sem sair no primeiro).
A chave nunca sai de `devices.py` a não ser no `Set-Cookie` do próprio aparelho: `list_public()`, `find()`
e `get()` devolvem cópias sem `key`; o log mostra só nome e IP.
`last_seen`/`last_ip` (`touch`): sempre na memória, no disco no máximo a cada 60 s por aparelho (ou se o IP mudar).

**Quem pede** (`Handler._auth`, guardado em `self._ctx`):

1. `127.0.0.1`/`::1`: o próprio PC, pode tudo (`LOCAL_CTX`), sem aparelho.
2. Cookie `sdk` = chave de um aparelho: aquele aparelho (removido -> 403 no pedido seguinte, sem cache).
3. Cookie `sdk` = código geral (cookie de antes da 2.11): `devices.upgrade(ip, navegador)` cria o aparelho
   e a resposta desse mesmo pedido leva `Set-Cookie: sdk=<chave nova>` (HttpOnly, SameSite=Strict). Pedidos
   juntos do mesmo IP e navegador (120 s) reaproveitam o mesmo aparelho.
4. `?k=<código geral>` (scripts, testes): sem aparelho, todas as páginas, **sem** Controle total.
   Chave de aparelho em `?k=` não vale (chaves nunca vão no endereço).
5. Senão 403 `codigo de acesso invalido` e conta tentativa (`security.note_fail`, bloqueio após 10).

Primeiro acesso `/?k=<código>`: cria o aparelho (ou reaproveita, se o cookie já é de um aparelho) e responde
302 com `Set-Cookie` da chave e `Location: /` (ou `/#sync=`). Do próprio PC não cria aparelho.
`GET /api/info` só entrega `code` ao PC (um aparelho com páginas limitadas poderia se recadastrar com ele);
no celular, a troca de PC pelas abas usa `/#sync=` quando não há código guardado (entra pelo cookie daquele PC).
"Gerar novo código" troca só o código geral: aparelhos cadastrados continuam valendo.

**Permissões** (servidor decide; o celular só esconde):

- Páginas: `pages` `null` = todas. `GET /api/press` em página fora da lista -> 403 `{reason: "page"}`
  (não conta tentativa). A lista guarda **ids de página** (`page.id` no config, `^[0-9a-f]{4,16}$`, único;
  `schema.add_page_ids` dá um id a toda página sem id na migração; o editor dá id novo a página nova,
  duplicada ou de modelo e mantém o id ao mover). A cada pedido `httpd._dev_ctx` converte ids em posições
  atuais (`devices.page_indices`), então `X-Device-Pages`, `device.pages` e `/api/press` usam índices
  sempre certos: mover não muda o que o aparelho vê, página apagada some, página nova fica oculta para
  aparelho com páginas escolhidas até marcar. Listas antigas de índices (2.11 inicial) viram ids uma vez,
  com o config atual, ao ler o `aparelhos.json`.
- Controle total (`full`): sem ele, 403 `{reason: "full"}` para ações sensíveis (`devices.sensitive`):
  `command` que desliga/reinicia/suspende/encerra a sessão (`devices.POWER_RE`) e `multi` com algum
  desses; e `POST /api/monitor/kill`. Abrir programas, sites e comandos comuns continua liberado
  (os botões são montados no próprio PC).
- Migração do `allow_kill` (uma vez, quando `aparelhos.json` ainda não existe): grava `legacy_full` =
  `allow_kill` e tira `allow_kill` dos ajustes. Aparelhos criados pelo cookie antigo (os que já existiam)
  nascem com `full = legacy_full`; aparelhos novos pelo QR nascem sem.

**API**

- `/api/state` e `/api/info`: `device: {name, pages, full}` (no PC: `{"Este PC", null, true}`).
- `/api/config`: cabeçalho `X-Device-Pages` (`*` = todas, `0,2`, ou vazio = nenhuma), para o celular
  já abrir só com as páginas liberadas; o config vem inteiro (índices e ações `page` não mudam).
- `GET /api/local/devices` (só no PC): `{ok, devices: [{id, name, created, last_seen, last_ip, pages, full}],
  pages: [{name, index}]}`, sem chaves.
- `POST /api/local/devices` (só no PC) `{id, op, value}`: `op` = `rename` (1 a 40 letras), `pages`
  (`null` ou lista de ids), `full` (bool) ou `remove`. 400 valor inválido, 404 aparelho inexistente.

**Celular** (`deck.js`, funções puras em `core.js`: `SD.pageOk`, `SD.allowedPages`, `SD.nextPage`,
`SD.parseDevicePages`): `SD.device` (guardado em `sd_device`) esconde as páginas não liberadas nos pontos,
no deslizar, na troca automática pelo app e na ação "Ir para página"; sem nenhuma página mostra
"Nenhuma página liberada". Recusas 403 com `reason` viram avisos claros.
