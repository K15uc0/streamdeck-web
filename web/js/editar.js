/* Stream Deck - editor do PC (pagina /editar, so no proprio PC).
   Reutiliza core.js (rede, icones, cores, encaixe SD.flow, remapeamento de paginas).
   Salva sozinho (POST /api/config) ~600 ms depois de cada mudanca. */
(function () {
  "use strict";

  var SD = window.SD, $ = SD.$, esc = SD.esc, el = SD.el, clone = SD.clone;

  var FADERS = [["master", "Som do PC (master)"], ["effects", "Efeitos sonoros"], ["mic", "Microfone"]];
  var FADER_ICON = { master: "sound", effects: "music", mic: "mic" };
  var FADER_MAX = { master: 100, effects: 200, mic: 100 };
  var NO_STEP = { page: 1, multi: 1 };
  var LIVE = [["", "Nenhum (mostra o rótulo)"], ["clock", "Relógio (hora)"], ["date", "Data"],
    ["volume:master", "Volume do PC"], ["volume:effects", "Volume dos efeitos"], ["volume:mic", "Volume do microfone"],
    ["timer", "Cronômetro (desde que ligou)"], ["obs:stream", "OBS: transmissão"], ["obs:record", "OBS: gravação"],
    ["obs:scene", "OBS: cena atual"], ["sound", "Progresso do som"],
    ["nowplaying", "Música tocando agora"], ["nowplaying:title", "Só o nome da música"], ["nowplaying:artist", "Só o artista"]];
  /* grupos novos do 2.9: o PC e o consumo das IAs (discos: C, D, E; outra letra ja salva entra sozinha) */
  var LIVE_PC = [["pc:cpu", "CPU (uso)"], ["pc:mem", "Memória (uso)"], ["pc:gpu", "GPU (uso)"],
    ["pc:temp_cpu", "Temperatura da CPU"], ["pc:temp_gpu", "Temperatura da GPU"], ["pc:net", "Rede (baixar e enviar)"],
    ["pc:disk:C", "Disco (escolha a letra)"]];
  var LIVE_IA = [["ia:claude:5h", "Claude: janela de 5 h"], ["ia:claude:week", "Claude: semana"],
    ["ia:codex:5h", "Codex: janela de 5 h"], ["ia:codex:week", "Codex: semana"]];
  /* exemplo (so para a previa): {principal, linhas pequenas, barra 0..100, legenda} */
  var RICH_SAMPLE = {
    "pc:cpu": ["23%", [], 23, "CPU"], "pc:mem": ["58%", ["9,3/16 GB"], 58, "Memória"], "pc:gpu": ["41%", [], 41, "GPU"],
    "pc:temp_cpu": ["54 °C", [], null, "CPU °C"], "pc:temp_gpu": ["49 °C", [], null, "GPU °C"],
    "pc:net": ["\u2193 2,4 MB/s", ["\u2191 180 KB/s"], null, "Rede"],
    "ia:claude:5h": ["37%", ["usado · faltam 63%", "reinicia 18:40"], 37, "Claude 5 h"],
    "ia:claude:week": ["62%", ["usado · faltam 38%", "reinicia sex 09:00"], 62, "Claude sem"],
    "ia:codex:5h": ["12%", ["usado · faltam 88%", "reinicia 17:10"], 12, "Codex 5 h"],
    "ia:codex:week": ["29%", ["usado · faltam 71%", "reinicia seg 08:00"], 29, "Codex sem"] };
  function richSample(live) {
    var m = /^pc:disk:([A-Z])$/.exec(live || "");
    if (m) return [ "68%", [m[1] + ": 312/460 GB"], 68, "Disco " + m[1] + ":" ];
    return RICH_SAMPLE[live] || null;
  }
  function barColor(p) { return p < 70 ? "#30d158" : p < 90 ? "#ffd60a" : "#ff453a"; }
  var LIVE_SAMPLE = { clock: "", date: "", "volume:master": "75%", "volume:effects": "100%", "volume:mic": "80%", timer: "00:00",
    "obs:stream": "AO VIVO", "obs:record": "REC", "obs:scene": "Cena", sound: "0:12",
    nowplaying: "Música \u2014 Artista", "nowplaying:title": "Música", "nowplaying:artist": "Artista" };
  /* "acender quando" (lit): estado do OBS */
  var LIT = [["", "Nunca (normal)"], ["obs:stream", "OBS transmitindo"], ["obs:record", "OBS gravando"],
    ["obs:scene", "Cena do OBS for…"], ["obs:mute", "Fonte do OBS estiver mutada…"]];
  /* teclas que repetem ao segurar no celular (igual ao deck.js) */
  var REPEAT = { volumeup: 1, volumedown: 1, left: 1, right: 1, up: 1, down: 1, pageup: 1, pagedown: 1 };
  var GESTURES = [["hold", "Ao segurar"], ["double", "Toque duplo"]];
  var obsList = null;        /* {ok, scenes, inputs} de /api/local/obs/scenes (null = nao carregado) */
  var SIZES = [[1, 1], [2, 1], [1, 2], [2, 2]];
  var RECENT_KEY = "sd_ed_recent_colors";

  var cfg = null;            /* config em edicao */
  var page = 0;              /* pagina mostrada */
  var folder = -1;           /* indice da pasta aberta na pagina (-1 = pagina) */
  var orient = "land";       /* land | port (segue o aparelho escolhido) */
  /* aparelho da pre-visualizacao (tamanho da tela em px CSS, como no celular) */
  var DEV_KEY = "sd_ed_device";
  var DEVICES = [
    ["phone-p", "Celular (em pé)", 390, 844],
    ["phone-l", "Celular (deitado)", 844, 390],
    ["tab-p", "Tablet (em pé)", 820, 1180],
    ["tab-l", "Tablet (deitado)", 1180, 820],
    ["custom", "Personalizado", 0, 0]
  ];
  var dev = { id: "phone-l", w: 844, h: 390 };
  var geoEd = null;          /* SD.geometry da pre-visualizacao */
  var devScale = 1;          /* escala da moldura do aparelho na tela do editor */
  var sel = -1;              /* indice selecionado na lista (pode passar do fim = posicao vazia) */
  var msel = [];             /* selecao multipla (indices); contem sel */
  var clip = null;           /* blocos copiados (lista) */
  var sounds = [], images = [], windows = null;
  var rec = null;            /* gravacao de atalho em andamento */
  var appPath = false;       /* campo "app": guardar caminho em vez do exe */

  /* historico (desfazer/refazer): fotos do config */
  var hist = [], pos = -1, lastKey = null, lastAt = 0;

  /* salvamento */
  var schedWarn = "";        /* agendamento com acao incompleta (texto do aviso) */
  var savedV = null, dirty = false, inflight = false, saveT = null, seq = 0, saveBad = false;
  var retryMs = 0;           /* espera atual antes de tentar de novo (falha de rede/PC) */
  var bad = {};              /* "pagina:posicao[:filho]" -> campo faltando (acao incompleta) */

  /* ========================================================= utilidades === */
  var isEmpty = SD.isEmpty;   /* mesma regra do celular */
  /* vazio para o editor: alem da regra do celular, imagem/texto ao vivo/cor do texto contam como conteudo */
  function edEmpty(b) { return isEmpty(b) && !(b && (b.image || b.live || b.textColor || b.hold || b.double || b.lit)); }
  function curPage() { return cfg.pages[page]; }
  function fold() {
    var bs = curPage().buttons || [];
    return folder >= 0 && bs[folder] && bs[folder].kind === "folder" ? bs[folder] : null;
  }
  /* dono da lista em edicao: a pagina ou a pasta aberta */
  function holder() { var f = fold(); return f || curPage(); }
  function list() { var h = holder(); if (!h.buttons) h.buttons = []; return h.buttons; }
  function bkey(i) { return folder >= 0 ? page + ":" + folder + ":" + i : page + ":" + i; }
  function count(pg) {
    var bs = pg.buttons || [], n = 0;
    for (var i = 0; i < bs.length; i++) if (!edEmpty(bs[i])) n++;
    return n;
  }
  /* grade da orientacao: {c, r, auto} */
  function dims(o) {
    if (o === "land") return { c: cfg.columns, r: cfg.rows };
    if (cfg.portrait) return { c: cfg.portrait.columns, r: cfg.portrait.rows };
    if (cfg.columns > cfg.rows) return { c: cfg.rows, r: cfg.columns, auto: true };
    return { c: cfg.columns, r: cfg.rows, auto: true };
  }
  function opt(s, value, label, cur) {
    var o = el("option", null, null, s);
    o.value = value; o.textContent = label;
    if (String(cur) === String(value)) o.selected = true;
    return o;
  }
  function setStatus(text, cls) { var s = $("status"); s.textContent = text; s.className = "status" + (cls ? " " + cls : ""); }
  function clampSpan(v) { v = parseInt(v, 10) || 1; return Math.max(1, Math.min(4, v)); }
  function imgUrl(name) { return "/img/" + encodeURIComponent(name) + (SD.TOKEN ? "?k=" + encodeURIComponent(SD.TOKEN) : ""); }
  function isSel(i) { for (var k = 0; k < msel.length; k++) if (msel[k] === i) return true; return false; }
  function selectOne(i) { sel = i; msel = i >= 0 ? [i] : []; }
  function pageName(p) { return cfg.pages[p].name || "Página " + (p + 1); }

  /* envia bytes de um arquivo (FileReader -> ArrayBuffer -> XHR) */
  function upload(url, file, cb) {
    var fr = new FileReader();
    fr.onload = function () {
      var x = new XMLHttpRequest();
      x.open("POST", url + (url.indexOf("?") < 0 ? "?" : "&") + (SD.TOKEN ? "k=" + encodeURIComponent(SD.TOKEN) + "&" : "") + "t=" + SD.now(), true);
      x.setRequestHeader("X-StreamDeck", "1");
      x.setRequestHeader("Content-Type", "application/octet-stream");
      x.onreadystatechange = function () {
        if (x.readyState !== 4) return;
        var data = null;
        try { data = JSON.parse(x.responseText); } catch (e) {}
        cb(x.status === 200 && !!data && data.ok !== false, data, x.status);
      };
      x.send(fr.result);
    };
    fr.onerror = function () { cb(false, { error: "não leu o arquivo" }, -1); };
    fr.readAsArrayBuffer(file);
  }
  function pickFile(accept, multiple, fn) {
    var i = el("input");
    i.type = "file"; i.accept = accept; i.multiple = !!multiple;
    i.style.display = "none";
    document.body.appendChild(i);
    i.onchange = function () { var fs = i.files; document.body.removeChild(i); if (fs && fs.length) fn(fs); };
    i.click();
  }

  /* ======================================================= historico === */
  function snapshot() { return JSON.stringify(cfg); }
  function resetHistory() { hist = [snapshot()]; pos = 0; lastKey = null; updUndo(); }
  /* change(fn, key, light): aplica a mudanca, guarda no historico e salva.
     key: mudancas seguidas no mesmo campo viram um passo so do desfazer.
     light: nao redesenha o formulario (o campo em edicao continua com o foco). */
  function change(fn, key, light) {
    closePop();
    fn();
    var t = new Date().getTime();
    var snap = snapshot();
    if (snap === hist[pos]) { renderAll(light); return; }
    hist = hist.slice(0, pos + 1);
    if (key && key === lastKey && t - lastAt < 1500 && pos > 0) hist[pos] = snap;
    else { hist.push(snap); pos++; if (hist.length > 200) { hist.shift(); pos--; } }
    lastKey = key || null; lastAt = t;
    renderAll(light);
    scheduleSave();
  }
  function undo() { if (pos > 0) { pos--; restore(); } }
  function redo() { if (pos < hist.length - 1) { pos++; restore(); } }
  function fixView() {
    if (page >= cfg.pages.length) page = cfg.pages.length - 1;
    if (folder >= 0 && !fold()) { folder = -1; selectOne(-1); }
    var ns = cfg.schedules ? cfg.schedules.length : 0;
    if (schedSel >= ns) schedSel = ns - 1;
  }
  function restore() {
    closePop();
    cfg = JSON.parse(hist[pos]);
    lastKey = null;
    fixView();
    renderAll();
    scheduleSave();
  }
  function updUndo() { $("undo").disabled = pos <= 0; $("redo").disabled = pos >= hist.length - 1; }

  /* ======================================================== salvamento === */
  function blank(v) {
    return v === undefined || v === null || (typeof v === "string" && !SD.trim(v)) ||
      (v && typeof v === "object" && (v.length === 0 || (v.length === undefined && !Object.keys(v).length)));
  }
  /* primeiro campo obrigatorio vazio da acao (ou null se esta completa).
     Passos incompletos sao tirados da lista (fixSteps) para nao travar o salvamento. */
  function missing(a, fixSteps) {
    var s = SD.schemaOf(a);
    if (!s) return null;   /* tipo desconhecido: o PC decide */
    var fs = s.fields || [];
    for (var i = 0; i < fs.length; i++) {
      var v = a[fs[i].key];
      if (fs[i].kind === "steps" && v && v.length) {
        var keep = [], miss = null;
        for (var j = 0; j < v.length; j++) {
          var m = v[j] && v[j].type ? missing(v[j], fixSteps) : "tipo do passo";
          if (m) { if (!miss) miss = "passo " + (j + 1) + ": " + m; } else keep.push(v[j]);
        }
        if (miss && fixSteps) a[fs[i].key] = keep;
        if (miss && !fixSteps) return miss;
        if (fs[i].required && !keep.length && miss) return miss;
        continue;
      }
      if (fs[i].required && blank(v)) return fs[i].label;
    }
    return null;
  }
  function emptyKeep(b) {
    var e = SD.emptyButton();
    if (b && clampSpan(b.w) > 1) e.w = clampSpan(b.w);
    if (b && clampSpan(b.h) > 1) e.h = clampSpan(b.h);
    return e;
  }
  /* limpa uma lista de botoes (pagina ou pasta) antes de salvar */
  function cleanList(bs, prefix, inFolder) {
    for (var k = 0; k < bs.length; k++) {
      var b = bs[k];
      if (!b) continue;
      if (b.kind === "folder") {
        if (inFolder) { bs[k] = SD.emptyButton(); continue; }   /* pasta dentro de pasta: nao */
        if (!b.buttons) b.buttons = [];
        cleanList(b.buttons, prefix + k + ":", true);
        continue;
      }
      if (b.on && blank(b.on)) delete b.on;
      if (b.kind === "fader" || b.kind === "monitor") { delete b.hold; delete b.double; delete b.confirm; delete b.lit; delete b.action; delete b.on; delete b.toggle; continue; }
      if (!b.confirm) delete b.confirm;
      if (!b.lit || /=$/.test(b.lit)) delete b.lit;
      for (var g = 0; g < GESTURES.length; g++) {
        var gk = GESTURES[g][0], ga = b[gk];
        if (!ga || !ga.type || ga.type === "none") { delete b[gk]; continue; }
        var gm = missing(ga, false);
        if (gm) { if (!bad[prefix + k]) bad[prefix + k] = GESTURES[g][1].toLowerCase() + ": " + gm; if (missing(ga, true)) delete b[gk]; }
      }
      if (b.kind === "fader" || !b.action || !b.action.type || b.action.type === "none") continue;
      var orig = missing(b.action, false);
      if (!orig) continue;
      bad[prefix + k] = orig;
      if (missing(b.action, true)) b.action = { type: "none" };
    }
    while (bs.length && edEmpty(bs[bs.length - 1]) && clampSpan(bs[bs.length - 1].w) === 1 && clampSpan(bs[bs.length - 1].h) === 1) bs.pop();
    for (var i = 0; i < bs.length; i++) if (edEmpty(bs[i])) bs[i] = emptyKeep(bs[i]);
  }
  function cleaned() {
    /* posicoes vazias no fim nao precisam ir para o arquivo.
       Acao incompleta vai como "nenhuma" (o rascunho continua no editor). */
    var c = clone(cfg);
    bad = {};
    for (var p = 0; p < c.pages.length; p++) {
      if (!c.pages[p].buttons) c.pages[p].buttons = [];
      cleanList(c.pages[p].buttons, p + ":", false);
      if (c.pages[p].apps && !c.pages[p].apps.length) delete c.pages[p].apps;
    }
    schedWarn = cleanSchedules(c);
    return c;
  }
  function badText() {
    for (var key in bad) if (bad.hasOwnProperty(key)) {
      var pk = key.split(":");
      if (pk.length === 3) return "Botão " + (+pk[2] + 1) + " da pasta (posição " + (+pk[1] + 1) + ") da página " + (+pk[0] + 1) + " incompleto: preencha " + bad[key];
      return "Botão " + (+pk[1] + 1) + " da página " + (+pk[0] + 1) + " incompleto: preencha " + bad[key];
    }
    return "";
  }
  function scheduleSave() {
    dirty = true; seq++;
    setStatus("Alterações não salvas…", "busy");
    retryMs = 0;
    clearTimeout(saveT);
    saveT = setTimeout(save, 600);
  }
  function save() {
    if (inflight) { saveT = setTimeout(save, 300); return; }
    inflight = true;
    var mySeq = seq;
    setStatus("Salvando…", "busy");
    var body = JSON.stringify(cleaned());
    if (cfg) renderGrid();   /* marca os blocos incompletos */
    SD.req("POST", "/api/config", body, function (ok, data, status) {
      inflight = false;
      if (ok) {
        retryMs = 0; saveBad = false;
        if (data && data.v != null) savedV = String(data.v);
        if (mySeq === seq) {
          dirty = false;
          var w = badText() || schedWarn;
          if (w) setStatus(w, "err"); else setStatus("Salvo ✓", "ok");
          /* o PC desligou um "uma vez" que ja rodou: recarrega para mostrar */
          if (data && data.once_disabled > 0 && !dirty) loadConfig(false);   /* nao descarta edicoes feitas durante o salvamento */
        }
        if (schedOpen) loadSchedInfo();
      } else if (status === 400) {
        /* erro de validacao: tentar de novo nao adianta; espera a proxima mudanca */
        retryMs = 0; saveBad = true;
        setStatus("Não salvou: " + SD.errText(data, status, "dados inválidos"), "err");
      } else {
        /* rede ou PC com problema: tenta de novo com espera crescente (2s, 4s, 8s... ate 30s) */
        retryMs = retryMs ? Math.min(retryMs * 2, 30000) : 2000;
        setStatus("Não salvou: " + SD.errText(data, status, "erro no PC") +
          " — tentando de novo em " + Math.round(retryMs / 1000) + " s", "err");
        clearTimeout(saveT);
        saveT = setTimeout(function () { if (dirty) save(); }, retryMs);
      }
    });
  }
  function loadConfig(first, msg) {
    SD.req("GET", "/api/config", null, function (ok, data, status, x) {
      if (!ok || !data || !data.pages) {
        setStatus("Erro ao carregar: " + SD.errText(data, status), "err");
        if (first) setTimeout(function () { loadConfig(true); }, 2000);
        return;
      }
      /* recarga automatica nao atropela edicoes feitas enquanto ela vinha */
      if (!first && !msg && dirty) return;
      cfg = data;
      savedV = x.getResponseHeader("X-Config-Version");
      if (page >= cfg.pages.length) page = 0;
      fixView();
      resetHistory();
      renderAll();
      setStatus(msg || (first ? "Pronto" : "Atualizado (mudou em outro lugar)"), "ok");
    });
  }
  /* se o config mudou fora daqui (outra aba, arquivo), recarrega quando nao ha nada pendente */
  function poll() {
    if (!cfg || dirty || inflight) return;
    SD.req("GET", "/api/state", null, function (ok, data) {
      if (ok && data && data.v != null && savedV && String(data.v) !== savedV && !dirty && !inflight) loadConfig(false);
    });
  }

  /* ============================================================ desenho === */
  function renderAll(light) {
    if (!cfg) return;
    renderPages();
    renderSchedRow();
    if (schedOpen) { renderSched(light); updUndo(); return; }
    hideSched();
    renderBar();
    renderGrid();
    if (light) renderPreview(); else renderInspector();
    updUndo();
  }

  /* ------------------------------------------------------------ paginas --- */
  var dragPage = -1;
  function renderPages() {
    var box = $("pages");
    box.innerHTML = "";
    for (var i = 0; i < cfg.pages.length; i++) (function (i) {
      var pg = cfg.pages[i];
      var row = el("div", "pg" + (i === page && !schedOpen ? " on" : ""), null, box);
      row.draggable = true;
      el("span", "n", String(i + 1), row);
      var t = el("span", "t", esc(pageName(i)), row);
      if (pg.apps && pg.apps.length) el("span", "ap", "auto", row).title = "Troca sozinha: " + pg.apps.join(", ");
      el("span", "c", String(count(pg)), row);
      var more = el("button", "more", "…", row);
      more.title = "Mais opções";
      more.onclick = function (e) { e.stopPropagation(); var r = more.getBoundingClientRect(); pageMenu(i, r.left, r.bottom + 4); };
      row.oncontextmenu = function (e) { e.preventDefault(); e.stopPropagation(); pageMenu(i, e.clientX, e.clientY); };
      var del = el("button", "del", "×", row);
      del.title = "Apagar página";
      row.onclick = function () {
        if (page !== i || folder >= 0 || schedOpen) { if (schedOpen) closeSched(); page = i; folder = -1; selectOne(-1); renderAll(); }
      };
      t.ondblclick = function (e) { e.stopPropagation(); renamePage(i, row, t); };
      del.onclick = function (e) { e.stopPropagation(); deletePage(i); };
      row.ondragstart = function (e) { dragPage = i; SD.setClass(row, "dragging", true); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", "p" + i); };
      row.ondragend = function () { dragPage = -1; renderPages(); };
      row.ondragover = function (e) {
        if (dragPage < 0) return;
        e.preventDefault();
        var r = row.getBoundingClientRect(), after = e.clientY > r.top + r.height / 2;
        SD.setClass(row, "drop-before", !after); SD.setClass(row, "drop-after", after);
      };
      row.ondragleave = function () { SD.setClass(row, "drop-before", false); SD.setClass(row, "drop-after", false); };
      row.ondrop = function (e) {
        if (dragPage < 0) return;
        e.preventDefault();
        var r = row.getBoundingClientRect(), to = e.clientY > r.top + r.height / 2 ? i + 1 : i;
        movePage(dragPage, to);
      };
    })(i);
  }
  function renamePage(i, row, t) {
    var inp = el("input");
    inp.value = cfg.pages[i].name || "";
    inp.maxLength = 60;
    row.replaceChild(inp, t);
    row.draggable = false;
    inp.focus(); inp.select();
    var done = false;
    function finish(keep) {
      if (done) return; done = true;
      var v = SD.trim(inp.value);
      if (keep && v && v !== cfg.pages[i].name) change(function () { cfg.pages[i].name = v; });
      else renderPages();
    }
    inp.onkeydown = function (e) {
      if (e.key === "Enter") finish(true);
      else if (e.key === "Escape") finish(false);
      e.stopPropagation();
    };
    inp.onblur = function () { finish(true); };
    inp.onclick = function (e) { e.stopPropagation(); };
  }
  /* remapeia acoes "Ir para pagina" das paginas e de dentro das pastas */
  function remapAll(map) { SD.remapPages(cfg, map); }   /* SD.remapPages ja entra nas pastas */
  /* move a pagina "from" para antes da posicao "to" e corrige os botoes "Ir para pagina" */
  function movePage(from, to) {
    var n = cfg.pages.length;
    if (to > from) to--;
    if (to === from) { renderPages(); return; }
    change(function () {
      var order = [], i, map = {};
      for (i = 0; i < n; i++) order.push(i);
      order.splice(from, 1);
      order.splice(to, 0, from);
      var pages = [];
      for (i = 0; i < n; i++) { pages.push(cfg.pages[order[i]]); map[order[i]] = i; }
      cfg.pages = pages;
      remapAll(map);
      page = map[page];
    });
  }
  function pageRefs(idx) {
    /* quantos botoes levam para a pagina idx */
    var n = 0;
    function walk(a) {
      if (!a) return;
      var s = SD.schemaOf(a);
      var fs = s && s.fields || [];
      for (var k = 0; k < fs.length; k++) {
        var v = a[fs[k].key];
        if (fs[k].kind === "page" && v === idx) n++;
        if (fs[k].kind === "steps" && v && v.length) for (var j = 0; j < v.length; j++) walk(v[j]);
      }
    }
    function walkList(bs) {
      for (var i = 0; i < bs.length; i++) {
        if (!bs[i] || bs[i].kind === "fader") continue;
        if (bs[i].kind === "folder") walkList(bs[i].buttons || []);
        else { walk(bs[i].action); walk(bs[i].hold); walk(bs[i].double); }   /* gestos tambem contam */
      }
    }
    for (var p = 0; p < cfg.pages.length; p++) walkList(cfg.pages[p].buttons || []);
    return n;
  }
  function deletePage(i) {
    if (cfg.pages.length <= 1) { SD.toast("Precisa ter ao menos uma página", true); return; }
    var pg = cfg.pages[i], refs = pageRefs(i);
    var msg = "Apagar a página \"" + pageName(i) + "\" e seus " + count(pg) + " botões?";
    if (refs) msg += "\n\n" + refs + " botão(ões) que levam para ela ficarão vazios.";
    msg += "\n\nDá para desfazer com Ctrl+Z.";
    if (!window.confirm(msg)) return;
    change(function () {
      var map = {}, n = cfg.pages.length;
      for (var k = 0; k < n; k++) map[k] = k < i ? k : (k === i ? -1 : k - 1);
      cfg.pages.splice(i, 1);
      remapAll(map);
      if (page > i || page >= cfg.pages.length) page = Math.max(0, page - 1);
      folder = -1;
      selectOne(-1);
    });
  }

  /* ---------------------------------------------- orientacao e tamanho --- */
  function numSelect(parent, cur, lo, hi, onChange) {
    var s = el("select", null, null, parent);
    for (var v = lo; v <= hi; v++) opt(s, v, String(v), cur);
    s.onchange = function () { onChange(parseInt(s.value, 10)); };
    return s;
  }
  function loadDev() {
    var o = null;
    try { o = JSON.parse(window.localStorage.getItem(DEV_KEY)); } catch (e) { o = null; }
    if (o && o.id) setDev(o.id, o.w, o.h, true);
    else setDev(dev.id, dev.w, dev.h, true);
  }
  function setDev(id, w, h, quiet) {
    var p = null;
    for (var k = 0; k < DEVICES.length; k++) if (DEVICES[k][0] === id) p = DEVICES[k];
    if (!p) { p = DEVICES[1]; id = p[0]; }
    if (id !== "custom") { w = p[2]; h = p[3]; }
    w = Math.max(240, Math.min(3000, parseInt(w, 10) || 0)); h = Math.max(240, Math.min(3000, parseInt(h, 10) || 0));
    dev = { id: id, w: w, h: h };
    orient = w >= h ? "land" : "port";
    if (!quiet) try { window.localStorage.setItem(DEV_KEY, JSON.stringify(dev)); } catch (e) {}
  }
  /* Horizontal/Vertical: gira o aparelho escolhido */
  function setOrient(o) {
    if (o === orient) return;
    var map = { "phone-p": "phone-l", "phone-l": "phone-p", "tab-p": "tab-l", "tab-l": "tab-p" };
    if (map[dev.id]) setDev(map[dev.id]);
    else setDev("custom", dev.h, dev.w);
  }
  function renderDevPick() {
    var dp = $("devpick");
    dp.innerHTML = "";
    el("span", null, "Aparelho:", dp);
    var s = el("select", null, null, dp);
    s.id = "devSel";
    for (var k = 0; k < DEVICES.length; k++) opt(s, DEVICES[k][0], DEVICES[k][1], dev.id);
    s.onchange = function () { setDev(s.value, dev.w, dev.h); renderAll(); };
    if (dev.id === "custom") {
      var iw = el("input", "num", null, dp), ih;
      iw.type = "number"; iw.id = "devW"; iw.value = dev.w; iw.min = 240; iw.max = 3000; iw.title = "Largura (px)";
      el("span", "x", "×", dp);
      ih = el("input", "num", null, dp);
      ih.type = "number"; ih.id = "devH"; ih.value = dev.h; ih.min = 240; ih.max = 3000; ih.title = "Altura (px)";
      el("span", "x", "px", dp);
      iw.onchange = ih.onchange = function () {
        setDev("custom", iw.value, ih.value);
        /* espera o foco ir para o proximo campo e devolve o foco depois de redesenhar */
        setTimeout(function () {
          var a = document.activeElement, id = a && a.id;
          renderAll();
          if (id && document.getElementById(id)) { try { document.getElementById(id).focus(); } catch (e) {} }
        }, 0);
      };
    } else el("span", "x", dev.w + " × " + dev.h, dp);
  }
  function renderBar() {
    /* caminho: Pagina > Pasta */
    var cr = $("crumb");
    cr.innerHTML = "";
    var f = fold();
    if (f) {
      cr.style.display = "";
      var bk = el("button", "crback", "‹ Voltar", cr);
      bk.id = "folderBack";
      bk.onclick = closeFolder;
      var pl = el("a", "crp", esc(pageName(page)), cr);
      pl.onclick = closeFolder;
      el("span", "crs", "›", cr);
      el("b", null, esc(SD.trim(f.label) || "Pasta"), cr);
      el("span", "crh", "Editando os botões de dentro da pasta", cr);
    } else cr.style.display = "none";

    renderDevPick();
    var o = $("orient");
    o.innerHTML = "";
    [["land", "Horizontal"], ["port", "Vertical"]].forEach(function (x) {
      var b = el("button", orient === x[0] ? "on" : "", x[1], o);
      b.id = "or-" + x[0];
      b.onclick = function () { setOrient(x[0]); renderAll(); };
    });
    var s = $("sizes");
    s.innerHTML = "";
    if (orient === "land") {
      el("span", null, "Grade horizontal:", s);
      numSelect(s, cfg.columns, 1, 10, function (v) { change(function () { cfg.columns = v; }); }).title = "Colunas";
      el("span", "x", "colunas ×", s);
      numSelect(s, cfg.rows, 1, 8, function (v) { change(function () { cfg.rows = v; }); }).title = "Linhas";
      el("span", "x", "linhas", s);
    } else {
      var d = dims("port");
      el("span", null, "Grade vertical:", s);
      var m = el("select", null, null, s);
      m.id = "portMode";
      opt(m, "auto", "Automática (invertida)", cfg.portrait ? "custom" : "auto");
      opt(m, "custom", "Personalizada", cfg.portrait ? "custom" : "auto");
      m.onchange = function () {
        change(function () {
          if (m.value === "auto") delete cfg.portrait;
          else cfg.portrait = { columns: Math.min(10, d.c), rows: Math.min(8, d.r) };
        });
      };
      if (cfg.portrait) {
        numSelect(s, cfg.portrait.columns, 1, 10, function (v) { change(function () { cfg.portrait.columns = v; }); });
        el("span", "x", "colunas ×", s);
        numSelect(s, cfg.portrait.rows, 1, 8, function (v) { change(function () { cfg.portrait.rows = v; }); });
        el("span", "x", "linhas", s);
      } else {
        el("span", "x", d.c + " × " + d.r, s);
      }
    }
  }
  function openFolder(i) {
    var b = list()[i];
    if (!b || b.kind !== "folder" || folder >= 0) return;
    if (!b.buttons) b.buttons = [];
    folder = i; selectOne(-1);
    renderAll();
  }
  function closeFolder() {
    if (folder < 0) return;
    var f = folder;
    folder = -1; selectOne(f);
    renderAll();
  }

  /* --------------------------------------------------------------- grade --- */
  /* aparencia efetiva: com on=true junta os campos de "Quando ligado" */
  function look(b, on) {
    var o = { label: b.label, icon: b.icon, color: b.color, textColor: b.textColor, image: b.image };
    if (on && b.on) {
      for (var k in b.on) if (b.on.hasOwnProperty(k) && b.on[k]) o[k] = b.on[k];
      /* igual ao deck.js: icone ligado sem imagem ligada esconde a imagem */
      if (b.on.icon && !b.on.image) o.image = "";
    }
    return o;
  }
  function liveText(live) {
    var d = new Date();
    function two(n) { return (n < 10 ? "0" : "") + n; }
    if (live === "clock") return two(d.getHours()) + ":" + two(d.getMinutes());
    if (live === "date") return two(d.getDate()) + "/" + two(d.getMonth() + 1);
    return LIVE_SAMPLE[live] || "";
  }
  /* ponto do liga-desliga e selos de gesto/confirmacao/acender (comum a todos os blocos) */
  function decorate(t, b, size, pad, opts) {
    if (b.toggle) {
      var ds = Math.max(6, Math.round(size * 0.08));
      var dot = el("div", "dot" + (opts.on ? " lit" : ""), null, t);
      dot.style.width = ds + "px"; dot.style.height = ds + "px";
      dot.style.right = pad + "px"; dot.style.top = pad + "px";
    }
    var gb = [];
    if (b.hold && b.hold.type && b.hold.type !== "none") gb.push(["●", "Ao segurar"]);
    if (b.double && b.double.type && b.double.type !== "none") gb.push(["●●", "Toque duplo"]);
    if (b.confirm) gb.push(["!", "Pede confirmação"]);
    if (b.lit) gb.push(["\u26a1\ufe0e", "Acende conforme o OBS"]);
    if (gb.length && b.kind !== "folder" && size >= 40) {
      var gw = el("div", "gbadges", null, t);
      gw.style.right = (b.toggle ? pad + Math.max(6, Math.round(size * 0.08)) + 4 : Math.round(pad * 0.6)) + "px";
      gw.style.top = Math.round(pad * 0.6) + "px";
      gb.forEach(function (x) { var s0 = el("span", null, x[0], gw); s0.title = x[1]; });
      gw.title = gb.map(function (x) { return x[1]; }).join(" · ");
    }
  }
  /* bloco de texto ao vivo pc:* / ia:* com valor de exemplo, como no celular:
     legenda e icone em cima, valor grande, linhas pequenas e barra colorida embaixo */
  function paintRichTile(t, W, H, size, pad, rs, fgc, light, icon, b) {
    SD.setClass(t, "rich", true);
    var fs = Math.max(9, Math.min(15, Math.round(size * 0.1)));
    var cap = SD.trim(b.label) || rs[3];
    var hasIc = !!icon && size >= 56, isz = Math.max(14, Math.round(size * 0.2));
    if (hasIc) {
      var ic = el("div", "ic", SD.iconHtml(icon, isz, fgc), t);
      ic.style.right = pad + "px"; ic.style.top = pad + "px";
    }
    var c = el("div", "lcap", esc(cap), t);
    c.style.left = pad + "px"; c.style.top = pad + "px"; c.style.right = pad + (hasIc ? isz + 6 : 0) + "px";
    c.style.fontSize = fs + "px"; c.style.color = fgc;
    var barH = rs[2] != null ? Math.max(4, Math.round(size * 0.05)) : 0;
    var botPad = Math.max(6, Math.round(pad * 0.7)) + barH;
    var subFs = Math.max(9, Math.round(fs * 0.85)), lh = Math.round(subFs * 1.3);
    var mainFs = Math.max(14, Math.min(44, Math.round(size * 0.27)));
    mainFs = Math.max(11, Math.min(mainFs, Math.floor((W - pad * 1.7) / (Math.max(3, rs[0].length) * 0.6))));
    var avail = H - (pad + Math.round(fs * 1.4)) - botPad - Math.round(mainFs * 1.2) - 2;
    var n = size < 70 ? 0 : Math.max(0, Math.min(rs[1].length, Math.floor(avail / lh)));
    if (n) {
      var sb = el("div", "lsub", rs[1].slice(0, n).map(function (x) { return "<div>" + esc(x) + "</div>"; }).join(""), t);
      sb.style.left = pad + "px"; sb.style.right = pad * 0.7 + "px"; sb.style.bottom = botPad - 1 + "px";
      sb.style.fontSize = subFs + "px"; sb.style.lineHeight = lh + "px"; sb.style.color = fgc;
    }
    var lb = el("div", "lb", esc(rs[0]), t);
    lb.style.left = pad + "px"; lb.style.right = pad * 0.7 + "px"; lb.style.bottom = botPad + n * lh + "px";
    lb.style.fontSize = mainFs + "px"; lb.style.color = fgc;
    if (barH) {
      var br = el("div", "sbar", "<i></i>", t);
      br.style.height = barH + "px";
      br.firstChild.style.width = rs[2] + "%"; br.firstChild.style.backgroundColor = barColor(rs[2]);
    }
    return t;
  }
  /* desenha um bloco como no celular (estilo Atalhos do iOS). W x H em px */
  function paintTile(b, W, H, opts) {
    opts = opts || {};
    H = H || W;
    var t = el("div", "tile");
    t.style.width = W + "px"; t.style.height = H + "px";
    var size = Math.min(W, H);
    t.style.borderRadius = Math.round(Math.min(size, 110) * 0.22) + "px";
    if (edEmpty(b)) {
      SD.setClass(t, "empty", true);
      var ps = Math.round(size * 0.3);
      var ic0 = el("div", "ic", SD.svg("plus", ps, isLight() ? "rgba(60,60,67,0.3)" : "rgba(235,235,245,0.35)"), t);
      ic0.style.left = (W - ps) / 2 - 2 + "px"; ic0.style.top = (H - ps) / 2 - 2 + "px";
      return t;
    }
    var L = look(b, opts.on);
    var color = SD.validColor(L.color) ? L.color : SD.DEFAULT_TILE;
    var light = SD.isLight(color);
    var label = SD.trim(L.label), icon = SD.hasIcon(L.icon) ? L.icon : "";
    var pad = Math.max(7, Math.round(size * 0.12));
    var fs = Math.max(10, Math.min(22, Math.round(size * 0.118)));
    var ic, lb;
    if (b.kind === "fader") {
      SD.setClass(t, "fader", true);
      var fill = el("div", "fill", null, t);
      fill.style.background = SD.validColor(L.color) ? L.color : "#fff";
      var max = FADER_MAX[b.target] || 100;
      fill.style.height = Math.round(75 / max * 100) + "%";
      var fg = SD.validColor(L.textColor) ? L.textColor : (SD.validColor(L.color) && !light ? "#fff" : "#1c1c1e");
      icon = icon || FADER_ICON[b.target] || "sound";
      var is = Math.round(size * 0.26);
      ic = el("div", "ic", SD.iconHtml(icon, is, SD.validColor(L.textColor) ? L.textColor : "#fff"), t);
      ic.style.left = (W - is) / 2 + "px"; ic.style.top = pad + "px";
      lb = el("div", "lb c", esc(label || "Fader"), t);
      lb.style.left = "4px"; lb.style.right = "4px"; lb.style.bottom = pad * 0.8 + "px";
      lb.style.fontSize = fs + "px"; lb.style.color = fg;
      if (size >= 70) {
        var rg = el("div", "rng", "0–" + max + "%", t);
        rg.style.top = pad + is + 4 + "px"; rg.style.color = SD.validColor(L.textColor) ? L.textColor : "rgba(255,255,255,0.75)";
      }
      return t;
    }
    t.style.background = color;
    if (light) SD.setClass(t, "light", true);
    var fgc = SD.validColor(L.textColor) ? L.textColor : (light ? "rgba(0,0,0,0.78)" : "#fff");
    if (L.image) {
      SD.setClass(t, "img", true);
      t.style.backgroundImage = "url(\"" + imgUrl(L.image) + "\")";
      t.style.backgroundSize = "cover";
      t.style.backgroundPosition = "center";
      icon = "";
      if (!SD.validColor(L.textColor)) fgc = "#fff";
    }
    var rs = b.live && size >= 40 ? richSample(b.live) : null;
    if (rs && !L.image) { paintRichTile(t, W, H, size, pad, rs, fgc, light, icon, b); decorate(t, b, size, pad, opts); return t; }
    if (b.live) label = (richSample(b.live) ? richSample(b.live)[0] : liveText(b.live)) || label;
    if (b.kind === "monitor") { if (!icon) icon = "monitor"; if (!label) label = "Monitor"; }
    if (!icon && !label && b.kind === "folder") icon = "folder";
    if (L.image && label) el("div", "shade", null, t);
    if (icon && (!label || size < 66)) {
      var cs = Math.round(size * 0.44);
      ic = el("div", "ic", SD.iconHtml(icon, cs, fgc), t);
      ic.style.left = (W - cs) / 2 + "px"; ic.style.top = (H - cs) / 2 + "px";
    } else if (icon) {
      var is2 = Math.max(16, Math.round(size * 0.26));
      ic = el("div", "ic", SD.iconHtml(icon, is2, fgc), t);
      ic.style.left = pad + "px"; ic.style.top = pad + "px";
      lb = el("div", "lb", esc(label), t);
      lb.style.left = pad + "px"; lb.style.right = pad * 0.7 + "px"; lb.style.bottom = pad * 0.85 + "px";
      lb.style.fontSize = fs + "px"; lb.style.color = fgc;
    } else if (label || !L.image) {
      lb = el("div", "lb c", esc(label || "(sem nome)"), t);
      lb.style.left = pad * 0.6 + "px"; lb.style.right = pad * 0.6 + "px";
      if (L.image) { lb.style.bottom = pad * 0.7 + "px"; }
      else { lb.style.top = "50%"; lb.style.transform = "translateY(-50%)"; }
      lb.style.fontSize = Math.round(fs * (b.live ? 1.5 : 1.1)) + "px"; lb.style.color = fgc;
    }
    decorate(t, b, size, pad, opts);
    if (b.kind === "folder") {
      var fb = el("div", "fbadge", SD.svg("folder", 12, "#fff") + (b.buttons ? "<span>" + count(b) + "</span>" : ""), t);
      fb.title = "Pasta";
    }
    return t;
  }

  /* encaixe da lista atual: posicoes ocupadas + posicoes livres (indices virtuais) */
  function layout() {
    var d = dims(orient), bs = list();
    var fl = SD.flow(bs, d.c, d.r), used = {}, placed = {}, k, free = [];
    for (k = 0; k < fl.length; k++) {
      placed[fl[k].i] = fl[k];
      for (var yy = fl[k].y; yy < fl[k].y + fl[k].h; yy++) for (var xx = fl[k].x; xx < fl[k].x + fl[k].w; xx++) used[yy * d.c + xx] = 1;
    }
    /* uma posicao livre vira o proximo indice: botoes 1x1 acrescentados caem nelas em ordem */
    var n = bs.length;
    for (var c = 0; c < d.c * d.r; c++) if (!used[c]) free.push({ i: n++, x: c % d.c, y: Math.floor(c / d.c), w: 1, h: 1, virt: true });
    var hidden = [];
    for (k = 0; k < bs.length; k++) if (!placed[k] && !edEmpty(bs[k])) hidden.push(k);
    return { d: d, flow: fl, free: free, placed: placed, hidden: hidden };
  }
  function rectOf(L, i) {
    if (L.placed[i]) return L.placed[i];
    for (var k = 0; k < L.free.length; k++) if (L.free[k].i === i) return L.free[k];
    return null;
  }

  /* moldura do aparelho: mesma barra de cima, faixa dos pontos e SD.geometry do celular,
     desenhada no tamanho real (px CSS) e reduzida por escala para caber no centro */
  function layoutDevice(d) {
    var stage = $("stage"), box = $("devbox"), devEl = $("device");
    var area = SD.deviceArea(null);
    var g = SD.geometry(dev.w, dev.h, d.c, d.r, area);
    geoEd = g;
    var aw = Math.max(100, stage.clientWidth - 24), ah = Math.max(100, stage.clientHeight - 56);
    var s = Math.min(aw / dev.w, ah / dev.h, 1);
    devScale = s;
    devEl.style.width = dev.w + "px"; devEl.style.height = dev.h + "px";
    SD.css(devEl, "transform", "scale(" + s + ")");
    box.style.width = Math.round(dev.w * s) + "px"; box.style.height = Math.round(dev.h * s) + "px";
    var nav = $("dnav");
    nav.style.height = area.nav + "px";
    nav.innerHTML = '<span class="dn-l">‹ Páginas</span><b>' +
      esc(folder >= 0 ? (SD.trim((fold() || {}).label) || "Pasta") : pageName(page)) + "</b>";
    var dots = $("ddots"), h = "";
    dots.style.bottom = area.dotsBottom + "px"; dots.style.height = area.dots + "px";
    if (folder < 0 && cfg.pages.length > 1) for (var k = 0; k < cfg.pages.length; k++) h += "<i" + (k === page ? ' class="on"' : "") + "></i>";
    dots.innerHTML = h;
    return g;
  }

  var dragFrom = -1;
  function renderGrid() {
    var L = layout(), d = L.d, bs = list();
    var grid = $("grid");
    var g = layoutDevice(d);
    grid.innerHTML = "";
    var items = L.flow.concat(L.free);
    for (var n = 0; n < items.length; n++) (function (r) {
      var i = r.i, b = r.virt ? null : bs[i];
      var rc = g.rect(r.x, r.y, r.w, r.h);
      var t = paintTile(b, rc.w, rc.h);
      t.style.position = "absolute";
      t.style.left = rc.x + "px"; t.style.top = rc.y + "px";
      t.setAttribute("data-i", i);
      if (isSel(i)) SD.setClass(t, msel.length > 1 ? "msel" : "sel", true);
      if (bad[bkey(i)]) {
        SD.setClass(t, "warn", true);
        var bd = el("div", "badge", "!", t);
        bd.title = "Incompleto: preencha " + bad[bkey(i)];
      }
      t.onclick = function (e) { clickTile(i, e); };
      t.oncontextmenu = function (e) {
        e.preventDefault(); e.stopPropagation();
        if (!isSel(i)) { selectOne(i); renderGrid(); renderInspector(); }
        tileMenu(e.clientX, e.clientY);
      };
      if (b && b.kind === "folder") t.ondblclick = function () { openFolder(i); };
      if (b && !edEmpty(b)) {
        t.draggable = true;
        t.ondragstart = function (e) { dragFrom = i; SD.setClass(t, "dragging", true); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", "b" + i); };
        t.ondragend = function () { dragFrom = -1; SD.setClass(t, "dragging", false); };
      }
      t.ondragover = function (e) { if (dragFrom >= 0) { e.preventDefault(); SD.setClass(t, "over", true); } };
      t.ondragleave = function () { SD.setClass(t, "over", false); };
      t.ondrop = function (e) {
        if (dragFrom < 0) return;
        e.preventDefault();
        var from = dragFrom; dragFrom = -1;
        if (from !== i) swap(from, i);
      };
      /* puxador para mudar o tamanho (canto do bloco selecionado) */
      if (i === sel && msel.length === 1 && b && !edEmpty(b)) {
        var hz = el("div", "rz", null, t);
        hz.title = "Arraste para mudar o tamanho";
        /* puxador no tamanho de sempre na tela, apesar da escala da moldura */
        var hs = Math.round(18 / devScale), ho = Math.round(6 / devScale);
        hz.style.width = hs + "px"; hz.style.height = hs + "px"; hz.style.right = ho + "px"; hz.style.bottom = ho + "px";
        hz.onmousedown = function (e) { startResize(e, i, t); };
        hz.onclick = function (e) { e.stopPropagation(); };
      }
      grid.appendChild(t);
    })(items[n]);
    /* aviso: botoes que nao cabem nesta grade */
    var w = $("warn");
    if (L.hidden.length) {
      var pos0 = [];
      for (var k = 0; k < L.hidden.length && k < 6; k++) pos0.push(L.hidden[k] + 1);
      w.style.display = "";
      w.textContent = "Nesta grade " + (orient === "land" ? "horizontal" : "vertical") + " (" + d.c + " × " + d.r + "), " +
        L.hidden.length + " botão(ões) não cabem e ficam escondidos (posição " + pos0.join(", ") + (L.hidden.length > 6 ? "…" : "") + "). " +
        "Aumente a grade, diminua os blocos grandes ou mova os botões para antes.";
    } else w.style.display = "none";
  }
  function clickTile(i, e) {
    if (e.ctrlKey || e.metaKey) {
      if (isSel(i)) {
        msel = msel.filter(function (x) { return x !== i; });
        sel = msel.length ? msel[msel.length - 1] : -1;
      } else { msel.push(i); sel = i; }
    } else if (e.shiftKey && sel >= 0) {
      var a = Math.min(sel, i), z = Math.max(sel, i);
      msel = [];
      for (var k = a; k <= z; k++) msel.push(k);
      /* sel fica no primeiro clicado (ancora) */
    } else selectOne(i);
    renderGrid(); renderInspector();
  }
  function swap(a, b) {
    change(function () {
      var h = holder();
      SD.padButtons(h, Math.max(a, b) + 1);
      var bs = h.buttons;
      var x = bs[a]; bs[a] = bs[b]; bs[b] = x;
      selectOne(b);
    });
  }
  function startResize(e, i, tileEl) {
    e.preventDefault(); e.stopPropagation();
    tileEl.draggable = false;
    var b = list()[i], d = dims(orient);
    var stepX = (geoEd.w + geoEd.gap) * devScale, stepY = (geoEd.h + geoEd.gap) * devScale;
    var x0 = e.clientX, y0 = e.clientY, w0 = clampSpan(b.w), h0 = clampSpan(b.h);
    var maxW = Math.min(4, d.c), maxH = Math.min(4, d.r), key = "size:" + Math.random();
    SD.setClass(document.body, "resizing", true);
    function mv(ev) {
      var nw = Math.max(1, Math.min(maxW, w0 + Math.round((ev.clientX - x0) / stepX)));
      var nh = Math.max(1, Math.min(maxH, h0 + Math.round((ev.clientY - y0) / stepY)));
      var cur = list()[i];
      if (clampSpan(cur.w) !== nw || clampSpan(cur.h) !== nh) {
        change(function () { setSpan(list()[i], nw, nh); }, key);
        setStatus("Tamanho " + nw + " × " + nh, "busy");
      }
    }
    function up() {
      document.removeEventListener("mousemove", mv);
      document.removeEventListener("mouseup", up);
      SD.setClass(document.body, "resizing", false);
      lastKey = null;
    }
    document.addEventListener("mousemove", mv);
    document.addEventListener("mouseup", up);
  }
  function setSpan(x, w, h) {
    w = clampSpan(w); h = clampSpan(h);
    if (w > 1) x.w = w; else delete x.w;
    if (h > 1) x.h = h; else delete x.h;
  }

  /* ============================================================ inspetor === */
  function curBtn() {
    if (sel < 0) return null;
    return list()[sel] || null;
  }
  /* devolve o botao na posicao i, criando a posicao se for preciso */
  function ensureAt(i) {
    var h = holder();
    SD.padButtons(h, i + 1);
    if (!h.buttons[i]) h.buttons[i] = SD.emptyButton();
    return h.buttons[i];
  }
  function edit(fn, key, light) {
    if (schedOpen) { editSched(fn, key, light); return; }   /* campos da acao do agendamento */
    change(function () { fn(ensureAt(sel)); }, key ? bkey(sel) + ":" + key : null, light); }
  /* aplica em todos os selecionados */
  function editAll(fn, key, light) {
    change(function () { for (var k = 0; k < msel.length; k++) fn(ensureAt(msel[k])); }, key ? "multi:" + key : null, light);
  }

  function renderPreview() {
    var p = $("prev");
    if (!p) return;
    p.innerHTML = "";
    var b = curBtn();
    var w = b ? clampSpan(b.w) : 1, h = b ? clampSpan(b.h) : 1;
    var base = Math.max(w, h) > 1 ? 66 : 110;
    var t = paintTile(b, w * base + (w - 1) * 8, h * base + (h - 1) * 8);
    t.style.cursor = "default";
    p.appendChild(t);
    if (b && b.toggle && !edEmpty(b)) {
      var t2 = paintTile(b, w * base + (w - 1) * 8, h * base + (h - 1) * 8, { on: true });
      t2.style.cursor = "default";
      t2.id = "prevOn";
      var wrap = el("div", "pvon", null, p);
      wrap.appendChild(t2);
      el("div", "pvl", "ligado", wrap);
    }
  }

  function field(parent, label, help) {
    var f = el("div", "f", null, parent);
    if (label) el("div", "l", esc(label), f);
    var body = el("div", null, null, f);
    if (help) el("div", "help", esc(help), f);
    return body;
  }
  function section(parent, title, id) {
    var s = el("div", "sec", null, parent);
    if (id) s.id = id;
    el("div", "sec-h", esc(title), s);
    return s;
  }

  /* ---------------------------------------------------- cor (componente) --- */
  function recentColors() {
    try { var l = JSON.parse(window.localStorage.getItem(RECENT_KEY)); return l && l.length != null ? l : []; }
    catch (e) { return []; }
  }
  function pushRecent(c) {
    if (!SD.validColor(c)) return;
    c = c.toLowerCase();
    var l = recentColors().filter(function (x) { return x !== c; });
    l.unshift(c);
    try { window.localStorage.setItem(RECENT_KEY, JSON.stringify(l.slice(0, 8))); } catch (e) {}
  }
  function fullHex(c) {
    var m = /^#?([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(c || "");
    if (m) return ("#" + m[1] + m[1] + m[2] + m[2] + m[3] + m[3]).toLowerCase();
    return SD.validColor(c) ? ("#" + String(c).replace("#", "")).toLowerCase() : "";
  }
  /* colorPicker(parent, atual, {auto, autoTitle, id, fallback}, set(valor, leve)) */
  function colorPicker(parent, cur, o, set) {
    cur = cur || "";
    var box = el("div", "cpick", null, parent);
    if (o.id) box.id = o.id;
    var row = el("div", "colors", null, box);
    var def = el("button", "sw def" + (cur ? "" : " on"), o.auto || "—", row);
    def.title = o.autoTitle || "Padrão";
    def.onclick = function () { set(""); };
    var nat = el("input", "native", null, row);
    nat.type = "color";
    nat.title = "Escolher qualquer cor";
    nat.value = fullHex(cur) || o.fallback || "#3a3a3c";
    var hex = el("input", "in hex", null, row);
    hex.value = cur; hex.placeholder = "#rrggbb"; hex.maxLength = 7;
    nat.oninput = function () { hex.value = nat.value; set(nat.value, true); };
    nat.onchange = function () { pushRecent(nat.value); };
    hex.oninput = function () {
      var v = SD.trim(hex.value);
      if (v && v.charAt(0) !== "#") v = "#" + v;
      if (!v) { set("", true); return; }
      /* o servidor so aceita #rrggbb: expande #rgb */
      if (/^#[0-9a-f]{6}$/i.test(v) || /^#[0-9a-f]{3}$/i.test(v)) {
        v = fullHex(v);
        nat.value = v;
        set(v, true);
      }
    };
    hex.onchange = function () { pushRecent(fullHex(hex.value)); };
    var sws = el("div", "colors", null, box);
    SD.COLORS.forEach(function (c) {
      var sw = el("button", "sw" + (String(cur).toLowerCase() === c[1] ? " on" : ""), null, sws);
      sw.style.background = c[1]; sw.title = c[0];
      sw.setAttribute("data-c", c[1]);
      sw.onclick = function () { pushRecent(c[1]); set(c[1]); };
    });
    var rc = recentColors();
    if (rc.length) {
      var rr = el("div", "colors recent", null, box);
      el("span", "rl", "Recentes", rr);
      rc.forEach(function (c) {
        var sw = el("button", "sw sm" + (String(cur).toLowerCase() === c ? " on" : ""), null, rr);
        sw.style.background = c; sw.title = c;
        sw.onclick = function () { pushRecent(c); set(c); };
      });
    }
    return box;
  }
  /* ------------------------------------------------- icone (seletor) --- */
  var ICON_RECENT_KEY = "sd_ed_recent_icons";
  var MAX_NAME = 60, MAX_PAGE_BTNS = 120, MAX_FOLDER_BTNS = 60;   /* limites do servidor (schema.py) */
  var pickSt = {};           /* estado de cada seletor (aba, busca, categoria) entre redesenhos */
  var EMOJIS = ("🎙️ 🎤 🎧 📻 🎵 🎶 🎼 🎹 🥁 🎸 🎺 🔊 🔉 🔇 📢 📣 🔔 🔕 📷 📸 🎥 📹 🎬 📺 💻 🖥️ ⌨️ 🖱️ 💡 " +
    "🔴 🟠 🟡 🟢 🔵 🟣 ⚫ ⚪ ⭐ ❤️ 👍 👎 👏 🙌 👋 😂 😍 😮 😢 😡 🤔 😎 🎉 🔥 💯 ✅ ❌ ⚠️ ❓ ❗ " +
    "⏯️ ▶️ ⏸️ ⏹️ ⏺️ ⏭️ ⏮️ ⬆️ ⬇️ ⬅️ ➡️ 🔁 🔀 1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣ 8️⃣ 9️⃣ 🔟 " +
    "🇧🇷 ⚽ 🏆 ☕ 📞 💬 ✉️ ⏰ 🕒 🌙 ☀️ 🚀 🔒 🔓 ⚙️ 🗑️ 📁 🎮 💰 📅").split(" ");
  /* texto sem acento e minusculo, para a busca */
  function plain(s) {
    s = String(s == null ? "" : s).toLowerCase();
    if (s.normalize) s = s.normalize("NFD").replace(/[̀-ͯ]/g, "");
    return s;
  }
  /* quantidade de caracteres (pares substitutos contam 1, como no servidor) */
  /* mesma regra do servidor (valid_icon em streamdeck/schema.py) */
  function emojiOk(t) {
    if (!/\S/.test(t)) return false;
    for (var i = 0; i < t.length; i++) {
      var o = t.charCodeAt(i);
      if (o < 32 || (o >= 0x7f && o < 0xa0) || o === 0x2028 || o === 0x2029 || '<>&"'.indexOf(t.charAt(i)) >= 0) return false;
    }
    return true;
  }
  function charLen(s) { return String(s).replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g, "_").length; }
  function iconColor() { return isLight() ? "#1c1c1e" : "#fff"; }
  /* lista para a busca: SD.ICON_META + icones do conjunto sem descricao */
  function iconMeta() {
    var out = [], seen = {}, meta = SD.ICON_META || [];
    for (var k = 0; k < meta.length; k++) {
      var m = meta[k];
      if (!m || !m.name || !SD.ICONS.hasOwnProperty(m.name) || seen[m.name]) continue;
      seen[m.name] = 1;
      out.push({ name: m.name, label: m.label || m.name, cat: m.cat || m.category || m.group || "",
        key: plain(m.name + " " + (m.label || "") + " " + (m.tags || []).join(" ") + " " + (m.cat || m.category || m.group || "")) });
    }
    Object.keys(SD.ICONS).forEach(function (n) {
      if (!seen[n]) out.push({ name: n, label: n, cat: "", key: plain(n) });
    });
    return out;
  }
  function recentIcons() {
    try { var l = JSON.parse(window.localStorage.getItem(ICON_RECENT_KEY)); return l && l.length != null ? l : []; }
    catch (e) { return []; }
  }
  function pushRecentIcon(v) {
    if (!SD.hasIcon(v)) return;
    var l = recentIcons().filter(function (x) { return x !== v; });
    l.unshift(v);
    try { window.localStorage.setItem(ICON_RECENT_KEY, JSON.stringify(l.slice(0, 12))); } catch (e) {}
  }
  /* iconPicker(pai, atual, set(valor), id): busca, categorias, recentes e aba de emoji */
  function iconPicker(parent, cur, set, id) {
    cur = cur || "";
    var who = page + "/" + folder + "/" + sel;
    var st = pickSt[id] || (pickSt[id] = { q: "", cat: "" });
    /* aba volta ao padrao quando outro botao e selecionado */
    if (st.who !== who) { st.who = who; st.tab = SD.isEmoji(cur) ? "emoji" : "icons"; }
    var box = el("div", "ipick", null, parent);
    box.id = id;
    function choose(v) { if (v) pushRecentIcon(v); set(v); }
    function btn(parentEl, v, title) {
      var b = el("button", "ib" + (cur === v ? " on" : ""), SD.iconHtml(v, 20, iconColor()), parentEl);
      b.title = title || v;
      b.setAttribute("data-icon", v);
      b.onclick = function () { choose(v); };
      return b;
    }
    var top = el("div", "iptop", null, box);
    var cv = el("div", "ipcur", cur && SD.hasIcon(cur) ? SD.iconHtml(cur, 24, iconColor()) : "", top);
    cv.title = cur || "Sem ícone";
    var tabs = el("div", "seg sm", null, top);
    [["icons", "Ícones"], ["emoji", "Emoji"]].forEach(function (x) {
      var b = el("button", st.tab === x[0] ? "on" : "", x[1], tabs);
      b.setAttribute("data-tab", x[0]);
      b.onclick = function () { st.tab = x[0]; draw(); };
    });
    var none = el("button", "mini ipnone" + (cur ? "" : " on"), "Sem ícone", top);
    none.onclick = function () { set(""); };
    var body = el("div", "ipbody", null, box);
    function draw() {
      for (var c = tabs.firstChild; c; c = c.nextSibling) SD.setClass(c, "on", c.getAttribute("data-tab") === st.tab);
      body.innerHTML = "";
      if (st.tab === "emoji") drawEmoji(); else drawIcons();
    }
    function drawIcons() {
      var q = el("input", "in search ipq", null, body);
      q.placeholder = "Buscar ícone (ex.: microfone, play, OBS)";
      q.value = st.q;
      var all = iconMeta(), cats = [];
      all.forEach(function (m) { if (m.cat && cats.indexOf(m.cat) < 0) cats.push(m.cat); });
      if (cats.length > 1) {
        var ch = el("div", "ipcats", null, body);
        [""].concat(cats).forEach(function (c) {
          var b = el("button", "ipcat" + (st.cat === c ? " on" : ""), esc(c || "Todos"), ch);
          b.onclick = function () { st.cat = c; draw(); };
        });
      } else st.cat = "";
      var rec0 = recentIcons().filter(SD.hasIcon);
      var rw = null;
      if (rec0.length) {
        rw = el("div", "iprec", null, body);
        el("span", "rl", "Recentes", rw);
        rec0.forEach(function (v) { btn(rw, v); });
      }
      var g = el("div", "icons", null, body);
      function fill() {
        g.innerHTML = "";
        var words = plain(SD.trim(q.value)).split(/\s+/).filter(function (w) { return w; }), n = 0;
        if (rw) rw.style.display = words.length ? "none" : "";
        all.forEach(function (m) {
          if (st.cat && m.cat !== st.cat) return;
          for (var k = 0; k < words.length; k++) if (m.key.indexOf(words[k]) < 0) return;
          btn(g, m.name, m.label); n++;
        });
        if (!n) el("div", "ipnone0", "Nenhum ícone encontrado. Tente a aba Emoji.", g);
      }
      q.oninput = function () { st.q = q.value; fill(); };
      fill();
    }
    function drawEmoji() {
      var row = el("div", "addrow", null, body);
      var inp = el("input", "in ipemo", null, row);
      inp.placeholder = "Digite ou cole um emoji";
      inp.value = SD.isEmoji(cur) ? cur.slice(6) : "";
      var ok = el("button", "mini", "Usar", row);
      function use() {
        var v = SD.trim(inp.value);
        if (!v) return;
        if (charLen(v) > 8) { SD.toast("Use no máximo 8 caracteres", true); return; }
        if (!emojiOk(v)) { SD.toast("Emoji inválido: não use < > & \" nem caracteres de controle", true); return; }
        choose("emoji:" + v);
      }
      ok.onclick = use;
      inp.onkeydown = function (e) { if (e.key === "Enter") use(); };
      var rec1 = recentIcons().filter(SD.isEmoji);
      if (rec1.length) {
        var rw = el("div", "iprec", null, body);
        el("span", "rl", "Recentes", rw);
        rec1.forEach(function (v) { btn(rw, v); });
      }
      var g = el("div", "icons emo", null, body);
      EMOJIS.forEach(function (e) { if (e) btn(g, "emoji:" + e, e); });
    }
    draw();
    return box;
  }
  /* imagens: escolher da pasta, enviar nova, remover */
  function imagePicker(parent, cur, set, id) {
    var box = el("div", "imgs", null, parent);
    if (id) box.id = id;
    var none = el("button", "it none" + (cur ? "" : " on"), "sem", box);
    none.title = "Sem imagem";
    none.onclick = function () { set(""); };
    images.forEach(function (n) {
      var b = el("button", "it" + (cur === n ? " on" : ""), null, box);
      b.style.backgroundImage = "url(\"" + imgUrl(n) + "\")";
      b.title = n;
      b.setAttribute("data-name", n);
      b.onclick = function () { set(n); };
    });
    if (cur && images.indexOf(cur) < 0) {
      var miss = el("button", "it on", null, box);
      miss.style.backgroundImage = "url(\"" + imgUrl(cur) + "\")";
      miss.title = cur + " (não está na lista)";
    }
    var row = el("div", "imgacts", null, parent);
    var up = el("button", "mini", "Enviar imagem…", row);
    up.onclick = function () {
      pickFile("image/png,image/jpeg,image/gif,image/webp", false, function (fs) { uploadImage(fs[0], set); });
    };
    if (cur) {
      var rm = el("button", "mini red", "Remover imagem", row);
      rm.onclick = function () { set(""); };
    }
    return box;
  }
  function uploadImage(file, set) {
    if (file.size > 2 * 1024 * 1024) { SD.toast("Imagem maior que 2 MB", true); return; }
    setStatus("Enviando imagem…", "busy");
    upload("/api/local/images?name=" + encodeURIComponent(file.name), file, function (ok, data, status) {
      if (!ok) { setStatus("", ""); SD.toast("Não enviou: " + SD.errText(data, status), true); return; }
      SD.toast("Imagem enviada");
      setStatus("", "");
      loadImages(function () { set(data.name || file.name); });
    });
  }
  function sizePicker(parent, w, h, set) {
    var row = el("div", "sizepick", null, parent);
    row.id = "sizepick";
    SIZES.forEach(function (s) {
      var b = el("button", "szb" + (s[0] === w && s[1] === h ? " on" : ""), null, row);
      var ic = el("span", "szi", null, b);
      ic.style.width = s[0] * 9 + (s[0] - 1) * 2 + "px"; ic.style.height = s[1] * 9 + (s[1] - 1) * 2 + "px";
      el("span", null, s[0] + "×" + s[1], b);
      b.setAttribute("data-size", s[0] + "x" + s[1]);
      b.onclick = function () { set(s[0], s[1]); };
    });
    var cu = el("span", "szc", null, row);
    var sw = numSelect(cu, w, 1, 4, function (v) { set(v, h); });
    sw.id = "spanW"; sw.className = "in sm";
    el("span", "x", "×", cu);
    var sh = numSelect(cu, h, 1, 4, function (v) { set(w, v); });
    sh.id = "spanH"; sh.className = "in sm";
  }

  function renderInspector() {
    if (schedOpen) { renderSched(); return; }
    var box = $("inspector");
    box.innerHTML = "";
    if (!cfg) return;
    if (msel.length > 1) { renderMulti(box); return; }
    if (sel < 0) { if (folder >= 0) renderFolderInfo(box); else renderPageSettings(box); return; }
    var b = curBtn() || SD.emptyButton();
    var L = layout(), r = rectOf(L, sel);
    var where = r ? "linha " + (r.y + 1) + ", coluna " + (r.x + 1) : "escondido nesta grade";
    var hdr = el("div", "hdr", (folder >= 0 ? "Dentro da pasta · " : "") + "Posição " + (sel + 1) + " · " + where, box);
    hdr.id = "selinfo";
    inspMore(hdr);
    var pv = el("div", "preview", null, box);
    pv.id = "prev";
    renderPreview();

    /* tipo */
    var kind = b.kind === "fader" ? "fader" : b.kind === "folder" ? "folder" : b.kind === "monitor" ? "monitor" : (b.toggle ? "toggle" : "button");
    var tf = field(box, "Tipo");
    var seg = el("div", "seg", null, tf);
    seg.id = "kind";
    var kinds = [["button", "Botão"], ["toggle", "Liga-desliga"], ["fader", "Fader"]];
    kinds.push(["monitor", "Monitor"]);
    if (folder < 0) kinds.push(["folder", "Pasta"]);
    kinds.forEach(function (x) {
      var bt = el("button", kind === x[0] ? "on" : "", x[1], seg);
      bt.setAttribute("data-kind", x[0]);
      bt.onclick = function () { setKind(x[0]); };
    });

    if (kind === "folder") {
      var fo = el("div", "folderbox", null, box);
      el("div", null, "Pasta com <b>" + count(b) + "</b> botão(ões). No celular ela abre por cima da página, com um “Voltar”.", fo);
      var ob = el("button", "primary", "Abrir pasta", fo);
      ob.id = "openFolder";
      ob.onclick = function () { openFolder(sel); };
    }

    /* tamanho */
    var szf = field(box, "Tamanho (colunas × linhas)", "Também dá para arrastar o canto do bloco selecionado na grade.");
    sizePicker(szf, clampSpan(b.w), clampSpan(b.h), function (w, h) { edit(function (x) { setSpan(x, w, h); }); });

    /* rotulo */
    var lf = field(box, "Rótulo");
    var li = el("input", "in", null, lf);
    li.id = "label"; li.maxLength = 60; li.value = b.label || ""; li.placeholder = "Texto do bloco";
    li.oninput = function () { edit(function (x) { x.label = li.value; }, "label", true); };

    if (kind === "monitor") {
      var mo = el("div", "folderbox", null, box);
      el("div", null, "Tocar abre a <b>tela de processos</b> no celular, com CPU, memória e GPU ao vivo e o que mais consome.", mo);
    }

    if (kind === "button" || kind === "toggle") {
      var lvf = field(box, "Texto ao vivo", b.live === "timer" && kind !== "toggle" ? "O cronômetro conta desde que um botão liga-desliga foi ligado." : null);
      var lv = el("select", "in", null, lvf);
      lv.id = "live";
      var known = {};
      LIVE.forEach(function (x) { known[x[0]] = 1; opt(lv, x[0], x[1], b.live || ""); });
      [["PC", LIVE_PC], ["IAs", LIVE_IA]].forEach(function (g) {
        var og = el("optgroup", null, null, lv);
        og.label = g[0];
        g[1].forEach(function (x) { known[x[0]] = 1; opt(og, x[0], x[1], /^pc:disk:/.test(b.live || "") && x[0] === "pc:disk:C" ? "pc:disk:C" : b.live || ""); });
      });
      /* disco: o select mostra "Disco" e uma segunda lista escolhe a letra C-Z */
      var dm = /^pc:disk:([A-Z])$/.exec(b.live || "");
      if (dm) {
        lv.value = "pc:disk:C";
        var dl = el("select", "in", null, lvf);
        dl.id = "diskLetter"; dl.style.marginTop = "8px";
        for (var ci = 67; ci <= 90; ci++) opt(dl, String.fromCharCode(ci), "Unidade " + String.fromCharCode(ci) + ":", dm[1]);
        dl.onchange = function () { edit(function (x) { x.live = "pc:disk:" + dl.value; }); };
      }
      lv.onchange = function () { edit(function (x) { if (lv.value) x.live = lv.value; else delete x.live; }); };
    }

    /* icone */
    var icf = field(box, "Ícone", b.image && kind !== "fader" ? "A imagem substitui o ícone." : null);
    iconPicker(icf, b.icon, function (v) { edit(function (x) { x.icon = v; }); }, "iconGrid");

    if (kind !== "fader") {
      var imf = field(box, "Imagem");
      imagePicker(imf, b.image || "", function (v) { edit(function (x) { if (v) x.image = v; else delete x.image; }); }, "imgPick");
    }

    /* cores */
    var cf = field(box, "Cor");
    colorPicker(cf, b.color, { id: "colorPick" }, function (v, light) { edit(function (x) { x.color = v; }, "color", light); });
    var tcf = field(box, "Cor do texto/ícone");
    colorPicker(tcf, b.textColor, { id: "textPick", auto: "A", autoTitle: "Automática (contraste com o fundo)", fallback: "#ffffff" },
      function (v, light) { edit(function (x) { if (v) x.textColor = v; else delete x.textColor; }, "textColor", light); });

    if (kind === "fader") {
      var ff = field(box, "Controla", "Efeitos sonoros vão de 0 a 200%; os outros de 0 a 100%.");
      var fs = el("select", "in", null, ff);
      fs.id = "faderTarget";
      FADERS.forEach(function (x) { opt(fs, x[0], x[1] + " (0–" + FADER_MAX[x[0]] + "%)", b.target || "master"); });
      fs.onchange = function () { edit(function (x) { x.target = fs.value; }); };
    } else if (kind !== "folder" && kind !== "monitor") {
      renderAction(box, b);
      renderConfirm(box, b);
      renderGestures(box, b);
      renderLit(box, b);
      if (kind === "toggle") renderOn(box, b);
    }

    var acts = el("div", "acts", null, box);
    var test = el("button", "test", "Testar", acts);
    test.id = "test";
    test.disabled = kind === "fader" || kind === "folder" || kind === "monitor" || !b.action || b.action.type === "none" || b.action.type === "page";
    test.title = "Executa a ação agora neste PC, sem salvar";
    test.onclick = function () { testAction(curBtn().action); };
    var clr = el("button", "clear", "Limpar", acts);
    clr.onclick = clearSel;
  }

  /* ----------------------------------------- confirmacao, gestos, acender --- */
  function renderConfirm(box, b) {
    var cf = field(box, null, "O celular pede “Toque de novo para confirmar” antes de executar. Bom para desligar, fechar, apagar…");
    var lab = el("label", "chk", null, cf);
    var c = el("input", null, null, lab);
    c.type = "checkbox"; c.id = "confirm"; c.checked = !!b.confirm;
    el("span", null, "Pedir confirmação", lab);
    c.onchange = function () { edit(function (x) { if (c.checked) x.confirm = true; else delete x.confirm; }); };
  }
  /* a acao do toque repete ao segurar (volume, setas)? */
  function repeats(a) {
    return !!(a && a.type === "hotkey" && a.keys && a.keys.length === 1 && REPEAT[String(a.keys[0]).toLowerCase()]);
  }
  function renderGestures(box, b) {
    var s = section(box, "Gestos", "gestSec");
    GESTURES.forEach(function (g) {
      var gk = g[0], a = b[gk] || { type: "none" };
      var help = null;
      if (gk === "double") help = "Com toque duplo, o toque simples espera um instante (~0,3 s) antes de executar.";
      if (gk === "hold" && repeats(b.action)) help = "Botões de volume/setas repetem ao segurar; o “ao segurar” substitui a repetição.";
      var f = field(s, g[1], help);
      var sl = actionSelect(f, a.type, false, function (t) {
        edit(function (x) { if (t === "none") delete x[gk]; else x[gk] = newAction(t); });
      });
      sl.id = gk + "Action";
      /* garante a opcao "Nenhuma" mesmo se a lista do servidor nao tiver "none" */
      var on0 = sl.querySelector("option[value=none]");
      if (on0) on0.textContent = "Nenhuma";
      else { var o = el("option", null, "Nenhuma"); o.value = "none"; sl.insertBefore(o, sl.firstChild); if (a.type === "none") sl.value = "none"; }
      if (a.type === "none") return;
      var sc = SD.actionMap[a.type];
      if (sc && sc.help) el("div", "ahelp", esc(sc.help), s);
      var sub = el("div", "gest", null, s);
      renderFields(sub, a, [["@", gk]], gk);
    });
  }
  function renderLit(box, b) {
    var lit = b.lit || "", m = /^(obs:(?:scene|mute))=(.*)$/.exec(lit);
    var mode = m ? m[1] : lit, arg = m ? m[2] : "";
    var f = field(box, "Acender quando", "O bloco aparece aceso enquanto isso for verdade no OBS (independe do liga-desliga).");
    var s = el("select", "in", null, f);
    s.id = "lit";
    LIT.forEach(function (x) { opt(s, x[0], x[1], mode); });
    if (mode && !LIT.some(function (x) { return x[0] === mode; })) opt(s, mode, mode, mode);
    s.onchange = function () {
      var v = s.value;
      edit(function (x) {
        if (!v) delete x.lit;
        else if (v === "obs:scene" || v === "obs:mute") x.lit = v + "=" + (v === mode ? arg : "");
        else x.lit = v;
      });
    };
    if (mode === "obs:scene" || mode === "obs:mute") {
      obsPicker(f, mode === "obs:scene" ? "scenes" : "inputs", arg, "litArg", function (val, light) {
        edit(function (x) { x.lit = mode + "=" + val; }, "lit", light);
      });
    }
  }
  /* cenas/fontes do OBS: lista (select) + texto livre. Devolve o input de texto. */
  function loadObsList(cb) {
    SD.req("GET", "/api/local/obs/scenes", null, function (ok, data) {
      obsList = ok && data && data.ok ? { ok: true, scenes: data.scenes || [], inputs: data.inputs || [] } : { ok: false, scenes: [], inputs: [] };
      if (cb) cb();
    });
  }
  function obsPicker(parent, which, cur, id, set) {
    var wrap = el("div", "obsrow", null, parent);
    var s = el("select", "in", null, wrap);
    s.id = id + "-list";
    var inp = el("input", "in", null, wrap);
    inp.id = id;
    inp.value = cur;
    inp.placeholder = which === "scenes" ? "Nome da cena" : "Nome da fonte de áudio";
    inp.oninput = function () { s.value = ""; set(inp.value, true); };
    var note = el("div", "help obsnote", "", parent);
    function fill() {
      s.innerHTML = "";
      var l = obsList ? obsList[which] : [];
      opt(s, "", obsList ? (l.length ? (which === "scenes" ? "Escolher cena…" : "Escolher fonte…") : "(lista vazia)") : "Carregando…", "");
      l.forEach(function (n) { opt(s, n, n, cur); });
      if (obsList) opt(s, "__r", "↻ Atualizar lista", "");
      note.textContent = obsList && !obsList.ok ? "OBS não conectado — configure em Conectar > OBS" : "";
      note.style.display = note.textContent ? "" : "none";
    }
    s.onchange = function () {
      if (s.value === "__r") { obsList = null; fill(); loadObsList(function () { if (s.parentNode) fill(); }); return; }
      if (!s.value) return;
      inp.value = s.value;
      set(s.value);
    };
    fill();
    if (!obsList) loadObsList(function () { if (s.parentNode) fill(); });
    return inp;
  }

  /* aparencia quando ligado (botao liga-desliga) */
  function renderOn(box, b) {
    var on = b.on || {};
    var s = section(box, "Quando ligado", "onSec");
    el("div", "help", "Aparência do bloco enquanto estiver ligado. Em branco = igual ao desligado.", s);
    function setOn(k, v, light) {
      edit(function (x) {
        if (!x.on) x.on = {};
        if (v === "" || v == null) delete x.on[k]; else x.on[k] = v;
        if (!Object.keys(x.on).length) delete x.on;
      }, "on:" + k, light);
    }
    var lf = field(s, "Rótulo ligado");
    var li = el("input", "in", null, lf);
    li.id = "onLabel"; li.maxLength = 60; li.value = on.label || ""; li.placeholder = b.label || "Texto quando ligado";
    li.oninput = function () { setOn("label", li.value, true); };
    var icf = field(s, "Ícone ligado");
    iconPicker(icf, on.icon || "", function (v) { setOn("icon", v); }, "onIcon");
    var cf = field(s, "Cor ligado");
    colorPicker(cf, on.color, { id: "onColor" }, function (v, light) { setOn("color", v, light); });
    var tf = field(s, "Cor do texto ligado");
    colorPicker(tf, on.textColor, { id: "onText", auto: "A", autoTitle: "Automática", fallback: "#ffffff" }, function (v, light) { setOn("textColor", v, light); });
    var imf = field(s, "Imagem ligado");
    imagePicker(imf, on.image || "", function (v) { setOn("image", v); }, "onImg");
  }

  /* varios blocos selecionados: cor, cor do texto, tamanho, limpar */
  function renderMulti(box) {
    var bs = list();
    var mh = el("div", "hdr", msel.length + " blocos selecionados", box);
    mh.id = "selinfo";
    inspMore(mh);
    el("div", "help pad", "Ctrl+clique adiciona/tira, Shift+clique seleciona um intervalo. As mudanças abaixo valem para todos.", box);
    var first = bs[msel[0]] || {};
    var cf = field(box, "Cor");
    colorPicker(cf, first.color, { id: "colorPick" }, function (v, light) {
      editAll(function (x) { if (x.kind === "fader" || !edEmpty(x) || v) x.color = v; }, "color", light);
    });
    var tcf = field(box, "Cor do texto/ícone");
    colorPicker(tcf, first.textColor, { id: "textPick", auto: "A", autoTitle: "Automática", fallback: "#ffffff" }, function (v, light) {
      editAll(function (x) { if (v) x.textColor = v; else delete x.textColor; }, "textColor", light);
    });
    var szf = field(box, "Tamanho");
    sizePicker(szf, clampSpan(first.w), clampSpan(first.h), function (w, h) { editAll(function (x) { setSpan(x, w, h); }); });
    var acts = el("div", "acts", null, box);
    var clr = el("button", "clear", "Limpar " + msel.length + " blocos", acts);
    clr.id = "clearMulti";
    clr.onclick = clearSel;
  }

  function renderFolderInfo(box) {
    var f = fold();
    el("div", "hdr", "Pasta: " + esc(SD.trim(f.label) || "sem nome"), box);
    el("div", "insp-empty", "Selecione um bloco da pasta para editar.<br><br>Use <b>‹ Voltar</b> acima da grade para voltar à página.", box);
  }

  /* ajustes da pagina (nada selecionado) */
  function renderPageSettings(box) {
    var pg = curPage();
    el("div", "hdr", "Página " + (page + 1), box);
    var nf = field(box, "Nome da página");
    var ni = el("input", "in", null, nf);
    ni.id = "pageName"; ni.maxLength = 60; ni.value = pg.name || "";
    ni.oninput = function () {
      var v = SD.trim(ni.value);
      if (v) change(function () { curPage().name = v; }, "pname:" + page, true);
    };
    var af = field(box, "Trocar para esta página quando estes apps estiverem em foco",
      "Nome do programa (.exe). Quando um deles estiver em primeiro plano no PC, os aparelhos mudam para esta página (se a troca automática estiver ligada no aparelho).");
    var chips = el("div", "chips", null, af);
    chips.id = "apps";
    var apps = pg.apps || [];
    apps.forEach(function (a, i) {
      var c = el("span", "chip", esc(a), chips);
      var x = el("button", null, "×", c);
      x.title = "Tirar";
      x.onclick = function () { change(function () { curPage().apps.splice(i, 1); if (!curPage().apps.length) delete curPage().apps; }); };
    });
    if (!apps.length) el("span", "none", "Nenhum app", chips);
    function addApp(v) {
      /* so o nome do arquivo (tira pastas), minusculo, termina em .exe */
      v = String(v || "").split("/").pop().split("\\").pop();
      v = SD.trim(v).toLowerCase();
      if (!v) return;
      if (!/\.exe$/.test(v)) v += ".exe";
      /* mesma regra do servidor (EXE_RE): sem separadores nem caracteres de controle */
      if (v.length > 80 || /[\/\\:*?"<>|\u0000-\u001f\u007f]/.test(v) || !/^[^.\s]/.test(v)) {
        SD.toast("Nome de app inválido");
        return;
      }
      var cur = curPage().apps || [];
      if (cur.indexOf(v) >= 0) { SD.toast("Já está na lista"); return; }
      change(function () { if (!curPage().apps) curPage().apps = []; curPage().apps.push(v); });
    }
    var row = el("div", "addrow", null, af);
    var ti = el("input", "in", null, row);
    ti.id = "appInput"; ti.placeholder = "obs64.exe";
    ti.onkeydown = function (e) { if (e.key === "Enter") { addApp(ti.value); } };
    var ab = el("button", "mini", "Adicionar", row);
    ab.onclick = function () { addApp(ti.value); };
    var ws = el("select", "in", null, af);
    ws.id = "appPick";
    windowOptions(ws, "Escolher entre os apps abertos…", true);
    ws.onchange = function () {
      if (ws.value === "__r") { windows = null; loadWindows(function () { renderInspector(); }); return; }
      if (ws.value) addApp(ws.value);
    };
    el("div", "insp-empty small", "Selecione um bloco na grade para editar.<br>Clique em <b>+</b> para criar um botão.", box);
  }
  /* opcoes de janelas abertas num select (value = exe) */
  function windowOptions(s, first, uniqueExe) {
    opt(s, "", first, "");
    if (windows === null) {
      opt(s, "__r", "Carregando janelas…", "");
      loadWindows(function () { if (s.parentNode) { s.innerHTML = ""; windowOptions(s, first, uniqueExe); } });
      return;
    }
    var seen = {};
    windows.forEach(function (w, i) {
      var exe = (w.exe || "").toLowerCase();
      if (!exe || (uniqueExe && seen[exe])) return;
      seen[exe] = 1;
      opt(s, uniqueExe ? exe : String(i), (w.title || exe) + " — " + exe, "");
    });
    if (!windows.length) opt(s, "", "(nenhuma janela encontrada)", "");
    opt(s, "__r", "↻ Atualizar lista", "");
  }
  function loadWindows(cb) {
    SD.req("GET", "/api/local/windows", null, function (ok, data, status) {
      windows = ok && data && data.windows ? data.windows : [];
      if (!ok) SD.toast("Não listou as janelas: " + SD.errText(data, status), true);
      if (cb) cb();
    });
  }

  function setKind(k) {
    edit(function (x) {
      var keep = { label: x.label || "", icon: x.icon || "", color: x.color || "" }, p;
      if (x.textColor) keep.textColor = x.textColor;
      if (x.w) keep.w = x.w;
      if (x.h) keep.h = x.h;
      if (k === "fader") {
        keep.kind = "fader"; keep.target = x.target || "master";
        for (p in x) if (x.hasOwnProperty(p)) delete x[p];
        for (p in keep) x[p] = keep[p];
        x.kind = "fader";
      } else if (k === "monitor") {
        for (p in x) if (x.hasOwnProperty(p)) delete x[p];
        for (p in keep) x[p] = keep[p];
        x.kind = "monitor";
        if (!x.icon) x.icon = "monitor";
      } else if (k === "folder") {
        if (x.image) keep.image = x.image;
        keep.buttons = x.buttons || [];
        for (p in x) if (x.hasOwnProperty(p)) delete x[p];
        x.kind = "folder";
        for (p in keep) x[p] = keep[p];
        if (!x.icon) x.icon = "folder";
      } else {
        if (x.kind === "fader") { delete x.target; x.action = { type: "none" }; }
        if (x.kind === "folder") {
          if (x.buttons && x.buttons.length && count(x) && !window.confirm("Transformar a pasta em botão apaga os " + count(x) + " botões de dentro. Continuar?")) return;
          delete x.buttons;
        }
        x.kind = "button";
        if (!x.action) x.action = { type: "none" };
        if (k === "toggle") x.toggle = true; else { delete x.toggle; delete x.on; }
      }
    });
  }

  /* ------------------------------------------------ acao e seus campos --- */
  function actionSelect(parent, cur, isStep, onChange, skip) {
    var s = el("select", "in", null, parent);
    var groups = {}, order = [];
    (SD.actions || []).forEach(function (a) {
      if (isStep && (NO_STEP[a.type] || a.type === "none")) return;
      if (skip && skip[a.type]) return;
      var g = a.group || "Geral";
      if (!groups[g]) { groups[g] = el("optgroup"); groups[g].label = g; order.push(g); }
      opt(groups[g], a.type, a.label, cur);
    });
    for (var i = 0; i < order.length; i++) s.appendChild(groups[order[i]]);
    if (cur && !SD.actionMap[cur]) opt(s, cur, cur + " (desconhecida)", cur);
    s.onchange = function () { onChange(s.value); };
    return s;
  }
  function newAction(type) {
    var a = { type: type }, s = SD.actionMap[type];
    var fs = s && s.fields || [];
    for (var i = 0; i < fs.length; i++) {
      if (fs[i].default !== undefined) a[fs[i].key] = clone(fs[i].default);
      else if (fs[i].kind === "page") a[fs[i].key] = 0;
      else if (fs[i].kind === "steps") a[fs[i].key] = [];
    }
    return a;
  }
  function renderAction(box, b) {
    var a = b.action || { type: "none" };
    var af = field(box, "Ação");
    var s = actionSelect(af, a.type, false, function (t) {
      edit(function (x) { x.action = newAction(t); });
    });
    s.id = "action";
    var sc = SD.actionMap[a.type];
    if (sc && sc.help) el("div", "ahelp", esc(sc.help), box);
    /* caminho = lista de chaves ate a acao (para os passos) */
    renderFields(box, a, [], "a");
  }

  /* acao dentro do botao selecionado, seguindo o caminho (passos) */
  function actionAt(x, path) {
    var a = x.action, i = 0;
    /* ["@", "hold"] no inicio = acao de um gesto (x.hold / x.double) */
    if (path.length && path[0][0] === "@") { a = x[path[0][1]]; i = 1; }
    for (; i < path.length; i++) a = a[path[i][0]][path[i][1]];
    return a;
  }
  function renderFields(box, a, path, idp) {
    var sc = SD.actionMap[a.type];
    var fs = sc && sc.fields || [];
    for (var i = 0; i < fs.length; i++) renderField(box, a, fs[i], path, idp);
  }
  function setVal(path, key, v, light) {
    edit(function (x) {
      var a = actionAt(x, path);
      if (v === undefined) delete a[key]; else a[key] = v;
    }, "f:" + JSON.stringify(path) + ":" + key, light);
  }
  function parseKeys(val) {
    var parts = String(val).split("+"), keys = [];
    for (var k = 0; k < parts.length; k++) { var p = SD.trim(parts[k]).toLowerCase(); if (p) keys.push(p); }
    return keys;
  }
  function renderField(box, a, f, path, idp) {
    var v = a[f.key], body, inp;
    if (f.kind === "bool") {
      body = field(box, null, f.help);
      var lab = el("label", "chk", null, body);
      inp = el("input", null, null, lab);
      inp.type = "checkbox";
      inp.checked = v === undefined ? !!f["default"] : !!v;
      el("span", null, esc(f.label), lab);
      inp.onchange = function () { setVal(path, f.key, inp.checked); };
      inp.id = idp + "-" + f.key;
      return;
    }
    body = field(box, f.label, f.help);
    if (f.kind === "keys") {
      var kr = el("div", "keyrow", null, body);
      inp = el("input", "in", null, kr);
      inp.value = v && v.join ? v.join("+") : (v || "");
      inp.oninput = function () { var keys = parseKeys(inp.value); setVal(path, f.key, keys.length ? keys : undefined, true); };
      var rb = el("button", "mini rec", "Gravar", kr);
      rb.id = idp + "-" + f.key + "-rec";
      rb.title = "Aperte o atalho no teclado deste PC";
      rb.onclick = function () {
        if (rec) { stopRec(); return; }
        startRec(inp, rb, function (keys) { setVal(path, f.key, keys); });
      };
    } else if (f.kind === "text") {
      inp = el("input", "in", null, body);
      inp.value = v == null ? "" : String(v);
      inp.oninput = function () { setVal(path, f.key, inp.value === "" ? undefined : inp.value, true); };
    } else if (f.kind === "app") {
      inp = el("input", "in", null, body);
      inp.value = v == null ? "" : String(v);
      inp.oninput = function () { setVal(path, f.key, inp.value === "" ? undefined : inp.value, true); };
      var ar = el("div", "approw", null, body);
      var ws = el("select", "in", null, ar);
      ws.id = idp + "-" + f.key + "-win";
      windowOptions(ws, "Escolher entre as janelas abertas…", false);
      ws.onchange = function () {
        if (ws.value === "__r") { windows = null; loadWindows(function () { renderInspector(); }); return; }
        var w = windows && windows[parseInt(ws.value, 10)];
        if (!w) return;
        var val = appPath && w.path ? w.path : (w.exe || "").toLowerCase();
        setVal(path, f.key, val);
      };
      var pl = el("label", "chk small", null, ar);
      var pc = el("input", null, null, pl);
      pc.type = "checkbox"; pc.checked = appPath;
      pc.id = idp + "-" + f.key + "-path";
      el("span", null, "usar caminho", pl);
      pc.onchange = function () { appPath = pc.checked; };
    } else if (f.kind === "color") {
      colorPicker(body, v == null ? "" : String(v), { id: idp + "-" + f.key }, function (c, light) {
        setVal(path, f.key, c === "" ? undefined : c, light);
      });
      return;
    } else if (f.kind === "textarea") {
      inp = el("textarea", "in", null, body);
      inp.value = v == null ? "" : String(v);
      inp.oninput = function () { setVal(path, f.key, inp.value === "" ? undefined : inp.value, true); };
    } else if (f.kind === "number") {
      inp = el("input", "in", null, body);
      inp.type = "number";
      if (f.min != null) inp.min = f.min;
      if (f.max != null) inp.max = f.max;
      if (f.step != null) inp.step = f.step;
      inp.value = v == null ? (f["default"] != null ? f["default"] : "") : v;
      inp.oninput = function () {
        var n = parseFloat(inp.value);
        if (inp.value === "") setVal(path, f.key, undefined, true);
        else if (!isNaN(n)) setVal(path, f.key, n, true);
      };
    } else if (f.kind === "select") {
      inp = el("select", "in", null, body);
      var cur = v == null ? f["default"] : v;
      (f.options || []).forEach(function (o) { opt(inp, o.value, o.label, cur); });
      inp.onchange = function () { setVal(path, f.key, inp.value); };
    } else if (f.kind === "sound") {
      inp = el("input", "in", null, body);
      var dl = el("datalist", null, null, body);
      dl.id = idp + "-dl-" + f.key;
      inp.setAttribute("list", dl.id);
      sounds.forEach(function (s) { el("option", null, null, dl).value = s; });
      inp.value = v == null ? "" : String(v);
      inp.oninput = function () { setVal(path, f.key, inp.value === "" ? undefined : inp.value, true); };
      if (!sounds.length) el("div", "help", "Nenhum som na pasta sons ainda.", body);
    } else if (f.kind === "page") {
      inp = el("select", "in", null, body);
      for (var p = 0; p < cfg.pages.length; p++) opt(inp, p, (p + 1) + ". " + pageName(p), v);
      if (v == null) inp.selectedIndex = -1;
      inp.onchange = function () { setVal(path, f.key, parseInt(inp.value, 10)); };
    } else if (f.kind === "obs_scene" || f.kind === "obs_input") {
      inp = obsPicker(body, f.kind === "obs_scene" ? "scenes" : "inputs", v == null ? "" : String(v), idp + "-" + f.key, function (val, light) {
        setVal(path, f.key, val === "" ? undefined : val, light);
      });
      if (f.placeholder) inp.placeholder = f.placeholder;
      return;
    } else if (f.kind === "steps") {
      renderSteps(body, v || [], path.concat([[f.key]]), idp + "-" + f.key);
      return;
    } else {
      /* tipo de campo desconhecido: texto simples */
      inp = el("input", "in", null, body);
      inp.value = v == null ? "" : (typeof v === "object" ? JSON.stringify(v) : String(v));
      inp.oninput = function () { setVal(path, f.key, inp.value === "" ? undefined : inp.value, true); };
    }
    if (inp) {
      inp.id = idp + "-" + f.key;
      if (f.placeholder) inp.placeholder = f.placeholder;
    }
  }

  /* --------------------------------------------- gravar atalho de teclado --- */
  var MOD = { Control: "ctrl", Shift: "shift", Alt: "alt", AltGraph: "alt", Meta: "win", OS: "win" };
  var CODE = {
    Enter: "enter", NumpadEnter: "enter", Escape: "esc", Tab: "tab", Space: "space", Backspace: "backspace",
    Delete: "delete", Home: "home", End: "end", PageUp: "pageup", PageDown: "pagedown",
    ArrowLeft: "left", ArrowUp: "up", ArrowRight: "right", ArrowDown: "down", PrintScreen: "printscreen",
    MediaPlayPause: "playpause", MediaTrackNext: "next", MediaTrackPrevious: "prev", MediaStop: "stop",
    AudioVolumeMute: "mute", AudioVolumeUp: "volumeup", AudioVolumeDown: "volumedown",
    VolumeMute: "mute", VolumeUp: "volumeup", VolumeDown: "volumedown",
    Period: ".", Comma: ",", Minus: "-", Equal: "=", Semicolon: ";", Slash: "/",
    NumpadDecimal: ".", NumpadSubtract: "-", NumpadDivide: "/"
  };
  var KEYNAME = {
    Enter: "enter", Escape: "esc", Esc: "esc", Tab: "tab", " ": "space", Spacebar: "space", Backspace: "backspace",
    Delete: "delete", Del: "delete", Home: "home", End: "end", PageUp: "pageup", PageDown: "pagedown",
    ArrowLeft: "left", ArrowUp: "up", ArrowRight: "right", ArrowDown: "down", Left: "left", Up: "up", Right: "right", Down: "down",
    PrintScreen: "printscreen", MediaPlayPause: "playpause", MediaTrackNext: "next", MediaTrackPrevious: "prev",
    MediaStop: "stop", AudioVolumeMute: "mute", AudioVolumeUp: "volumeup", AudioVolumeDown: "volumedown"
  };
  /* nome da tecla no formato do servidor (ou null se nao suportada) */
  function keyName(e) {
    var c = e.code || "", k = e.key || "", m;
    if (MOD[k]) return MOD[k];
    if ((m = /^Key([A-Z])$/.exec(c))) return m[1].toLowerCase();
    if ((m = /^(?:Digit|Numpad)([0-9])$/.exec(c))) return m[1];
    if ((m = /^F([0-9]{1,2})$/.exec(c)) && +m[1] >= 1 && +m[1] <= 24) return "f" + m[1];
    if (CODE[c]) return CODE[c];
    if (KEYNAME[k]) return KEYNAME[k];
    if ((m = /^F([0-9]{1,2})$/.exec(k)) && +m[1] >= 1 && +m[1] <= 24) return "f" + m[1];
    if (/^[a-z0-9]$/i.test(k)) return k.toLowerCase();
    if (/^[.,\-=;\/]$/.test(k)) return k;
    return null;
  }
  function startRec(inp, btn, done) {
    var held = {}, old = inp.value;
    btn.textContent = "Parar";
    SD.setClass(btn, "on", true);
    inp.value = ""; inp.placeholder = "Aperte o atalho…";
    SD.setClass(inp, "recording", true);
    function mods(e) {
      var l = [];
      if (e.ctrlKey || held.ctrl) l.push("ctrl");
      if (e.shiftKey || held.shift) l.push("shift");
      if (e.altKey || held.alt) l.push("alt");
      if (e.metaKey || held.win) l.push("win");
      return l;
    }
    function kd(e) {
      e.preventDefault(); e.stopPropagation();
      var n = keyName(e);
      if (n === "ctrl" || n === "shift" || n === "alt" || n === "win") {
        held[n] = true;
        inp.value = mods(e).join("+") + "+…";
        return;
      }
      if (!n) { SD.toast("Tecla não suportada: " + (e.key || e.code), true); return; }
      var keys = mods(e);
      keys.push(n);
      finish(keys);
    }
    function ku(e) {
      e.preventDefault(); e.stopPropagation();
      var n = keyName(e);
      /* so modificadores (ex.: "win" sozinho): grava ao soltar */
      if (held[n]) {
        var keys = [];
        ["ctrl", "shift", "alt", "win"].forEach(function (m) { if (held[m]) keys.push(m); });
        if (keys.length) finish(keys);
      }
    }
    function finish(keys) {
      cleanup();
      inp.value = keys.join("+");
      done(keys);
    }
    function cleanup() {
      document.removeEventListener("keydown", kd, true);
      document.removeEventListener("keyup", ku, true);
      SD.setClass(inp, "recording", false);
      SD.setClass(btn, "on", false);
      btn.textContent = "Gravar";
      rec = null;
    }
    document.addEventListener("keydown", kd, true);
    document.addEventListener("keyup", ku, true);
    rec = { stop: function () { cleanup(); inp.value = old; } };
    try { inp.blur(); btn.focus(); } catch (e) {}
  }
  function stopRec() { if (rec) rec.stop(); }

  /* lista de passos: cada passo e uma acao (sem pagina/sequencia) */
  function renderSteps(body, steps, base, idp) {
    var key = base[base.length - 1][0], parent = base.slice(0, -1);
    var wrap = el("div", "steps", null, body);
    wrap.id = idp;
    function mutate(fn) {
      edit(function (x) {
        var a = actionAt(x, parent);
        if (!a[key] || !a[key].length) a[key] = [];
        fn(a[key]);
      });
    }
    for (var i = 0; i < steps.length; i++) (function (i) {
      var st = steps[i] || {};
      var card = el("div", "step", null, wrap);
      var sh = el("div", "sh", null, card);
      el("b", null, String(i + 1), sh);
      actionSelect(sh, st.type, true, function (t) { mutate(function (l) { l[i] = newAction(t); }); });
      var up = el("button", null, "↑", sh); up.title = "Subir"; up.disabled = i === 0;
      var dn = el("button", null, "↓", sh); dn.title = "Descer"; dn.disabled = i === steps.length - 1;
      var rm = el("button", "x", "×", sh); rm.title = "Remover passo";
      up.onclick = function () { mutate(function (l) { var t = l[i]; l[i] = l[i - 1]; l[i - 1] = t; }); };
      dn.onclick = function () { mutate(function (l) { var t = l[i]; l[i] = l[i + 1]; l[i + 1] = t; }); };
      rm.onclick = function () { mutate(function (l) { l.splice(i, 1); }); };
      renderFields(card, st, parent.concat([[key, i]]), idp + "-" + i);
    })(i);
    var add = el("button", "addstep", "+ Adicionar passo", wrap);
    add.onclick = function () { mutate(function (l) { l.push(newAction("hotkey")); }); };
  }

  function testAction(a) {
    if (!a) return;
    SD.req("POST", "/api/local/test", JSON.stringify({ action: a }), function (ok, data, status) {
      if (ok) SD.toast("Ação executada");
      else SD.toast("Não funcionou: " + SD.errText(data, status), true);
    });
  }

  /* ======================================================= agendamentos === */
  /* painel no lugar da grade/inspetor: lista a esquerda, formulario a direita.
     Edicao passa por edit() (mesmo desfazer/autosave); a acao usa renderFields. */
  var MAX_SCHED = 50;
  var DAY_ABBR = ["D", "S", "T", "Q", "Q", "S", "S"];
  var DAY_NAME = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
  var DAY_FULL = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
  var DAY_PRESETS = [["Todos", []], ["Dias úteis", [1, 2, 3, 4, 5]], ["Fim de semana", [0, 6]]];
  var EVERY_OPTS = [5, 10, 15, 30, 60, 120];
  var SKIP_SCHED = { page: 1 };
  var schedOpen = false;     /* painel aberto */
  var schedSel = -1;         /* indice em edicao (-1 = nenhum) */
  var schedInfo = {};        /* id -> {next, last, last_error} de /api/local/schedules */
  var schedNow = null;       /* "agora" do PC (ISO) */
  var schedErr = "";         /* erro ao consultar o PC */
  var schedT = null;
  var schedCustom = {};      /* id -> mostrar campo de minutos personalizado */

  function scheds() { if (!cfg.schedules) cfg.schedules = []; return cfg.schedules; }
  function curSched() { return schedOpen && schedSel >= 0 && cfg && cfg.schedules ? cfg.schedules[schedSel] || null : null; }
  function newId() {
    var cs = "abcdefghijklmnopqrstuvwxyz0123456789", taken = {}, l = cfg.schedules || [], id, k;
    for (k = 0; k < l.length; k++) taken[l[k].id] = 1;
    do {
      id = "";
      for (k = 0; k < 6; k++) id += cs.charAt(Math.floor(Math.random() * cs.length));
    } while (taken[id]);
    return id;
  }
  function sortedDays(d) {
    var out = [];
    for (var i = 0; i < 7; i++) if (d && d.indexOf(i) >= 0) out.push(i);
    return out;
  }
  function sameDays(a, b) { return sortedDays(a).join() === sortedDays(b).join(); }
  function joinE(l) { return l.length > 1 ? l.slice(0, -1).join(", ") + " e " + l[l.length - 1] : l.join(""); }
  /* texto dos dias: null = todos */
  function daysText(d) {
    d = sortedDays(d);
    if (!d.length || d.length === 7) return null;
    if (sameDays(d, [1, 2, 3, 4, 5])) return "dia útil";
    if (sameDays(d, [0, 6])) return "fim de semana";
    if (d.length === 1) return DAY_FULL[d[0]];
    return joinE(d.map(function (x) { return DAY_NAME[x]; }));
  }
  function minText(m) {
    m = parseInt(m, 10) || 0;
    if (m >= 60 && m % 60 === 0) return m === 60 ? "1 hora" : (m / 60) + " horas";
    return m + " min";
  }
  /* "2026-12-25T20:00[:ss]" -> Date local (ou null) */
  function parseIso(s) {
    var m = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(String(s || ""));
    return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null;
  }
  function isoDate(d) { return d.getFullYear() + "-" + two(d.getMonth() + 1) + "-" + two(d.getDate()); }
  function hm(d) { return two(d.getHours()) + ":" + two(d.getMinutes()); }
  /* descricao humana do "quando" */
  function whenText(w) {
    w = w || {};
    var dt;
    if (w.type === "daily") {
      dt = daysText(w.days);
      return (dt === null ? "Todo dia" : dt === "dia útil" ? "Todo dia útil" : dt === "fim de semana" ? "Todo fim de semana" :
        "Toda semana: " + dt) + " às " + (w.time || "--:--");
    }
    if (w.type === "every") {
      var s = "A cada " + minText(w.minutes);
      if (w.from || w.to) s += ", das " + (w.from || "00:00") + " às " + (w.to || "23:59");
      dt = daysText(w.days);
      if (dt !== null) s += dt === "dia útil" ? ", em dias úteis" : dt === "fim de semana" ? ", no fim de semana" : " (" + dt + ")";
      return s;
    }
    if (w.type === "once") {
      dt = parseIso(w.at);
      if (!dt) return "Uma vez (escolha a data)";
      var y = dt.getFullYear() !== new Date().getFullYear() ? "/" + dt.getFullYear() : "";
      return "Uma vez em " + two(dt.getDate()) + "/" + two(dt.getMonth() + 1) + y + " às " + hm(dt);
    }
    return "Quando: inválido";
  }
  /* "hoje às 08:00", "amanhã às 08:00", "sex 25/12 às 20:00" (relativo ao relogio do PC) */
  function relText(iso) {
    var d = parseIso(iso);
    if (!d) return "";
    var base = parseIso(schedNow) || new Date();
    var d0 = new Date(base.getFullYear(), base.getMonth(), base.getDate()).getTime();
    var d1 = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    var days = Math.round((d1 - d0) / 86400000);
    var day = days === 0 ? "hoje" : days === 1 ? "amanhã" : days === -1 ? "ontem" :
      DAY_NAME[d.getDay()] + " " + two(d.getDate()) + "/" + two(d.getMonth() + 1) + (d.getFullYear() !== base.getFullYear() ? "/" + d.getFullYear() : "");
    return day + " às " + hm(d);
  }

  function blankSched() {
    return { id: newId(), name: "", enabled: true, when: { type: "daily", time: "08:00", days: [] }, action: { type: "none" } };
  }
  /* troca o tipo do "quando" mantendo o que da (horario, dias) */
  function whenOf(type, old) {
    old = old || {};
    var days = old.days ? sortedDays(old.days) : [];
    var time = old.time || old.from || (old.at ? String(old.at).substring(11, 16) : "") || "08:00";
    if (type === "daily") return { type: "daily", time: time, days: days };
    if (type === "every") return { type: "every", minutes: 15, days: days };
    var t = new Date(new Date().getTime() + 86400000);
    return { type: "once", at: isoDate(t) + "T" + time };
  }

  function loadSchedInfo() {
    if (!schedOpen) return;
    SD.req("GET", "/api/local/schedules", null, function (ok, data, status) {
      if (ok && data && data.items) {
        schedInfo = {};
        for (var i = 0; i < data.items.length; i++) if (data.items[i]) schedInfo[data.items[i].id] = data.items[i];
        schedNow = data.now || null;
        schedErr = "";
      } else schedErr = SD.errText(data, status, "PC sem resposta");
      if (schedOpen) renderSchedList();
    });
  }
  function openSched() {
    if (!cfg) return;
    closePop();
    if (folder >= 0) { folder = -1; selectOne(-1); }
    schedOpen = true;
    if (schedSel < 0 && cfg.schedules && cfg.schedules.length) schedSel = 0;
    clearInterval(schedT);
    schedT = setInterval(loadSchedInfo, 30000);
    loadSchedInfo();
    renderAll();
  }
  function closeSched() {
    schedOpen = false;
    clearInterval(schedT); schedT = null;
  }
  function addSched() {
    if (scheds().length >= MAX_SCHED) { SD.toast("No máximo " + MAX_SCHED + " agendamentos", true); return; }
    change(function () { scheds().push(blankSched()); schedSel = cfg.schedules.length - 1; });
    var n = $("schName");
    if (n) n.focus();
  }
  function dupSched(i) {
    if (scheds().length >= MAX_SCHED) { SD.toast("No máximo " + MAX_SCHED + " agendamentos", true); return; }
    change(function () {
      var c = clone(cfg.schedules[i]);
      c.id = newId();
      c.name = cutName((c.name || "Agendamento") + " (cópia)", MAX_NAME);
      cfg.schedules.splice(i + 1, 0, c);
      schedSel = i + 1;
    });
  }
  function delSched(i) {
    var s = cfg.schedules[i];
    if (!window.confirm("Apagar o agendamento “" + (s.name || "sem nome") + "”?")) return;
    change(function () {
      cfg.schedules.splice(i, 1);
      /* o selecionado acompanha a lista quando um anterior e apagado */
      if (i < schedSel) schedSel--;
      else if (i === schedSel) schedSel = Math.min(i, cfg.schedules.length - 1);
      if (schedSel >= cfg.schedules.length) schedSel = cfg.schedules.length - 1;
    });
    SD.toast("Agendamento apagado (Ctrl+Z desfaz)");
  }
  function toggleSched(i, on) {
    var id = cfg.schedules[i].id;
    change(function () { cfg.schedules[i].enabled = on; }, "s:" + id + ":enabled");
  }
  /* testa agora: espera o salvamento pendente (o PC roda o que esta salvo) */
  function runSched(i) {
    var s = cfg.schedules[i];
    if (!s) return;
    if (missing(s.action || {}, false) || !s.action || s.action.type === "none") { SD.toast("Escolha e preencha a ação primeiro", true); return; }
    if (saveBad) { SD.toast("Corrija o erro antes de testar", true); return; }
    var id = s.id, tries = 0;
    function go() {
      if (saveBad) { SD.toast("Corrija o erro antes de testar", true); return; }
      if ((dirty || inflight) && tries++ < 40) { setTimeout(go, 250); return; }
      SD.req("POST", "/api/local/schedules/run", JSON.stringify({ id: id }), function (ok, data, status) {
        if (ok) SD.toast("Agendamento executado");
        else SD.toast("Não funcionou: " + SD.errText(data, status), true);
        loadSchedInfo();
      });
    }
    go();
  }

  function schedSwitch(parent, on, onChange, title) {
    var lab = el("label", "switch", null, parent);
    var inp = el("input", null, null, lab);
    inp.type = "checkbox"; inp.checked = !!on;
    el("i", null, null, lab);
    if (title) lab.title = title;
    lab.onclick = function (e) { e.stopPropagation(); };
    inp.onchange = function () { onChange(inp.checked); };
    return inp;
  }
  function renderSchedRow() {
    var r = $("schedRow");
    if (!r || !cfg) return;
    r.className = "pg schedrow" + (schedOpen ? " on" : "");
    r.innerHTML = "";
    el("span", "n ic", SD.svg("clock", 16, schedOpen ? "#fff" : isLight() ? "#007aff" : "#0a84ff"), r);
    el("span", "t", "Agendamentos", r);
    var l = cfg.schedules || [], on = 0;
    for (var i = 0; i < l.length; i++) if (l[i].enabled !== false) on++;
    var c = el("span", "c", String(l.length), r);
    c.title = on + " ligado(s) de " + l.length;
  }

  function renderSched(light) {
    var p = $("sched");
    p.style.display = "";
    $("center").style.display = "none";
    $("right").style.display = "none";
    if (!p.firstChild) {
      var lw = el("div", "schlist", null, p);
      lw.id = "schListWrap";
      var fw = el("div", "schform", null, p);
      fw.id = "schForm";
    }
    renderSchedList();
    if (!light) renderSchedForm();
  }
  function hideSched() {
    var p = $("sched");
    if (p) p.style.display = "none";
    $("center").style.display = "";
    $("right").style.display = "";
  }

  function renderSchedList() {
    var w = $("schListWrap");
    if (!w || !cfg) return;
    var st = w.scrollTop;
    w.innerHTML = "";
    var head = el("div", "schhead", null, w);
    var ht = el("div", "schtitle", null, head);
    el("h2", null, "Agendamentos", ht);
    el("p", null, "Rodam sozinhos no horário do PC, mesmo sem nenhum celular conectado.", ht);
    var add = el("button", "primary", "+ Novo agendamento", head);
    add.id = "schAdd";
    add.disabled = scheds().length >= MAX_SCHED;
    add.onclick = addSched;
    if (schedErr) el("div", "warnbox", "Não deu para ver as próximas execuções: " + esc(schedErr), w);
    var l = cfg.schedules || [];
    if (!l.length) {
      var em = el("div", "schempty", null, w);
      em.innerHTML = SD.svg("clock", 44, "rgba(142,142,147,0.7)") + "<b>Nenhum agendamento</b><span>Toque uma vinheta na hora certa, troque de cena no OBS ou rode um atalho todo dia no mesmo horário.</span>";
      return;
    }
    var box = el("div", "list schitems", null, w);
    box.id = "schItems";
    for (var i = 0; i < l.length; i++) (function (i) {
      var s = l[i], inf = schedInfo[s.id] || {}, on = s.enabled !== false;
      var row = el("div", "schitem" + (i === schedSel ? " sel" : "") + (on ? "" : " off"), null, box);
      row.setAttribute("data-id", s.id);
      schedSwitch(row, on, function (v) { toggleSched(i, v); }, on ? "Ligado" : "Desligado");
      var tx = el("div", "tx", null, row);
      var sc = SD.actionMap[s.action && s.action.type];
      el("div", "nm", esc(s.name || "Sem nome"), tx);
      el("div", "wh", esc(whenText(s.when)) + (sc && s.action.type !== "none" ? " · " + esc(sc.label) : " · <span class=\"warn\">sem ação</span>"), tx);
      var meta = el("div", "mt", null, tx);
      if (!on) el("span", null, s.when && s.when.type === "once" && inf.last ? "Já rodou · desligado" : "Desligado", meta);
      else if (inf.next) el("span", "nx", "Próxima: " + esc(relText(inf.next)), meta);
      else if (schedInfo.hasOwnProperty(s.id)) el("span", null, "Sem próxima execução", meta);
      else if (!schedErr) el("span", null, dirty || inflight ? "Salvando…" : "Próxima: …", meta);
      if (inf.last) el("span", inf.last_error ? "er" : "ls", (inf.last_error ? "Erro " : "Última: ") + esc(relText(inf.last)) +
        (inf.last_error ? ": " + esc(inf.last_error) : ""), meta);
      var acts = el("div", "ac", null, row);
      var tb = el("button", "mini", "Testar agora", acts);
      tb.title = "Executa a ação deste agendamento agora";
      tb.onclick = function (e) { e.stopPropagation(); runSched(i); };
      var mb = el("button", "more", "…", acts);
      mb.title = "Mais opções";
      mb.onclick = function (e) {
        e.stopPropagation();
        popAt(mb, [{ label: "Editar", fn: function () { schedSel = i; renderSched(); } },
          { label: "Duplicar", fn: function () { dupSched(i); } },
          { label: "Testar agora", fn: function () { runSched(i); } },
          { sep: true }, { label: "Apagar", red: true, fn: function () { delSched(i); } }]);
      };
      row.onclick = function () { if (schedSel !== i) { schedSel = i; renderSched(); } };
      row.oncontextmenu = function (e) { e.preventDefault(); mb.onclick(e); };
    })(i);
    w.scrollTop = st;
  }

  function editSched(fn, key, light) {
    var s = curSched();
    if (!s) return;
    var id = s.id;
    change(function () { fn(cfg.schedules[schedSel]); }, key ? "s:" + id + ":" + key : null, light);
  }
  function dayChips(parent, days, set) {
    var row = el("div", "days", null, parent);
    row.id = "schDays";
    var d = sortedDays(days), all = !d.length;
    for (var i = 0; i < 7; i++) (function (i) {
      var on = all || d.indexOf(i) >= 0;
      var b = el("button", "day" + (on ? " on" : ""), DAY_ABBR[i], row);
      b.title = DAY_FULL[i];
      b.setAttribute("data-day", i);
      b.onclick = function () {
        var cur = all ? [0, 1, 2, 3, 4, 5, 6] : d.slice(), k = cur.indexOf(i);
        if (k >= 0) cur.splice(k, 1); else cur.push(i);
        if (!cur.length) { SD.toast("Escolha pelo menos um dia", true); return; }
        cur = sortedDays(cur);
        set(cur.length === 7 ? [] : cur);
      };
    })(i);
    var pr = el("div", "presets", null, parent);
    DAY_PRESETS.forEach(function (x) {
      var b = el("button", "chip" + (sameDays(x[1], d) || (!x[1].length && all) ? " on" : ""), x[0], pr);
      b.onclick = function () { set(x[1].slice()); };
    });
  }
  function timeInput(parent, val, id, set) {
    var t = el("input", "in time", null, parent);
    t.type = "time"; t.id = id; t.value = val || ""; t.required = true;
    /* edicao leve: nao redesenha o formulario enquanto digita, so o resumo */
    t.onchange = function () { if (/^\d\d:\d\d/.test(t.value)) { set(t.value.substring(0, 5)); schedSummary(); } };
    return t;
  }
  function schedSummary() {
    var s = curSched(), sm = $("schSummary");
    if (s && sm) sm.innerHTML = esc(whenText(s.when));
  }
  function renderSchedForm() {
    var f = $("schForm");
    if (!f) return;
    f.innerHTML = "";
    var s = curSched();
    if (!s) {
      el("div", "schnone", (cfg.schedules || []).length ? "Escolha um agendamento na lista para editar." : "Crie um agendamento para começar.", f);
      return;
    }
    var w = s.when || {}, typ = w.type || "daily";
    var hdr = el("div", "hdr withmore", null, f);
    el("span", null, "Editar agendamento", hdr);

    var nf = field(f, "Nome");
    var ni = el("input", "in", null, nf);
    ni.id = "schName"; ni.maxLength = MAX_NAME; ni.value = s.name || ""; ni.placeholder = "Ex.: Vinheta da hora certa";
    ni.oninput = function () { editSched(function (x) { x.name = ni.value; }, "name", true); };

    var ef = field(f, null);
    var el0 = el("label", "chk", null, ef);
    var ei = el("input", null, null, el0);
    ei.type = "checkbox"; ei.id = "schEnabled"; ei.checked = s.enabled !== false;
    el("span", null, "Ligado", el0);
    ei.onchange = function () { editSched(function (x) { x.enabled = ei.checked; }); };

    var tf = field(f, "Quando");
    var seg = el("div", "seg full", null, tf);
    seg.id = "schType";
    [["daily", "Todo dia"], ["every", "A cada"], ["once", "Uma vez"]].forEach(function (x) {
      var b = el("button", typ === x[0] ? "on" : "", x[1], seg);
      b.setAttribute("data-type", x[0]);
      b.onclick = function () { if (typ !== x[0]) editSched(function (y) { y.when = whenOf(x[0], y.when); }); };
    });

    if (typ === "daily") {
      var hf = field(f, "Horário");
      timeInput(hf, w.time, "schTime", function (v) { editSched(function (x) { x.when.time = v; }, "time", true); });
      var df = field(f, "Dias");
      dayChips(df, w.days, function (v) { editSched(function (x) { x.when.days = v; }); });
    } else if (typ === "every") {
      var mf = field(f, "Intervalo", "Alinhado ao relógio: a cada 15 min roda às :00, :15, :30 e :45; a cada 60 min, toda hora cheia.");
      var mr = el("div", "row2", null, mf);
      var ms = el("select", "in", null, mr);
      ms.id = "schEvery";
      var mins = parseInt(w.minutes, 10) || 15, custom = schedCustom[s.id] || EVERY_OPTS.indexOf(mins) < 0;
      EVERY_OPTS.forEach(function (m) { opt(ms, String(m), "A cada " + minText(m), custom ? "" : String(mins)); });
      opt(ms, "c", "Personalizado…", custom ? "c" : "");
      ms.onchange = function () {
        if (ms.value === "c") { schedCustom[s.id] = true; renderSchedForm(); var ci = $("schMinutes"); if (ci) ci.focus(); return; }
        schedCustom[s.id] = false;
        var v = parseInt(ms.value, 10);
        editSched(function (x) { x.when.minutes = v; });
      };
      if (custom) {
        var ci = el("input", "in num", null, mr);
        ci.type = "number"; ci.min = 1; ci.max = 1440; ci.step = 1; ci.id = "schMinutes"; ci.value = mins;
        el("span", "unit", "min", mr);
        ci.oninput = function () {
          var v = parseInt(ci.value, 10);
          if (v >= 1 && v <= 1440) editSched(function (x) { x.when.minutes = v; }, "minutes", true);
        };
        ci.onchange = function () { renderSchedForm(); };
      }
      var wf = field(f, "Horário do dia");
      var wl = el("label", "chk", null, wf);
      var wc = el("input", null, null, wl);
      wc.type = "checkbox"; wc.id = "schWindow"; wc.checked = !!(w.from || w.to);
      el("span", null, "Só numa faixa de horário", wl);
      wc.onchange = function () {
        editSched(function (x) {
          if (wc.checked) { x.when.from = "08:00"; x.when.to = "22:00"; } else { delete x.when.from; delete x.when.to; }
        });
      };
      if (w.from || w.to) {
        var wr = el("div", "row2 win", null, wf);
        el("span", "unit", "das", wr);
        timeInput(wr, w.from || "00:00", "schFrom", function (v) { editSched(function (x) { x.when.from = v; }, "from", true); });
        el("span", "unit", "às", wr);
        timeInput(wr, w.to || "23:59", "schTo", function (v) { editSched(function (x) { x.when.to = v; }, "to", true); });
      }
      var df2 = field(f, "Dias");
      dayChips(df2, w.days, function (v) { editSched(function (x) { x.when.days = v; }); });
    } else {
      var at = String(w.at || ""), of = field(f, "Data e horário", "Depois de rodar, o agendamento se desliga sozinho.");
      var orow = el("div", "row2", null, of);
      var di = el("input", "in", null, orow);
      di.type = "date"; di.id = "schDate"; di.value = at.substring(0, 10);
      var ti = timeInput(orow, at.substring(11, 16) || "08:00", "schAt", function () { setAt(); });
      var setAt = function () {
        if (/^\d{4}-\d\d-\d\d$/.test(di.value) && /^\d\d:\d\d/.test(ti.value)) {
          var v = di.value + "T" + ti.value.substring(0, 5);
          editSched(function (x) { x.when.at = v; }, "at", true);
          schedSummary();
        }
      };
      di.onchange = setAt;
      var atd = parseIso(at);
      if (atd && atd.getTime() < new Date().getTime()) el("div", "help warn", "Essa data já passou: ele não vai rodar.", of);
    }
    el("div", "sumline", esc(whenText(s.when)), f).id = "schSummary";

    /* acao: o mesmo editor dos botoes (sem trocar de pagina) */
    var a = s.action || { type: "none" };
    var af = field(f, "Ação");
    var as = actionSelect(af, a.type, false, function (t) { editSched(function (x) { x.action = newAction(t); }); }, SKIP_SCHED);
    as.id = "schAction";
    var sc = SD.actionMap[a.type];
    if (sc && sc.help) el("div", "ahelp", esc(sc.help), f);
    renderFields(f, a, [], "sa");

    var acts = el("div", "acts", null, f);
    var tb = el("button", "test", "Testar agora", acts);
    tb.id = "schTest";
    tb.disabled = !a.type || a.type === "none";
    tb.onclick = function () { runSched(schedSel); };
    var db = el("button", "dup", "Duplicar", acts);
    db.id = "schDup";
    db.onclick = function () { dupSched(schedSel); };
    var xb = el("button", "clear", "Apagar", acts);
    xb.id = "schDel";
    xb.onclick = function () { delSched(schedSel); };
  }
  /* limpeza antes de salvar: devolve o texto do primeiro problema (ou "") */
  function cleanSchedules(c) {
    var l = c.schedules, warn = "";
    if (!l) return "";
    for (var i = 0; i < l.length; i++) {
      var s = l[i];
      s.name = SD.trim(s.name || "");
      if (s.enabled === undefined) s.enabled = true;
      var w = s.when || {};
      if (w.days) w.days = sortedDays(w.days);
      if (w.type === "every") { if (!w.from) delete w.from; if (!w.to) delete w.to; }
      if (!s.action || !s.action.type || s.action.type === "page") s.action = { type: "none" };
      var m = s.action.type === "none" ? null : missing(s.action, false);
      if (m) {
        if (!warn) warn = "Agendamento “" + (s.name || i + 1) + "” incompleto: preencha " + m;
        if (missing(s.action, true)) s.action = { type: "none" };
      }
    }
    return warn;
  }

  /* ========================================================= biblioteca === */
  var lib = null;
  function openLibrary() {
    var m = modal("Biblioteca de comandos", "libModal");
    var q = el("input", "in search", null, m.head);
    q.id = "libSearch"; q.placeholder = "Buscar (ex.: OBS, Discord, mudo)";
    var target = libTarget();
    el("div", "help", target.text, m.head).id = "libTarget";
    var body = m.body;
    function draw() {
      body.innerHTML = "";
      if (!lib) { el("div", "none", "Carregando…", body); return; }
      var s = SD.trim(q.value).toLowerCase(), any = false;
      (lib.groups || []).forEach(function (g) {
        var items = (g.items || []).filter(function (it) {
          if (!s) return true;
          return ((it.label || "") + " " + (it.help || "") + " " + g.name + " " + (it.action && it.action.type || "")).toLowerCase().indexOf(s) >= 0;
        });
        if (!items.length) return;
        any = true;
        el("div", "lg", esc(g.name), body);
        var gr = el("div", "litems", null, body);
        items.forEach(function (it) {
          var c = el("button", "litem", null, gr);
          var t = paintTile({ label: it.label, icon: it.icon, color: it.color, toggle: it.toggle, action: it.action }, 54);
          c.appendChild(t);
          var tx = el("div", "lt", "<b>" + esc(it.label) + "</b>" + (it.help ? "<span>" + esc(it.help) + "</span>" : ""), c);
          tx.title = it.help || "";
          c.onclick = function () { applyLib(it); m.close(); };
        });
      });
      if (!any) el("div", "none", "Nada encontrado.", body);
    }
    q.oninput = draw;
    draw();
    q.focus();
    if (!lib) {
      SD.req("GET", "/api/library", null, function (ok, data, status) {
        if (ok && data && data.groups) { lib = data; draw(); }
        else { body.innerHTML = ""; el("div", "none", "Não carregou a biblioteca: " + esc(SD.errText(data, status)), body); }
      });
    }
  }
  /* onde o comando da biblioteca vai entrar */
  function libTarget() {
    var bs = list();
    if (msel.length === 1 && sel >= 0 && (!bs[sel] || bs[sel].kind !== "folder")) return { i: sel, text: "Vai preencher o bloco selecionado (posição " + (sel + 1) + ")." };
    for (var i = 0; i < bs.length; i++) if (edEmpty(bs[i])) return { i: i, text: "Vai preencher o primeiro espaço vazio (posição " + (i + 1) + ")." };
    return { i: bs.length, text: "Vai preencher o primeiro espaço vazio (posição " + (bs.length + 1) + ")." };
  }
  function applyLib(it) {
    var tg = libTarget();
    change(function () {
      var h = holder();
      SD.padButtons(h, tg.i + 1);
      var old = h.buttons[tg.i] || {};
      var b = { kind: "button", label: it.label || "", icon: it.icon || "", color: it.color || "", action: clone(it.action || { type: "none" }) };
      if (it.toggle) b.toggle = true;
      if (it.textColor) b.textColor = it.textColor;
      if (it.on) b.on = clone(it.on);
      if (it.image) b.image = it.image;
      if (it.live) b.live = it.live;
      if (it.w) b.w = it.w;
      if (it.h) b.h = it.h;
      if (old.w) b.w = old.w;
      if (old.h) b.h = old.h;
      h.buttons[tg.i] = b;
      selectOne(tg.i);
    });
    SD.toast("“" + (it.label || "Comando") + "” adicionado");
  }
  function modal(title, id) {
    var wrap = el("div", "modal", null, document.body);
    wrap.id = id;
    var box = el("div", "mbox", null, wrap);
    var head = el("div", "mhead", null, box);
    var tr = el("div", "mtitle", null, head);
    el("b", null, esc(title), tr);
    var x = el("button", "mclose", "×", tr);
    x.title = "Fechar (Esc)";
    var body = el("div", "mbody", null, box);
    var m = { head: head, body: body, close: function () {
      document.removeEventListener("keydown", kd, true);
      if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    } };
    function kd(e) { if (e.key === "Escape") { e.stopPropagation(); m.close(); } }
    document.addEventListener("keydown", kd, true);
    x.onclick = m.close;
    wrap.onclick = function (e) { if (e.target === wrap) m.close(); };
    return m;
  }

  /* ===================================================== menu flutuante === */
  /* popMenu(x, y, itens): itens = [{label, fn, red, disabled, sub:[itens], sep}] */
  var popEl = null;
  function closePop() {
    if (popEl && popEl.parentNode) popEl.parentNode.removeChild(popEl);
    popEl = null;
  }
  function popMenu(x, y, items, title) {
    closePop();
    var m = el("div", "pop", null, document.body);
    m.id = "pop";
    popEl = m;
    m.onclick = function (e) { e.stopPropagation(); };
    m.oncontextmenu = function (e) { e.preventDefault(); };
    function fill(list0, head, back) {
      m.innerHTML = "";
      if (back) {
        var bk = el("button", "pi back", "‹ " + esc(head), m);
        bk.onclick = back;
      } else if (head) el("div", "ph", esc(head), m);
      list0.forEach(function (it) {
        if (it.sep) { el("div", "psep", null, m); return; }
        var b = el("button", "pi" + (it.red ? " red" : "") + (it.sub ? " more" : ""), esc(it.label), m);
        if (it.id) b.id = it.id;
        if (it.disabled) b.disabled = true;
        b.onclick = function () {
          if (it.sub) { fill(it.sub, it.label.replace(/…$/, ""), function () { fill(list0, head); }); return; }
          closePop();
          it.fn();
        };
      });
      /* mantem dentro da janela */
      var r = m.getBoundingClientRect();
      m.style.left = Math.max(8, Math.min(x, window.innerWidth - r.width - 8)) + "px";
      m.style.top = Math.max(8, Math.min(y, window.innerHeight - r.height - 8)) + "px";
    }
    m.style.left = x + "px"; m.style.top = y + "px";
    fill(items, title);
    return m;
  }
  function popAt(btnEl, items, title) {
    var r = btnEl.getBoundingClientRect();
    return popMenu(r.left, r.bottom + 4, items, title);
  }

  /* ================================================ paginas: inserir === */
  /* nome livre: "X", "X (2)", "X (3)"... */
  /* corta s para caber em max caracteres (sem quebrar par de surrogates) */
  function cutName(s, max) {
    s = String(s);
    if (charLen(s) <= max) return s;
    var out = "", n = 0;
    for (var i = 0; i < s.length && n < max; i++, n++) {
      var c = s.charAt(i);
      if (/[\uD800-\uDBFF]/.test(c) && i + 1 < s.length) { c += s.charAt(i + 1); i++; }
      out += c;
    }
    return SD.trim(out);
  }
  /* tail: final fixo (ex.: " (copia)"); o nome inteiro fica com ate MAX_NAME caracteres */
  function freeName(name, tail) {
    var used = {};
    tail = tail || "";
    cfg.pages.forEach(function (p, i) { used[plain(pageName(i))] = 1; });
    function mk(suf) { return cutName(name, MAX_NAME - charLen(tail + suf)) + tail + suf; }
    if (!used[plain(mk(""))]) return mk("");
    for (var n = 2; n < 999; n++) if (!used[plain(mk(" (" + n + ")"))]) return mk(" (" + n + ")");
    return mk("");
  }
  /* insere pg na posicao at e corrige os "Ir para pagina" das paginas existentes.
     remapNew: corrige tambem as acoes da pagina nova (copia de uma pagina deste config). */
  function insertPage(at, pg, remapNew) {
    var n = cfg.pages.length, map = {};
    for (var k = 0; k < n; k++) map[k] = k < at ? k : k + 1;
    if (remapNew) cfg.pages.push(pg);
    remapAll(map);
    if (remapNew) cfg.pages.pop();
    cfg.pages.splice(at, 0, pg);
    page = at; folder = -1; selectOne(-1);
  }
  function addBlankPage() {
    if (cfg.pages.length >= 50) { SD.toast("No máximo 50 páginas", true); return; }
    change(function () { insertPage(page + 1, { name: freeName("Página " + (cfg.pages.length + 1)), buttons: [] }); selectOne(0); });
  }
  function duplicatePage(i) {
    if (cfg.pages.length >= 50) { SD.toast("No máximo 50 páginas", true); return; }
    change(function () {
      var cp = clone(cfg.pages[i]);
      cp.name = freeName(pageName(i), " (cópia)");
      /* troca automatica por app ficaria repetida: so a original troca sozinha */
      delete cp.apps;
      insertPage(i + 1, cp, true);
    });
    SD.toast("Página duplicada");
  }
  function pageMenu(i, x, y) {
    var row = $("pages").children[i];
    popMenu(x, y, [
      { label: "Duplicar", id: "pmDup", fn: function () { duplicatePage(i); } },
      { label: "Renomear", id: "pmRen", fn: function () {
        renderPages();
        var r = $("pages").children[i];
        if (r) renamePage(i, r, r.querySelector(".t"));
      } },
      { sep: true },
      { label: "Mover para cima", id: "pmUp", disabled: i === 0, fn: function () { movePage(i, i - 1); } },
      { label: "Mover para baixo", id: "pmDown", disabled: i >= cfg.pages.length - 1, fn: function () { movePage(i, i + 2); } },
      { sep: true },
      { label: "Excluir", id: "pmDel", red: true, disabled: cfg.pages.length <= 1, fn: function () { deletePage(i); } }
    ], pageName(i));
    return row;
  }

  /* --------------------------------------------------------- modelos --- */
  var templates = null;
  /* modelos de reserva (quando o servidor ainda nao tem /api/templates) */
  function mockTemplates() {
    function hk(l, ic, c, keys) { return { label: l, icon: ic, color: c, action: { type: "hotkey", keys: keys } }; }
    return [
      { id: "midia", name: "Mídia", desc: "Tocar, pausar, faixas e volume", icon: "playpause", page: { name: "Mídia", buttons: [
        hk("Anterior", "back", "#0a84ff", ["prev"]), hk("Play/Pausa", "playpause", "#30d158", ["playpause"]),
        hk("Próxima", "forward", "#0a84ff", ["next"]), hk("Volume -", "sound", "#636366", ["volumedown"]),
        hk("Volume +", "sound", "#636366", ["volumeup"]) ] } },
      { id: "windows", name: "Atalhos do Windows", desc: "Copiar, colar, desfazer e área de trabalho", icon: "copy", page: { name: "Atalhos", buttons: [
        hk("Copiar", "copy", "#0a84ff", ["ctrl", "c"]), hk("Colar", "emoji:📋", "#0a84ff", ["ctrl", "v"]),
        hk("Desfazer", "emoji:↩️", "#ff9f0a", ["ctrl", "z"]), hk("Área de trabalho", "emoji:🖥️", "#5e5ce6", ["win", "d"]) ] } }
    ];
  }
  function loadTemplates(cb) {
    if (templates) { cb(templates); return; }
    SD.req("GET", "/api/templates", null, function (ok, data) {
      /* reserva nao fica guardada: tenta o servidor de novo na proxima vez */
      if (ok && data && data.templates) { templates = data.templates; cb(templates); }
      else cb(mockTemplates());
    });
  }
  function miniPage(pg, parentEl) {
    var d = dims("land"), W = 150, gap = 3;
    var cw = Math.floor((W - gap * (d.c - 1)) / d.c), H = cw * d.r + gap * (d.r - 1);
    var wrap = el("div", "tmini", null, parentEl);
    wrap.style.width = W + "px"; wrap.style.height = H + "px";
    var fl = SD.flow(pg.buttons || [], d.c, d.r);
    for (var k = 0; k < fl.length; k++) {
      var b = (pg.buttons || [])[fl[k].i];
      if (!b || edEmpty(b)) continue;
      var w = fl[k].w * cw + (fl[k].w - 1) * gap, h = fl[k].h * cw + (fl[k].h - 1) * gap;
      var t = paintTile(b, w, h);
      t.style.position = "absolute";
      t.style.left = fl[k].x * (cw + gap) + "px"; t.style.top = fl[k].y * (cw + gap) + "px";
      wrap.appendChild(t);
    }
    return wrap;
  }
  function openTemplates() {
    var m = modal("Nova página a partir de um modelo", "tplModal");
    el("div", "help", "A página entra logo depois de “" + esc(pageName(page)) + "”. Depois dá para mudar qualquer botão.", m.head);
    var body = m.body;
    el("div", "none", "Carregando…", body);
    loadTemplates(function (list0) {
      body.innerHTML = "";
      if (!list0.length) { el("div", "none", "Nenhum modelo disponível.", body); return; }
      var gr = el("div", "titems", null, body);
      list0.forEach(function (tp) {
        var c = el("button", "titem", null, gr);
        c.setAttribute("data-id", tp.id || "");
        var hd = el("div", "th", null, c);
        el("span", "ti", SD.hasIcon(tp.icon) ? SD.iconHtml(tp.icon, 22, "#fff") : "", hd);
        el("div", "tt", "<b>" + esc(tp.name || "Modelo") + "</b>" + (tp.desc ? "<span>" + esc(tp.desc) + "</span>" : ""), hd);
        miniPage(tp.page || {}, c);
        c.onclick = function () { m.close(); addTemplate(tp); };
      });
    });
  }
  function addTemplate(tp) {
    if (cfg.pages.length >= 50) { SD.toast("No máximo 50 páginas", true); return; }
    var pg = clone(tp.page || {});
    pg.name = freeName(SD.trim(pg.name || tp.name || "Página"));   /* freeName ja limita o tamanho */
    if (!pg.buttons) pg.buttons = [];
    change(function () { insertPage(page + 1, pg, false); });
    SD.toast("Página “" + pg.name + "” criada");
  }
  function setupAddMenu() {
    var btn = $("addPage"), menu = $("addMenu");
    btn.onclick = function (e) { e.stopPropagation(); closePop(); menu.style.display = menu.style.display === "block" ? "none" : "block"; };
    document.addEventListener("click", function () { menu.style.display = "none"; closePop(); });
    $("addBlank").onclick = function () { menu.style.display = "none"; if (cfg) addBlankPage(); };
    $("addTpl").onclick = function () { menu.style.display = "none"; if (cfg && !$("tplModal")) openTemplates(); };
    window.addEventListener("blur", closePop);
    window.addEventListener("resize", closePop);
  }

  /* ============================================ blocos: copiar / mover === */
  /* posicao livre na lista bs a partir de "from" (ou fim) */
  function freeSlot(bs, from, taken) {
    for (var i = from; i < bs.length; i++) if (edEmpty(bs[i]) && !taken[i]) return i;
    var j = Math.max(bs.length, from);
    while (taken[j]) j++;
    return j;
  }
  function selFull() {
    var bs = list();
    return sorted().filter(function (i) { return bs[i] && !edEmpty(bs[i]); });
  }
  /* copia (ou move) os selecionados para a pagina p (primeiras posicoes livres) */
  /* tamanho final da lista bs depois de ocupar n posicoes livres a partir de from */
  function sizeAfter(bs, n, from, taken0) {
    var taken = {}, k, max = bs.length;
    for (k in taken0) if (taken0.hasOwnProperty(k)) taken[k] = 1;
    for (k = 0; k < n; k++) {
      var j = freeSlot(bs, from, taken);
      taken[j] = 1;
      if (j + 1 > max) max = j + 1;
    }
    return max;
  }
  function sendTo(p, move) {
    var idx = selFull();
    if (!idx.length) return;
    if (sizeAfter(cfg.pages[p].buttons || [], idx.length, 0, {}) > MAX_PAGE_BTNS) { SD.toast("Página cheia", true); return; }
    change(function () {
      var src = list(), dst = cfg.pages[p];
      if (!dst.buttons) dst.buttons = [];
      var taken = {};
      idx.forEach(function (i) {
        var j = freeSlot(dst.buttons, 0, taken);
        taken[j] = 1;
        SD.padButtons(dst, j + 1);
        dst.buttons[j] = clone(src[i]);
        if (move) src[i] = SD.emptyButton();
      });
    });
    SD.toast(idx.length + (idx.length > 1 ? " blocos " + (move ? "movidos" : "copiados") : " bloco " + (move ? "movido" : "copiado")) +
      " para “" + pageName(p) + "”");
  }
  function dupHere() {
    var idx = selFull();
    if (!idx.length) return;
    var noFolder = folder >= 0;
    var h0 = holder(), taken0 = {}, size = h0.buttons.length;
    idx.forEach(function (i) { taken0[i] = 1; });
    idx.forEach(function (i) {
      var j = freeSlot(h0.buttons, i + 1, taken0);
      taken0[j] = 1;
      if (j + 1 > size) size = j + 1;
    });
    if (size > (noFolder ? MAX_FOLDER_BTNS : MAX_PAGE_BTNS)) { SD.toast(noFolder ? "Pasta cheia" : "Página cheia", true); return; }
    change(function () {
      var h = holder(), taken = {}, out = [];
      idx.forEach(function (i) { taken[i] = 1; });
      idx.forEach(function (i) {
        var j = freeSlot(h.buttons, i + 1, taken);
        taken[j] = 1;
        SD.padButtons(h, j + 1);
        var c = clone(h.buttons[i]);
        if (noFolder && c.kind === "folder") c = SD.emptyButton();
        h.buttons[j] = c;
        out.push(j);
      });
      msel = out; sel = out[0];
    });
  }
  /* botao "…" no inspetor */
  function inspMore(hdr) {
    SD.setClass(hdr, "withmore", true);
    var b = el("button", "hmore", "…", hdr);
    b.id = "tileMore"; b.title = "Copiar, mover, duplicar…";
    b.onclick = function (e) { e.stopPropagation(); var r = b.getBoundingClientRect(); tileMenu(r.right - 220, r.bottom + 4); };
  }
  function tileMenu(x, y) {
    var full = selFull().length > 0;
    function pages(move) {
      var l = [];
      for (var p = 0; p < cfg.pages.length; p++) (function (p) {
        if (p === page && folder < 0) return;
        l.push({ label: (p + 1) + ". " + pageName(p) + (p === page ? " (fora da pasta)" : ""), fn: function () { sendTo(p, move); } });
      })(p);
      if (!l.length) l.push({ label: "Não há outra página", disabled: true, fn: function () {} });
      return l;
    }
    var n = msel.length > 1 ? msel.length + " blocos" : "Posição " + (sel + 1);
    popMenu(x, y, [
      { label: "Copiar para página…", id: "tmCopy", disabled: !full, sub: pages(false) },
      { label: "Mover para página…", id: "tmMove", disabled: !full, sub: pages(true) },
      { label: "Duplicar aqui", id: "tmDup", disabled: !full, fn: dupHere },
      { sep: true },
      { label: "Limpar", id: "tmClear", red: true, disabled: !full, fn: clearSel }
    ], n);
  }

  /* ================================================================ tema === */
  var THEME_KEY = "sd_ed_theme";
  var mqLight = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
  function getTheme() {
    try { var t = window.localStorage.getItem(THEME_KEY); return t === "escuro" || t === "claro" ? t : "auto"; }
    catch (e) { return "auto"; }
  }
  function isLight() { return SD.hasClass(document.documentElement, "light"); }
  function applyTheme() {
    var t = getTheme(), l = t === "claro" || (t === "auto" && !!(mqLight && mqLight.matches));
    var was = isLight();
    SD.setClass(document.documentElement, "light", l);
    var mt = document.querySelector("meta[name=theme-color]");
    if (mt) mt.setAttribute("content", l ? "#f2f2f7" : "#000000");
    renderTheme();
    if (was !== l && cfg) renderAll();
  }
  function renderTheme() {
    var s = $("themeSeg"), t = getTheme();
    s.innerHTML = "";
    [["auto", "Automático"], ["escuro", "Escuro"], ["claro", "Claro"]].forEach(function (x) {
      var b = el("button", t === x[0] ? "on" : "", x[1], s);
      b.setAttribute("data-theme", x[0]);
      b.onclick = function () {
        try { window.localStorage.setItem(THEME_KEY, x[0]); } catch (e) {}
        applyTheme();
      };
    });
  }
  function setupTheme() {
    if (mqLight) {
      if (mqLight.addEventListener) mqLight.addEventListener("change", applyTheme);
      else if (mqLight.addListener) mqLight.addListener(applyTheme);
    }
    applyTheme();
  }

  /* ============================================================ teclado === */
  function clearSel() {
    if (sel < 0) return;
    var bs = list(), any = false;
    for (var k = 0; k < msel.length; k++) if (bs[msel[k]] && !edEmpty(bs[msel[k]])) any = true;
    if (!any) return;
    change(function () {
      var l = list();
      for (var k = 0; k < msel.length; k++) if (msel[k] < l.length) l[msel[k]] = SD.emptyButton();
    });
  }
  function typing(e) {
    var t = e.target, n = t && t.tagName;
    return n === "INPUT" || n === "TEXTAREA" || n === "SELECT";
  }
  function sorted() { return msel.slice().sort(function (a, b) { return a - b; }); }
  function copySel() {
    var bs = list(), out = [], s = sorted();
    for (var k = 0; k < s.length; k++) out.push(clone(bs[s[k]] || SD.emptyButton()));
    var any = out.some(function (b) { return !edEmpty(b); });
    if (any) clip = out;
    return any;
  }
  function paste() {
    if (!clip || sel < 0) return;
    var start = msel.length > 1 ? sorted()[0] : sel, c = clone(clip);
    if (folder >= 0) c = c.map(function (b) { return b && b.kind === "folder" ? SD.emptyButton() : b; });
    change(function () {
      var h = holder();
      SD.padButtons(h, start + c.length);
      for (var k = 0; k < c.length; k++) h.buttons[start + k] = c[k];
      msel = [];
      for (k = 0; k < c.length; k++) msel.push(start + k);
      sel = start;
    });
  }
  /* indice do bloco na celula (x, y) */
  function atCell(L, x, y) {
    var all = L.flow.concat(L.free);
    for (var k = 0; k < all.length; k++) {
      var r = all[k];
      if (x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h) return r.i;
    }
    return -1;
  }
  /* atalho tratado fecha o menu flutuante */
  function onKey(e) {
    if (onKey0(e) || e.defaultPrevented) closePop();
  }
  function onKey0(e) {
    if (popEl && e.key === "Escape") { closePop(); e.preventDefault(); return; }
    if (!cfg || rec || $("libModal") || $("tplModal")) return;
    var ctrl = e.ctrlKey || e.metaKey, k = (e.key || "").toLowerCase();
    if (typing(e)) {
      if (e.key === "Escape") e.target.blur();
      return;
    }
    if (ctrl && k === "z" && !e.shiftKey) { e.preventDefault(); undo(); return; }
    if (ctrl && (k === "y" || (k === "z" && e.shiftKey))) { e.preventDefault(); redo(); return; }
    if (schedOpen) return;   /* painel de agendamentos: so desfazer/refazer */
    if (sel < 0) {
      if (/^arrow/.test(k)) { selectOne(0); renderGrid(); renderInspector(); e.preventDefault(); }
      else if (k === "escape" && folder >= 0) { closeFolder(); return true; }
      return;
    }
    if (ctrl && k === "a") {
      e.preventDefault();
      var L0 = layout(); msel = [];
      for (var q = 0; q < L0.flow.length; q++) if (!edEmpty(list()[L0.flow[q].i])) msel.push(L0.flow[q].i);
      if (msel.length) sel = msel[0]; else selectOne(-1);
      renderGrid(); renderInspector();
      return;
    }
    if (ctrl && k === "c") {
      if (copySel()) SD.toast(clip.length > 1 ? clip.length + " blocos copiados" : "Bloco copiado");
      e.preventDefault(); return;
    }
    if (ctrl && k === "x") {
      if (copySel()) { clearSel(); SD.toast(clip.length > 1 ? clip.length + " blocos recortados" : "Bloco recortado"); }
      e.preventDefault(); return;
    }
    if (ctrl && k === "v") { paste(); e.preventDefault(); return; }
    if (k === "delete" || k === "backspace") { e.preventDefault(); clearSel(); return; }
    if (k === "escape") { selectOne(-1); renderGrid(); renderInspector(); return true; }
    if (k === "enter" && curBtn() && curBtn().kind === "folder") { openFolder(sel); return true; }
    var L = layout(), r = rectOf(L, sel), n = sel;
    if (k === "arrowleft") n = sel - 1;
    else if (k === "arrowright") n = sel + 1;
    else if (k === "arrowup") n = r ? atCell(L, r.x, r.y - 1) : -1;
    else if (k === "arrowdown") n = r ? atCell(L, r.x, r.y + r.h) : -1;
    else return;
    e.preventDefault();
    if (n >= 0 && rectOf(L, n)) { selectOne(n); renderGrid(); renderInspector(); }
  }

  /* ============================================================== sons === */
  function loadInfo() {
    SD.req("GET", "/api/info", null, function (ok, data) {
      if (!ok || !data) return;
      SD.info = data;
      sounds = data.sounds || [];
      var box = $("soundList");
      box.innerHTML = "";
      if (!sounds.length) el("div", "none", "Nenhum som ainda", box);
      sounds.forEach(function (s) { el("div", null, esc(s), box).title = s; });
      if (cfg) renderInspector();
    });
  }
  function uploadSounds(files) {
    var list0 = [], i;
    for (i = 0; i < files.length; i++) {
      if (/\.(mp3|wav)$/i.test(files[i].name)) list0.push(files[i]);
      else SD.toast("Só MP3 ou WAV: " + files[i].name, true);
    }
    var n = 0, fails = 0;
    function next() {
      if (n >= list0.length) {
        if (list0.length) SD.toast(fails ? fails + " som(ns) não enviados" : (list0.length > 1 ? list0.length + " sons enviados" : "Som enviado"), !!fails);
        loadInfo();
        return;
      }
      var f = list0[n++];
      if (f.size > 20 * 1024 * 1024) { fails++; SD.toast("Maior que 20 MB: " + f.name, true); next(); return; }
      setStatus("Enviando " + f.name + "…", "busy");
      upload("/api/local/sounds?name=" + encodeURIComponent(f.name), f, function (ok, data, status) {
        if (!ok) { fails++; SD.toast("Não enviou " + f.name + ": " + SD.errText(data, status), true); }
        setStatus(dirty ? "Alterações não salvas…" : "Pronto", dirty ? "busy" : "ok");
        next();
      });
    }
    next();
  }
  function setupSoundDrop() {
    var zone = $("soundZone");
    var depth = 0;
    function hasFiles(e) { var t = e.dataTransfer && e.dataTransfer.types; return t && Array.prototype.indexOf.call(t, "Files") >= 0; }
    zone.addEventListener("dragenter", function (e) { if (!hasFiles(e)) return; e.preventDefault(); depth++; SD.setClass(zone, "drop", true); });
    zone.addEventListener("dragover", function (e) { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
    zone.addEventListener("dragleave", function () { depth = Math.max(0, depth - 1); if (!depth) SD.setClass(zone, "drop", false); });
    zone.addEventListener("drop", function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); depth = 0; SD.setClass(zone, "drop", false);
      uploadSounds(e.dataTransfer.files);
    });
    /* soltar arquivo fora da area nao deve abrir o arquivo no navegador */
    window.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
    window.addEventListener("drop", function (e) { if (hasFiles(e)) e.preventDefault(); });
  }
  function loadImages(cb) {
    SD.req("GET", "/api/images", null, function (ok, data) {
      if (ok && data && data.images) images = data.images;
      if (cb) cb(); else if (cfg) renderInspector();
    });
  }

  /* ============================================================ backup === */
  function exportZip() {
    var x = new XMLHttpRequest();
    x.open("GET", "/api/local/export?" + (SD.TOKEN ? "k=" + encodeURIComponent(SD.TOKEN) + "&" : "") + "t=" + SD.now(), true);
    x.setRequestHeader("X-StreamDeck", "1");
    x.responseType = "blob";
    x.onload = function () {
      if (x.status !== 200) { SD.toast("Não exportou (erro " + x.status + ")", true); return; }
      var d = new Date(), two = function (n) { return (n < 10 ? "0" : "") + n; };
      var name = "streamdeck-backup-" + d.getFullYear() + two(d.getMonth() + 1) + two(d.getDate()) + ".zip";
      var cd = x.getResponseHeader("Content-Disposition") || "";
      var m = /filename="?([^";]+)"?/.exec(cd);
      if (m) name = m[1];
      var url = URL.createObjectURL(x.response);
      var a = el("a", null, null, document.body);
      a.href = url; a.download = name; a.style.display = "none";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(url); document.body.removeChild(a); }, 1000);
      SD.toast("Backup baixado: " + name);
    };
    x.onerror = function () { SD.toast("Sem conexão com o PC", true); };
    x.send(null);
  }
  function importZip() {
    pickFile(".zip,application/zip", false, function (fs) {
      var f = fs[0];
      if (!window.confirm("Importar \"" + f.name + "\"?\n\nOs botões e páginas atuais serão substituídos (o PC guarda uma cópia de segurança). Imagens e sons do arquivo são adicionados.")) return;
      setStatus("Importando…", "busy");
      upload("/api/local/import", f, function (ok, data, status) {
        if (!ok) { setStatus("Não importou: " + SD.errText(data, status), "err"); return; }
        dirty = false; clearTimeout(saveT); saveBad = false;
        page = 0; folder = -1; selectOne(-1);
        loadConfig(false, "Backup importado ✓");
        schedOffToast(data);
        loadInfo(); loadImages();
      });
    });
  }
  /* importar/restaurar: o PC desliga os agendamentos que chegaram */
  function schedOffToast(data) {
    var n = data && data.schedules_disabled;
    if (n > 0) SD.toast(n + " agendamento(s) importado(s) desligado(s) — revise e ligue");
  }
  /* versoes anteriores (copias guardadas pelo PC a cada salvamento) */
  function two(n) { return (n < 10 ? "0" : "") + n; }
  function fmtWhen(epoch) {
    var d = new Date(epoch * 1000);
    return two(d.getDate()) + "/" + two(d.getMonth() + 1) + "/" + d.getFullYear() + " às " + two(d.getHours()) + ":" + two(d.getMinutes()) + ":" + two(d.getSeconds());
  }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }
  function openVersions() {
    var m = modal("Versões anteriores", "verModal");
    el("div", "help", "O PC guarda as últimas 20 versões dos botões (uma a cada salvamento). Escolha uma para ver as páginas e restaurar.", m.head);
    m.body.className += " vbody";
    var listBox = el("div", "vlist", null, m.body);
    var side = el("div", "vside", null, m.body);
    var chosen = null;
    el("div", "none", "Carregando…", listBox);
    el("div", "none", "Selecione uma versão.", side);
    function preview(b) {
      side.innerHTML = "";
      el("div", "vtitle", esc(fmtWhen(b.when)), side);
      var pv = el("div", "vpages", null, side);
      el("div", "none", "Carregando…", pv);
      var go = el("button", "vrestore", "Restaurar esta versão", side);
      go.id = "verRestore";
      go.onclick = function () { doRestore(b); };
      SD.req("GET", "/api/local/backups/" + encodeURIComponent(b.name), null, function (ok, data, status) {
        if (chosen !== b) return;
        pv.innerHTML = "";
        if (!ok || !data || !data.pages) { el("div", "none", "Não abriu: " + esc(SD.errText(data, status)), pv); return; }
        el("div", "lg", "Páginas", pv);
        var ul = el("ol", "vnames", null, pv);
        data.pages.forEach(function (p, i) {
          var n = (p.buttons || []).filter(function (x) { return x && ((x.label && SD.trim(String(x.label))) || (x.action && x.action.type && x.action.type !== "none")); }).length;
          el("li", null, "<b>" + esc(p.name || ("Página " + (i + 1))) + "</b><span>" + esc(plural(n, "botão", "botões")) + "</span>", ul);
        });
      });
    }
    function doRestore(b) {
      if (dirty || inflight) { SD.toast("Aguarde salvar as mudanças atuais e tente de novo", true); return; }
      if (!window.confirm("Restaurar a versão de " + fmtWhen(b.when) + "?\n\nOs botões e páginas atuais serão substituídos. A versão atual fica guardada nesta lista, então dá para voltar depois.")) return;
      setStatus("Restaurando…", "busy");
      SD.req("POST", "/api/local/backups/restore", JSON.stringify({ name: b.name }), function (ok, data, status) {
        if (!ok || !data || !data.ok) { setStatus("Não restaurou: " + SD.errText(data, status), "err"); SD.toast("Não restaurou: " + SD.errText(data, status), true); return; }
        m.close();
        dirty = false; clearTimeout(saveT); saveBad = false;
        page = 0; folder = -1; selectOne(-1);
        schedOffToast(data);
        loadConfig(false, "Versão de " + fmtWhen(b.when) + " restaurada ✓");
      });
    }
    SD.req("GET", "/api/local/backups", null, function (ok, data, status) {
      listBox.innerHTML = "";
      if (!ok || !data || !data.backups) { el("div", "none", "Não carregou: " + esc(SD.errText(data, status)), listBox); return; }
      if (!data.backups.length) { el("div", "none", "Nenhuma versão guardada ainda. Elas aparecem aqui depois que você muda algum botão.", listBox); return; }
      data.backups.forEach(function (b, i) {
        var r = el("button", "vrow", "<b>" + esc(fmtWhen(b.when)) + (b.current ? " <em>atual</em>" : "") + "</b><span>" +
          esc(plural(b.pages, "página", "páginas") + " · " + plural(b.buttons, "botão", "botões")) + "</span>", listBox);
        r.onclick = function () {
          var all = listBox.querySelectorAll(".vrow");
          for (var k = 0; k < all.length; k++) all[k].className = "vrow";
          r.className = "vrow on";
          chosen = b;
          preview(b);
        };
      });
    });
  }
  function setupMenu() {
    var btn = $("backupBtn"), menu = $("backupMenu");
    btn.onclick = function (e) { e.stopPropagation(); menu.style.display = menu.style.display === "block" ? "none" : "block"; };
    document.addEventListener("click", function () { menu.style.display = "none"; });
    $("exportBtn").onclick = function () { menu.style.display = "none"; exportZip(); };
    $("importBtn").onclick = function () { menu.style.display = "none"; importZip(); };
    $("versionsBtn").onclick = function () { menu.style.display = "none"; if (!$("verModal")) openVersions(); };
  }

  /* ============================================================= inicio === */
  function start() {
    $("undo").onclick = undo;
    $("redo").onclick = redo;
    setupAddMenu();
    setupTheme();
    $("schedRow").onclick = function () { if (cfg && !schedOpen) openSched(); };
    $("libBtn").onclick = function () { if (cfg) openLibrary(); };
    $("pageBtn").onclick = function () { if (!cfg) return; if (folder >= 0) closeFolder(); selectOne(-1); renderGrid(); renderInspector(); };
    $("openSounds").onclick = function () {
      SD.req("POST", "/api/local/sounds", "{}", function (ok, data, status) {
        if (!ok) SD.toast("Não abriu: " + SD.errText(data, status), true);
      });
    };
    $("sendSound").onclick = function () { pickFile(".mp3,.wav,audio/mpeg,audio/wav", true, uploadSounds); };
    $("reloadSounds").onclick = loadInfo;
    setupSoundDrop();
    setupMenu();
    loadDev();
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", function () { if (cfg) renderGrid(); });
    window.addEventListener("beforeunload", function (e) {
      if (dirty || inflight) { e.preventDefault(); e.returnValue = ""; }
    });
    SD.loadActions(function (ok) {
      if (!ok) setStatus("Não carregou as ações", "err");
      loadConfig(true);
    });
    loadInfo();
    loadImages();
    setInterval(poll, 3000);
  }
  start();
})();
