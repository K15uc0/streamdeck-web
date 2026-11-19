/* Stream Deck - nucleo: rede, utilidades, icones, estado global (window.SD),
   folhas (sheets), alertas e componentes de lista no estilo iOS.
   ES5 puro: precisa rodar no navegador de Android antigo. */
(function () {
  "use strict";

  var SD = window.SD = window.SD || {};

  /* ------------------------------------------------------- utilidades --- */
  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function clone(o) { return o == null ? o : JSON.parse(JSON.stringify(o)); }
  function trim(s) { return String(s == null ? "" : s).replace(/^\s+|\s+$/g, ""); }
  function qs(name) {
    var m = new RegExp("[?&]" + name + "=([^&]*)").exec(location.search);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function el(tag, cls, html, parent) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    if (parent) parent.appendChild(e);
    return e;
  }
  function now() { return new Date().getTime(); }
  function hasClass(e, c) { return (" " + e.className + " ").indexOf(" " + c + " ") >= 0; }
  function setClass(e, c, on) {
    var has = hasClass(e, c);
    if (on && !has) e.className = trim(e.className + " " + c);
    else if (!on && has) e.className = trim((" " + e.className + " ").replace(" " + c + " ", " "));
  }
  function css(e, prop, value) {
    /* aplica com e sem prefixo -webkit- (transform, transition...) */
    e.style[prop] = value;
    e.style["webkit" + prop.charAt(0).toUpperCase() + prop.slice(1)] = value;
  }
  function vibrate(ms) { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) {} }

  SD.$ = $; SD.esc = esc; SD.clone = clone; SD.trim = trim; SD.qs = qs; SD.el = el;
  SD.now = now; SD.hasClass = hasClass; SD.setClass = setClass; SD.css = css; SD.vibrate = vibrate;

  /* ------------------------------------------------------------ cores --- */
  /* paleta de cores do sistema do iOS (modo escuro) */
  SD.COLORS = [
    ["Azul", "#0a84ff"], ["Índigo", "#5e5ce6"], ["Roxo", "#bf5af2"], ["Rosa", "#ff375f"],
    ["Vermelho", "#ff453a"], ["Laranja", "#ff9f0a"], ["Amarelo", "#ffd60a"], ["Verde", "#30d158"],
    ["Menta", "#63e6e2"], ["Azul-petróleo", "#40c8e0"], ["Ciano", "#64d2ff"], ["Marrom", "#ac8e68"],
    ["Cinza", "#8e8e93"]
  ];
  SD.TINT = "#0a84ff";
  SD.RED = "#ff453a";
  SD.GREEN = "#30d158";
  SD.DEFAULT_TILE = "#3a3a3c";

  function rgb(c) {
    var m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(trim(c || ""));
    if (!m) return null;
    var h = m[1];
    if (h.length === 3) h = h.charAt(0) + h.charAt(0) + h.charAt(1) + h.charAt(1) + h.charAt(2) + h.charAt(2);
    return [parseInt(h.substr(0, 2), 16), parseInt(h.substr(2, 2), 16), parseInt(h.substr(4, 2), 16)];
  }
  /* cor clara (amarelo, menta...) pede texto escuro */
  SD.isLight = function (c) {
    var v = rgb(c);
    if (!v) return false;
    return (0.299 * v[0] + 0.587 * v[1] + 0.114 * v[2]) / 255 > 0.72;
  };
  SD.validColor = function (c) { return !!rgb(c); };

  /* ----------------------------------------------------------- icones --- */
  var S = ' stroke="#fff" stroke-width="2" fill="none" ';
  SD.ICONS = {
    playpause: '<path d="M3 5v14l9-7z M14 5h3v14h-3z M19 5h2v14h-2z" fill="#fff"/>',
    play: '<path d="M7 4v16l13-8z" fill="#fff"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="1.5" fill="#fff"/>',
    prev: '<path d="M6 6h2v12H6z M9.5 12L18 18V6z" fill="#fff"/>',
    next: '<path d="M16 6h2v12h-2z M6 18l8.5-6L6 6z" fill="#fff"/>',
    record: '<circle cx="12" cy="12" r="7" fill="#fff"/>',
    sound: '<path d="M3 9v6h4l5 5V4L7 9H3z" fill="#fff"/><path d="M16 8.5a5 5 0 0 1 0 7M19 5.5a9 9 0 0 1 0 13"' + S + '/>',
    volup: '<path d="M3 9v6h4l5 5V4L7 9H3z" fill="#fff"/><path d="M15 12h7M18.5 8.5v7"' + S + '/>',
    voldown: '<path d="M3 9v6h4l5 5V4L7 9H3z" fill="#fff"/><path d="M15 12h7"' + S + '/>',
    mute: '<path d="M3 9v6h4l5 5V4L7 9H3z" fill="#fff"/><path d="M15 9l6 6M21 9l-6 6"' + S + '/>',
    mic: '<rect x="9" y="2" width="6" height="12" rx="3" fill="#fff"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4"' + S + '/>',
    micoff: '<rect x="9" y="2" width="6" height="12" rx="3" fill="#fff"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4M3 3l18 18"' + S + '/>',
    headphones: '<path d="M4 15v-3a8 8 0 0 1 16 0v3"' + S + '/><rect x="3" y="14" width="4" height="7" rx="1" fill="#fff"/><rect x="17" y="14" width="4" height="7" rx="1" fill="#fff"/>',
    music: '<path d="M9 18V5l11-2v13"' + S + '/><circle cx="6.5" cy="18" r="2.5" fill="#fff"/><circle cx="17.5" cy="16" r="2.5" fill="#fff"/>',
    playlist: '<path d="M3 6h13M3 11h13M3 16h8"' + S + '/><path d="M15 14l6 3.5-6 3.5z" fill="#fff"/>',
    radio: '<rect x="3" y="8" width="18" height="12" rx="2"' + S + '/><path d="M7 8l10-5M6 12h4M6 15.5h4"' + S + '/><circle cx="15.5" cy="14" r="2.5" fill="#fff"/>',
    onair: '<circle cx="12" cy="12" r="2.5" fill="#fff"/><path d="M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8"' + S + '/>',
    sliders: '<path d="M6 3v18M12 3v18M18 3v18"' + S + '/><rect x="3.5" y="13" width="5" height="3" rx="1" fill="#fff"/><rect x="9.5" y="6" width="5" height="3" rx="1" fill="#fff"/><rect x="15.5" y="10" width="5" height="3" rx="1" fill="#fff"/>',
    globe: '<circle cx="12" cy="12" r="9"' + S + '/><path d="M3 12h18M12 3c3.5 3.5 3.5 14.5 0 18M12 3c-3.5 3.5-3.5 14.5 0 18"' + S + '/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"' + S + '/>',
    folder: '<path d="M3 6h7l2 2h9v11H3z" fill="#fff"/>',
    terminal: '<rect x="3" y="4" width="18" height="16" rx="2"' + S + '/><path d="M7 9l3 3-3 3M12 15h5"' + S + '/>',
    calc: '<rect x="5" y="3" width="14" height="18" rx="2"' + S + '/><rect x="8" y="6" width="8" height="3" fill="#fff"/><path d="M8 12h2v2H8zM14 12h2v2h-2zM8 16h2v2H8zM14 16h2v2h-2z" fill="#fff"/>',
    camera: '<path d="M4 7h4l2-2h4l2 2h4v12H4z" fill="#fff"/><circle cx="12" cy="13" r="3.5" fill="rgba(0,0,0,0.45)"/>',
    desktop: '<rect x="3" y="4" width="18" height="12" rx="1"' + S + '/><path d="M8 20h8M12 16v4"' + S + '/>',
    chart: '<path d="M4 20V10h3v10zM10.5 20V4h3v16zM17 20v-7h3v7z" fill="#fff"/>',
    lock: '<rect x="5" y="10" width="14" height="11" rx="2" fill="#fff"/><path d="M8 10V7a4 4 0 0 1 8 0v3"' + S + '/>',
    keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"' + S + '/><path d="M5 9h2v2H5zM9 9h2v2H9zM13 9h2v2h-2zM17 9h2v2h-2zM7 14h10v2H7z" fill="#fff"/>',
    text: '<path d="M5 6V4h14v2M12 4v16M9 20h6"' + S + '/>',
    copy: '<rect x="8" y="8" width="12" height="13" rx="1"' + S + '/><path d="M4 16V4h12"' + S + '/>',
    paste: '<rect x="5" y="4" width="14" height="17" rx="1"' + S + '/><rect x="9" y="2" width="6" height="4" rx="1" fill="#fff"/>',
    cut: '<circle cx="6" cy="18" r="3"' + S + '/><circle cx="18" cy="18" r="3"' + S + '/><path d="M8 16L18 3M16 16L6 3"' + S + '/>',
    undo: '<path d="M9 4L4 9l5 5"' + S + '/><path d="M4 9h10a5.5 5.5 0 0 1 0 11h-3"' + S + '/>',
    redo: '<path d="M15 4l5 5-5 5"' + S + '/><path d="M20 9H10a5.5 5.5 0 0 0 0 11h3"' + S + '/>',
    save: '<path d="M4 4h13l3 3v13H4z"' + S + '/><rect x="7" y="4" width="8" height="5" fill="#fff"/><rect x="7" y="13" width="10" height="7" fill="#fff"/>',
    select: '<rect x="4" y="4" width="16" height="16" stroke-dasharray="3 2"' + S + '/>',
    apps: '<rect x="3" y="3" width="8" height="8" rx="2" fill="#fff"/><rect x="13" y="3" width="8" height="8" rx="2" fill="#fff"/><rect x="3" y="13" width="8" height="8" rx="2" fill="#fff"/><rect x="13" y="13" width="8" height="8" rx="2" fill="#fff"/>',
    list: '<path d="M9 6h11M9 12h11M9 18h11"' + S + '/><circle cx="4.5" cy="6" r="1.5" fill="#fff"/><circle cx="4.5" cy="12" r="1.5" fill="#fff"/><circle cx="4.5" cy="18" r="1.5" fill="#fff"/>',
    page: '<rect x="5" y="3" width="14" height="18" rx="2"' + S + '/><path d="M9 8h6M9 12h6M9 16h3"' + S + '/>',
    scene: '<rect x="3" y="5" width="18" height="14" rx="1"' + S + '/><path d="M6 16l4-5 3 3 2-2 3 4z" fill="#fff"/>',
    chat: '<path d="M4 4h16v11H9l-5 4z"' + S + '/><path d="M8 8.5h8M8 11.5h5"' + S + '/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="1"' + S + '/><path d="M3 6l9 7 9-7"' + S + '/>',
    bell: '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z" fill="#fff"/><path d="M10 20.5a2 2 0 0 0 4 0"' + S + '/>',
    smile: '<circle cx="12" cy="12" r="9"' + S + '/><path d="M8 14a5 5 0 0 0 8 0"' + S + '/><circle cx="9" cy="9.5" r="1.3" fill="#fff"/><circle cx="15" cy="9.5" r="1.3" fill="#fff"/>',
    star: '<path d="M12 3l2.8 5.8 6.2.9-4.5 4.4 1 6.2L12 17.4 6.5 20.3l1-6.2L3 9.7l6.2-.9z" fill="#fff"/>',
    heart: '<path d="M12 20s-8-5-8-10.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8 2.5C20 15 12 20 12 20z" fill="#fff"/>',
    bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z" fill="#fff"/>',
    home: '<path d="M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10"' + S + '/>',
    code: '<path d="M8 6l-6 6 6 6M16 6l6 6-6 6"' + S + '/>',
    power: '<path d="M12 2v10"' + S + '/><path d="M6.3 5.7a8 8 0 1 0 11.4 0"' + S + '/>',
    gear: '<circle cx="12" cy="12" r="3.5"' + S + '/><path d="M12 2v4M12 18v4M2 12h4M18 12h4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"' + S + '/>',
    back: '<path d="M15 4l-8 8 8 8"' + S + '/>',
    forward: '<path d="M9 4l8 8-8 8"' + S + '/>',
    updown: '<path d="M12 4v16M7 9l5-5 5 5M7 15l5 5 5-5"' + S + '/>',
    close: '<path d="M5 5l14 14M19 5L5 19"' + S + '/>',
    plus: '<path d="M12 4v16M4 12h16"' + S + '/>'
  };
  /* icones da interface (nao aparecem na grade de escolha) */
  var UI_ICONS = {
    chevron: '<path d="M9 5l7 7-7 7" stroke="#fff" stroke-width="2.6" fill="none"/>',
    chevleft: '<path d="M15 4l-8 8 8 8" stroke="#fff" stroke-width="2.8" fill="none"/>',
    check: '<path d="M4.5 12.5l5 5 10-11" stroke="#fff" stroke-width="2.6" fill="none"/>',
    minus: '<path d="M6 12h12" stroke="#fff" stroke-width="3" fill="none"/>',
    wifi: '<path d="M2 9a15 15 0 0 1 20 0M5.5 12.5a10 10 0 0 1 13 0M9 16a5 5 0 0 1 6 0" stroke="#fff" stroke-width="2.2" fill="none"/><circle cx="12" cy="19.5" r="1.6" fill="#fff"/>',
    download: '<path d="M12 3v12M7 10l5 5 5-5M4 20h16" stroke="#fff" stroke-width="2.2" fill="none"/>',
    expand: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" stroke="#fff" stroke-width="2.2" fill="none"/>',
    cog: '<path d="M10.3 2.5h3.4l.5 2.6 1.7.9 2.4-1.2 2.4 2.4-1.2 2.4.7 1.7 2.6.5v3.4l-2.6.5-.7 1.7 1.2 2.4-2.4 2.4-2.4-1.2-1.7.7-.5 2.6h-3.4l-.5-2.6-1.7-.7-2.4 1.2-2.4-2.4 1.2-2.4-.7-1.7-2.6-.5v-3.4l2.6-.5.7-1.7-1.2-2.4 2.4-2.4 2.4 1.2 1.7-.9z" stroke="#fff" stroke-width="1.8" fill="none" stroke-linejoin="round"/><circle cx="12" cy="12" r="3.2" stroke="#fff" stroke-width="1.8" fill="none"/>',
    shrink: '<path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" stroke="#fff" stroke-width="2.2" fill="none"/>',
    phone: '<rect x="6" y="2" width="12" height="20" rx="2.5" stroke="#fff" stroke-width="2" fill="none"/><path d="M10.5 18.5h3" stroke="#fff" stroke-width="2"/>',
    share: '<path d="M12 3v12M8 7l4-4 4 4M6 11H5v10h14V11h-1" stroke="#fff" stroke-width="2" fill="none"/>',
    grid: '<rect x="3" y="3" width="7.5" height="7.5" rx="2" fill="#fff"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2" fill="#fff"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2" fill="#fff"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" fill="#fff"/>',
    pages: '<rect x="7" y="2" width="13" height="16" rx="2" fill="#fff" opacity="0.55"/><rect x="4" y="6" width="13" height="16" rx="2" fill="#fff"/>',
    info: '<circle cx="12" cy="12" r="9.5" stroke="#fff" stroke-width="2" fill="none"/><path d="M12 11v6" stroke="#fff" stroke-width="2.4"/><circle cx="12" cy="7.5" r="1.4" fill="#fff"/>',
    qr: '<path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3z" stroke="#fff" stroke-width="2" fill="none"/><path d="M14 14h3v3h-3zM18 18h3v3h-3zM18 14h3v2h-3zM14 18h2v3h-2z" fill="#fff"/>',
    warn: '<path d="M12 3L2 20h20z" fill="#fff"/><path d="M12 9v5" stroke="#000" stroke-width="2.2"/><circle cx="12" cy="17" r="1.3" fill="#000"/>'
  };

  /* svg(nome, tamanho, cor): troca o branco do desenho pela cor pedida */
  SD.svg = function (name, size, color) {
    var body = SD.ICONS[name] || UI_ICONS[name];
    if (!body) return "";
    if (color && color !== "#fff") body = body.replace(/#fff/g, color);
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size +
      '" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">' + body + "</svg>";
  };
  SD.hasIcon = function (name) { return !!(name && SD.ICONS.hasOwnProperty(name)); };

  /* ------------------------------------------------------ estado global --- */
  SD.TOKEN = qs("k");
  SD.denied = false;       /* codigo recusado: para de tentar (evita bloqueio por tentativas) */
  SD.cfg = null;
  SD.cfgV = null;
  SD.page = 0;
  SD.info = null;
  SD.actions = null;       /* lista de ActionSchema (GET /api/actions) */
  SD.actionMap = {};
  SD.toggles = {};         /* "p:b": true */
  SD.levels = {};          /* master/effects/mic -> {v, muted} */
  SD.online = true;
  SD.here = location.host;
  SD.conns = [];
  SD.alive = {};

  /* ------------------------------------------------------------- rede --- */
  SD.req = function (method, url, body, cb) {
    var x = new XMLHttpRequest(), done = false;
    x.open(method, url + (url.indexOf("?") < 0 ? "?" : "&") +
      (SD.TOKEN ? "k=" + encodeURIComponent(SD.TOKEN) + "&" : "") + "t=" + now(), true);
    var timer = setTimeout(function () { try { x.abort(); } catch (e) {} finish(); }, 8000);
    function finish() {
      if (done) return;
      done = true;
      clearTimeout(timer);
      var data = null, status = 0;
      try { status = x.status; data = JSON.parse(x.responseText); } catch (e) {}
      var was = SD.online;
      SD.online = status !== 0;
      if (was !== SD.online && SD.onConn) SD.onConn();
      if (status === 403 && data && data.error === "codigo de acesso invalido") SD.denied = true;
      if (cb) cb(status === 200 && !!data && data.ok !== false, data, status, x);
    }
    x.onreadystatechange = function () { if (x.readyState === 4) finish(); };
    x.onerror = finish;
    x.setRequestHeader("X-StreamDeck", "1");
    if (body) x.setRequestHeader("Content-Type", "application/json");
    x.send(body || null);
  };

  SD.errText = function (data, status, fallback) {
    if (status === 0) return "Sem conexão com o PC";
    return (data && data.error) || fallback || "Não funcionou";
  };

  /* --------------------------------------------------------- avisos --- */
  var toastT = null;
  SD.toast = function (text, err) {
    var t = $("toast");
    t.innerHTML = (err ? SD.svg("warn", 16, "#ff453a") + " " : "") + esc(text);
    t.className = "show" + (err ? " err" : "");
    clearTimeout(toastT);
    toastT = setTimeout(function () { t.className = err ? "err" : ""; }, err ? 4000 : 1600);
  };

  /* ---------------------------------------------------------- config --- */
  var CFG_KEY = "sd_cfg_" + SD.here;
  SD.cacheCfg = function () { try { window.localStorage.setItem(CFG_KEY, JSON.stringify(SD.cfg)); } catch (e) {} };
  SD.cachedCfg = function () {
    try { var c = JSON.parse(window.localStorage.getItem(CFG_KEY)); return c && c.pages && c.pages.length ? c : null; }
    catch (e) { return null; }
  };
  SD.dropCache = function () { try { window.localStorage.removeItem(CFG_KEY); } catch (e) {} };

  SD.emptyButton = function () { return { kind: "button", label: "", icon: "", color: "", action: { type: "none" } }; };
  /* regra unica (celular e editor): vazio = nao e fader, acao nenhuma
     e sem texto, icone, liga/desliga ou cor */
  SD.isEmpty = function (b) {
    if (!b) return true;
    if (b.kind === "fader") return false;
    var t = b.action && b.action.type;
    return (!t || t === "none") && !SD.trim(b.label) && !b.icon && !b.toggle && !b.color;
  };
  /* isEmpty tambem vale para pasta (kind "folder" nunca e vazia) */
  var isEmpty0 = SD.isEmpty;
  SD.isEmpty = function (b) { return b && b.kind === "folder" ? false : isEmpty0(b); };

  /* Encaixe da grade (celular e editor usam a mesma regra):
     percorre os botoes na ordem; cada um ocupa w x h (1..4, limitado ao
     tamanho da grade) na primeira posicao livre, linha a linha, da
     esquerda para a direita (como o "dense" do CSS grid). O que nao couber
     fica de fora. Devolve [{i, x, y, w, h}] (x/y = coluna/linha, base 0). */
  SD.flow = function (buttons, cols, rows) {
    var used = [], out = [], i, x, y, w, h, b, placed;
    for (i = 0; i < cols * rows; i++) used.push(false);
    function free(x0, y0, w0, h0) {
      if (x0 + w0 > cols || y0 + h0 > rows) return false;
      for (var yy = y0; yy < y0 + h0; yy++) {
        for (var xx = x0; xx < x0 + w0; xx++) if (used[yy * cols + xx]) return false;
      }
      return true;
    }
    for (i = 0; i < (buttons || []).length; i++) {
      b = buttons[i] || {};
      w = Math.max(1, Math.min(cols, parseInt(b.w, 10) || 1));
      h = Math.max(1, Math.min(rows, parseInt(b.h, 10) || 1));
      placed = false;
      for (y = 0; y < rows && !placed; y++) {
        for (x = 0; x < cols && !placed; x++) {
          if (free(x, y, w, h)) {
            for (var yy = y; yy < y + h; yy++) for (var xx = x; xx < x + w; xx++) used[yy * cols + xx] = true;
            out.push({ i: i, x: x, y: y, w: w, h: h });
            placed = true;
          }
        }
      }
    }
    return out;
  };

  SD.padButtons = function (pg, n) {
    if (!pg.buttons) pg.buttons = [];
    while (pg.buttons.length < n) pg.buttons.push(SD.emptyButton());
  };

  /* Salva o config inteiro no PC.
     otimista = mostra a mudanca na hora e desfaz se o PC recusar. */
  SD.saveCfg = function (newCfg, done, optimistic) {
    var old = SD.cfg;
    if (optimistic) { SD.cfg = newCfg; if (SD.page >= newCfg.pages.length) SD.page = newCfg.pages.length - 1; SD.render(); }
    SD.req("POST", "/api/config", JSON.stringify(newCfg), function (ok, data, status) {
      if (ok) {
        SD.cfg = newCfg;
        if (data && data.v != null) SD.cfgV = String(data.v);
        SD.cacheCfg();
        if (SD.page >= SD.cfg.pages.length) SD.page = SD.cfg.pages.length - 1;
        if (!optimistic) SD.render();
        if (done) done(true);
      } else {
        if (optimistic && SD.cfg === newCfg) { SD.cfg = old; SD.render(); }
        SD.toast("Não salvou: " + SD.errText(data, status, "erro no PC"), true);
        if (done) done(false);
      }
    });
  };

  /* ---------------------------------------------- esquemas das acoes --- */
  var actWait = null;
  SD.loadActions = function (cb) {
    if (SD.actions) { if (cb) cb(true); return; }
    SD.actionsFailed = false;
    if (actWait) { if (cb) actWait.push(cb); return; }
    actWait = cb ? [cb] : [];
    SD.req("GET", "/api/actions", null, function (ok, data) {
      var list = actWait; actWait = null;
      if (ok && data && data.actions) {
        SD.actions = data.actions;
        SD.actionMap = {};
        for (var i = 0; i < data.actions.length; i++) SD.actionMap[data.actions[i].type] = data.actions[i];
      }
      SD.actionsFailed = !SD.actions;
      for (var j = 0; j < list.length; j++) list[j](!!SD.actions);
    });
  };
  SD.schemaOf = function (a) { return a && SD.actionMap[a.type] || null; };

  /* campos que apontam para paginas: usa o esquema; sem ele, o formato conhecido do contrato */
  function pageFields(a) {
    var s = SD.schemaOf(a), out = [], i;
    if (s && s.fields) {
      for (i = 0; i < s.fields.length; i++) {
        if (s.fields[i].kind === "page" || s.fields[i].kind === "steps") out.push(s.fields[i]);
      }
      return out;
    }
    if (a.type === "page") out.push({ key: "to", kind: "page" });
    if (a.steps && a.steps.length != null) out.push({ key: "steps", kind: "steps" });
    return out;
  }
  /* map[antigo] = novo (ou -1 se a pagina sumiu). Devolve false se a acao ficou invalida. */
  function remapAction(a, map) {
    if (!a) return true;
    var fs = pageFields(a);
    for (var i = 0; i < fs.length; i++) {
      var f = fs[i], v = a[f.key];
      if (f.kind === "page" && v != null) {
        var n = map[parseInt(v, 10)];
        if (n == null || n < 0) return false;
        a[f.key] = n;
      } else if (f.kind === "steps" && v && v.length != null) {
        var keep = [];
        for (var j = 0; j < v.length; j++) if (remapAction(v[j], map)) keep.push(v[j]);
        a[f.key] = keep;
      }
    }
    return true;
  }
  SD.remapPages = function (cfg, map) {
    for (var p = 0; p < cfg.pages.length; p++) {
      var bs = cfg.pages[p].buttons || [];
      for (var i = 0; i < bs.length; i++) {
        if (bs[i] && bs[i].action && !remapAction(bs[i].action, map)) bs[i] = SD.emptyButton();
      }
    }
  };

  /* ---------------------------------------------- abas (um PC por aba) --- */
  var CONNS_KEY = "sd_conns", synced = null;
  function lsGet() {
    try { var l = JSON.parse(window.localStorage.getItem(CONNS_KEY)); return l && l.length != null ? l : []; }
    catch (e) { return []; }
  }
  function lsSet(l) { try { window.localStorage.setItem(CONNS_KEY, JSON.stringify(l)); } catch (e) {} }
  SD.lsConns = lsGet;

  /* guarda no navegador e tambem no PC (abas.json), para nao depender so do navegador */
  SD.saveConns = function () {
    lsSet(SD.conns);
    SD.req("POST", "/api/tabs", JSON.stringify(SD.conns), function (ok, data, status) {
      if (!ok) SD.toast("Computadores não salvos no PC: " + SD.errText(data, status), true);
    });
  };

  /* lista de abas que veio de outro PC no endereco (#sync=...) */
  SD.readSync = function () {
    var m = /[#&]sync=([^&]*)/.exec(location.hash);
    if (!m) return;
    try {
      var l = JSON.parse(decodeURIComponent(m[1]));
      if (l && l.length != null) { synced = l; lsSet(l); }
    } catch (e) {}
    if (window.history && history.replaceState) history.replaceState(null, "", location.pathname);
    else location.hash = "";
  };
  SD.initConns = function () {
    if (!SD.conns.length) SD.conns = synced || lsGet();
  };

  SD.updAvail = function () { return !!(SD.info && SD.info.update && SD.info.update.available); };

  var updToastShown = false;
  SD.loadInfo = function (cb) {
    SD.req("GET", "/api/info", null, function (ok, data) {
      if (ok && data) {
        SD.info = data;
        /* prioridade: lista que veio de outro PC > salva no navegador > salva neste PC */
        if (!SD.conns.length) SD.conns = synced || lsGet();
        if (!SD.conns.length && data.tabs && data.tabs.length) SD.conns = data.tabs;
        synced = null;
        var found = null;
        for (var i = 0; i < SD.conns.length; i++) if (SD.conns[i].host === SD.here) found = SD.conns[i];
        if (!found) SD.conns.unshift({ name: data.name || SD.here, host: SD.here, code: data.code });
        else found.code = data.code;
        SD.saveConns();
        if (SD.renderNav) SD.renderNav();
        if (SD.updAvail() && !updToastShown) {
          updToastShown = true;
          SD.toast("Versão " + (data.update.latest || "nova") + " disponível. Veja em Ajustes.");
        }
      }
      if (cb) cb(ok);
    });
  };

  SD.pingAll = function () {
    for (var i = 0; i < SD.conns.length; i++) {
      (function (h) {
        if (h === SD.here) return;
        var img = new Image(), done = false;
        function fin(v) {
          if (done) return;
          done = true;
          if (SD.alive[h] !== v) { SD.alive[h] = v; if (SD.renderNav) SD.renderNav(); if (SD.onAlive) SD.onAlive(); }
        }
        img.onload = function () { fin(true); };
        img.onerror = function () { fin(false); };
        setTimeout(function () { fin(false); }, 3000);
        img.src = "http://" + h + "/ping.gif?t=" + now();
      })(SD.conns[i].host);
    }
  };

  SD.switchTo = function (idx) {
    var c = SD.conns[idx];
    function go() {
      location.href = "http://" + c.host + "/?k=" + encodeURIComponent(c.code || "") +
        "&sync=" + encodeURIComponent(JSON.stringify(SD.conns));
    }
    if (SD.alive[c.host] === false) {
      SD.alert({ title: "“" + (c.name || c.host) + "” não respondeu",
        msg: "Verifique se o Stream Deck está aberto naquele PC e na mesma rede.",
        buttons: [{ text: "Cancelar", style: "cancel" }, { text: "Abrir mesmo assim", fn: go }] });
      return;
    }
    go();
  };

  /* ------------------------------------------------------ tela cheia --- */
  SD.canFullscreen = function () {
    var d = document.documentElement;
    return !!(d.requestFullscreen || d.webkitRequestFullscreen);
  };
  SD.isFullscreen = function () { return !!(document.fullscreenElement || document.webkitFullscreenElement); };
  /* o celular (deck.js) troca por uma versao que tambem trava a orientacao */
  SD.toggleFullscreen = function () {
    var d = document.documentElement, r = null;
    try {
      if (SD.isFullscreen()) r = (document.exitFullscreen || document.webkitExitFullscreen).call(document);
      else r = (d.requestFullscreen || d.webkitRequestFullscreen).call(d);
    } catch (e) {}
    if (r && r["catch"]) r["catch"](function () {});
    setTimeout(function () { if (SD.layout) SD.layout(); }, 400);
  };

  /* ============================================================ alerta === */
  /* SD.alert({title, msg, buttons:[{text, style: "cancel"|"destructive"|"default", fn}]}) */
  SD.alert = function (o) {
    var wrap = $("alert");
    wrap.innerHTML = "";
    var box = el("div", "al-box", null, wrap);
    var txt = el("div", "al-txt", null, box);
    if (o.title) el("div", "al-t", esc(o.title), txt);
    if (o.msg) el("div", "al-m", esc(o.msg), txt);
    var bts = o.buttons || [{ text: "OK" }];
    var row = el("div", "al-b" + (bts.length === 2 ? " two" : ""), null, box);
    for (var i = 0; i < bts.length; i++) (function (b) {
      var e = el("div", "al-btn" + (b.style ? " " + b.style : ""), esc(b.text), row);
      e.onclick = function () { SD.closeAlert(); if (b.fn) b.fn(); };
    })(bts[i]);
    wrap.style.display = "block";
    setTimeout(function () { wrap.className = "show"; }, 10);
  };
  SD.closeAlert = function () { var w = $("alert"); w.className = ""; w.style.display = "none"; };
  SD.alertOpen = function () { return $("alert").style.display === "block"; };
  SD.confirm = function (title, msg, okText, destructive, fn) {
    SD.alert({ title: title, msg: msg, buttons: [{ text: "Cancelar", style: "cancel" },
      { text: okText, style: destructive ? "destructive" : "default", fn: fn }] });
  };

  /* ============================================================ folhas === */
  /* Uma folha (sheet) com pilha de telas, como a navegacao do iOS.
     view = { title, left:{text,fn}, right:{text,fn,bold}, render(body, view), onLeave() } */
  var stack = [], sheetOpen = false;

  function buildView(v, back) {
    var e = el("div", "view");
    var head = el("div", "sh-head", null, e);
    var hl = el("div", "hb l", null, head), ht = el("div", "ht", esc(v.title || ""), head), hr = el("div", "hb r", null, head);
    var left = v.left;
    if (!left && back) {
      var prev = stack[stack.length - 1], pt = prev && prev.backTitle || prev && prev.title || "Voltar";
      if (pt.length > 14) pt = "Voltar";
      left = { text: pt, back: true, fn: function () { SD.sheet.pop(); } };
    }
    if (left) {
      hl.innerHTML = (left.back ? SD.svg("chevleft", 20, SD.TINT) : "") + "<span>" + esc(left.text) + "</span>";
      if (left.back) hl.className += " back";
      hl.onclick = function () { left.fn(); };
    }
    if (v.right) {
      hr.innerHTML = esc(v.right.text);
      if (v.right.bold) hr.className += " b";
      hr.onclick = function () { if (!SD.hasClass(hr, "off")) v.right.fn(); };
    }
    v.hr = hr; v.ht = ht;
    var body = el("div", "sh-body", null, e);
    v.el = e; v.body = body;
    var inner = el("div", "sh-in", null, body);
    v.inner = inner;
    v.render(inner, v);
    dragHead(head);
    return e;
  }

  function sheetEl() { return $("sheet"); }
  /* tela girada por CSS no celular: usa o referencial da tela girada (SD.toLocal) */
  function localY(t) { return SD.toLocal ? SD.toLocal(t.clientX, t.clientY).y : t.clientY; }

  /* puxar a folha para baixo pelo cabecalho fecha (como no iOS) */
  function dragHead(head) {
    var sy = 0, dy = 0, on = false, sh = sheetEl();
    head.addEventListener("touchstart", function (e) {
      if (e.target !== head && !SD.hasClass(e.target, "ht")) return;
      on = true; sy = localY(e.touches[0]); dy = 0;
      css(sh, "transition", "none");
    }, false);
    head.addEventListener("touchmove", function (e) {
      if (!on) return;
      dy = Math.max(0, localY(e.touches[0]) - sy);
      css(sh, "transform", "translate3d(0," + dy + "px,0)");
      e.preventDefault();
    }, false);
    head.addEventListener("touchend", function () {
      if (!on) return;
      on = false;
      css(sh, "transition", "");
      css(sh, "transform", "");
      if (dy > 110) SD.sheet.cancel();
    }, false);
  }

  function slide(e, x) { css(e, "transform", "translate3d(" + x + ",0,0)"); }

  SD.sheet = {
    open: function (v) {
      var views = $("views");
      for (var i = 0; i < stack.length; i++) if (stack[i].onLeave) stack[i].onLeave();
      stack = [];
      views.innerHTML = "";
      views.appendChild(buildView(v, false));
      stack.push(v);
      var wrap = $("sheetwrap");
      wrap.style.display = "block";
      sheetOpen = true;
      setTimeout(function () { wrap.className = "show"; }, 20);
    },
    push: function (v) {
      var views = $("views"), top = stack[stack.length - 1];
      var e = buildView(v, true);
      slide(e, "100%");
      views.appendChild(e);
      stack.push(v);
      setTimeout(function () {
        slide(e, "0");
        if (top) slide(top.el, "-30%");
        if (top) top.el.style.opacity = "0";
      }, 20);
    },
    pop: function () {
      if (stack.length < 2) return SD.sheet.close();
      var v = stack.pop(), prev = stack[stack.length - 1];
      if (v.onLeave) v.onLeave();
      slide(v.el, "100%");
      prev.el.style.opacity = "1";
      slide(prev.el, "0");
      SD.sheet.refresh(prev);
      setTimeout(function () { if (v.el.parentNode) v.el.parentNode.removeChild(v.el); }, 320);
    },
    /* redesenha a tela mantendo a rolagem */
    refresh: function (v) {
      v = v || stack[stack.length - 1];
      if (!v) return;
      var st = v.body.scrollTop;
      v.inner.innerHTML = "";
      v.render(v.inner, v);
      v.body.scrollTop = st;
    },
    setTitle: function (t) { var v = stack[stack.length - 1]; if (v) v.ht.innerHTML = esc(t); },
    setRight: function (enabled) { var v = stack[stack.length - 1]; if (v && v.hr) SD.setClass(v.hr, "off", !enabled); },
    cancel: function () {
      var root = stack[0];
      if (root && root.onCancel) root.onCancel();
      SD.sheet.close();
    },
    close: function () {
      for (var i = stack.length - 1; i >= 0; i--) if (stack[i].onLeave) stack[i].onLeave();
      var closing = stack;
      stack = [];
      sheetOpen = false;
      var wrap = $("sheetwrap");
      wrap.className = "";
      try { document.activeElement && document.activeElement.blur && document.activeElement.blur(); } catch (e) {}
      setTimeout(function () {
        if (sheetOpen) return;
        wrap.style.display = "none";
        $("views").innerHTML = "";
        for (var j = 0; j < closing.length; j++) if (closing[j].onClosed) closing[j].onClosed();
      }, 320);
    },
    isOpen: function () { return sheetOpen; },
    top: function () { return stack[stack.length - 1]; }
  };

  /* ================================================ componentes de lista === */
  var ui = SD.ui = {};

  /* grupo arredondado (inset grouped). Devolve o elemento da lista; .foot(texto) poe rodape */
  ui.group = function (parent, header, footer) {
    if (header) el("div", "grp-h", esc(header), parent);
    var g = el("div", "grp", null, parent);
    g.foot = function (text, cls, html) {
      var f = el("div", "grp-f" + (cls ? " " + cls : ""), html ? text : esc(text));
      if (g.nextSibling) parent.insertBefore(f, g.nextSibling); else parent.appendChild(f);
      return f;
    };
    if (footer) g.foot(footer);
    return g;
  };

  /* linha: {icon, iconColor, iconHtml, title, sub, value, chevron, check, tint, red, center, bold, onTap, badge} */
  ui.row = function (g, o) {
    var r = el("div", "row" + (o.onTap ? " tap" : "") + (o.center ? " center" : "") + (o.icon || o.iconHtml ? " has-ic" : ""), null, g);
    var h = "";
    if (o.iconHtml) h += o.iconHtml;
    else if (o.icon) h += '<span class="r-ic" style="background:' + esc(o.iconColor || "#8e8e93") + '">' + SD.svg(o.icon, 18) + "</span>";
    var tc = "r-t" + (o.tint ? " tint" : "") + (o.red ? " red" : "") + (o.bold ? " bold" : "") + (o.dim ? " dim" : "");
    h += '<span class="' + tc + '">' + esc(o.title) + (o.sub ? '<span class="r-sub">' + esc(o.sub) + "</span>" : "") + "</span>";
    if (o.badge) h += '<span class="r-badge">' + esc(o.badge) + "</span>";
    if (o.value != null && o.value !== "") h += '<span class="r-v">' + esc(o.value) + "</span>";
    if (o.check) h += '<span class="r-chk">' + SD.svg("check", 18, SD.TINT) + "</span>";
    if (o.chevron) h += '<span class="r-chev">' + SD.svg("chevron", 14, "rgba(235,235,245,0.3)") + "</span>";
    r.innerHTML = h;
    if (o.onTap) r.onclick = function () { o.onTap(r); };
    return r;
  };

  /* linha com campo de texto: rotulo a esquerda, campo ocupando o resto */
  ui.input = function (g, label, value, o) {
    o = o || {};
    var r = el("div", "row in" + (label ? "" : " nolabel"), null, g);
    if (label) el("span", "r-l", esc(label), r);
    var i = el("input", "r-in", null, r);
    i.type = o.type || "text";
    if (o.inputmode) i.setAttribute("inputmode", o.inputmode);
    if (o.min != null) i.min = o.min;
    if (o.max != null) i.max = o.max;
    if (o.step != null) i.step = o.step;
    if (o.maxlength) i.maxLength = o.maxlength;
    i.value = value == null ? "" : value;
    i.placeholder = o.placeholder || "";
    i.setAttribute("autocapitalize", o.autocap ? "sentences" : "off");
    i.setAttribute("autocorrect", "off");
    i.setAttribute("spellcheck", "false");
    if (o.onInput) {
      i.oninput = function () { o.onInput(i.value); };
      i.onchange = function () { o.onInput(i.value); if (o.onChange) o.onChange(i.value); };
    }
    r.onclick = function (e) { if (e.target !== i) i.focus(); };
    return i;
  };

  ui.textarea = function (g, value, o) {
    o = o || {};
    var r = el("div", "row ta", null, g);
    var t = el("textarea", "r-ta", null, r);
    t.value = value == null ? "" : value;
    t.placeholder = o.placeholder || "";
    t.setAttribute("autocapitalize", "off");
    t.setAttribute("autocorrect", "off");
    t.setAttribute("spellcheck", "false");
    if (o.mono) t.className += " mono";
    if (o.onInput) { t.oninput = function () { o.onInput(t.value); }; t.onchange = t.oninput; }
    return t;
  };

  /* chave liga/desliga do iOS */
  ui.switchEl = function (on, onChange) {
    var s = el("span", "sw" + (on ? " on" : ""), "<i></i>");
    s.onclick = function (e) {
      if (e && e.stopPropagation) e.stopPropagation();
      on = !on;
      SD.setClass(s, "on", on);
      onChange(on);
    };
    return s;
  };
  ui.switchRow = function (g, label, on, onChange) {
    var r = el("div", "row tap", '<span class="r-t">' + esc(label) + "</span>", g);
    var s = ui.switchEl(on, onChange);
    r.appendChild(s);
    r.onclick = function (e) { if (e.target === r || (e.target.className || "").indexOf("r-t") >= 0) s.onclick(); };
    return r;
  };

  /* - | + */
  ui.stepperRow = function (g, label, value, min, max, onChange) {
    var r = el("div", "row", '<span class="r-t">' + esc(label) + '</span><span class="r-v num">' + value + "</span>", g);
    var st = el("span", "stp", '<span class="m">' + SD.svg("minus", 16) + '</span><span class="p">' + SD.svg("plus", 16) + "</span>", r);
    var vEl = r.childNodes[1], m = st.firstChild, p = st.lastChild;
    function upd() { SD.setClass(m, "off", value <= min); SD.setClass(p, "off", value >= max); vEl.innerHTML = value; }
    m.onclick = function () { if (value > min) { value--; upd(); onChange(value); } };
    p.onclick = function () { if (value < max) { value++; upd(); onChange(value); } };
    upd();
    return r;
  };

  /* controle segmentado */
  ui.segmented = function (parent, opts, value, onChange) {
    var s = el("div", "seg", null, parent);
    for (var i = 0; i < opts.length; i++) (function (o) {
      var it = el("span", o[0] === value ? "on" : "", esc(o[1]), s);
      it.onclick = function () {
        var sp = s.childNodes;
        for (var j = 0; j < sp.length; j++) sp[j].className = "";
        it.className = "on";
        onChange(o[0]);
      };
    })(opts[i]);
    css(s, "boxSizing", "border-box");
    return s;
  };

  /* lista de escolha nativa (no iOS vira a roleta; no Android, a lista do sistema) */
  ui.selectRow = function (g, label, options, value, onChange) {
    var r = el("div", "row sel tap", null, g);
    el("span", "r-t", esc(label), r);
    var shown = el("span", "r-v", "", r);
    el("span", "r-chev", SD.svg("updown", 14, "rgba(235,235,245,0.3)"), r);
    var s = el("select", "r-sel", null, r);
    var cur = "";
    for (var i = 0; i < options.length; i++) {
      var o = el("option", null, esc(options[i].label), s);
      o.value = String(options[i].value);
      if (String(options[i].value) === String(value)) { o.selected = true; cur = options[i].label; }
    }
    shown.innerHTML = esc(cur);
    s.onchange = function () {
      shown.innerHTML = esc(s.options[s.selectedIndex] ? s.options[s.selectedIndex].text : "");
      onChange(s.value);
    };
    return s;
  };
})();
