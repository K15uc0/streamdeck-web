/* Stream Deck (celular, so uso) - grade de botoes, toque, paginas, faders, liga/desliga,
   tela cheia e orientacao (trava do sistema ou giro por CSS). */
(function () {
  "use strict";

  var SD = window.SD, $ = SD.$, esc = SD.esc, el = SD.el, css = SD.css;
  var grid, dotsEl, msg;
  var keys = [];          /* blocos da pagina atual */
  var fkeys = [];         /* blocos da pasta aberta */
  var geo = null;         /* medidas da grade atual */

  /* ============================================================ blocos === */
  /* Um bloco pode ser usado na grade do celular ou na pre-visualizacao do editor do PC.
     t = { el, b, kind, empty, lit, level, tkey, ... } ; paintTile(t, w, h) desenha. */
  SD.buildTile = function (b) {
    var t = { b: b, kind: b && b.kind === "fader" ? "fader" : "button" };
    t.folder = !!(b && b.kind === "folder");
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
  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  /* ------------------------------------------------------ texto ao vivo --- */
  SD.since = {};       /* "p:b" -> epoch_s (do PC) dos liga/desliga ligados */
  SD.skew = 0;         /* relogio do PC - relogio do aparelho (ms), pelo cabecalho Date */
  SD.app = null;       /* exe em foco no PC */

  function fmtTimer(s) {
    s = Math.max(0, Math.floor(s));
    var h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = s % 60;
    return h ? h + ":" + pad2(m) + ":" + pad2(x) : pad2(m) + ":" + pad2(x);
  }
  function liveText(t, live) {
    var d = new Date();
    if (live === "clock") return pad2(d.getHours()) + ":" + pad2(d.getMinutes());
    if (live === "date") return pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1);
    if (live.indexOf("volume:") === 0) {
      var lv = levelOf(live.substring(7));
      if (!lv || lv.v == null) return "--";
      return lv.muted ? "Mudo" : Math.round(lv.v) + "%";
    }
    if (live === "obs:stream" || live === "obs:record") {
      var o = SD.obs;
      if (!o || !o.ok) return "OBS off";
      if (live === "obs:stream") return o.stream ? "AO VIVO" : "Fora do ar";
      return o.record ? "Gravando" : "Parado";
    }
    if (live === "obs:scene") return SD.obs && SD.obs.ok ? String(SD.obs.scene || "--") : "OBS off";
    if (live === "sound") {
      /* null = nada tocando: mostra o rotulo normal */
      var sp = soundOf(t);
      return sp ? fmtTimer(Math.ceil(Math.max(0, sp.dur - sp.cur))) : null;
    }
    if (live === "timer") {
      var since = t.tkey && SD.since[t.tkey];
      if (!t.lit || !since) return "00:00";
      return fmtTimer((SD.now() + SD.skew) / 1000 - since);
    }
    return "";
  }
  SD.liveText = liveText;

  /* ------------------------------------------------- OBS e sons (2.6) --- */
  SD.obs = null;       /* {ok, stream, record, scene, muted:{fonte:bool}} */
  SD.sounds = {};      /* "p:b[:f]" -> {pos, dur, at (relogio local ms), file} */

  /* som tocando por este bloco, com a posicao estimada agora (cur, s) */
  function soundOf(t) {
    var s = t && t.tkey ? SD.sounds[t.tkey] : null;
    if (!s || !(s.dur > 0)) return null;
    var cur = s.pos + (SD.now() - s.at) / 1000;
    if (cur > s.dur + 0.4) return null;
    return { cur: Math.min(cur, s.dur), dur: s.dur };
  }
  /* mostra barra de progresso? (live=sound ou acao de tocar som) */
  function showsSound(t) {
    var b = t.b;
    return !!(b && (b.live === "sound" || (b.action && b.action.type === "sound")));
  }
  /* acende pelo OBS? */
  function obsLit(b) {
    var l = b && b.lit ? String(b.lit) : "", o = SD.obs;
    if (!l || !o || !o.ok) return false;
    if (l === "obs:stream") return !!o.stream;
    if (l === "obs:record") return !!o.record;
    if (l.indexOf("obs:scene=") === 0) return String(o.scene || "") === l.substring(10);
    if (l.indexOf("obs:mute=") === 0) return !!(o.muted && o.muted[l.substring(9)]);
    return false;
  }

  /* aparencia efetiva: liga/desliga aceso com "on" usa os campos de "on" por cima */
  function hasOn(o) { return !!(o && typeof o === "object" && (o.label || o.icon || o.color || o.textColor || o.image)); }
  function look(t) {
    var b = t.b || {}, lit = t.lit || t.olit, on = lit && (b.toggle || b.lit) && hasOn(b.on) ? b.on : null;
    var a = { label: b.label, icon: b.icon, color: b.color, textColor: b.textColor, image: b.image, invert: false, on: !!on };
    if (on) {
      if (on.label) a.label = on.label;
      if (on.icon) { a.icon = on.icon; if (!on.image) a.image = ""; }
      if (on.color) a.color = on.color;
      if (on.textColor) a.textColor = on.textColor;
      if (on.image) a.image = on.image;
    } else if (lit) a.invert = true;
    return a;
  }

  SD.paintTile = function (t, w, h) {
    var e = t.el, b = t.b || {}, m = Math.min(w, h), r = Math.round(Math.min(m, 110) * 0.22), st = e.style;
    var isDown = SD.hasClass(e, "down");
    st.width = px(w); st.height = px(h);
    st.borderRadius = px(r);
    t.w = w; t.h = h;
    if (t.kind === "fader") return paintFader(t, w, h, m, r);
    t.fl.style.borderRadius = px(r);
    var ic = t.ic, lb = t.lb;
    ic.style.cssText = ""; lb.style.cssText = ""; lb.className = "lb";
    if (t.empty) {
      e.className = "key empty";
      st.backgroundColor = ""; st.backgroundImage = "";
      ic.innerHTML = "";
      lb.innerHTML = "";
      return;
    }
    var a = look(t);
    var color = SD.validColor(a.color) ? a.color : SD.lightTheme ? "#ffffff" : SD.DEFAULT_TILE;
    var tc = SD.validColor(a.textColor) ? a.textColor : "";
    var img = a.image ? String(a.image) : "";
    var fg, bg;
    if (a.invert) { bg = "#fff"; fg = tc || (SD.isLight(color) ? "#1c1c1e" : color); }
    else { bg = color; fg = tc || (img ? "#fff" : SD.isLight(color) ? "rgba(0,0,0,0.78)" : "#fff"); }
    var live = b.live ? String(b.live) : "";
    var lt = live ? liveText(t, live) : null;
    if (lt == null) live = "";
    var label = live ? lt : SD.trim(a.label);
    var icon = img ? "" : SD.hasIcon(a.icon) ? a.icon : t.folder ? "folder" : "";
    e.className = "key" + (t.lit || t.olit ? " lit" : "") + (a.on ? " onlook" : "") + (b.toggle ? " tg" : "") +
      (t.folder ? " folder" : "") + (img ? " img" + (label ? "" : " nolb") : "") + (live ? " live" : "") +
      (!img && SD.isLight(bg) ? " light" : "") + (m >= 140 ? " big" : "") +
      (t.conf ? " confirm" : "") + (t.holding ? " holding" + (t.holding === 2 ? " hgo" : "") : "") + (isDown ? " down" : "");
    st.backgroundColor = bg;
    paintExtras(t, w, h, m, r);
    var bgi = img ? 'url("' + SD.imgUrl(img) + '")' : "";
    if (t.bgi !== bgi) { st.backgroundImage = bgi; t.bgi = bgi; }
    lb.style.color = fg;
    var pad = Math.max(7, Math.round(Math.min(m, 140) * 0.12));
    lb.innerHTML = esc(label);
    if (img) {
      /* imagem cobre o bloco; rotulo embaixo sobre um degrade */
      ic.innerHTML = "";
      var fi = Math.max(10, Math.min(live ? 34 : 17, Math.round(m * (live ? 0.2 : 0.118))));
      lb.className = "lb bl";
      lb.style.left = px(pad); lb.style.right = px(pad * 0.7); lb.style.bottom = px(pad * 0.85);
      lb.style.fontSize = px(fi);
    } else if (icon && (!label || m < 66)) {
      /* pequeno ou sem rotulo: so o icone, centralizado */
      var cs = Math.round(Math.min(m, 160) * 0.44);
      ic.innerHTML = SD.iconHtml(icon, cs, fg);
      ic.style.left = px((w - cs) / 2); ic.style.top = px((h - cs) / 2);
      lb.style.display = "none";
    } else if (icon) {
      /* como no app Atalhos: icone em cima a esquerda, rotulo embaixo a esquerda */
      var is = Math.max(16, Math.round(Math.min(m, 160) * 0.26));
      ic.innerHTML = SD.iconHtml(icon, is, fg);
      ic.style.left = px(pad); ic.style.top = px(pad);
      var fs = live ? Math.max(12, Math.min(40, Math.round(m * 0.22))) : Math.max(10, Math.min(19, Math.round(m * 0.118)));
      lb.className = "lb bl";
      lb.style.left = px(pad); lb.style.right = px(pad * 0.7); lb.style.bottom = px(pad * 0.85);
      lb.style.fontSize = px(fs);
    } else {
      /* so texto: centralizado, maior */
      ic.innerHTML = "";
      var f2 = live ? Math.max(12, Math.min(56, Math.floor(Math.min(m * 0.3, (w - pad * 1.4) / (Math.max(3, label.length) * 0.62)))))
                    : Math.max(11, Math.min(24, Math.round(m * 0.16)));
      lb.className = "lb mid";
      lb.style.left = px(pad * 0.6); lb.style.right = px(pad * 0.6);
      lb.style.fontSize = px(f2);
      lb.style.top = "50%";
    }
  };

  /* camadas do 2.6: progresso de segurar, confirmacao e barra do som (criadas sob demanda) */
  function paintExtras(t, w, h, m, r) {
    if (t.holding && !t.hp) t.hp = el("div", "hp", "<i></i>", t.el);
    if (t.hp) t.hp.style.borderRadius = px(r);
    if (t.conf) {
      if (!t.cf) {
        t.cf = el("div", "cf", null, t.el);
        t.cf.innerHTML = '<svg class="ring" viewBox="0 0 36 36"><circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="3"/>' +
          '<circle class="arc" cx="18" cy="18" r="15" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-dasharray="94.25" transform="rotate(-90 18 18)"/></svg>' +
          '<span class="ct"></span>';
      }
      var rs = Math.max(16, Math.min(40, Math.round(m * 0.26))), small = m < 92 || h < 80;
      var sv = t.cf.firstChild, ct = t.cf.lastChild;
      sv.setAttribute("width", rs); sv.setAttribute("height", rs);
      sv.style.left = px((w - rs) / 2);
      sv.style.top = px(small ? (h - rs) / 2 - Math.round(m * 0.08) : Math.max(6, h / 2 - rs - 2));
      ct.innerHTML = small ? "Confirmar?" : "Toque de novo para confirmar";
      ct.style.fontSize = px(Math.max(10, Math.min(15, Math.round(m * (small ? 0.14 : 0.105)))));
      ct.style.top = small ? px((h + rs) / 2 - Math.round(m * 0.04)) : px(h / 2 + 4);
      t.cf.style.borderRadius = px(r);
    } else if (t.cf) { t.el.removeChild(t.cf); t.cf = null; }
    paintSound(t);
  }
  /* barra do som no rodape do bloco (so o preenchimento muda a cada passo) */
  function paintSound(t) {
    var sp = showsSound(t) ? soundOf(t) : null;
    if (!sp) { if (t.pb) { t.el.removeChild(t.pb); t.pb = null; } return; }
    if (!t.pb) { t.pb = el("div", "sbar", "<i></i>", t.el); t.pbw = -1; }
    var f = Math.max(0, Math.min(1, sp.cur / sp.dur)), wpx = Math.round((t.w || 0) * f);
    if (wpx !== t.pbw) { t.pb.firstChild.style.width = px(wpx); t.pbw = wpx; }
  }

  /* fader no estilo da Central de Controle: preenche de baixo para cima.
     A parte clara repete icone e texto em cor escura (recortada pelo preenchimento).
     Escala 0..max (efeitos ate 200%). */
  function paintFader(t, w, h, m, r) {
    var b = t.b || {}, lv = t.level, known = !!(lv && lv.v != null);
    var max = lv && lv.max > 0 ? lv.max : 100;
    var v = known ? Math.max(0, Math.min(max, lv.v)) : 0, muted = !!(lv && lv.muted);
    var color = SD.validColor(b.color) ? b.color : "#fff";
    t.el.className = "key fader" + (muted ? " muted" : "") + (h > w * 1.6 ? " tall" : "");
    t.el.style.background = "";
    var fillH = Math.round(h * v / max);
    t.fill.style.height = px(fillH);
    t.inner.style.width = px(w); t.inner.style.height = px(h);
    var target = b.target || "master";
    var icon = muted ? (target === "mic" ? "micoff" : "mute") : (SD.hasIcon(b.icon) ? b.icon : FADER_ICON[target] || "sound");
    var is = Math.round(Math.min(m, 140) * (m < 80 ? 0.34 : 0.27));
    var label = SD.trim(b.label) || FADER_NAME[target] || "";
    var val = known ? (muted ? "Mudo" : Math.round(v) + "%") : "--";
    var fs = Math.max(10, Math.min(16, Math.round(m * 0.105)));
    var vs = Math.max(12, Math.min(30, Math.round(m * 0.17)));
    var small = m < 80;
    /* tema claro: trilho cinza claro, texto escuro nas duas camadas */
    var lt = !!SD.lightTheme, top = lt ? "rgba(0,0,0,0.78)" : "#fff";
    var pairs = [[t.ic, t.lb, t.val, top, lt ? "rgba(60,60,67,0.6)" : "rgba(235,235,245,0.6)"],
                 [t.ic2, t.lb2, t.val2, muted || SD.isLight(color) ? "#1c1c1e" : color, "rgba(0,0,0,0.5)"]];
    var key = icon + "|" + is + "|" + color + "|" + muted + "|" + lt;
    var top0 = Math.round(Math.min(m, 140) * 0.1);
    for (var i = 0; i < 2; i++) {
      var p = pairs[i];
      if (p[0].getAttribute("data-k") !== key) {
        p[0].innerHTML = SD.iconHtml(icon, is, i === 0 ? top : pairs[1][3]);
        p[0].setAttribute("data-k", key);
      }
      p[0].style.left = px((w - is) / 2); p[0].style.bottom = px(Math.round(Math.min(m, 140) * 0.12)); p[0].style.top = "auto";
      p[1].innerHTML = small ? "" : esc(label);
      p[1].style.fontSize = px(fs); p[1].style.top = px(top0); p[1].style.color = p[4];
      p[2].innerHTML = esc(val);
      p[2].style.fontSize = px(vs); p[2].style.color = i === 0 ? top : p[3];
      p[2].style.top = px(small ? top0 : top0 + fs + 3);
    }
  }


  /* ========================================================= estado ===== */
  function curPage() { return SD.cfg && SD.cfg.pages[SD.page]; }
  SD.curPage = curPage;

  /* {v, muted, max} ; max = 100 (efeitos: o que o PC mandar, ate 200) */
  function levelOf(target) {
    var l = SD.levels;
    if (!l) return null;
    var x = l[target];
    if (x == null) return null;
    if (typeof x === "object") return { v: x.v, muted: !!x.muted, max: x.max > 0 ? x.max : 100 };
    return { v: x, muted: !!l[target + "Mute"], max: 100 };   /* formato antigo (1.x) */
  }
  SD.levelOf = levelOf;

  /* ============================================ ajustes deste aparelho === */
  /* sd_prefs = { orientation: "auto"|"portrait"|"landscape", autoFullscreen: bool,
                  vibrate: bool (padrao true), autoPage: bool (padrao true),
                  theme: "auto"|"escuro"|"claro" } */
  var PREFS_KEY = "sd_prefs";
  SD.prefs = { orientation: "auto", autoFullscreen: false, vibrate: true, autoPage: true, theme: "auto" };
  function loadPrefs() {
    try {
      var p = JSON.parse(window.localStorage.getItem(PREFS_KEY));
      if (p && typeof p === "object") {
        if (p.orientation === "portrait" || p.orientation === "landscape") SD.prefs.orientation = p.orientation;
        SD.prefs.autoFullscreen = !!p.autoFullscreen;
        if (typeof p.vibrate === "boolean") SD.prefs.vibrate = p.vibrate;
        if (typeof p.autoPage === "boolean") SD.prefs.autoPage = p.autoPage;
        if (p.theme === "escuro" || p.theme === "claro") SD.prefs.theme = p.theme;
      }
    } catch (e) {}
  }
  SD.setPref = function (name, value) {
    SD.prefs[name] = value;
    try { window.localStorage.setItem(PREFS_KEY, JSON.stringify(SD.prefs)); } catch (e) {}
    if (name === "orientation") { lockOrientation(); SD.layout(); }
    if (name === "theme") SD.applyTheme();
  };

  /* ============================================================ tema === */
  /* sd_prefs.theme = "auto" | "escuro" | "claro"; auto segue o aparelho.
     Tema claro = classe "theme-light" no <html> (sobrescritas no CSS). */
  SD.lightTheme = false;
  var themeMq = null;
  function systemLight() {
    try { return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches); } catch (e) { return false; }
  }
  SD.applyTheme = function () {
    var p = SD.prefs.theme, light = p === "claro" ? true : p === "escuro" ? false : systemLight();
    var root = document.documentElement, cls = root.className.replace(/(^|\s)theme-light(\s|$)/g, " ").replace(/^\s+|\s+$/g, "");
    root.className = light ? (cls ? cls + " " : "") + "theme-light" : cls;
    var tm = document.querySelector ? document.querySelector('meta[name="theme-color"]') : null;
    if (tm) tm.setAttribute("content", light ? "#f2f2f7" : "#000000");
    var sb = document.querySelector ? document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]') : null;
    if (sb) sb.setAttribute("content", light ? "default" : "black-translucent");
    if (light === SD.lightTheme) return;
    SD.lightTheme = light;
    SD.TINT = light ? "#007aff" : "#0a84ff";
    if (SD.cfg) SD.render(); else SD.layout();
    if (SD.sheet && SD.sheet.isOpen()) SD.sheet.refresh();
  };
  function watchTheme() {
    try {
      if (window.matchMedia) {
        themeMq = window.matchMedia("(prefers-color-scheme: light)");
        if (themeMq.addEventListener) themeMq.addEventListener("change", SD.applyTheme, false);
        else if (themeMq.addListener) themeMq.addListener(SD.applyTheme);
      }
    } catch (e) {}
    /* navegadores antigos sem aviso: confere ao voltar para o app */
    document.addEventListener("visibilitychange", function () { if (!document.hidden) SD.applyTheme(); }, false);
    SD.applyTheme();
  }

  /* ======================================================= tela cheia === */
  /* instalado na tela de inicio (PWA): ja ocupa a tela toda */
  SD.isStandalone = function () {
    try {
      if (window.navigator.standalone) return true;
      /* no Chrome, display-mode: fullscreen tambem casa com a tela cheia do navegador */
      if (SD.isFullscreen()) return false;
      if (window.matchMedia && (window.matchMedia("(display-mode: fullscreen)").matches ||
          window.matchMedia("(display-mode: standalone)").matches)) return true;
    } catch (e) {}
    return false;
  };
  /* botao de tela cheia so onde a API existe (nao existe no Safari do iPhone) */
  SD.fsAvailable = function () { return SD.canFullscreen() && !SD.isStandalone(); };

  var fsPendingUntil = 0;
  SD.setFullscreen = function (on) {
    var d = document.documentElement, r = null;
    if (on) {
      if (SD.isFullscreen() || SD.now() < fsPendingUntil) return;
      fsPendingUntil = SD.now() + 1500;
      try {
        if (d.requestFullscreen) r = d.requestFullscreen({ navigationUI: "hide" });
        else if (d.webkitRequestFullscreen) r = d.webkitRequestFullscreen();
      } catch (e) { fsPendingUntil = 0; }
    } else {
      if (!SD.isFullscreen()) return;
      fsPendingUntil = 0;
      try {
        if (document.exitFullscreen) r = document.exitFullscreen();
        else if (document.webkitExitFullscreen) r = document.webkitExitFullscreen();
      } catch (e2) {}
    }
    if (r && r["catch"]) r["catch"](function () { fsPendingUntil = 0; });
  };
  SD.toggleFullscreen = function () { SD.setFullscreen(!SD.isFullscreen()); };

  function onFsChange() {
    fsPendingUntil = 0;
    lockOrientation();
    SD.layoutSoon();
    if (SD.sheet.isOpen()) SD.sheet.refresh();
  }

  /* "Abrir sempre em tela cheia": o navegador so deixa entrar em tela cheia num toque.
     Usa o fim do primeiro toque (touchend/mouseup), DEPOIS de tratar o botao: o toque nao se perde. */
  var autoFsDone = false;
  function maybeAutoFs() {
    if (autoFsDone) return;
    autoFsDone = true;
    if (SD.prefs.autoFullscreen && SD.fsAvailable() && !SD.isFullscreen()) SD.setFullscreen(true);
  }

  /* trava a orientacao pelo sistema quando der (tela cheia ou app instalado) */
  function lockOrientation() {
    var o = window.screen && window.screen.orientation, want = SD.prefs.orientation;
    if (!o) return;
    try {
      if (want === "auto") { if (o.unlock) o.unlock(); return; }
      if (!o.lock || !(SD.isFullscreen() || SD.isStandalone())) return;
      var r = o.lock(want);
      if (r && r["catch"]) r["catch"](function () {});
    } catch (e) {}
  }

  /* ===================================================== moldura (giro) === */
  /* Quando a orientacao escolhida difere da tela real (sem trava do sistema), o #app
     e girado 90 graus por CSS. Toda coordenada de toque passa por SD.toLocal. */
  var frame = { w: 0, h: 0, rot: false, portrait: false };
  SD.frame = frame;

  function applyFrame() {
    var W = window.innerWidth, H = window.innerHeight, app = $("app");
    var actual = W >= H ? "landscape" : "portrait", want = SD.prefs.orientation;
    var rot = want !== "auto" && want !== actual && W !== H;
    if (rot) {
      frame.w = H; frame.h = W;
      app.style.width = px(H); app.style.height = px(W);
      css(app, "transformOrigin", "0 0");
      css(app, "transform", "translate(" + W + "px,0) rotate(90deg)");
    } else {
      frame.w = W; frame.h = H;
      app.style.width = ""; app.style.height = "";
      css(app, "transform", "");
    }
    frame.rot = rot;
    frame.portrait = frame.w < frame.h;
    SD.setClass(document.body, "rot", rot);
  }
  /* tela (clientX/Y) -> coordenadas do #app. Giro: tela = (W - y, x) */
  SD.toLocal = function (x, y) { return frame.rot ? { x: y, y: frame.h - x } : { x: x, y: y }; };

  /* margens seguras (entalhe / barra de gestos) lidas do CSS, ja no referencial do #app */
  function safe() {
    var p = $("safe"), s = window.getComputedStyle ? getComputedStyle(p) : null;
    function v(x) { var n = s ? parseFloat(s[x]) : 0; return isNaN(n) ? 0 : n; }
    var a = { t: v("paddingTop"), r: v("paddingRight"), b: v("paddingBottom"), l: v("paddingLeft") };
    return frame.rot ? { t: a.r, r: a.b, b: a.l, l: a.t } : a;
  }

  /* grade da orientacao atual: columns/rows = horizontal; portrait = vertical
     (sem portrait, a vertical e a horizontal transposta quando columns > rows) */
  function okDim(n, max) { n = parseInt(n, 10); return n >= 1 && n <= max ? n : 0; }
  SD.gridDims = function (cfg, portrait) {
    var c = okDim(cfg.columns, 10) || 5, r = okDim(cfg.rows, 8) || 3, p = cfg.portrait;
    if (!portrait) return { cols: c, rows: r };
    if (p && okDim(p.columns, 10) && okDim(p.rows, 8)) return { cols: okDim(p.columns, 10), rows: okDim(p.rows, 8) };
    return c > r ? { cols: r, rows: c } : { cols: c, rows: r };
  };
  function dims() { return SD.gridDims(SD.cfg, frame.portrait); }

  /* blocos na tela (pagina e pasta aberta) */
  function visible() { return folder ? keys.concat(fkeys) : keys; }

  /* precisa dos volumes? (fader ou texto ao vivo de volume na tela) */
  function needLevels() {
    var v = visible();
    for (var i = 0; i < v.length; i++) {
      var b = v[i].b;
      if (!b || v[i].empty) continue;
      if (v[i].kind === "fader" || (b.live && String(b.live).indexOf("volume:") === 0)) return true;
    }
    return false;
  }

  /* vibrar (se ligado nos ajustes deste aparelho) */
  function buzz(p) {
    if (!SD.prefs.vibrate) return;
    try { if (navigator.vibrate) navigator.vibrate(p); } catch (e) {}
  }

  /* ========================================================== barra ===== */
  SD.renderNav = function () {
    var L = $("nav-l"), T = $("nav-t"), R = $("nav-r");
    L.innerHTML = ""; R.innerHTML = "";
    var pg = curPage();
    T.innerHTML = esc(pg ? (pg.name || "Página " + (SD.page + 1)) : (SD.cfg && SD.cfg.title) || "Stream Deck");
    var aj = el("span", "nb ib", SD.svg("cog", 24, SD.TINT), L);
    aj.setAttribute("aria-label", "Ajustes");
    aj.onclick = function () { SD.openSettings(); };
    if (SD.updAvail()) el("i", "nbadge", null, aj);
    if (SD.conns.length > 1) {
      for (var i = 0; i < SD.conns.length; i++) (function (idx) {
        var c = SD.conns[idx], isHere = c.host === SD.here;
        var st = isHere ? (SD.online ? "up" : "down") : (SD.alive[c.host] === true ? "up" : SD.alive[c.host] === false ? "down" : "");
        var p = el("span", "pill" + (isHere ? " on" : ""), '<i class="' + st + '"></i>' + esc(c.name || c.host), L);
        p.onclick = function () { if (!isHere) SD.switchTo(idx); };
      })(i);
    } else {
      el("i", "cdot" + (SD.online ? "" : " off"), null, L);
    }
    if (SD.fsAvailable()) {
      var fs = SD.isFullscreen();
      var fb = el("span", "nb ib", SD.svg(fs ? "shrink" : "expand", 22, SD.TINT), R);
      fb.setAttribute("aria-label", fs ? "Sair da tela cheia" : "Tela cheia");
      fb.onclick = function () { SD.toggleFullscreen(); };
    }
    /* titulo centralizado sem encostar nos lados */
    var W = frame.w || window.innerWidth, side = Math.max(L.offsetWidth, R.offsetWidth) + 12;
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
    renderDots();
    SD.layout();
  };

  /* monta os blocos de uma lista de botoes numa grade cols x rows (regra SD.flow);
     posicoes que nenhum botao cobre viram blocos vazios. fi = indice da pasta (ou null). */
  function buildTiles(box, buttons, d, p, fi) {
    var out = [], used = [], i, j, pl = SD.flow(buttons || [], d.cols, d.rows);
    for (i = 0; i < d.cols * d.rows; i++) used.push(false);
    function add(b, bi, x, y, w, h) {
      var t = SD.buildTile(b);
      if (fi != null && t.folder) { t.folder = false; }   /* pasta dentro de pasta nao vale */
      t.p = p; t.bi = bi; t.f = fi;
      t.idx = fi != null ? fi : bi;
      t.tkey = bi < 0 ? "" : fi != null ? p + ":" + fi + ":" + bi : p + ":" + bi;
      if (fi != null) { t.bi = fi; t.f = bi; }
      t.lit = !!(b && b.toggle && t.tkey && SD.toggles[t.tkey]);
      t.olit = obsLit(b);
      if (t.kind === "fader") t.level = levelOf(b.target || "master");
      t.gx = x; t.gy = y; t.gw = w; t.gh = h;
      var cell = el("div", "cell" + (t.empty ? " empty-cell" : ""), null, box);
      cell.appendChild(t.el);
      cell.setAttribute("data-i", out.length);
      cell.sdTile = t;
      t.cell = cell;
      out.push(t);
    }
    for (i = 0; i < pl.length; i++) {
      var q = pl[i];
      for (var yy = q.y; yy < q.y + q.h; yy++) for (var xx = q.x; xx < q.x + q.w; xx++) used[yy * d.cols + xx] = true;
      add(buttons[q.i], q.i, q.x, q.y, q.w, q.h);
    }
    for (j = 0; j < used.length; j++) if (!used[j]) add(null, -1, j % d.cols, Math.floor(j / d.cols), 1, 1);
    return out;
  }

  /* recria os blocos quando muda a pagina, o config ou a grade (orientacao) */
  var built = null;
  function renderGrid(d) {
    var pg = curPage();
    grid.innerHTML = "";
    keys = buildTiles(grid, pg.buttons, d, SD.page, null);
    built = { cfg: SD.cfg, page: SD.page, cols: d.cols, rows: d.rows };
    if (folder) reopenFolder(d);
    setupLive();
  }
  SD.getKeys = function () { return keys; };

  function renderDots() {
    var n = SD.cfg.pages.length, h = "";
    if (n > 1) for (var j = 0; j < n; j++) h += '<span data-p="' + j + '"' + (j === SD.page ? ' class="on"' : "") + "><i></i></span>";
    dotsEl.innerHTML = h;
    var sp = dotsEl.getElementsByTagName("span");
    for (var k = 0; k < sp.length; k++) sp[k].onclick = function () { SD.goPage(parseInt(this.getAttribute("data-p"), 10)); };
  }

  /* posiciona blocos (celulas somadas com os vaos entre elas) */
  function placeTiles(list) {
    var g = geo;
    for (var i = 0; i < list.length; i++) {
      var k = list[i];
      var rc = g.rect(k.gx, k.gy, k.gw, k.gh), w = rc.w, h = rc.h;
      k.x = rc.x; k.y = rc.y;
      var st = k.cell.style;
      st.left = px(k.x); st.top = px(k.y); st.width = px(w); st.height = px(h);
      SD.paintTile(k, w, h);
    }
  }

  SD.layout = function () {
    applyFrame();
    var sa = safe(), nav = $("nav");
    nav.style.paddingTop = px(sa.t); nav.style.paddingLeft = px(sa.l); nav.style.paddingRight = px(sa.r);
    fbar.style.paddingTop = px(sa.t); fbar.style.paddingLeft = px(sa.l); fbar.style.paddingRight = px(sa.r);
    if (!SD.cfg) { SD.renderNav(); return; }
    var d = dims();
    if (!built || built.cfg !== SD.cfg || built.page !== SD.page || built.cols !== d.cols || built.rows !== d.rows) renderGrid(d);
    var area = SD.deviceArea(sa);
    geo = SD.geometry(frame.w, frame.h, d.cols, d.rows, area);
    placeTiles(keys);
    if (folder) placeTiles(fkeys);
    dotsEl.style.bottom = px(area.dotsBottom);
    SD.renderNav();
  };
  var layoutT = null;
  SD.layoutSoon = function () { clearTimeout(layoutT); layoutT = setTimeout(SD.layout, 60); };

  /* ========================================================= paginas ===== */
  SD.goPage = function (to, dir) {
    if (!SD.cfg || !SD.cfg.pages[to] || to === SD.page) return;
    if (folder) closeFolder(true);
    if (dir == null) dir = to > SD.page ? 1 : -1;
    SD.page = to;
    SD.render();
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

  /* =========================================================== pasta ===== */
  /* abre por cima da pagina (zoom a partir do bloco, como no iOS), mesma grade,
     com barra "Voltar". Toques dentro: /api/press?p&b&f ; liga/desliga "p:b:f". */
  var folder = null;      /* { bi, b } */
  var fwrap, fbar, fgrid, ftitle, histPushed = false;

  function folderBtn(bi) {
    var pg = curPage(), b = pg && pg.buttons && pg.buttons[bi];
    return b && b.kind === "folder" ? b : null;
  }

  function fillFolder(d) {
    fgrid.innerHTML = "";
    var b = folder.b;
    ftitle.innerHTML = esc(SD.trim(b.label) || "Pasta");
    fkeys = buildTiles(fgrid, b.buttons || [], d, SD.page, folder.bi);
  }

  function openFolder(t) {
    if (folder) return;
    folder = { bi: t.bi, b: t.b };
    fillFolder(dims());
    if (geo) placeTiles(fkeys);
    /* zoom a partir do centro do bloco da pasta */
    var cx = (t.x || 0) + (t.w || 0) / 2, cy = (t.y || 0) + (t.h || 0) / 2;
    css(fwrap, "transformOrigin", Math.round(cx) + "px " + Math.round(cy) + "px");
    css(fwrap, "transition", "none");
    css(fwrap, "transform", "scale(0.25)");
    fwrap.style.opacity = "0";
    fwrap.style.display = "block";
    fwrap.offsetWidth;   /* aplica o estado inicial antes da transicao */
    css(fwrap, "transition", "");
    css(fwrap, "transform", "scale(1)");
    fwrap.style.opacity = "1";
    SD.setClass(document.body, "fopen", true);
    try { if (window.history && history.pushState) { history.pushState({ sdFolder: 1 }, ""); histPushed = true; } } catch (e) {}
    setupLive();
    pollSoon();
  }

  /* fromPop = veio do botao voltar do aparelho (historico ja voltou) */
  function closeFolder(quick, fromPop) {
    if (!folder) return;
    var t = null;
    for (var i = 0; i < keys.length; i++) if (keys[i].bi === folder.bi && keys[i].f == null) t = keys[i];
    folder = null;
    if (histPushed && !fromPop) { histPushed = false; try { history.back(); } catch (e) {} }
    histPushed = false;
    SD.setClass(document.body, "fopen", false);
    var done = function () { if (!folder) { fwrap.style.display = "none"; fgrid.innerHTML = ""; fkeys = []; css(fgrid, "transform", ""); } };
    if (quick) { done(); setupLive(); return; }
    if (t) css(fwrap, "transformOrigin", Math.round(t.x + t.w / 2) + "px " + Math.round(t.y + t.h / 2) + "px");
    css(fwrap, "transition", "");
    css(fwrap, "transform", "scale(0.25)");
    fwrap.style.opacity = "0";
    setTimeout(done, 280);
    setupLive();
  }
  SD.closeFolder = function () { closeFolder(false); };

  /* config ou grade mudou com a pasta aberta: remonta (ou fecha se a pasta sumiu) */
  function reopenFolder(d) {
    var b = folderBtn(folder.bi);
    if (!b) { closeFolder(true); return; }
    folder.b = b;
    fillFolder(d);
  }

  function onPop() { if (folder) { histPushed = false; closeFolder(false, true); } }

  /* ====================================================== ao vivo ===== */
  /* relogio/data: a cada 15 s alinhados; cronometro: a cada segundo, so se estiver na tela */
  var liveT = null, secT = null;
  function liveKinds() {
    var v = visible(), k = { clock: false, timer: false };
    for (var i = 0; i < v.length; i++) {
      var l = v[i].b && v[i].b.live;
      if (l === "clock" || l === "date") k.clock = true;
      if (l === "timer") k.timer = true;
    }
    return k;
  }
  function repaintLive(test) {
    var v = visible();
    for (var i = 0; i < v.length; i++) {
      var l = v[i].b && v[i].b.live;
      if (l && v[i].w && test(String(l))) SD.paintTile(v[i], v[i].w, v[i].h);
    }
  }
  function setupLive() {
    clearTimeout(liveT); clearInterval(secT); secT = null;
    var k = liveKinds();
    if (k.clock) {
      liveT = setTimeout(function () {
        repaintLive(function (l) { return l === "clock" || l === "date"; });
        setupLive();
      }, 15000 - (SD.now() % 15000) + 50);
    }
    if (k.timer) secT = setInterval(function () {
      if (!document.hidden) repaintLive(function (l) { return l === "timer"; });
    }, 1000);
  }

  /* ====================================================== apertar ===== */
  var REPEAT = { volumeup: 1, volumedown: 1, left: 1, right: 1, up: 1, down: 1, pageup: 1, pagedown: 1 };
  var pending = 0;

  /* segurar repete (so volume e setas: repetir outros atalhos seria perigoso) */
  function canRepeat(k) {
    var a = k.b && k.b.action;
    return !!(!k.folder && a && a.type === "hotkey" && a.keys && a.keys.length === 1 && REPEAT[String(a.keys[0]).toLowerCase()]);
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

  SD.applyToggles = function (t, since) {
    if (t) SD.toggles = t;
    if (since) SD.since = since;
    var v = visible();
    for (var i = 0; i < v.length; i++) {
      var k = v[i];
      if (k.kind === "button" && k.b && k.b.toggle && k.tkey) {
        var on = !!SD.toggles[k.tkey];
        if (k.lit !== on) setLit(k, on);
        else if (since && k.b.live === "timer" && k.w) SD.paintTile(k, k.w, k.h);
      }
    }
  };

  /* acao de um gesto: tap = action, hold/double = campos do 2.6 */
  function gestureAction(b, g) {
    var a = b && (g === "tap" ? b.action : b[g]);
    return a && typeof a === "object" && a.type && a.type !== "none" ? a : null;
  }
  SD.gestureAction = gestureAction;

  /* g = "tap" (padrao) | "hold" | "double". quiet = a resposta visual ja foi dada */
  function press(k, repeating, g, quiet) {
    g = g || "tap";
    var b = k.b, a = b && (g === "tap" ? b.action : gestureAction(b, g));
    if (k.folder) { if (g === "tap") { buzz(10); openFolder(k); } return; }
    var toggles = g === "tap" && b && b.toggle;
    /* liga/desliga sem acao (ex.: ON AIR) ainda alterna o estado no PC */
    if (!b || ((!a || a.type === "none") && !toggles)) return;
    if (a && a.type === "page") { buzz(10); return SD.goPage(parseInt(a.to, 10) || 0); }
    if (repeating && pending > 0) return;   /* nao empilha pedidos se a rede estiver lenta */
    if (!quiet) { flash(k, true); buzz(10); }   /* resposta visual na hora */
    var p = k.p, tkey = k.tkey, was = !!SD.toggles[tkey];
    if (toggles) {
      SD.toggles[tkey] = !was;
      if (!was) SD.since[tkey] = Math.floor((SD.now() + SD.skew) / 1000); else delete SD.since[tkey];
      setLit(k, !was);
    }
    pending++;
    var url = "/api/press?p=" + p + "&b=" + k.bi + (k.f != null ? "&f=" + k.f : "") + (g !== "tap" ? "&g=" + g : "");
    SD.req("GET", url, null, function (ok, data, status) {
      pending--;
      if (ok) {
        if (data && data.toggles) { if (p === SD.page) SD.applyToggles(data.toggles); else SD.toggles = data.toggles; }
        /* som, OBS: o estado muda no PC; busca logo para acender/mostrar o progresso */
        if (a && (a.type === "sound" || a.type === "stopsound" || String(a.type).indexOf("obs_") === 0)) pollSoon();
        return;
      }
      if (toggles) { SD.toggles[tkey] = was; if (p === SD.page) setLit(k, was); }
      flash(k, false);
      buzz([30, 40, 30]);
      SD.toast(SD.errText(data, status), true);
    });
  }

  /* ---------------------------------------------- toque duplo e confirmar --- */
  var DOUBLE_MS = 300, HOLD_MS = 500, CONFIRM_MS = 3000;
  var dbl = null;      /* { k, t } toque simples esperando a janela do duplo */
  var conf = null;     /* { k, g, t } bloco pedindo confirmacao */

  function repaint(k) { if (k.w) SD.paintTile(k, k.w, k.h); }

  function endConfirm() {
    if (!conf) return;
    var k = conf.k;
    clearTimeout(conf.t);
    conf = null;
    k.conf = false;
    repaint(k);
  }
  function askConfirm(k, g) {
    endConfirm();
    buzz([12, 50, 12]);
    k.conf = g;
    conf = { k: k, g: g, t: setTimeout(endConfirm, CONFIRM_MS) };
    repaint(k);
  }

  /* dispara um gesto, passando pela confirmacao quando o botao pede */
  function fire(k, g, quiet) {
    if (k.b && k.b.confirm) { askConfirm(k, g); return; }
    press(k, false, g, quiet);
  }

  /* toque simples terminado (sem segurar nem arrastar) */
  function tap(k) {
    if (k.folder || k.empty) { press(k, false, "tap"); return; }
    /* bloco esperando confirmacao: este toque confirma o gesto pendente */
    if (conf && conf.k === k) {
      var g = conf.g;
      endConfirm();
      press(k, false, g);
      return;
    }
    if (conf) endConfirm();
    if (gestureAction(k.b, "double")) {
      if (dbl && dbl.k === k) {
        clearTimeout(dbl.t); dbl = null;
        fire(k, "double");
        return;
      }
      flushDouble();
      flash(k, true); buzz(10);   /* resposta na hora; o envio espera a janela */
      dbl = { k: k, t: setTimeout(function () { var d = dbl; dbl = null; if (d) fire(d.k, "tap", true); }, DOUBLE_MS) };
      return;
    }
    flushDouble();
    fire(k, "tap");
  }
  /* outro bloco tocado durante a janela: o toque simples anterior sai na hora */
  function flushDouble() {
    if (!dbl) return;
    var d = dbl; dbl = null; clearTimeout(d.t);
    fire(d.k, "tap", true);
  }

  /* ========================================================= faders ===== */
  var sending = {};   /* alvo -> {busy, next} */
  var holdUntil = {}; /* alvo -> ate quando ignorar o PC (nao brigar com o dedo) */

  /* redesenha faders e textos ao vivo de volume */
  function paintFaders(target) {
    var v = visible();
    for (var i = 0; i < v.length; i++) {
      var k = v[i];
      if (k.kind === "fader" && (!target || (k.b.target || "master") === target)) {
        k.level = levelOf(k.b.target || "master");
        if (k.w) SD.paintTile(k, k.w, k.h);
      } else if (k.b && k.b.live && String(k.b.live).indexOf("volume:") === 0 && k.w &&
                 (!target || String(k.b.live) === "volume:" + target)) {
        SD.paintTile(k, k.w, k.h);
      }
    }
  }

  function setLocalLevel(target, v, muted) {
    var cur = levelOf(target) || { v: 0, muted: false, max: target === "effects" ? 200 : 100 };
    SD.levels[target] = { v: v == null ? cur.v : v, muted: muted == null ? cur.muted : muted, max: cur.max };
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
    buzz(8);
    SD.req("GET", "/api/volume?c=" + encodeURIComponent(target) + "&mute=toggle", null, function (ok, data, status) {
      if (ok && data && data.levels) { holdUntil[target] = 0; SD.applyLevels(data.levels, true); return; }
      if (!ok) { setLocalLevel(target, null, cur.muted); SD.toast(SD.errText(data, status, "Não foi possível silenciar"), true); }
    });
  }

  function fetchLevels() {
    SD.req("GET", "/api/volume", null, function (ok, data) { if (ok && data) SD.applyLevels(data.levels); });
  }

  /* ========================================================= gestos ===== */
  /* Um gesto por vez, tratado no documento: press (toque), repeat (segurar),
     fader (arrastar volume), swipe (trocar pagina / fechar pasta). x/y ja no referencial do #app. */
  var G = null, lastTouch = 0;

  function cellOf(target) {
    while (target && target !== document.body) {
      if (target.sdTile && SD.hasClass(target, "cell")) return target;
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
    clearTimeout(G.holdT); clearInterval(G.repT);
  }
  function stopHold(k) {
    if (!k || !k.holding) return;
    k.holding = false;
    SD.setClass(k.el, "hgo", false);
    SD.setClass(k.el, "holding", false);
  }
  function up() { if (G && G.k) { SD.setClass(G.k.el, "down", false); stopHold(G.k); } }

  function start(x, y, target) {
    if (SD.sheet.isOpen() || SD.alertOpen() || !SD.cfg) return false;
    if (isIn(target, "nav") || isIn(target, "dots-bar") || isIn(target, "fd-bar")) return false;
    var cell = cellOf(target), k = cell ? cell.sdTile : null;
    if (k && folder && k.f == null) k = null;   /* pasta aberta: a pagina de tras nao responde */
    G = { k: k, sx: x, sy: y, x: x, y: y, t0: SD.now(), mode: "pending", moved: false };
    if (!k) return true;
    if (k.kind === "fader") {
      var lv = levelOf(k.b.target || "master");
      G.mode = "fader"; G.target = k.b.target || "master"; G.v0 = lv && lv.v != null ? lv.v : 0;
      G.max = lv && lv.max > 0 ? lv.max : (G.target === "effects" ? 200 : 100);
      return true;
    }
    if (!k.empty) SD.setClass(k.el, "down", true);
    if (!k.empty && !k.folder && gestureAction(k.b, "hold")) {
      /* segurar: progresso no bloco e dispara em HOLD_MS (vence a repeticao) */
      k.holding = 1; repaint(k);
      k.el.offsetWidth;   /* aplica o estado inicial antes da transicao */
      k.holding = 2; SD.setClass(k.el, "hgo", true);
      G.holdT = setTimeout(function () {
        if (!G || G.k !== k || G.mode !== "pending") return;
        G.mode = "held";
        stopHold(k);
        if (conf && conf.k !== k) endConfirm();
        flushDouble();
        if (SD.prefs.vibrate) SD.vibrate(15);
        flash(k, true);
        fire(k, "hold", true);
      }, HOLD_MS);
    } else if (!k.empty && canRepeat(k)) {
      G.holdT = setTimeout(function () {
        if (!G || G.mode !== "pending") return;
        G.mode = "repeat";
        press(k, true);
        G.repT = setInterval(function () { press(k, true); }, 130);
      }, 450);
    }
    return true;
  }

  function move(x, y) {
    if (!G) return;
    G.x = x; G.y = y;
    var dx = x - G.sx, dy = y - G.sy, adx = Math.abs(dx), ady = Math.abs(dy);
    if (adx > 6 || ady > 6) G.moved = true;
    if (G.mode === "fader") {
      /* para cima (no referencial da tela, girada ou nao) aumenta */
      var h = G.k.h || 100, v = Math.max(0, Math.min(G.max, G.v0 - dy / h * G.max * 1.15));
      if (!G.moved) return;
      var cur = levelOf(G.target);
      if (cur && cur.v != null && Math.round(cur.v) === Math.round(v)) return;
      setLocalLevel(G.target, Math.round(v), null);
      holdUntil[G.target] = SD.now() + 1500;
      sendLevel(G.target, v);
      return;
    }
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
      /* toque na parte de baixo (icone) liga/desliga o mudo */
      if (!g.moved && !cancel && g.y > g.k.y + g.k.h * 0.6) toggleMute(g.k);
    } else if (g.mode === "swipe") {
      swipeEnd(g.x - g.sx, SD.now() - g.t0);
    } else if (g.mode === "pending" && g.k && !cancel) {
      tap(g.k);
    }
    G = null;
  }

  /* ---------------------------------------- deslizar (paginas / pasta) --- */
  function swipeMove(dx) {
    if (folder) {
      /* pasta: arrastar para a direita fecha */
      css(fgrid, "transition", "none");
      css(fgrid, "transform", "translate3d(" + Math.round(dx > 0 ? dx : dx / 4) + "px,0,0)");
      fwrap.style.opacity = String(Math.max(0.35, 1 - Math.max(0, dx) / (frame.w || 400)));
      return;
    }
    var n = SD.cfg.pages.length;
    if ((SD.page === 0 && dx > 0) || (SD.page === n - 1 && dx < 0)) dx = dx / 3;   /* elastico nas pontas */
    css(grid, "transition", "none");
    css(grid, "transform", "translate3d(" + Math.round(dx) + "px,0,0)");
  }
  function swipeEnd(dx, dt) {
    var W = frame.w, fast = Math.abs(dx) > 40 && dt < 300;
    if (folder) {
      css(fgrid, "transition", "");
      if (dx > 0 && (dx > W * 0.22 || fast)) {
        css(fgrid, "transform", "translate3d(" + Math.round(W * 0.3) + "px,0,0)");
        closeFolder(false);
      } else {
        css(fgrid, "transform", "");
        fwrap.style.opacity = "1";
      }
      return;
    }
    css(grid, "transition", "");
    var to = SD.page + (dx < 0 ? 1 : -1);
    if ((Math.abs(dx) > W * 0.18 || fast) && SD.cfg.pages[to]) {
      css(grid, "transform", "translate3d(" + (dx < 0 ? -W : W) * 0.4 + "px,0,0)");
      grid.style.opacity = "0";
      setTimeout(function () { SD.goPage(to, dx < 0 ? 1 : -1); }, 120);
    } else {
      css(grid, "transform", "");
    }
  }

  /* ----------------------------------------------- eventos do documento --- */
  function onTS(e) {
    lastTouch = SD.now();
    if (e.touches.length > 1) { if (G) end(true); return; }
    var t = e.touches[0], p = SD.toLocal(t.clientX, t.clientY);
    if (start(p.x, p.y, e.target)) e.preventDefault();
  }
  function onTM(e) {
    if (G) { var t = e.touches[0], p = SD.toLocal(t.clientX, t.clientY); move(p.x, p.y); e.preventDefault(); return; }
    /* sem folha aberta, a tela nao rola nem da zoom */
    if (!SD.sheet.isOpen() && !SD.alertOpen()) e.preventDefault();
  }
  function onTE(e) {
    if (G) { e.preventDefault(); end(false); }
    maybeAutoFs();
  }
  function onTC() { if (G) end(true); }

  function onMD(e) {
    if (SD.now() - lastTouch < 800 || e.button !== 0) return;
    var p = SD.toLocal(e.clientX, e.clientY);
    if (start(p.x, p.y, e.target)) e.preventDefault();
  }
  function onMM(e) { if (G && SD.now() - lastTouch > 800) { var p = SD.toLocal(e.clientX, e.clientY); move(p.x, p.y); } }
  function onMU() {
    if (SD.now() - lastTouch < 800) return;
    if (G) end(false);
    maybeAutoFs();
  }

  /* ===================================================== OBS e sons ===== */
  /* consulta a cada 1 s enquanto toca som ou ha bloco do OBS na tela */
  function needFast() {
    for (var key in SD.sounds) if (SD.sounds.hasOwnProperty(key)) return true;
    /* OBS so acelera a consulta se ele estiver configurado e conectado */
    if (!SD.obs || !SD.obs.ok) return false;
    var v = visible();
    for (var i = 0; i < v.length; i++) {
      var b = v[i].b;
      if (b && (b.lit || String(b.live || "").indexOf("obs:") === 0)) return true;
    }
    return false;
  }

  SD.applyObs = function (o) {
    SD.obs = o && typeof o === "object" ? o : null;
    var v = visible();
    for (var i = 0; i < v.length; i++) {
      var k = v[i], b = k.b;
      if (!b || k.kind !== "button" || k.empty) continue;
      var on = obsLit(b), lv = String(b.live || "");
      if (on !== !!k.olit) { k.olit = on; repaint(k); }
      else if (lv.indexOf("obs:") === 0) repaint(k);
    }
  };

  /* lista do PC -> mapa por chave, com a hora local para interpolar */
  var soundT = null;
  SD.applySounds = function (list) {
    var map = {}, t = SD.now();
    if (list && list.length) {
      for (var i = 0; i < list.length; i++) {
        var s = list[i];
        if (s && s.key != null && s.dur > 0) map[String(s.key)] = { pos: +s.pos || 0, dur: +s.dur, at: t, file: s.file };
      }
    }
    SD.sounds = map;
    soundTick(true);
  };
  /* passo local (250 ms) so enquanto algo toca */
  function soundTick(all) {
    var v = visible(), any = false;
    for (var i = 0; i < v.length; i++) {
      var k = v[i];
      if (!k.w || !k.b || k.kind !== "button" || !showsSound(k)) continue;
      var has = !!soundOf(k);
      if (has) any = true;
      if (k.b.live === "sound") {
        /* texto mm:ss: redesenha so quando muda */
        var txt = String(liveText(k, "sound"));
        if (all || txt !== k.stxt) { k.stxt = txt; repaint(k); continue; }
      } else if (all || has !== !!k.pb) { repaint(k); continue; }
      paintSound(k);
    }
    for (var key in SD.sounds) if (SD.sounds.hasOwnProperty(key)) any = true;
    clearTimeout(soundT); soundT = null;
    if (any && !document.hidden) soundT = setTimeout(function () { soundTick(false); }, 250);
  }

  /* ======================================================== rede ===== */
  var offlineToast = false, pollT = null;

  function showMsg(icon, title, text) {
    msg.innerHTML = '<div class="m-ic">' + SD.svg(icon, 34, SD.lightTheme ? "rgba(60,60,67,0.6)" : "rgba(235,235,245,0.6)") + "</div><b>" + esc(title) + "</b><p>" + esc(text) + "</p>";
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
        if (folder) closeFolder(true);
        SD.cfg = null; keys = []; built = null;
        grid.innerHTML = ""; dotsEl.innerHTML = "";
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

  /* pagina que lista este exe em "apps" (-1 se nenhuma) */
  function pageForApp(app) {
    app = String(app || "").toLowerCase();
    if (!app || !SD.cfg) return -1;
    var base = app.replace(/^.*[\\\/]/, "");
    for (var i = 0; i < SD.cfg.pages.length; i++) {
      var l = SD.cfg.pages[i].apps;
      if (!l || !l.length) continue;
      for (var j = 0; j < l.length; j++) {
        var a = String(l[j] || "").toLowerCase().replace(/^.*[\\\/]/, "");
        if (a && (a === base || a + ".exe" === base)) return i;
      }
    }
    return -1;
  }

  /* troca de pagina pelo app em foco: so quando o app MUDA (nao briga com o usuario) */
  function onApp(app) {
    if (app == null) return;
    app = String(app).toLowerCase();
    if (app === SD.app) return;
    SD.app = app;
    if (!SD.prefs.autoPage || G || SD.sheet.isOpen()) return;
    var to = pageForApp(app);
    if (to >= 0 && to !== SD.page) SD.goPage(to);
  }
  SD.pageForApp = pageForApp;

  /* relogio do PC pelo cabecalho Date (para o cronometro) */
  function readSkew(x) {
    try {
      var d = x && x.getResponseHeader("Date"), t = d ? Date.parse(d) : NaN;
      if (!isNaN(t)) SD.skew = t + 500 - SD.now();
    } catch (e) {}
  }

  /* consulta leve: mudancas feitas no PC, estados liga/desliga, volumes, app em foco e versoes novas */
  function poll() {
    clearTimeout(pollT);
    var lv = needLevels();
    pollT = setTimeout(poll, needFast() ? 1000 : lv ? 2000 : 5000);
    if (SD.denied || !SD.cfg || document.hidden) return;
    SD.req("GET", "/api/state" + (lv ? "?levels=1" : ""), null, function (ok, st, status, x) {
      if (!ok) { if (status === 403) SD.load(); return; }
      if (offlineToast) { offlineToast = false; SD.toast("Conectado"); }
      readSkew(x);
      if (st.toggles) SD.applyToggles(st.toggles, st.since || {});
      if (st.levels) SD.applyLevels(st.levels);
      SD.applySounds(st.sounds);
      SD.applyObs(st.obs);
      if (SD.cfgV != null && st.v != null && String(st.v) !== String(SD.cfgV) && !G) SD.load();
      if (SD.info && SD.info.update && !!st.update !== !!SD.info.update.available) SD.loadInfo();
      if (st.app !== undefined) onApp(st.app);
    });
  }
  function pollSoon() {
    clearTimeout(pollT);
    pollT = setTimeout(poll, 50);
    if (needLevels()) fetchLevels();
  }
  SD.pollSoon = pollSoon;

  /* ======================================================== inicio ===== */
  SD.start = function () {
    grid = $("grid"); dotsEl = $("dots"); msg = $("msg");
    fwrap = $("folder"); fbar = $("fd-bar"); fgrid = $("fgrid"); ftitle = $("fd-t");
    $("fd-back").onclick = function () { closeFolder(false); };
    loadPrefs();
    watchTheme();
    document.addEventListener("touchstart", onTS, { passive: false });
    document.addEventListener("touchmove", onTM, { passive: false });
    document.addEventListener("touchend", onTE, { passive: false });
    document.addEventListener("touchcancel", onTC, false);
    document.addEventListener("mousedown", onMD, false);
    document.addEventListener("mousemove", onMM, false);
    document.addEventListener("mouseup", onMU, false);
    document.addEventListener("fullscreenchange", onFsChange, false);
    document.addEventListener("webkitfullscreenchange", onFsChange, false);
    window.addEventListener("resize", SD.layoutSoon, false);
    window.addEventListener("orientationchange", function () { setTimeout(SD.layout, 300); }, false);
    window.addEventListener("popstate", onPop, false);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) { pollSoon(); SD.pingAll(); setupLive(); soundTick(true); } }, false);
    $("scrim").onclick = function () { SD.sheet.cancel(); };
    setInterval(function () { if (!document.hidden) SD.pingAll(); }, 20000);

    SD.readSync();
    SD.initConns();
    lockOrientation();   /* app instalado: trava ja na abertura */
    SD.cfg = SD.cachedCfg();
    if (SD.cfg) { msg.style.display = "none"; SD.render(); }   /* abre na hora com o que estava guardado */
    else { SD.layout(); showMsg("wifi", "Conectando…", "Procurando o Stream Deck no PC."); }
    SD.load();
  };
})();
