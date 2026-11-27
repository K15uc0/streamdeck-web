/* Stream Deck - ponte da extensao com o programa no proprio PC (127.0.0.1).
   Usado pelo service worker (sw.js) e pelos testes (tests/js/extensao.test.js).
   - Parear: codigo curto do Conectar -> chave longa (chrome.storage.local).
   - Abas: manda a lista (id, titulo, endereco, ativa, tocando) quando muda.
   - Comandos: long-poll em /api/browser/commands (ate 25 s).
   Nao le o conteudo das paginas: chrome.scripting so roda no YouTube (pausar e rolar). */
(function (root) {
  "use strict";

  var PORTS = [8765, 8766, 8767];
  var WAIT = 25;
  var YT_RE = /^https:\/\/(www\.|m\.|music\.)?youtube\.com\//;

  function criarPonte(chrome, fetchFn, opt) {
    opt = opt || {};
    var setT = opt.setTimeout || setTimeout, clearT = opt.clearTimeout || clearTimeout;
    var st = { port: null, key: null, running: false, online: false, error: "", polling: false };
    var tabsT = null, gen = 0;

    function sleep(ms) { return new Promise(function (r) { setT(r, ms); }); }
    function p(fn) {   /* chrome.* com callback -> Promise */
      return new Promise(function (res, rej) {
        try {
          fn(function (v) {
            var e = chrome.runtime && chrome.runtime.lastError;
            if (e) rej(new Error(e.message || String(e))); else res(v);
          });
        } catch (e) { rej(e); }
      });
    }

    function call(method, path, body, port, signal) {
      var h = { "Content-Type": "application/json" };
      if (st.key) h["X-StreamDeck-Ext"] = st.key;
      var o = { method: method, headers: h, cache: "no-store" };
      if (body) o.body = JSON.stringify(body);
      if (signal) o.signal = signal;
      return fetchFn("http://127.0.0.1:" + (port || st.port) + path, o).then(function (r) {
        return r.json().then(function (d) { return { status: r.status, data: d }; },
          function () { return { status: r.status, data: null }; });
      });
    }

    /* acha a porta do programa: a primeira que responde /api/browser/hello */
    function findPort() {
      var i = 0;
      function next() {
        if (i >= PORTS.length) return Promise.resolve(null);
        var port = PORTS[i++];
        return call("GET", "/api/browser/hello", null, port).then(function (r) {
          return r.status === 200 && r.data && r.data.app === "streamdeck" ? port : next();
        }, next);
      }
      return next();
    }

    function load() {
      return p(function (cb) { chrome.storage.local.get(["port", "key"], cb); }).then(function (v) {
        st.port = (v && v.port) || null; st.key = (v && v.key) || null;
        return st;
      });
    }

    function pair(code, port) {
      code = String(code || "").replace(/[\s-]/g, "").toUpperCase();
      if (!/^[A-Z0-9]{4,12}$/.test(code)) return Promise.reject(new Error("Digite o código mostrado no Conectar."));
      var pr = port ? Promise.resolve(port) : findPort();
      return pr.then(function (pt) {
        if (!pt) throw new Error("Stream Deck não encontrado neste PC. Ele está aberto?");
        st.key = null;
        return call("POST", "/api/browser/pair", { code: code }, pt).then(function (r) {
          if (r.status !== 200 || !r.data || !r.data.key) throw new Error((r.data && r.data.error) || "Não pareou.");
          st.port = pt; st.key = r.data.key; st.error = "";
          return p(function (cb) { chrome.storage.local.set({ port: pt, key: st.key }, cb); });
        });
      }).then(function () { start(); return status(); });
    }

    function unpair() {
      stop();
      st.key = null; st.online = false;
      return p(function (cb) { chrome.storage.local.remove(["key"], cb); }).then(status);
    }

    function status() {
      return { paired: !!st.key, port: st.port, online: st.online, error: st.error };
    }

    /* ---------------------------------------------------------- abas --- */
    function snapshot() {
      return Promise.all([
        p(function (cb) { chrome.tabs.query({}, cb); }),
        p(function (cb) { chrome.windows.getLastFocused({}, cb); }).catch(function () { return null; })
      ]).then(function (r) {
        var tabs = r[0] || [], fw = r[1] && r[1].id;
        return tabs.map(function (t) {
          return { id: t.id, window: t.windowId, title: t.title || "", url: t.url || t.pendingUrl || "",
                   active: !!t.active, audible: !!t.audible, current: !!(t.active && t.windowId === fw) };
        });
      });
    }
    function sendTabs() {
      if (!st.key || !st.port) return Promise.resolve(false);
      return snapshot().then(function (tabs) {
        return call("POST", "/api/browser/tabs", { tabs: tabs });
      }).then(function (r) {
        if (r.status === 401) return lost();
        st.online = r.status === 200;
        return st.online;
      }, function () { st.online = false; return false; });
    }
    function tabsChanged() {
      if (!st.key) return;
      clearT(tabsT);
      tabsT = setT(function () { tabsT = null; sendTabs(); }, opt.debounce == null ? 400 : opt.debounce);
    }

    /* ------------------------------------------------------ comandos --- */
    function activeTab() {
      return p(function (cb) { chrome.tabs.query({ active: true, lastFocusedWindow: true }, cb); })
        .then(function (ts) { return ts && ts[0]; });
    }
    function ytTab() {
      return p(function (cb) { chrome.tabs.query({}, cb); }).then(function (ts) {
        var yt = (ts || []).filter(function (t) { return YT_RE.test(t.url || ""); });
        var pick = function (f) { for (var i = 0; i < yt.length; i++) if (f(yt[i])) return yt[i]; return null; };
        return pick(function (t) { return t.audible; }) || pick(function (t) { return t.active; }) || yt[0] || null;
      });
    }
    function inTab(tab, fn, args) {
      if (!tab) return Promise.resolve(null);
      return chrome.scripting.executeScript({ target: { tabId: tab.id }, func: fn, args: args || [] })
        .then(function (r) { return r && r[0] ? r[0].result : null; });
    }
    /* rodam DENTRO da pagina do YouTube (sem acesso a nada da extensao) */
    function ytToggle() {
      var v = document.querySelector("video");
      if (!v) return null;
      if (v.paused) v.play(); else v.pause();
      return !v.paused;
    }
    function scrollPage(dir) {
      var h = window.innerHeight * 0.85;
      if (dir === "top") window.scrollTo({ top: 0, behavior: "smooth" });
      else if (dir === "bottom") window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
      else window.scrollBy({ top: dir === "up" ? -h : h, behavior: "smooth" });
      return true;
    }
    function focus(t) {
      return p(function (cb) { chrome.tabs.update(t.id, { active: true }, cb); }).then(function () {
        return p(function (cb) { chrome.windows.update(t.windowId, { focused: true }, cb); }).catch(function () {});
      });
    }
    function step(d) {
      return activeTab().then(function (a) {
        if (!a) return;
        return p(function (cb) { chrome.tabs.query({ windowId: a.windowId }, cb); }).then(function (ts) {
          ts.sort(function (x, y) { return x.index - y.index; });
          var i = 0;
          for (; i < ts.length; i++) if (ts[i].id === a.id) break;
          var n = ts[(i + d + ts.length) % ts.length];
          return p(function (cb) { chrome.tabs.update(n.id, { active: true }, cb); });
        });
      });
    }
    function withActive(fn) { return activeTab().then(function (a) { if (a) return fn(a); }); }

    function run(cmd) {
      switch (cmd && cmd.op) {
        case "activate":
          return p(function (cb) { chrome.tabs.get(cmd.tab, cb); }).then(focus);
        case "close_tab":
          if (cmd.tab != null) return p(function (cb) { chrome.tabs.remove(cmd.tab, cb); });
          return withActive(function (a) { return p(function (cb) { chrome.tabs.remove(a.id, cb); }); });
        case "open_url":
          if (!/^https?:\/\//.test(cmd.url || "")) return Promise.resolve();
          return p(function (cb) { chrome.tabs.create({ url: cmd.url, active: true }, cb); });
        case "tab_next": return step(1);
        case "tab_prev": return step(-1);
        case "back": return withActive(function (a) { return p(function (cb) { chrome.tabs.goBack(a.id, cb); }); });
        case "forward": return withActive(function (a) { return p(function (cb) { chrome.tabs.goForward(a.id, cb); }); });
        case "reload": return withActive(function (a) { return p(function (cb) { chrome.tabs.reload(a.id, {}, cb); }); });
        case "yt_toggle": return ytTab().then(function (t) { return inTab(t, ytToggle); });
        case "scroll": return activeTab().then(function (a) {
          return a && YT_RE.test(a.url || "") ? inTab(a, scrollPage, [cmd.dir]) : null;
        });
      }
      return Promise.resolve();
    }

    function lost() {   /* chave nao vale mais (desfeito no Conectar) */
      st.error = "Pareamento desfeito no PC. Pareie de novo.";
      st.online = false;
      return unpair().then(function () { return false; });
    }

    /* long-poll; um so laco por vez (gen) */
    function loop(my) {
      if (!st.running || my !== gen) return Promise.resolve();
      st.polling = true;
      return call("GET", "/api/browser/commands?wait=" + WAIT).then(function (r) {
        if (r.status === 401) return lost();
        if (r.status !== 200 || !r.data) { st.online = false; return sleep(5000); }
        var first = !st.online;
        st.online = true; st.error = "";
        if (first) sendTabs();
        var cmds = r.data.commands || [], chain = Promise.resolve();
        cmds.forEach(function (c) { chain = chain.then(function () { return run(c); }).catch(function () {}); });
        return chain.then(function () {
          if (cmds.length) tabsChanged();
          /* sempre devolve a vez ao navegador; sem comandos espera um pouco
             (o servidor ja segura o pedido ate 25 s, isto so evita laco apertado) */
          return sleep(r.data.busy ? 3000 : cmds.length ? 0 : 250);
        });
      }, function () {
        st.online = false;
        /* programa fechado ou mudou de porta: procura de novo */
        return sleep(5000).then(findPort).then(function (pt) {
          if (pt && pt !== st.port) { st.port = pt; chrome.storage.local.set({ port: pt }); }
        });
      }).then(function () { st.polling = false; return loop(my); });
    }

    var alive = null;
    function start() {
      if (!st.key || !st.port) return false;
      if (st.running) return true;
      st.running = true;
      gen++;
      /* chamar uma API do Chrome de tempos em tempos mantem o service worker vivo */
      if (!alive && !opt.noKeepAlive) alive = setInterval(function () { chrome.runtime.getPlatformInfo(function () {}); }, 20000);
      sendTabs();
      loop(gen);
      return true;
    }
    function stop() {
      st.running = false;
      gen++;
      if (alive) { clearInterval(alive); alive = null; }
    }

    return { load: load, pair: pair, unpair: unpair, status: status, start: start, stop: stop, run: run,
             sendTabs: sendTabs, tabsChanged: tabsChanged, findPort: findPort, snapshot: snapshot, _st: st,
             _loop: function () { return loop(gen); } };
  }

  root.criarPonte = criarPonte;
  root.PONTE_PORTS = PORTS;
  if (typeof module !== "undefined" && module.exports) module.exports = { criarPonte: criarPonte, PORTS: PORTS };
})(typeof self !== "undefined" ? self : this);
