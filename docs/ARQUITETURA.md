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
