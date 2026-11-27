/* Testes da ponte da extensao (extensao/ponte.js) com um "chrome" e um fetch
   falsos: achar a porta, parear, mandar abas, long-poll e comandos.
   Rodar: node tests/js/extensao.test.js */
"use strict";
var assert = require("assert");
var path = require("path");
var criarPonte = require(path.join(__dirname, "..", "..", "extensao", "ponte.js")).criarPonte;

function fakeChrome() {
  var store = {}, calls = [];
  var tabs = [
    { id: 1, index: 0, windowId: 9, title: "Notícias", url: "https://g1.globo.com/", active: false, audible: false },
    { id: 2, index: 1, windowId: 9, title: "Vídeo", url: "https://www.youtube.com/watch?v=1", active: true, audible: true },
    { id: 3, index: 2, windowId: 9, title: "Busca", url: "https://www.google.com/", active: false, audible: false }
  ];
  function rec(name) { return function () { calls.push([name].concat([].slice.call(arguments, 0, -1))); arguments[arguments.length - 1](); }; }
  var c = {
    runtime: { lastError: null, getPlatformInfo: function (cb) { cb({}); } },
    storage: { local: {
      get: function (keys, cb) { var o = {}; keys.forEach(function (k) { if (k in store) o[k] = store[k]; }); cb(o); },
      set: function (o, cb) { Object.keys(o).forEach(function (k) { store[k] = o[k]; }); if (cb) cb(); },
      remove: function (keys, cb) { keys.forEach(function (k) { delete store[k]; }); cb(); }
    } },
    tabs: {
      query: function (q, cb) {
        var r = tabs.filter(function (t) {
          if (q.active && !t.active) return false;
          if (q.windowId && t.windowId !== q.windowId) return false;
          return true;
        });
        cb(r.slice());
      },
      get: function (id, cb) { cb(tabs.filter(function (t) { return t.id === id; })[0]); },
      update: function (id, o, cb) { calls.push(["update", id, o]); cb(); },
      remove: rec("remove"), create: rec("create"), goBack: rec("goBack"), goForward: rec("goForward"),
      reload: function (id, o, cb) { calls.push(["reload", id]); cb(); }
    },
    windows: {
      getLastFocused: function (o, cb) { cb({ id: 9 }); },
      update: function (id, o, cb) { calls.push(["focus", id]); cb(); }
    },
    scripting: { executeScript: function (o) { calls.push(["script", o.target.tabId, o.func.name, o.args]); return Promise.resolve([{ result: true }]); } }
  };
  c._store = store; c._calls = calls; c._tabs = tabs;
  return c;
}

/* servidor falso: porta 8766 e a do programa */
function fakeServer() {
  var s = { reqs: [], queue: [], key: "k".repeat(64), code: "ABC234" };
  s.fetch = function (url, o) {
    var m = /^http:\/\/127\.0\.0\.1:(\d+)(\/[^?]*)/.exec(url), port = +m[1], p = m[2];
    s.reqs.push({ port: port, path: p, method: o.method, headers: o.headers, body: o.body ? JSON.parse(o.body) : null });
    if (port !== 8766) return Promise.reject(new TypeError("Failed to fetch"));
    function res(status, d) { return Promise.resolve({ status: status, json: function () { return Promise.resolve(d); } }); }
    var authed = o.headers["X-StreamDeck-Ext"] === s.key;
    if (p === "/api/browser/hello") return res(200, { ok: true, app: "streamdeck" });
    if (p === "/api/browser/pair") {
      return JSON.parse(o.body).code === s.code ? res(200, { ok: true, key: s.key }) : res(400, { ok: false, error: "codigo errado" });
    }
    if (!authed) return res(401, { ok: false });
    if (p === "/api/browser/tabs") return res(200, { ok: true });
    if (p === "/api/browser/commands") return res(200, { ok: true, commands: s.queue.splice(0) });
    return res(404, {});
  };
  return s;
}

var timers = { setTimeout: function (fn) { setImmediate(fn); return 1; }, clearTimeout: function () {} };

function nova(c, s) { return criarPonte(c, s.fetch, { setTimeout: timers.setTimeout, clearTimeout: timers.clearTimeout, debounce: 0, noKeepAlive: true }); }

async function testPareamento() {
  var c = fakeChrome(), s = fakeServer(), p = nova(c, s);
  await p.load();
  assert.strictEqual(await p.findPort(), 8766);
  await assert.rejects(p.pair("errado"), /código|codigo/i);
  await assert.rejects(p.pair("ZZZ999"), /codigo errado/);
  var st = await p.pair("abc-234");
  p.stop();
  assert.ok(st.paired);
  assert.strictEqual(c._store.key, s.key);
  assert.strictEqual(c._store.port, 8766);
  /* so fala com 127.0.0.1 */
  s.reqs.forEach(function (r) { assert.ok([8765, 8766, 8767].indexOf(r.port) >= 0); });
  await p.unpair();
  assert.ok(!("key" in c._store));
}

async function testAbas() {
  var c = fakeChrome(), s = fakeServer(), p = nova(c, s);
  c._store.key = s.key; c._store.port = 8766;
  await p.load();
  await p.sendTabs();
  var r = s.reqs.filter(function (x) { return x.path === "/api/browser/tabs"; }).pop();
  assert.strictEqual(r.headers["X-StreamDeck-Ext"], s.key);
  assert.strictEqual(r.body.tabs.length, 3);
  assert.deepStrictEqual(r.body.tabs[1], { id: 2, window: 9, title: "Vídeo", url: "https://www.youtube.com/watch?v=1",
                                         active: true, audible: true, current: true });
  assert.ok(p.status().online);
}

async function testComandos() {
  var c = fakeChrome(), s = fakeServer(), p = nova(c, s);
  c._store.key = s.key; c._store.port = 8766;
  await p.load();
  await p.run({ op: "activate", tab: 3 });
  await p.run({ op: "close_tab", tab: 1 });
  await p.run({ op: "close_tab" });
  await p.run({ op: "open_url", url: "https://exemplo.com/" });
  await p.run({ op: "open_url", url: "javascript:alert(1)" });
  await p.run({ op: "tab_next" });
  await p.run({ op: "tab_prev" });
  await p.run({ op: "back" });
  await p.run({ op: "forward" });
  await p.run({ op: "reload" });
  await p.run({ op: "yt_toggle" });
  await p.run({ op: "scroll", dir: "down" });
  assert.deepStrictEqual(c._calls, [
    ["update", 3, { active: true }], ["focus", 9],
    ["remove", 1], ["remove", 2],
    ["create", { url: "https://exemplo.com/", active: true }],
    ["update", 3, { active: true }], ["update", 1, { active: true }],
    ["goBack", 2], ["goForward", 2], ["reload", 2],
    ["script", 2, "ytToggle", []], ["script", 2, "scrollPage", ["down"]]
  ]);
  /* rolar fora do YouTube: a extensao nao tem permissao (o servidor usa atalho) */
  c._calls.length = 0;
  c._tabs[1].active = false; c._tabs[0].active = true;
  await p.run({ op: "scroll", dir: "up" });
  assert.deepStrictEqual(c._calls, []);
}

async function testLongPoll() {
  var c = fakeChrome(), s = fakeServer(), p = nova(c, s);
  c._store.key = s.key; c._store.port = 8766;
  await p.load();
  s.queue.push({ op: "reload" });
  p.start();
  await new Promise(function (r) { setTimeout(r, 30); });
  assert.ok(c._calls.some(function (x) { return x[0] === "reload"; }));
  assert.ok(s.reqs.some(function (x) { return x.path === "/api/browser/commands"; }));
  /* chave desfeita no PC: para e esquece a chave */
  s.key = "outra";
  await new Promise(function (r) { setTimeout(r, 30); });
  assert.ok(!p.status().paired);
  assert.ok(!("key" in c._store));
  p.stop();
}

(async function () {
  var tests = [testPareamento, testAbas, testComandos, testLongPoll];
  for (var i = 0; i < tests.length; i++) {
    await tests[i]();
    console.log("ok - " + tests[i].name);
  }
  console.log("extensao: " + tests.length + " testes ok");
})().catch(function (e) { console.error(e); process.exit(1); });
