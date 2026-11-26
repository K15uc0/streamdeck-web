/* Testes das funcoes puras de web/js/core.js (SD.flow, SD.geometry, SD.isEmpty,
   SD.remapPages), sem dependencias: carrega o arquivo com o modulo vm do Node
   numa janela/documento falsos. Rodar: node tests/js/flow.test.js */
"use strict";
var fs = require("fs");
var path = require("path");
var vm = require("vm");
var assert = require("assert");

function loadCore() {
  var src = fs.readFileSync(path.join(__dirname, "..", "..", "web", "js", "core.js"), "utf8");
  var store = {};
  function fakeEl() {
    return { style: {}, className: "", childNodes: [], appendChild: function () {}, addEventListener: function () {} };
  }
  var win = {
    location: { search: "?k=abc", host: "127.0.0.1:8765", hash: "", pathname: "/" },
    localStorage: {
      getItem: function (k) { return store.hasOwnProperty(k) ? store[k] : null; },
      setItem: function (k, v) { store[k] = String(v); },
      removeItem: function (k) { delete store[k]; }
    },
    navigator: {},
    document: {
      getElementById: function () { return fakeEl(); },
      createElement: function () { return fakeEl(); },
      addEventListener: function () {},
      documentElement: fakeEl(),
      body: fakeEl()
    },
    history: { replaceState: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: function () { return 0; }, clearInterval: function () {},
    XMLHttpRequest: function () {},
    addEventListener: function () {},
    console: console, Math: Math, JSON: JSON, Date: Date
  };
  win.window = win;
  win.self = win;
  vm.createContext(win);
  vm.runInContext(src, win, { filename: "core.js" });
  return win.SD;
}

var SD = loadCore();
var passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log("ok   " + name); }
  catch (e) { failed++; console.log("FALHA " + name + "\n      " + (e && e.stack || e)); }
}
/* objetos do contexto vm tem outro Object.prototype: compara via JSON */
function same(a, b, msg) { assert.deepStrictEqual(JSON.parse(JSON.stringify(a)), b, msg); }

test("carrega e le o codigo da url", function () {
  assert.strictEqual(typeof SD.flow, "function");
  assert.strictEqual(SD.TOKEN, "abc");
});

/* ------------------------------------------------------------- flow --- */
test("flow: botoes 1x1 linha a linha", function () {
  var r = SD.flow([{}, {}, {}, {}], 3, 2);
  same(r, [{ i: 0, x: 0, y: 0, w: 1, h: 1 }, { i: 1, x: 1, y: 0, w: 1, h: 1 },
           { i: 2, x: 2, y: 0, w: 1, h: 1 }, { i: 3, x: 0, y: 1, w: 1, h: 1 }]);
});

test("flow: botao grande e preenchimento denso", function () {
  var r = SD.flow([{ w: 2, h: 2 }, {}, {}, {}, {}], 3, 3);
  same(r, [{ i: 0, x: 0, y: 0, w: 2, h: 2 }, { i: 1, x: 2, y: 0, w: 1, h: 1 },
           { i: 2, x: 2, y: 1, w: 1, h: 1 }, { i: 3, x: 0, y: 2, w: 1, h: 1 },
           { i: 4, x: 1, y: 2, w: 1, h: 1 }]);
});

test("flow: o que nao cabe fica de fora, sem sobreposicao", function () {
  var bs = [{ w: 3 }, { w: 2, h: 2 }, {}, {}, {}, {}, {}];
  var r = SD.flow(bs, 3, 2);
  var used = {};
  r.forEach(function (p) {
    for (var y = p.y; y < p.y + p.h; y++) for (var x = p.x; x < p.x + p.w; x++) {
      assert.ok(!used[x + ":" + y], "sobreposicao em " + x + ":" + y);
      assert.ok(x < 3 && y < 2, "fora da grade");
      used[x + ":" + y] = true;
    }
  });
  same(r.map(function (p) { return p.i; }), [0, 2, 3, 4]);   /* 2x2 nao cabe sob a linha cheia */
});

test("flow: tamanho limitado a grade e valores ruins", function () {
  var r = SD.flow([{ w: 9, h: 9 }], 2, 2);
  same(r, [{ i: 0, x: 0, y: 0, w: 2, h: 2 }]);
  r = SD.flow([{ w: "x", h: 0 }, null, { w: -3 }], 3, 1);
  same(r.map(function (p) { return [p.w, p.h]; }), [[1, 1], [1, 1], [1, 1]]);
  same(SD.flow(null, 3, 3), []);
  same(SD.flow([], 3, 3), []);
});

test("flow: botao maior que o espaco restante pula para a proxima linha", function () {
  var r = SD.flow([{}, {}, { w: 2 }], 3, 2);
  same(r[2], { i: 2, x: 0, y: 1, w: 2, h: 1 });
});

/* --------------------------------------------------------- geometry --- */
test("geometry: blocos dentro da tela e area cheia", function () {
  [[390, 844, 3, 5], [844, 390, 5, 3], [1180, 820, 5, 3], [320, 480, 4, 6]].forEach(function (c) {
    var ins = SD.deviceArea({ t: 20, b: 10 });
    var g = SD.geometry(c[0], c[1], c[2], c[3], ins);
    assert.strictEqual(g.cols, c[2]);
    assert.ok(g.w >= 24 && g.h >= 24);
    assert.ok(g.gap >= 6 && g.gap <= 20);
    var last = g.rect(c[2] - 1, c[3] - 1);
    assert.ok(g.x0 >= ins.l, "x0");
    assert.ok(g.y0 >= ins.t, "y0");
    assert.ok(last.x + last.w <= c[0] - ins.r, "passou da direita " + JSON.stringify(c));
    assert.ok(last.y + last.h <= c[1] - ins.b, "passou de baixo " + JSON.stringify(c));
    /* ocupa quase toda a area (sobra so arredondamento + margem lateral) */
    assert.ok(c[0] - ins.l - ins.r - g.gw <= 2 * 16 + c[2], "largura mal usada");
    assert.ok(c[1] - ins.t - ins.b - g.gh <= 6 + c[3], "altura mal usada");
  });
});

test("geometry: rect de bloco grande soma celulas e espacos", function () {
  var g = SD.geometry(1000, 600, 4, 3, {});
  var r = g.rect(1, 1, 2, 2);
  assert.strictEqual(r.x, g.x0 + g.w + g.gap);
  assert.strictEqual(r.w, 2 * g.w + g.gap);
  assert.strictEqual(r.h, 2 * g.h + g.gap);
  var g0 = SD.geometry(100, 100, 0, 0);
  assert.strictEqual(g0.cols, 1);
  assert.strictEqual(g0.rows, 1);
});

test("deviceArea: barra e pontos com margem segura", function () {
  var a = SD.deviceArea();
  assert.strictEqual(a.t, SD.NAV_H);
  assert.strictEqual(a.b, 4 + SD.DOTS_H);
  a = SD.deviceArea({ t: 47, b: 34, l: 5, r: 6 });
  assert.strictEqual(a.t, 47 + SD.NAV_H);
  assert.strictEqual(a.b, 34 + SD.DOTS_H);
  assert.strictEqual(a.l, 5);
});

/* ---------------------------------------------------------- isEmpty --- */
test("isEmpty", function () {
  assert.strictEqual(SD.isEmpty(null), true);
  assert.strictEqual(SD.isEmpty(SD.emptyButton()), true);
  assert.strictEqual(SD.isEmpty({ label: "  ", action: { type: "none" } }), true);
  assert.strictEqual(SD.isEmpty({}), true);
  [{ label: "x" }, { icon: "play" }, { color: "#fff000" }, { toggle: true }, { image: "a.png" },
   { live: "clock" }, { textColor: "#ffffff" }, { action: { type: "hotkey", keys: ["a"] } },
   { kind: "fader", target: "master" }, { kind: "folder", buttons: [] }].forEach(function (b) {
    assert.strictEqual(SD.isEmpty(b), false, JSON.stringify(b));
  });
});

/* ------------------------------------------------------- remapPages --- */
function cfgPaginas() {
  return { pages: [
    { buttons: [{ label: "A", action: { type: "page", to: 1 } },
                { label: "B", action: { type: "page", to: 2 } },
                { label: "C", action: { type: "multi", steps: [{ type: "page", to: 2 }, { type: "hotkey", keys: ["a"] }, { type: "page", to: 1 }] } },
                { label: "D", action: { type: "hotkey", keys: ["f1"] } },
                null] },
    { buttons: [{ label: "Voltar", action: { type: "page", to: 0 } }] },
    { buttons: [] }
  ] };
}

test("remapPages sem esquema: troca indices e esvazia quem perdeu o destino", function () {
  SD.actionMap = {};
  var c = cfgPaginas();
  SD.remapPages(c, { 0: 0, 1: -1, 2: 1 });   /* pagina 1 apagada */
  assert.ok(SD.isEmpty(c.pages[0].buttons[0]), "A deveria ficar vazio");
  assert.strictEqual(c.pages[0].buttons[1].action.to, 1);
  same(c.pages[0].buttons[2].action.steps, [{ type: "page", to: 1 }, { type: "hotkey", keys: ["a"] }]);
  assert.strictEqual(c.pages[0].buttons[3].action.type, "hotkey");
  assert.strictEqual(c.pages[1].buttons[0].action.to, 0);
});

test("remapPages com esquema (de /api/actions): troca de ordem", function () {
  SD.actionMap = {
    page: { type: "page", fields: [{ key: "to", kind: "page" }] },
    multi: { type: "multi", fields: [{ key: "steps", kind: "steps" }, { key: "delay", kind: "number" }] },
    hotkey: { type: "hotkey", fields: [{ key: "keys", kind: "keys" }] }
  };
  var c = cfgPaginas();
  SD.remapPages(c, { 0: 2, 1: 0, 2: 1 });
  assert.strictEqual(c.pages[0].buttons[0].action.to, 0);
  assert.strictEqual(c.pages[0].buttons[1].action.to, 1);
  var st = c.pages[0].buttons[2].action.steps;
  assert.strictEqual(st.length, 3);
  assert.strictEqual(st[0].to, 1);
  assert.strictEqual(st[1].type, "hotkey");
  assert.strictEqual(st[2].to, 0);
  assert.strictEqual(c.pages[1].buttons[0].action.to, 2);
  SD.actionMap = {};
});

test("remapPages: segurar, toque duplo e pastas", function () {
  SD.actionMap = {};
  var c = { pages: [
    { buttons: [
      { label: "H", action: { type: "hotkey", keys: ["a"] }, hold: { type: "page", to: 2 },
        double: { type: "multi", steps: [{ type: "page", to: 1 }, { type: "page", to: 2 }] } },
      { label: "X", action: { type: "none" }, hold: { type: "page", to: 1 }, double: { type: "page", to: 2 } },
      { kind: "folder", label: "P", buttons: [
        { label: "F1", action: { type: "page", to: 2 }, hold: { type: "page", to: 1 } },
        { label: "F2", action: { type: "page", to: 1 } }] }] },
    { buttons: [] }, { buttons: [] }
  ] };
  SD.remapPages(c, { 0: 0, 1: -1, 2: 1 });
  var b = c.pages[0].buttons;
  assert.strictEqual(b[0].hold.to, 1);
  same(b[0].double.steps, [{ type: "page", to: 1 }]);
  assert.strictEqual(b[1].hold, undefined);
  assert.strictEqual(b[1].double.to, 1);
  var f = b[2].buttons;
  assert.strictEqual(f[0].action.to, 1);
  assert.strictEqual(f[0].hold, undefined);
  assert.ok(SD.isEmpty(f[1]), "F2 deveria ficar vazio");
});

/* -------------------------------------------------------- pageGrid --- */
test("pageGrid: sem grade propria usa a geral", function () {
  var c = { columns: 4, rows: 3, pages: [{ buttons: [] }] };
  assert.strictEqual(SD.pageGrid(c, 0), c);
  assert.strictEqual(SD.pageGrid(c, 5), c);
});
test("pageGrid: grade propria da pagina", function () {
  var g = { columns: 5, rows: 4 };
  var c = { columns: 4, rows: 3, pages: [{ buttons: [] }, { grid: g, buttons: [] }] };
  assert.strictEqual(SD.pageGrid(c, 1), g);
  assert.strictEqual(SD.pageGrid(c, 0), c);
});
test("pageGrid: grade propria invalida cai na geral", function () {
  var c = { columns: 4, rows: 3, pages: [{ grid: { columns: 11, rows: 2 } }, { grid: { columns: 3 } }] };
  assert.strictEqual(SD.pageGrid(c, 0), c);
  assert.strictEqual(SD.pageGrid(c, 1), c);
});
/* mesmos casos de tests/test_grade2101.py (schema.flow, migracao 2.10.1) */
test("flow: igual ao schema.flow do Python", function () {
  function b(o) { return Object.assign({ label: "X" }, o || {}); }
  var f = SD.flow([b({ w: 2, h: 2 }), b(), b({ w: 9 }), b({ h: 2 })], 4, 3).map(function (p) { return [p.i, p.x, p.y, p.w, p.h]; });
  assert.deepStrictEqual(f, [[0, 0, 0, 2, 2], [1, 2, 0, 1, 1], [2, 0, 2, 4, 1], [3, 3, 0, 1, 2]]);
  assert.strictEqual(SD.flow([b(), b(), b()], 1, 2).length, 2);
});

console.log("\n" + passed + " ok, " + failed + " com falha");
process.exit(failed ? 1 : 0);
