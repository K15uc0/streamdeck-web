/* Stream Deck - editor do PC (pagina /editar, so no proprio PC).
   Reutiliza core.js (rede, icones, cores, remapeamento de paginas).
   Salva sozinho (POST /api/config) ~600 ms depois de cada mudanca. */
(function () {
  "use strict";

  var SD = window.SD, $ = SD.$, esc = SD.esc, el = SD.el, clone = SD.clone;

  var FADERS = [["master", "Som do PC (master)"], ["effects", "Efeitos sonoros"], ["mic", "Microfone"]];
  var FADER_ICON = { master: "sound", effects: "music", mic: "mic" };
  var NO_STEP = { page: 1, multi: 1 };

  var cfg = null;            /* config em edicao */
  var page = 0;              /* pagina mostrada */
  var orient = "land";       /* land | port */
  var sel = -1;              /* posicao selecionada na pagina */
  var clip = null;           /* bloco copiado */
  var sounds = [];

  /* historico (desfazer/refazer): fotos do config */
  var hist = [], pos = -1, lastKey = null, lastAt = 0;

  /* salvamento */
  var savedV = null, dirty = false, inflight = false, saveT = null, seq = 0;

  /* ========================================================= utilidades === */
  function isEmpty(b) {
    if (!b) return true;
    if (b.kind === "fader") return false;
    var t = b.action && b.action.type;
    return (!t || t === "none") && !SD.trim(b.label) && !b.icon && !b.toggle;
  }
  function curPage() { return cfg.pages[page]; }
  function buttons() { var pg = curPage(); if (!pg.buttons) pg.buttons = []; return pg.buttons; }
  function used(pg) {
    var bs = pg.buttons || [], n = 0;
    for (var i = 0; i < bs.length; i++) if (!isEmpty(bs[i])) n = i + 1;
    return n;
  }
  function count(pg) {
    var bs = pg.buttons || [], n = 0;
    for (var i = 0; i < bs.length; i++) if (!isEmpty(bs[i])) n++;
    return n;
  }
  /* grade da orientacao: {c, r, auto} */
  function dims(o) {
    if (o === "land") return { c: cfg.columns, r: cfg.rows };
    if (cfg.portrait) return { c: cfg.portrait.columns, r: cfg.portrait.rows };
    if (cfg.columns > cfg.rows) return { c: cfg.rows, r: cfg.columns, auto: true };
    return { c: cfg.columns, r: cfg.rows, auto: true };
  }
  function opt(sel, value, label, cur) {
    var o = el("option", null, null, sel);
    o.value = value; o.textContent = label;
    if (String(cur) === String(value)) o.selected = true;
    return o;
  }
  function setStatus(text, cls) { var s = $("status"); s.textContent = text; s.className = "status" + (cls ? " " + cls : ""); }

  /* ======================================================= historico === */
  function snapshot() { return JSON.stringify(cfg); }
  function resetHistory() { hist = [snapshot()]; pos = 0; lastKey = null; updUndo(); }
  /* change(fn, key, light): aplica a mudanca, guarda no historico e salva.
     key: mudancas seguidas no mesmo campo viram um passo so do desfazer.
     light: nao redesenha o formulario (o campo em edicao continua com o foco). */
  function change(fn, key, light) {
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
  function restore() {
    cfg = JSON.parse(hist[pos]);
    lastKey = null;
    if (page >= cfg.pages.length) page = cfg.pages.length - 1;
    renderAll();
    scheduleSave();
  }
  function updUndo() { $("undo").disabled = pos <= 0; $("redo").disabled = pos >= hist.length - 1; }

  /* ======================================================== salvamento === */
  function cleaned() {
    /* posicoes vazias no fim da pagina nao precisam ir para o arquivo */
    var c = clone(cfg);
    for (var p = 0; p < c.pages.length; p++) {
      var bs = c.pages[p].buttons || [];
      while (bs.length && isEmpty(bs[bs.length - 1])) bs.pop();
      for (var i = 0; i < bs.length; i++) if (isEmpty(bs[i])) bs[i] = SD.emptyButton();
    }
    return c;
  }
  function scheduleSave() {
    dirty = true; seq++;
    setStatus("Alterações não salvas…", "busy");
    clearTimeout(saveT);
    saveT = setTimeout(save, 600);
  }
  function save() {
    if (inflight) { saveT = setTimeout(save, 300); return; }
    inflight = true;
    var mySeq = seq;
    setStatus("Salvando…", "busy");
    SD.req("POST", "/api/config", JSON.stringify(cleaned()), function (ok, data, status) {
      inflight = false;
      if (ok) {
        if (data && data.v != null) savedV = String(data.v);
        if (mySeq === seq) { dirty = false; setStatus("Salvo ✓", "ok"); }
      } else {
        setStatus("Não salvou: " + SD.errText(data, status, "erro no PC"), "err");
      }
    });
  }
  function loadConfig(first) {
    SD.req("GET", "/api/config", null, function (ok, data, status, x) {
      if (!ok || !data || !data.pages) {
        setStatus("Erro ao carregar: " + SD.errText(data, status), "err");
        if (first) setTimeout(function () { loadConfig(true); }, 2000);
        return;
      }
      cfg = data;
      savedV = x.getResponseHeader("X-Config-Version");
      if (page >= cfg.pages.length) page = 0;
      resetHistory();
      renderAll();
      setStatus(first ? "Pronto" : "Atualizado (mudou em outro lugar)", "ok");
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
      var row = el("div", "pg" + (i === page ? " on" : ""), null, box);
      row.draggable = true;
      el("span", "n", String(i + 1), row);
      var t = el("span", "t", esc(pg.name || "Página " + (i + 1)), row);
      el("span", "c", String(count(pg)), row);
      var del = el("button", "del", "×", row);
      del.title = "Apagar página";
      row.onclick = function () { if (page !== i) { page = i; sel = -1; renderAll(); } };
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
      SD.remapPages(cfg, map);
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
    for (var p = 0; p < cfg.pages.length; p++) {
      var bs = cfg.pages[p].buttons || [];
      for (var i = 0; i < bs.length; i++) if (bs[i] && bs[i].kind !== "fader") walk(bs[i].action);
    }
    return n;
  }
  function deletePage(i) {
    if (cfg.pages.length <= 1) { SD.toast("Precisa ter ao menos uma página", true); return; }
    var pg = cfg.pages[i], refs = pageRefs(i);
    var msg = "Apagar a página \"" + (pg.name || "Página " + (i + 1)) + "\" e seus " + count(pg) + " botões?";
    if (refs) msg += "\n\n" + refs + " botão(ões) que levam para ela ficarão vazios.";
    msg += "\n\nDá para desfazer com Ctrl+Z.";
    if (!window.confirm(msg)) return;
    change(function () {
      var map = {}, n = cfg.pages.length;
      for (var k = 0; k < n; k++) map[k] = k < i ? k : (k === i ? -1 : k - 1);
      cfg.pages.splice(i, 1);
      SD.remapPages(cfg, map);
      if (page > i || page >= cfg.pages.length) page = Math.max(0, page - 1);
      sel = -1;
    });
  }
  function addPage() {
    if (cfg.pages.length >= 50) { SD.toast("No máximo 50 páginas", true); return; }
    change(function () {
      cfg.pages.push({ name: "Página " + (cfg.pages.length + 1), buttons: [] });
      page = cfg.pages.length - 1; sel = 0;
    });
  }

  /* ---------------------------------------------- orientacao e tamanho --- */
  function numSelect(parent, cur, lo, hi, onChange) {
    var s = el("select", null, null, parent);
    for (var v = lo; v <= hi; v++) opt(s, v, String(v), cur);
    s.onchange = function () { onChange(parseInt(s.value, 10)); };
    return s;
  }
  function renderBar() {
    var o = $("orient");
    o.innerHTML = "";
    [["land", "Horizontal"], ["port", "Vertical"]].forEach(function (x) {
      var b = el("button", orient === x[0] ? "on" : "", x[1], o);
      b.id = "or-" + x[0];
      b.onclick = function () { orient = x[0]; renderAll(); };
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

  /* --------------------------------------------------------------- grade --- */
  /* desenha um bloco como no celular (estilo Atalhos do iOS) */
  function paintTile(b, size) {
    var t = el("div", "tile");
    t.style.width = size + "px"; t.style.height = size + "px";
    if (isEmpty(b)) {
      SD.setClass(t, "empty", true);
      var ps = Math.round(size * 0.3);
      var ic0 = el("div", "ic", SD.svg("plus", ps, "rgba(235,235,245,0.35)"), t);
      ic0.style.left = (size - ps) / 2 - 2 + "px"; ic0.style.top = (size - ps) / 2 - 2 + "px";
      return t;
    }
    var color = SD.validColor(b.color) ? b.color : SD.DEFAULT_TILE;
    var light = SD.isLight(color);
    var label = SD.trim(b.label), icon = SD.hasIcon(b.icon) ? b.icon : "";
    var pad = Math.max(7, Math.round(size * 0.12));
    var fs = Math.max(10, Math.min(17, Math.round(size * 0.118)));
    var ic, lb;
    if (b.kind === "fader") {
      SD.setClass(t, "fader", true);
      var fill = el("div", "fill", null, t);
      fill.style.background = SD.validColor(b.color) ? b.color : "#fff";
      var fg = SD.validColor(b.color) && !light ? "#fff" : "#1c1c1e";
      icon = icon || FADER_ICON[b.target] || "sound";
      var is = Math.round(size * 0.26);
      ic = el("div", "ic", SD.svg(icon, is, "#fff"), t);
      ic.style.left = (size - is) / 2 + "px"; ic.style.top = pad + "px";
      lb = el("div", "lb c", esc(label || "Fader"), t);
      lb.style.left = "4px"; lb.style.right = "4px"; lb.style.bottom = pad * 0.8 + "px";
      lb.style.fontSize = fs + "px"; lb.style.color = fg;
      return t;
    }
    t.style.background = color;
    if (light) SD.setClass(t, "light", true);
    var fgc = light ? "rgba(0,0,0,0.78)" : "#fff";
    if (icon && (!label || size < 66)) {
      var cs = Math.round(size * 0.44);
      ic = el("div", "ic", SD.svg(icon, cs, fgc), t);
      ic.style.left = (size - cs) / 2 + "px"; ic.style.top = (size - cs) / 2 + "px";
    } else if (icon) {
      var is2 = Math.max(16, Math.round(size * 0.26));
      ic = el("div", "ic", SD.svg(icon, is2, fgc), t);
      ic.style.left = pad + "px"; ic.style.top = pad + "px";
      lb = el("div", "lb", esc(label), t);
      lb.style.left = pad + "px"; lb.style.right = pad * 0.7 + "px"; lb.style.bottom = pad * 0.85 + "px";
      lb.style.fontSize = fs + "px"; lb.style.color = fgc;
    } else {
      lb = el("div", "lb c", esc(label || "(sem nome)"), t);
      lb.style.left = pad * 0.6 + "px"; lb.style.right = pad * 0.6 + "px"; lb.style.top = "50%";
      lb.style.transform = "translateY(-50%)";
      lb.style.fontSize = Math.round(fs * 1.1) + "px"; lb.style.color = fgc;
    }
    if (b.toggle) {
      var ds = Math.max(6, Math.round(size * 0.08));
      var dot = el("div", "dot", null, t);
      dot.style.width = ds + "px"; dot.style.height = ds + "px";
      dot.style.right = pad + "px"; dot.style.top = pad + "px";
    }
    return t;
  }

  var dragFrom = -1;
  function renderGrid() {
    var d = dims(orient), bs = buttons(), slots = d.c * d.r;
    var stage = $("stage"), grid = $("grid");
    var W = stage.clientWidth - 60, H = stage.clientHeight - 60, gap = 12;
    var size = Math.floor(Math.min((W - gap * (d.c - 1)) / d.c, (H - gap * (d.r - 1)) / d.r, 130));
    size = Math.max(40, size);
    grid.style.gridTemplateColumns = "repeat(" + d.c + ", " + size + "px)";
    grid.innerHTML = "";
    for (var i = 0; i < slots; i++) (function (i) {
      var t = paintTile(bs[i], size);
      t.setAttribute("data-i", i);
      if (i === sel) SD.setClass(t, "sel", true);
      t.onclick = function () { sel = i; renderGrid(); renderInspector(); };
      if (!isEmpty(bs[i])) {
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
      grid.appendChild(t);
    })(i);
    /* aviso: botoes que nao cabem nesta grade */
    var u = used(curPage()), w = $("warn");
    if (u > slots) {
      var hidden = 0;
      for (var k = slots; k < bs.length; k++) if (!isEmpty(bs[k])) hidden++;
      w.style.display = "";
      w.textContent = "Esta grade " + (orient === "land" ? "horizontal" : "vertical") + " tem " + slots +
        " posições, mas a página usa " + u + ". " + hidden + " botão(ões) não aparecem nesta orientação. " +
        "Aumente a grade ou mova os botões para posições anteriores.";
    } else w.style.display = "none";
  }
  function swap(a, b) {
    change(function () {
      var bs = buttons();
      SD.padButtons(curPage(), Math.max(a, b) + 1);
      var x = bs[a]; bs[a] = bs[b]; bs[b] = x;
      sel = b;
    });
  }

  /* ============================================================ inspetor === */
  function curBtn() {
    if (sel < 0) return null;
    return buttons()[sel] || null;
  }
  /* devolve o botao selecionado, criando a posicao se for preciso */
  function ensureBtn() {
    SD.padButtons(curPage(), sel + 1);
    var bs = buttons();
    if (!bs[sel]) bs[sel] = SD.emptyButton();
    return bs[sel];
  }
  function edit(fn, key, light) { change(function () { fn(ensureBtn()); }, key ? page + ":" + sel + ":" + key : null, light); }

  function renderPreview() {
    var p = $("prev");
    if (!p) return;
    p.innerHTML = "";
    var t = paintTile(curBtn(), 110);
    t.style.cursor = "default";
    p.appendChild(t);
  }

  function field(parent, label, help) {
    var f = el("div", "f", null, parent);
    if (label) el("div", "l", esc(label), f);
    var body = el("div", null, null, f);
    if (help) el("div", "help", esc(help), f);
    return body;
  }

  function renderInspector() {
    var box = $("inspector");
    box.innerHTML = "";
    if (!cfg) return;
    if (sel < 0) {
      el("div", "insp-empty", "Selecione um bloco na grade para editar.<br><br>Clique em <b>+</b> para criar um botão.", box);
      return;
    }
    var b = curBtn() || SD.emptyButton();
    var d = dims(orient);
    var hdr = el("div", "hdr", "Posição " + (sel + 1) + " · linha " + (Math.floor(sel / d.c) + 1) + ", coluna " + (sel % d.c + 1), box);
    hdr.id = "selinfo";
    var pv = el("div", "preview", null, box);
    pv.id = "prev";
    renderPreview();

    /* tipo */
    var kind = b.kind === "fader" ? "fader" : (b.toggle ? "toggle" : "button");
    var tf = field(box, "Tipo");
    var seg = el("div", "seg", null, tf);
    [["button", "Botão"], ["toggle", "Liga-desliga"], ["fader", "Fader"]].forEach(function (x) {
      var bt = el("button", kind === x[0] ? "on" : "", x[1], seg);
      bt.onclick = function () { setKind(x[0]); };
    });

    /* rotulo */
    var lf = field(box, "Rótulo");
    var li = el("input", "in", null, lf);
    li.id = "label"; li.maxLength = 60; li.value = b.label || ""; li.placeholder = "Texto do bloco";
    li.oninput = function () { edit(function (x) { x.label = li.value; }, "label", true); };

    /* icone */
    var icf = field(box, "Ícone");
    var ig = el("div", "icons", null, icf);
    var none = el("button", b.icon ? "" : "on", "nenhum", ig);
    none.onclick = function () { edit(function (x) { x.icon = ""; }); };
    Object.keys(SD.ICONS).forEach(function (name) {
      var ib = el("button", b.icon === name ? "on" : "", SD.svg(name, 20), ig);
      ib.title = name;
      ib.onclick = function () { edit(function (x) { x.icon = name; }); };
    });

    /* cor */
    var cf = field(box, "Cor");
    var cw = el("div", "colors", null, cf);
    var def = el("button", "sw def" + (b.color ? "" : " on"), "—", cw);
    def.title = "Padrão";
    def.onclick = function () { edit(function (x) { x.color = ""; }); };
    SD.COLORS.forEach(function (c) {
      var sw = el("button", "sw" + (String(b.color).toLowerCase() === c[1] ? " on" : ""), null, cw);
      sw.style.background = c[1]; sw.title = c[0];
      sw.onclick = function () { edit(function (x) { x.color = c[1]; }); };
    });
    var hex = el("input", "in", null, cw);
    hex.id = "hex"; hex.value = b.color || ""; hex.placeholder = "#rrggbb"; hex.maxLength = 7;
    hex.oninput = function () {
      var v = SD.trim(hex.value);
      if (v && v.charAt(0) !== "#") v = "#" + v;
      if (!v || /^#[0-9a-f]{6}$/i.test(v) || /^#[0-9a-f]{3}$/i.test(v)) edit(function (x) { x.color = v; }, "color", true);
    };

    if (kind === "fader") {
      var ff = field(box, "Controla");
      var fs = el("select", "in", null, ff);
      FADERS.forEach(function (x) { opt(fs, x[0], x[1], b.target || "master"); });
      fs.onchange = function () { edit(function (x) { x.target = fs.value; }); };
    } else {
      renderAction(box, b);
    }

    var acts = el("div", "acts", null, box);
    var test = el("button", "test", "Testar", acts);
    test.id = "test";
    test.disabled = kind === "fader" || !b.action || b.action.type === "none" || b.action.type === "page";
    test.title = "Executa a ação agora neste PC, sem salvar";
    test.onclick = function () { testAction(curBtn().action); };
    var clr = el("button", "clear", "Limpar", acts);
    clr.onclick = clearSel;
  }

  function setKind(k) {
    edit(function (x) {
      if (k === "fader") {
        var keep = { kind: "fader", label: x.label || "", icon: x.icon || "", color: x.color || "", target: x.target || "master" };
        for (var p in x) if (x.hasOwnProperty(p)) delete x[p];
        for (p in keep) x[p] = keep[p];
      } else {
        if (x.kind === "fader") { delete x.target; x.action = { type: "none" }; }
        x.kind = "button";
        if (!x.action) x.action = { type: "none" };
        if (k === "toggle") x.toggle = true; else delete x.toggle;
      }
    });
  }

  /* ------------------------------------------------ acao e seus campos --- */
  function actionSelect(parent, cur, isStep, onChange) {
    var s = el("select", "in", null, parent);
    var groups = {}, order = [];
    (SD.actions || []).forEach(function (a) {
      if (isStep && (NO_STEP[a.type] || a.type === "none")) return;
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
    var a = x.action;
    for (var i = 0; i < path.length; i++) a = a[path[i][0]][path[i][1]];
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
  function renderField(box, a, f, path, idp) {
    var v = a[f.key], body, inp;
    var label = f.label + (f.required ? "" : "");
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
    body = field(box, label, f.help);
    if (f.kind === "text" || f.kind === "keys") {
      inp = el("input", "in", null, body);
      inp.value = f.kind === "keys" ? (v && v.join ? v.join("+") : (v || "")) : (v == null ? "" : String(v));
      inp.oninput = function () {
        var val = inp.value;
        if (f.kind === "keys") {
          var parts = val.split("+"), keys = [];
          for (var k = 0; k < parts.length; k++) { var p = SD.trim(parts[k]).toLowerCase(); if (p) keys.push(p); }
          setVal(path, f.key, keys.length ? keys : undefined, true);
        } else setVal(path, f.key, val === "" ? undefined : val, true);
      };
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
      for (var p = 0; p < cfg.pages.length; p++) opt(inp, p, (p + 1) + ". " + (cfg.pages[p].name || "Página " + (p + 1)), v);
      if (v == null) inp.selectedIndex = -1;
      inp.onchange = function () { setVal(path, f.key, parseInt(inp.value, 10)); };
    } else if (f.kind === "steps") {
      renderSteps(body, v || [], path.concat([[f.key]]), idp + "-" + f.key);
      return;
    }
    if (inp) {
      inp.id = idp + "-" + f.key;
      if (f.placeholder) inp.placeholder = f.placeholder;
    }
  }

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
      renderFields(card, st, parent.concat([[key, i]]).map(function (p) { return p; }), idp + "-" + i);
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

  /* ============================================================ teclado === */
  function clearSel() {
    if (sel < 0 || isEmpty(curBtn())) return;
    change(function () { buttons()[sel] = SD.emptyButton(); });
  }
  function typing(e) {
    var t = e.target, n = t && t.tagName;
    return n === "INPUT" || n === "TEXTAREA" || n === "SELECT";
  }
  function onKey(e) {
    if (!cfg) return;
    var ctrl = e.ctrlKey || e.metaKey, k = (e.key || "").toLowerCase();
    if (typing(e)) {
      if (e.key === "Escape") e.target.blur();
      return;
    }
    if (ctrl && k === "z" && !e.shiftKey) { e.preventDefault(); undo(); return; }
    if (ctrl && (k === "y" || (k === "z" && e.shiftKey))) { e.preventDefault(); redo(); return; }
    if (sel < 0) {
      if (/^arrow/.test(k)) { sel = 0; renderGrid(); renderInspector(); e.preventDefault(); }
      return;
    }
    if (ctrl && k === "c") {
      var b = curBtn();
      if (!isEmpty(b)) { clip = clone(b); SD.toast("Bloco copiado"); }
      e.preventDefault(); return;
    }
    if (ctrl && k === "x") {
      if (!isEmpty(curBtn())) { clip = clone(curBtn()); clearSel(); SD.toast("Bloco recortado"); }
      e.preventDefault(); return;
    }
    if (ctrl && k === "v") {
      if (clip) { var c = clone(clip); change(function () { ensureBtn(); buttons()[sel] = c; }); }
      e.preventDefault(); return;
    }
    if (k === "delete" || k === "backspace") { e.preventDefault(); clearSel(); return; }
    if (k === "escape") { sel = -1; renderGrid(); renderInspector(); return; }
    var d = dims(orient), slots = d.c * d.r, n = sel;
    if (k === "arrowleft") n = sel - 1;
    else if (k === "arrowright") n = sel + 1;
    else if (k === "arrowup") n = sel - d.c;
    else if (k === "arrowdown") n = sel + d.c;
    else return;
    e.preventDefault();
    if (n >= 0 && n < slots) { sel = n; renderGrid(); renderInspector(); }
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

  /* ============================================================= inicio === */
  function start() {
    $("undo").onclick = undo;
    $("redo").onclick = redo;
    $("addPage").onclick = addPage;
    $("openSounds").onclick = function () {
      SD.req("POST", "/api/local/sounds", "{}", function (ok, data, status) {
        if (!ok) SD.toast("Não abriu: " + SD.errText(data, status), true);
      });
    };
    $("reloadSounds").onclick = loadInfo;
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
    setInterval(poll, 3000);
  }
  start();
})();
