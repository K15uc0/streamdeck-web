/* Stream Deck - grade de botoes, toque, paginas, faders e botoes liga/desliga. */
(function () {
  "use strict";

  var SD = window.SD, $ = SD.$, esc = SD.esc, el = SD.el, css = SD.css;
  var grid, dotsEl, msg;
  var keys = [];          /* celulas da pagina atual */
  var geo = null;         /* medidas da grade atual */

  /* ============================================================ blocos === */
  /* Um bloco pode ser usado na grade ou na pre-visualizacao do editor.
     t = { el, b, kind, empty, lit, level, ... } ; paintTile(t, w, h) desenha. */
  SD.buildTile = function (b) {
    var t = { b: b, kind: b && b.kind === "fader" ? "fader" : "button" };
    t.empty = SD.isEmpty(b);
    var e = t.el = el("div", "key");
    if (t.kind === "fader") {
      e.className = "key fader";
      t.ic = el("div", "ic", null, e); t.lb = el("div", "lb", null, e); t.val = el("div", "val", null, e);
      t.fill = el("div", "fill", null, e);
      t.inner = el("div", "inner", null, t.fill);
      t.ic2 = el("div", "ic", null, t.inner); t.lb2 = el("div", "lb", null, t.inner); t.val2 = el("div", "val", null, t.inner);
    } else {
      t.gl = el("div", "gl", null, e);
      t.ic = el("div", "ic", null, e);
      t.lb = el("div", "lb", null, e);
      t.fl = el("div", "fl", null, e);
    }
    return t;
  };

  var FADER_ICON = { master: "sound", effects: "music", mic: "mic" };
  var FADER_NAME = { master: "Som do PC", effects: "Efeitos", mic: "Microfone" };
  SD.FADER_TARGETS = [["master", "Som do PC (master)"], ["effects", "Efeitos sonoros"], ["mic", "Microfone"]];

  function px(n) { return Math.round(n) + "px"; }

  SD.paintTile = function (t, w, h) {
    var e = t.el, b = t.b || {}, m = Math.min(w, h), r = Math.round(m * 0.22), st = e.style;
    st.width = px(w); st.height = px(h);
    st.borderRadius = px(r);
    t.w = w; t.h = h;
    if (t.kind === "fader") return paintFader(t, w, h, m, r);
    t.fl.style.borderRadius = px(r);
    var ic = t.ic, lb = t.lb;
    ic.style.cssText = ""; lb.style.cssText = ""; lb.className = "lb";
    if (t.empty) {
      e.className = "key empty";
      st.background = "";
      var ps = Math.round(m * 0.3);
      ic.innerHTML = SD.editing ? SD.svg("plus", ps, "rgba(235,235,245,0.35)") : "";
      ic.style.left = px((w - ps) / 2); ic.style.top = px((h - ps) / 2);
      lb.innerHTML = "";
      return;
    }
    var color = SD.validColor(b.color) ? b.color : SD.DEFAULT_TILE;
    var fg, bg;
    if (t.lit) { bg = "#fff"; fg = SD.isLight(color) ? "#1c1c1e" : color; }
    else { bg = color; fg = SD.isLight(color) ? "rgba(0,0,0,0.78)" : "#fff"; }
    e.className = "key" + (t.lit ? " lit" : "") + (b.toggle ? " tg" : "");
    st.background = bg;
    lb.style.color = fg;
    var icon = SD.hasIcon(b.icon) ? b.icon : "";
    var label = SD.trim(b.label);
    var pad = Math.max(7, Math.round(m * 0.12));
    lb.innerHTML = esc(label);
    if (icon && (!label || m < 66)) {
      /* pequeno ou sem rotulo: so o icone, centralizado */
      var cs = Math.round(m * 0.44);
      ic.innerHTML = SD.svg(icon, cs, fg);
      ic.style.left = px((w - cs) / 2); ic.style.top = px((h - cs) / 2);
      lb.style.display = "none";
    } else if (icon) {
      /* como no app Atalhos: icone em cima a esquerda, rotulo embaixo a esquerda */
      var is = Math.max(16, Math.round(m * 0.26));
      ic.innerHTML = SD.svg(icon, is, fg);
      ic.style.left = px(pad); ic.style.top = px(pad);
      var fs = Math.max(10, Math.min(17, Math.round(m * 0.118)));
      lb.className = "lb bl";
      lb.style.left = px(pad); lb.style.right = px(pad * 0.7); lb.style.bottom = px(pad * 0.85);
      lb.style.fontSize = px(fs);
    } else {
      /* so texto: centralizado, maior */
      ic.innerHTML = "";
      var f2 = Math.max(11, Math.min(22, Math.round(m * 0.16)));
      lb.className = "lb mid";
      lb.style.left = px(pad * 0.6); lb.style.right = px(pad * 0.6);
      lb.style.fontSize = px(f2);
      lb.style.top = "50%";
    }
  };

  /* fader no estilo da Central de Controle: preenche de baixo para cima.
     A parte clara repete icone e texto em cor escura (recortada pelo preenchimento). */
  function paintFader(t, w, h, m, r) {
    var b = t.b || {}, lv = t.level, known = !!(lv && lv.v != null);
    var v = known ? Math.max(0, Math.min(100, lv.v)) : 0, muted = !!(lv && lv.muted);
    var color = SD.validColor(b.color) ? b.color : "#fff";
    t.el.className = "key fader" + (muted ? " muted" : "");
    t.el.style.background = "";
    var fillH = Math.round(h * v / 100);
    t.fill.style.height = px(fillH);
    t.inner.style.width = px(w); t.inner.style.height = px(h);
    var target = b.target || "master";
    var icon = muted ? (target === "mic" ? "micoff" : "mute") : (SD.hasIcon(b.icon) ? b.icon : FADER_ICON[target] || "sound");
    var is = Math.round(m * (m < 80 ? 0.34 : 0.27));
    var label = SD.trim(b.label) || FADER_NAME[target] || "";
    var val = known ? (muted ? "Mudo" : Math.round(v) + "%") : "--";
    var fs = Math.max(10, Math.min(15, Math.round(m * 0.105)));
    var vs = Math.max(12, Math.min(26, Math.round(m * 0.17)));
    var small = m < 80;
    var pairs = [[t.ic, t.lb, t.val, "#fff", "rgba(235,235,245,0.6)"],
                 [t.ic2, t.lb2, t.val2, muted || SD.isLight(color) ? "#1c1c1e" : color, "rgba(0,0,0,0.5)"]];
    var key = icon + "|" + is + "|" + color + "|" + muted;
    for (var i = 0; i < 2; i++) {
      var p = pairs[i];
      if (p[0].getAttribute("data-k") !== key) {
        p[0].innerHTML = SD.svg(icon, is, i === 0 ? "#fff" : pairs[1][3]);
        p[0].setAttribute("data-k", key);
      }
      p[0].style.left = px((w - is) / 2); p[0].style.bottom = px(Math.round(m * 0.12)); p[0].style.top = "auto";
      p[1].innerHTML = small ? "" : esc(label);
      p[1].style.fontSize = px(fs); p[1].style.top = px(Math.round(m * 0.1)); p[1].style.color = p[4];
      p[2].innerHTML = esc(val);
      p[2].style.fontSize = px(vs); p[2].style.color = i === 0 ? "#fff" : p[3];
      p[2].style.top = px(small ? Math.round(m * 0.1) : Math.round(m * 0.1) + fs + 3);
    }
  }

  /* ========================================================= estado ===== */
  function curPage() { return SD.cfg && SD.cfg.pages[SD.page]; }
  SD.curPage = curPage;

  function levelOf(target) {
    var l = SD.levels;
    if (!l) return null;
    var x = l[target];
    if (x == null) return null;
    if (typeof x === "object") return { v: x.v, muted: !!x.muted };
    return { v: x, muted: !!l[target + "Mute"] };   /* formato antigo (1.x) */
  }
  SD.levelOf = levelOf;

  function pageHasFaders() {
    var pg = curPage();
    if (!pg || !pg.buttons) return false;
    var n = SD.cfg.columns * SD.cfg.rows;
    for (var i = 0; i < pg.buttons.length && i < n; i++) if (pg.buttons[i] && pg.buttons[i].kind === "fader") return true;
    return false;
  }

  /* ========================================================== barra ===== */
  SD.renderNav = function () {
    var L = $("nav-l"), T = $("nav-t"), R = $("nav-r");
    L.innerHTML = ""; R.innerHTML = "";
    var pg = curPage();
    T.innerHTML = esc(pg ? (pg.name || "Página " + (SD.page + 1)) : (SD.cfg && SD.cfg.title) || "Stream Deck");
    if (SD.editing) {
      var aj = el("span", "nb", "Ajustes", L);
      aj.onclick = function () { SD.openSettings(); };
      if (SD.updAvail()) el("i", "nbadge", null, aj);
      var ok = el("span", "nb b", "OK", R);
      ok.onclick = function () { SD.setEditing(false); };
    } else {
      if (SD.conns.length > 1) {
        for (var i = 0; i < SD.conns.length; i++) (function (idx) {
          var c = SD.conns[idx], isHere = c.host === SD.here;
          var st = isHere ? (SD.online ? "up" : "down") : (SD.alive[c.host] === true ? "up" : SD.alive[c.host] === false ? "down" : "");
          var p = el("span", "pill" + (isHere ? " on" : ""), '<i class="' + st + '"></i>' + esc(c.name || c.host), L);
          p.onclick = function () { if (!isHere) SD.switchTo(idx); };
        })(i);
      }
      if (SD.cfg) {
        var ed = el("span", "nb", "Editar", R);
        ed.onclick = function () { SD.setEditing(true); };
        if (SD.updAvail()) el("i", "nbadge", null, ed);
      }
      if (SD.conns.length <= 1) el("i", "cdot" + (SD.online ? "" : " off"), null, L);
    }
    /* titulo centralizado sem encostar nos lados */
    var W = window.innerWidth, side = Math.max(L.offsetWidth, R.offsetWidth) + 12;
    if (W - 2 * side >= 90) { T.style.left = px(side); T.style.right = px(side); T.style.display = ""; }
    else {
      /* abas ocupam o lado esquerdo: o titulo vai para o espaco que sobra (ou some) */
      T.style.left = px(L.offsetWidth + 8); T.style.right = px(R.offsetWidth + 8);
      T.style.display = W - L.offsetWidth - R.offsetWidth - 16 < 70 ? "none" : "";
    }
  };
  SD.onConn = function () { SD.renderNav(); };

  /* ========================================================== grade ===== */
  SD.render = function () {
    if (!SD.cfg) return;
    if (SD.page >= SD.cfg.pages.length) SD.page = SD.cfg.pages.length - 1;
    if (SD.page < 0) SD.page = 0;
    document.body.className = SD.editing ? "editing" : "";
    SD.renderNav();
    renderGrid();
    renderDots();
    SD.layout();
  };

  function renderGrid() {
    var pg = curPage(), n = SD.cfg.columns * SD.cfg.rows;
    grid.innerHTML = "";
    keys = [];
    for (var i = 0; i < n; i++) {
      var b = pg.buttons && pg.buttons[i];
      var t = SD.buildTile(b);
      t.idx = i;
      t.lit = !!(b && b.toggle && SD.toggles[SD.page + ":" + i]);
      if (t.kind === "fader") t.level = levelOf(b.target || "master");
      var cell = el("div", "cell" + (i % 2 ? " odd" : "") + (t.empty ? " empty-cell" : ""), null, grid);
      cell.appendChild(t.el);
      cell.setAttribute("data-i", i);
      if (SD.drag && SD.drag.page === SD.page && SD.drag.idx === i) cell.className += " ghost";
      if (!t.empty) el("div", "del", SD.svg("minus", 14), cell);
      t.cell = cell;
      keys.push(t);
    }
  }
  SD.getKeys = function () { return keys; };

  function renderDots() {
    var n = SD.cfg.pages.length, h = "";
    if (n > 1 || SD.editing) for (var j = 0; j < n; j++) h += '<span data-p="' + j + '"' + (j === SD.page ? ' class="on"' : "") + "><i></i></span>";
    dotsEl.innerHTML = h;
    var sp = dotsEl.getElementsByTagName("span");
    for (var k = 0; k < sp.length; k++) sp[k].onclick = function () { SD.goPage(parseInt(this.getAttribute("data-p"), 10)); };
  }

  /* margens seguras (entalhe / barra de gestos) lidas do CSS */
  function safe() {
    var p = $("safe"), s = window.getComputedStyle ? getComputedStyle(p) : null;
    function v(x) { var n = s ? parseFloat(s[x]) : 0; return isNaN(n) ? 0 : n; }
    return { t: v("paddingTop"), r: v("paddingRight"), b: v("paddingBottom"), l: v("paddingLeft") };
  }

  function fitSq(aw, ah, cols, rows, gap) {
    return Math.min((aw - gap * (cols - 1)) / cols, (ah - gap * (rows - 1)) / rows);
  }

  SD.layout = function () {
    if (!SD.cfg) return;
    var W = window.innerWidth, H = window.innerHeight, sa = safe();
    var top = $("nav").offsetHeight, bottom = Math.max(sa.b, 4) + 26;
    var side = 12;
    var aw = W - sa.l - sa.r - side * 2, ah = H - top - bottom - 6;
    var gap = Math.max(8, Math.min(20, Math.round(Math.min(aw, ah) * 0.03)));
    var cols = SD.cfg.columns, rows = SD.cfg.rows;
    /* em pe (celular): troca colunas e linhas se os botoes ficarem maiores */
    if (fitSq(aw, ah, rows, cols, gap) > fitSq(aw, ah, cols, rows, gap)) { cols = SD.cfg.rows; rows = SD.cfg.columns; }
    var w = (aw - gap * (cols - 1)) / cols, h = (ah - gap * (rows - 1)) / rows;
    if (w > h * 1.35) w = h * 1.35;
    if (h > w * 1.15) h = w * 1.15;
    var cap = 230;
    if (w > cap * 1.2) w = cap * 1.2;
    if (h > cap) h = cap;
    w = Math.max(24, Math.floor(w)); h = Math.max(24, Math.floor(h));
    var gw = w * cols + gap * (cols - 1), gh = h * rows + gap * (rows - 1);
    var x0 = Math.round(sa.l + side + (aw - gw) / 2), y0 = Math.round(top + 3 + (ah - gh) / 2);
    geo = { cols: cols, rows: rows, w: w, h: h, gap: gap, x0: x0, y0: y0 };
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i], c = i % cols, r = Math.floor(i / cols);
      k.x = x0 + c * (w + gap); k.y = y0 + r * (h + gap);
      var st = k.cell.style;
      st.left = px(k.x); st.top = px(k.y); st.width = px(w); st.height = px(h);
      SD.paintTile(k, w, h);
    }
    dotsEl.style.bottom = px(Math.max(sa.b, 4));
    SD.renderNav();
  };
  var layoutT = null;
  SD.layoutSoon = function () { clearTimeout(layoutT); layoutT = setTimeout(SD.layout, 60); };

  /* ========================================================= paginas ===== */
  SD.goPage = function (to, dir) {
    if (!SD.cfg || !SD.cfg.pages[to] || to === SD.page) return;
    if (dir == null) dir = to > SD.page ? 1 : -1;
    SD.page = to;
    SD.render();
    if (SD.drag) return;
    css(grid, "transition", "none");
    css(grid, "transform", "translate3d(" + (dir * 60) + "px,0,0)");
    grid.style.opacity = "0.2";
    setTimeout(function () {
      css(grid, "transition", "");
      css(grid, "transform", "");
      grid.style.opacity = "";
    }, 20);
    pollSoon();
  };

  /* ====================================================== apertar ===== */
  var REPEAT = { volumeup: 1, volumedown: 1, left: 1, right: 1, up: 1, down: 1, pageup: 1, pagedown: 1 };
  var pending = 0;

  /* segurar repete (so volume e setas: repetir outros atalhos seria perigoso) */
  function canRepeat(k) {
    var a = k.b && k.b.action;
    return !!(a && a.type === "hotkey" && a.keys && a.keys.length === 1 && REPEAT[String(a.keys[0]).toLowerCase()]);
  }

  function flash(k, ok) {
    if (!k.fl) return;
    k.fl.className = "fl " + (ok ? "ok" : "err");
    setTimeout(function () { k.fl.className = "fl"; }, ok ? 140 : 650);
  }

  function setLit(k, on) {
    if (k.lit === on) return;
    k.lit = on;
    if (k.w) SD.paintTile(k, k.w, k.h);
  }

  SD.applyToggles = function (t) {
    if (t) SD.toggles = t;
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (k.kind === "button" && k.b && k.b.toggle) setLit(k, !!SD.toggles[SD.page + ":" + k.idx]);
    }
  };

  function press(k, repeating) {
    var b = k.b, a = b && b.action;
    if (!a || a.type === "none") return;
    if (a.type === "page") return SD.goPage(parseInt(a.to, 10) || 0);
    if (repeating && pending > 0) return;   /* nao empilha pedidos se a rede estiver lenta */
    flash(k, true);                          /* resposta visual na hora */
    var p = SD.page, idx = k.idx, tkey = p + ":" + idx, was = !!SD.toggles[tkey];
    if (b.toggle) { SD.toggles[tkey] = !was; setLit(k, !was); }
    pending++;
    SD.req("GET", "/api/press?p=" + p + "&b=" + idx, null, function (ok, data, status) {
      pending--;
      if (ok) {
        if (data && data.toggles) { if (p === SD.page) SD.applyToggles(data.toggles); else SD.toggles = data.toggles; }
        return;
      }
      if (b.toggle) { SD.toggles[tkey] = was; if (p === SD.page) setLit(k, was); }
      flash(k, false);
      SD.toast(SD.errText(data, status), true);
    });
  }

  /* ========================================================= faders ===== */
  var sending = {};   /* alvo -> {busy, next} */
  var holdUntil = {}; /* alvo -> ate quando ignorar o PC (nao brigar com o dedo) */

  function paintFaders(target) {
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (k.kind === "fader" && (!target || (k.b.target || "master") === target)) {
        k.level = levelOf(k.b.target || "master");
        if (k.w) SD.paintTile(k, k.w, k.h);
      }
    }
  }

  function setLocalLevel(target, v, muted) {
    var cur = levelOf(target) || { v: 0, muted: false };
    SD.levels[target] = { v: v == null ? cur.v : v, muted: muted == null ? cur.muted : muted };
    delete SD.levels[target + "Mute"];
    paintFaders(target);
  }

  SD.applyLevels = function (l, force) {
    if (!l) return;
    var t = SD.now();
    for (var name in l) {
      if (!l.hasOwnProperty(name) || /Mute$/.test(name)) continue;
      if (!force && (holdUntil[name] > t || (sending[name] && sending[name].busy) || (G && G.mode === "fader" && G.target === name))) continue;
      SD.levels[name] = l[name];
      if (l[name + "Mute"] != null) SD.levels[name + "Mute"] = l[name + "Mute"];
    }
    paintFaders();
  };

  function sendLevel(target, v) {
    var s = sending[target] || (sending[target] = {});
    if (s.busy) { s.next = v; return; }
    s.busy = true; s.next = null;
    SD.req("GET", "/api/volume?c=" + encodeURIComponent(target) + "&v=" + Math.round(v), null, function (ok, data, status) {
      s.busy = false;
      holdUntil[target] = SD.now() + 1200;
      if (!ok) SD.toast(SD.errText(data, status, "Não foi possível mudar o volume"), true);
      if (s.next != null) { var n = s.next; s.next = null; sendLevel(target, n); }
    });
  }

  function toggleMute(k) {
    var target = k.b.target || "master", cur = levelOf(target) || { v: 0, muted: false };
    setLocalLevel(target, null, !cur.muted);
    holdUntil[target] = SD.now() + 1500;
    SD.vibrate(8);
    SD.req("GET", "/api/volume?c=" + encodeURIComponent(target) + "&mute=toggle", null, function (ok, data, status) {
      if (ok && data && data.levels) { holdUntil[target] = 0; SD.applyLevels(data.levels, true); return; }
      if (!ok) { setLocalLevel(target, null, cur.muted); SD.toast(SD.errText(data, status, "Não foi possível silenciar"), true); }
    });
  }

  function fetchLevels() {
    SD.req("GET", "/api/volume", null, function (ok, data) { if (ok && data) SD.applyLevels(data.levels); });
  }

  /* ========================================================= gestos ===== */
  /* Um gesto por vez, tratado no documento:
     press (toque), fader (arrastar volume), swipe (trocar pagina),
     lift/drag (modo edicao: segurar e arrastar), del (badge de remover). */
  var G = null, lastTouch = 0;

  function cellOf(target) {
    while (target && target !== document.body) {
      if (target.getAttribute && target.getAttribute("data-i") != null && SD.hasClass(target, "cell")) return target;
      target = target.parentNode;
    }
    return null;
  }
  function isIn(target, cls) {
    while (target && target !== document.body) {
      if (target.className && typeof target.className === "string" && SD.hasClass(target, cls)) return true;
      target = target.parentNode;
    }
    return false;
  }

  function clearTimers() {
    if (!G) return;
    clearTimeout(G.holdT); clearInterval(G.repT); clearTimeout(G.lpT);
  }
  function up() { if (G && G.k) SD.setClass(G.k.el, "down", false); }

  function start(x, y, target) {
    if (SD.sheet.isOpen() || SD.alertOpen() || !SD.cfg) return false;
    if (isIn(target, "nav") || isIn(target, "dots-bar")) return false;
    var cell = cellOf(target), k = cell ? keys[parseInt(cell.getAttribute("data-i"), 10)] : null;
    G = { k: k, sx: x, sy: y, x: x, y: y, t0: SD.now(), mode: "pending", moved: false };
    if (!k) return true;
    if (SD.editing) {
      if (isIn(target, "del") && !k.empty) { G.mode = "del"; return true; }
      SD.setClass(k.el, "down", true);
      if (!k.empty) G.lpT = setTimeout(function () { if (G && G.mode === "pending") lift(); }, 260);
      return true;
    }
    if (k.kind === "fader") {
      var lv = levelOf(k.b.target || "master");
      G.mode = "fader"; G.target = k.b.target || "master"; G.v0 = lv && lv.v != null ? lv.v : 0;
      return true;
    }
    if (!k.empty) SD.setClass(k.el, "down", true);
    if (!k.empty && canRepeat(k)) {
      G.holdT = setTimeout(function () {
        if (!G || G.mode !== "pending") return;
        G.mode = "repeat";
        press(k, true);
        G.repT = setInterval(function () { press(k, true); }, 130);
      }, 450);
    } else {
      /* segurar ~0,6 s entra no modo edicao (como na tela de inicio do iOS) */
      G.lpT = setTimeout(function () {
        if (!G || G.mode !== "pending") return;
        up();
        SD.vibrate(12);
        var idx = G.k.idx;
        SD.setEditing(true);
        G.k = keys[idx];
        if (G.k && !G.k.empty) { lift(); G.fromLP = true; } else G.mode = "none";
      }, 600);
    }
    return true;
  }

  function lift() {
    G.mode = "lift";
    SD.setClass(G.k.cell, "lifted", true);
    SD.vibrate(8);
  }

  function move(x, y) {
    if (!G) return;
    G.x = x; G.y = y;
    var dx = x - G.sx, dy = y - G.sy, adx = Math.abs(dx), ady = Math.abs(dy);
    if (adx > 6 || ady > 6) G.moved = true;
    if (G.mode === "fader") {
      var h = G.k.h || 100, v = Math.max(0, Math.min(100, G.v0 - dy / h * 100 * 1.15));
      if (!G.moved) return;
      var cur = levelOf(G.target);
      if (cur && cur.v != null && Math.round(cur.v) === Math.round(v)) return;
      setLocalLevel(G.target, Math.round(v), null);
      holdUntil[G.target] = SD.now() + 1500;
      sendLevel(G.target, v);
      return;
    }
    if (G.mode === "lift") { startDrag(); }
    if (G.mode === "drag") { dragMove(x, y); return; }
    if (G.mode === "swipe") { swipeMove(dx); return; }
    if (G.mode === "pending" || G.mode === "repeat") {
      var lim = G.k ? Math.min(40, Math.max(18, (G.k.w || 80) * 0.25)) : 10;
      if (adx > 10 && adx > ady * 1.3 && G.mode === "pending") { cancelPress(); G.mode = "swipe"; swipeMove(dx); return; }
      if (adx > lim || ady > lim) { cancelPress(); G.mode = "none"; }
    }
  }

  function cancelPress() { clearTimers(); up(); }

  function end(cancel) {
    if (!G) return;
    var g = G;
    clearTimers(); up();
    if (g.mode === "fader") {
      holdUntil[g.target] = SD.now() + 1200;
      if (!g.moved && !cancel) {
        /* toque na parte de baixo (icone) liga/desliga o mudo */
        var r = g.k.cell.getBoundingClientRect();
        if (g.y > r.top + r.height * 0.6) toggleMute(g.k);
      }
    } else if (g.mode === "swipe") {
      swipeEnd(g.x - g.sx, SD.now() - g.t0);
    } else if (g.mode === "drag") {
      dragEnd(cancel);
    } else if (g.mode === "lift") {
      SD.setClass(g.k.cell, "lifted", false);
      if (!cancel && !g.fromLP && SD.editing && g.k.cell.parentNode) SD.openEditor(g.k.idx);
    } else if (g.mode === "del") {
      if (!cancel && !g.moved) SD.removeButton(g.k.idx);
    } else if (g.mode === "pending" && g.k && !cancel) {
      if (SD.editing) SD.openEditor(g.k.idx);
      else press(g.k, false);
    }
    G = null;
  }

  /* ---------------------------------------------- deslizar (paginas) --- */
  function swipeMove(dx) {
    var n = SD.cfg.pages.length;
    if ((SD.page === 0 && dx > 0) || (SD.page === n - 1 && dx < 0)) dx = dx / 3;   /* elastico nas pontas */
    css(grid, "transition", "none");
    css(grid, "transform", "translate3d(" + Math.round(dx) + "px,0,0)");
  }
  function swipeEnd(dx, dt) {
    css(grid, "transition", "");
    var W = window.innerWidth, fast = Math.abs(dx) > 40 && dt < 300;
    var to = SD.page + (dx < 0 ? 1 : -1);
    if ((Math.abs(dx) > W * 0.18 || fast) && SD.cfg.pages[to]) {
      css(grid, "transform", "translate3d(" + (dx < 0 ? -W : W) * 0.4 + "px,0,0)");
      grid.style.opacity = "0";
      setTimeout(function () { SD.goPage(to, dx < 0 ? 1 : -1); }, 120);
    } else {
      css(grid, "transform", "");
    }
  }

  /* --------------------------------------------- arrastar (edicao) --- */
  var edgeT = null;
  function startDrag() {
    var k = G.k;
    G.mode = "drag";
    SD.drag = { page: SD.page, idx: k.idx, cell: k.cell, ox: k.x, oy: k.y, w: k.w, h: k.h };
    var c = k.cell;
    SD.setClass(c, "lifted", true);
    SD.setClass(c, "dragging", true);
    $("draglayer").appendChild(c);   /* sobrevive a troca de pagina */
    var ghost = el("div", "cell ghost", null, grid);
    ghost.style.cssText = c.style.cssText;
  }

  function hitCell(x, y) {
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (x >= k.x && x <= k.x + k.w && y >= k.y && y <= k.y + k.h) return k;
    }
    return null;
  }

  function dragMove(x, y) {
    var d = SD.drag, c = d.cell;
    c.style.left = px(d.ox + (x - G.sx)); c.style.top = px(d.oy + (y - G.sy));
    var over = hitCell(x, y);
    for (var i = 0; i < keys.length; i++) SD.setClass(keys[i].cell, "over", keys[i] === over && !(d.page === SD.page && over.idx === d.idx));
    /* perto da borda: muda de pagina levando o botao */
    var W = window.innerWidth, edge = x < 28 ? -1 : x > W - 28 ? 1 : 0;
    if (!edge) { clearTimeout(edgeT); edgeT = null; return; }
    if (edgeT) return;
    edgeT = setTimeout(function () {
      edgeT = null;
      var to = SD.page + edge;
      if (SD.drag && SD.cfg.pages[to]) { SD.goPage(to, edge); SD.vibrate(8); }
    }, 650);
  }

  function dragEnd(cancel) {
    clearTimeout(edgeT); edgeT = null;
    var d = SD.drag, over = cancel ? null : hitCell(G.x, G.y);
    SD.drag = null;
    if (d.cell.parentNode) d.cell.parentNode.removeChild(d.cell);
    if (!over || (d.page === SD.page && over.idx === d.idx)) { SD.render(); return; }
    var c = SD.clone(SD.cfg), n = c.columns * c.rows;
    var src = c.pages[d.page], dst = c.pages[SD.page];
    SD.padButtons(src, n); SD.padButtons(dst, n);
    var tmp = dst.buttons[over.idx];
    dst.buttons[over.idx] = src.buttons[d.idx];
    src.buttons[d.idx] = tmp;
    /* estados liga/desliga acompanham o botao */
    var a = d.page + ":" + d.idx, b = SD.page + ":" + over.idx, ta = SD.toggles[a], tb = SD.toggles[b];
    delete SD.toggles[a]; delete SD.toggles[b];
    if (ta) SD.toggles[b] = true;
    if (tb) SD.toggles[a] = true;
    SD.saveCfg(c, null, true);
  }

  /* ----------------------------------------------- eventos do documento --- */
  function onTS(e) {
    lastTouch = SD.now();
    if (e.touches.length > 1) { if (G) end(true); return; }
    var t = e.touches[0];
    if (start(t.clientX, t.clientY, e.target)) e.preventDefault();
  }
  function onTM(e) {
    if (G) { var t = e.touches[0]; move(t.clientX, t.clientY); e.preventDefault(); return; }
    /* sem folha aberta, a tela nao rola nem da zoom */
    if (!SD.sheet.isOpen() && !SD.alertOpen()) e.preventDefault();
  }
  function onTE(e) { if (G) { e.preventDefault(); end(false); } }
  function onTC() { if (G) end(true); }

  function onMD(e) {
    if (SD.now() - lastTouch < 800 || e.button !== 0) return;
    if (start(e.clientX, e.clientY, e.target)) e.preventDefault();
  }
  function onMM(e) { if (G && SD.now() - lastTouch > 800) move(e.clientX, e.clientY); }
  function onMU() { if (G && SD.now() - lastTouch > 800) end(false); }

  /* ======================================================== rede ===== */
  var offlineToast = false, pollT = null;

  function showMsg(icon, title, text) {
    msg.innerHTML = '<div class="m-ic">' + SD.svg(icon, 34, "rgba(235,235,245,0.6)") + "</div><b>" + esc(title) + "</b><p>" + esc(text) + "</p>";
    msg.style.display = "block";
  }

  SD.load = function () {
    SD.req("GET", "/api/config", null, function (ok, data, status, x) {
      if (ok && data && data.pages) {
        SD.cfg = data;
        try { SD.cfgV = x.getResponseHeader("X-Config-Version"); } catch (e) {}
        SD.cacheCfg();
        offlineToast = false;
        msg.style.display = "none";
        if (SD.page >= SD.cfg.pages.length) SD.page = 0;
        SD.render();
        if (!SD.info) SD.loadInfo(SD.pingAll);
        pollSoon();
      } else if (status === 403 || status === 429) {
        SD.cfg = null; keys = [];
        grid.innerHTML = ""; dotsEl.innerHTML = "";
        SD.editing = false;
        SD.dropCache();
        SD.initConns(); SD.renderNav();
        if (status === 403) showMsg("lock", "Aparelho sem acesso", "Este aparelho ainda não tem o código de acesso (ou ele foi trocado). No PC, abra a tela Conectar e leia o QR code.");
        else showMsg("lock", "Muitas tentativas", "Muitas tentativas com código errado. Aguarde 10 minutos e leia o QR code de novo na tela do PC.");
      } else {
        if (!SD.conns.length) { SD.initConns(); SD.renderNav(); SD.pingAll(); }
        if (SD.cfg) {   /* mostra os botoes guardados e continua tentando */
          if (!offlineToast) { offlineToast = true; SD.toast("Sem conexão com o PC. Tentando de novo…", true); }
        } else {
          showMsg("wifi", "Sem conexão com o PC", "Verifique se o Stream Deck está aberto no PC e se os dois estão na mesma rede.");
          SD.renderNav();
        }
        setTimeout(SD.load, 3000);
      }
    });
  };

  /* consulta leve: edicoes de outro aparelho, estados liga/desliga, volumes e versoes novas */
  function poll() {
    clearTimeout(pollT);
    var faders = pageHasFaders();
    pollT = setTimeout(poll, faders ? 2000 : 5000);
    if (SD.denied || !SD.cfg || document.hidden) return;
    SD.req("GET", "/api/state" + (faders ? "?levels=1" : ""), null, function (ok, st, status) {
      if (!ok) { if (status === 403) SD.load(); return; }
      if (offlineToast) { offlineToast = false; SD.toast("Conectado"); }
      if (st.toggles) SD.applyToggles(st.toggles);
      if (st.levels) SD.applyLevels(st.levels);
      if (SD.cfgV != null && st.v != null && String(st.v) !== String(SD.cfgV) && !SD.editing && !SD.sheet.isOpen() && !G) SD.load();
      if (SD.info && SD.info.update && !!st.update !== !!SD.info.update.available) SD.loadInfo();
    });
  }
  function pollSoon() {
    clearTimeout(pollT);
    pollT = setTimeout(poll, 50);
    if (pageHasFaders()) fetchLevels();
  }
  SD.pollSoon = pollSoon;

  /* ======================================================== inicio ===== */
  SD.start = function () {
    grid = $("grid"); dotsEl = $("dots"); msg = $("msg");
    document.addEventListener("touchstart", onTS, { passive: false });
    document.addEventListener("touchmove", onTM, { passive: false });
    document.addEventListener("touchend", onTE, { passive: false });
    document.addEventListener("touchcancel", onTC, false);
    document.addEventListener("mousedown", onMD, false);
    document.addEventListener("mousemove", onMM, false);
    document.addEventListener("mouseup", onMU, false);
    window.addEventListener("resize", SD.layoutSoon, false);
    window.addEventListener("orientationchange", function () { setTimeout(SD.layout, 300); }, false);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) { pollSoon(); SD.pingAll(); } }, false);
    $("scrim").onclick = function () { SD.sheet.cancel(); };
    setInterval(function () { if (!document.hidden) SD.pingAll(); }, 20000);

    SD.readSync();
    SD.initConns();
    SD.cfg = SD.cachedCfg();
    if (SD.cfg) { msg.style.display = "none"; SD.render(); }   /* abre na hora com o que estava guardado */
    else { SD.renderNav(); showMsg("wifi", "Conectando…", "Procurando o Stream Deck no PC."); }
    SD.load();
  };
})();
