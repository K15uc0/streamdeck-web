/* Teste de fumaca no navegador (Playwright + Chromium).
   Sobe o servidor (python server.py) com dados numa pasta temporaria, abre a
   pagina do celular em 390x844 e 1180x820 e o editor do PC em 1440x900.
   Qualquer erro no console da pagina faz o teste falhar.
   Rodar: node tests/e2e/smoke.js   (PYTHON=python3 por padrao) */
"use strict";
var fs = require("fs");
var os = require("os");
var path = require("path");
var cp = require("child_process");
var assert = require("assert");
var playwright = require("playwright");

var ROOT = path.join(__dirname, "..", "..");
var PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

var CONFIG = {
  version: 2, title: "Teste", columns: 4, rows: 3,
  pages: [
    { name: "Um", buttons: [
      { label: "ON AIR", icon: "onair", color: "#ff453a", toggle: true, action: { type: "hotkey", keys: ["f9"] } },
      { label: "Copiar", icon: "copy", color: "#0a84ff", action: { type: "hotkey", keys: ["ctrl", "c"] } },
      { kind: "folder", label: "Pasta", icon: "folder", buttons: [
        { label: "Dentro", action: { type: "hotkey", keys: ["f5"] } }
      ] },
      { kind: "fader", label: "Efeitos", icon: "music", target: "effects" },
      { label: "Ir 2", icon: "forward", action: { type: "page", to: 1 } },
      { label: "", icon: "cpu", live: "pc:cpu" },
      { kind: "monitor", label: "Monitor" },
      { kind: "monitor" }
    ] },
    { name: "Dois", buttons: [{ label: "Voltar", icon: "back", action: { type: "page", to: 0 } }] },
    { name: "Tres", grid: { columns: 5, rows: 2, portrait: { columns: 2, rows: 5 } }, buttons: [
      { label: "A", action: { type: "hotkey", keys: ["f1"] } },
      { label: "B", action: { type: "hotkey", keys: ["f2"] } }
    ] }
  ]
};

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

function startServer(data) {
  fs.writeFileSync(path.join(data, "config.json"), JSON.stringify(CONFIG));
  var env = Object.assign({}, process.env, {
    STREAMDECK_DATA: data, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8",
    STREAMDECK_UPDATE_URL: "http://127.0.0.1:9/sem-rede"
  });
  var proc = cp.spawn(PY, ["server.py", "--minimizado"], { cwd: ROOT, env: env });
  var log = "";
  proc.stdout.on("data", function (d) { log += d; });
  proc.stderr.on("data", function (d) { log += d; });
  return new Promise(function (resolve, reject) {
    var t0 = Date.now();
    (function wait() {
      var m = /127\.0\.0\.1:(\d+)\/conectar/.exec(log);
      if (m) return resolve({ proc: proc, port: +m[1], log: function () { return log; } });
      if (proc.exitCode != null) return reject(new Error("servidor saiu:\n" + log));
      if (Date.now() - t0 > 20000) return reject(new Error("servidor nao subiu:\n" + log));
      setTimeout(wait, 100);
    })();
  });
}

function watchConsole(page, errors, name) {
  page.on("console", function (m) { if (m.type() === "error") errors.push(name + ": console: " + m.text()); });
  page.on("pageerror", function (e) { errors.push(name + ": pageerror: " + e.message); });
}

async function phone(browser, base, token, size, errors) {
  var name = "celular " + size.width + "x" + size.height;
  var ctx = await browser.newContext({ viewport: size, hasTouch: false });
  var page = await ctx.newPage();
  watchConsole(page, errors, name);
  await page.goto(base + "/?k=" + token);
  var cells = page.locator("#grid .cell:not(.empty-cell)");
  await cells.first().waitFor({ state: "visible", timeout: 10000 });
  var n = await cells.count();
  assert.ok(n >= 5, name + ": blocos desenhados: " + n);
  /* blocos dentro da tela */
  var boxes = await cells.evaluateAll(function (els) {
    return els.map(function (e) { var r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; });
  });
  boxes.forEach(function (b) {
    assert.ok(b[0] >= -1 && b[1] >= -1 && b[2] <= size.width + 1 && b[3] <= size.height + 1,
      name + ": bloco fora da tela " + JSON.stringify(b));
  });

  /* toque num botao -> /api/press ok */
  var pressed = page.waitForResponse(function (r) { return r.url().indexOf("/api/press?p=0&b=1") >= 0; });
  await page.locator("#grid .cell", { hasText: "Copiar" }).click();
  var resp = await pressed;
  assert.strictEqual(resp.status(), 200);
  assert.strictEqual((await resp.json()).ok, true);

  /* liga/desliga acende */
  var lit = page.waitForResponse(function (r) { return r.url().indexOf("/api/press?p=0&b=0") >= 0; });
  await page.locator("#grid .cell", { hasText: "ON AIR" }).click();
  assert.deepStrictEqual((await (await lit).json()).toggles, { "0:0": true });
  await page.locator("#grid .cell .key.lit").first().waitFor({ timeout: 5000 });
  /* desliga de novo para o proximo tamanho comecar igual */
  lit = page.waitForResponse(function (r) { return r.url().indexOf("/api/press?p=0&b=0") >= 0; });
  await page.locator("#grid .cell", { hasText: "ON AIR" }).click();
  await lit;

  /* toque num bloco vazio nao faz nada (nem erro no console) */
  var nErr = errors.length;
  await page.locator("#grid .cell.empty-cell").first().click();
  await page.waitForTimeout(200);
  assert.strictEqual(errors.length, nErr, name + ": erro ao tocar bloco vazio: " + errors.slice(nErr).join("; "));

  /* pasta abre e fecha */
  await page.locator("#grid .cell", { hasText: "Pasta" }).click();
  await page.locator("#folder").waitFor({ state: "visible", timeout: 5000 });
  await page.locator("#fgrid .cell", { hasText: "Dentro" }).waitFor({ state: "visible", timeout: 5000 });
  var fp = page.waitForResponse(function (r) { return r.url().indexOf("/api/press?") >= 0 && r.url().indexOf("&f=0") >= 0; });
  await page.locator("#fgrid .cell", { hasText: "Dentro" }).click();
  assert.strictEqual((await (await fp).json()).ok, true);
  await page.locator("#fd-back").click();
  await page.locator("#folder").waitFor({ state: "hidden", timeout: 5000 });

  /* monitor do PC (2.9): texto ao vivo pc:cpu e tela de processos */
  await page.locator("#grid .cell", { hasText: "25%" }).waitFor({ state: "visible", timeout: 8000 });
  await page.route("**/api/monitor?*", async function (route) {   /* servidor nao libera encerrar: simula ligado */
    var r = await route.fetch(), j = await r.json();
    j.allow_kill = true;
    await route.fulfill({ response: r, json: j });
  });
  await page.locator("#grid .cell", { hasText: "Monitor" }).last().click();   /* o sem rotulo (kind monitor) tambem abre */
  await page.locator("#sheetwrap.show").waitFor({ timeout: 5000 });
  await page.locator(".prow", { hasText: "chrome.exe" }).waitFor({ state: "visible", timeout: 8000 });
  assert.ok((await page.locator(".prow").count()) >= 3, name + ": lista de processos curta");
  await page.locator(".prow .pr-main").first().click();      /* abre o Encerrar */
  await page.locator(".prow.open .pr-kill").waitFor({ state: "visible", timeout: 3000 });
  await page.locator(".prow.open .pr-kill").click();           /* pede confirmacao */
  await page.locator("#alert.show").waitFor({ timeout: 3000 });
  await page.locator("#alert .al-btn", { hasText: "Cancelar" }).click();
  await page.locator("#alert").waitFor({ state: "hidden", timeout: 3000 });
  await page.locator("#sheet .hb.r").click();                 /* OK fecha a folha */
  await page.locator("#sheetwrap.show").waitFor({ state: "hidden", timeout: 5000 });

  /* folha de ajustes */
  await page.locator("[aria-label=Ajustes]").click();
  await page.locator("#sheetwrap.show").waitFor({ timeout: 5000 });
  await page.waitForTimeout(400);
  await ctx.close();
}

/* pagina com grade propria (2.10): colunas/linhas da pagina, nao a geral */
async function ownGrid(browser, base, token, size, cols, rows, errors) {
  var name = "grade propria " + size.width + "x" + size.height;
  var ctx = await browser.newContext({ viewport: size });
  var page = await ctx.newPage();
  watchConsole(page, errors, name);
  await page.goto(base + "/?k=" + token);
  await page.locator("#grid .cell").first().waitFor({ state: "visible", timeout: 10000 });
  async function grid() {
    return page.locator("#grid .cell").evaluateAll(function (els) {
      var xs = {}, ys = {};
      els.forEach(function (e) { var r = e.getBoundingClientRect(); xs[Math.round(r.left)] = 1; ys[Math.round(r.top)] = 1; });
      return { n: els.length, c: Object.keys(xs).length, r: Object.keys(ys).length };
    });
  }
  var g0 = await grid();
  await page.evaluate(function () { window.SD.goPage(2); });
  await page.locator("#grid .cell", { hasText: "B" }).waitFor({ state: "visible", timeout: 5000 });
  var g = await grid();
  assert.deepStrictEqual(g, { n: cols * rows, c: cols, r: rows }, name + ": " + JSON.stringify(g));
  await page.evaluate(function () { window.SD.goPage(0); });
  await page.locator("#grid .cell", { hasText: "Copiar" }).waitFor({ state: "visible", timeout: 5000 });
  assert.deepStrictEqual(await grid(), g0, name + ": volta para a grade geral");
  await ctx.close();
}

/* resumo do PC velho (ts 0) mostra o traco, nunca 0% */
async function stalePc(browser, base, token, errors) {
  var ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  var page = await ctx.newPage();
  watchConsole(page, errors, "pc velho");
  await page.route("**/api/state*", async function (route) {
    var r = await route.fetch(), j = await r.json();
    if (j.pc) j.pc = { cpu: 0, mem_pct: 0, ts: 0 };
    await route.fulfill({ response: r, json: j });
  });
  var seen = page.waitForResponse(function (r) { return r.url().indexOf("/api/state") >= 0 && r.url().indexOf("pc=1") >= 0; });
  await page.goto(base + "/?k=" + token);
  await seen;
  await page.waitForTimeout(500);
  var txt = await page.locator("#grid .key.live").first().innerText();
  assert.ok(txt.indexOf("\u2014") >= 0 && txt.indexOf("0%") < 0, "pc velho deveria mostrar traco: " + txt);
  await ctx.close();
}

/* avisos (2.12): o celular pergunta com since=<ultimo id>; um aviso novo vira
   faixa no topo, e tocar nela abre a central de avisos */
async function avisosFaixa(browser, base, token, errors) {
  var ctx = await browser.newContext({ viewport: { width: 640, height: 288 } });
  var page = await ctx.newPage();
  watchConsole(page, errors, "avisos");
  var ALERT = { id: 9000000000001, t: Math.floor(Date.now() / 1000), kind: "temp", level: "crit",
    title: "CPU a 93 °C", text: "Acima do limite de 90 °C." };
  var sinceSeen = false;
  await page.route("**/api/state*", async function (route) {
    var r = await route.fetch(), j = await r.json();
    var m = /[?&]since=(\d+)/.exec(route.request().url());
    j.alert_id = 9000000000000;
    if (m) { sinceSeen = true; j.alert_id = ALERT.id; j.alerts = +m[1] < ALERT.id ? [ALERT] : []; }
    await route.fulfill({ response: r, json: j });
  });
  await page.route("**/api/avisos*", async function (route) {
    await route.fulfill({ json: { ok: true, alerts: [ALERT], alert_id: ALERT.id } });
  });
  await page.goto(base + "/?k=" + token);
  await page.locator("#banner.show", { hasText: "CPU a 93" }).waitFor({ timeout: 15000 });
  assert.ok(sinceSeen, "poll deveria mandar since=");
  var box = await page.locator("#banner").boundingBox();
  assert.ok(box.y >= 0 && box.y < 40 && box.x >= 0 && box.x + box.width <= 640, "faixa fora do topo: " + JSON.stringify(box));
  await page.locator("#banner").click();
  await page.locator("#sheetwrap.show").waitFor({ timeout: 5000 });
  await page.locator(".av-row", { hasText: "CPU a 93" }).waitFor({ state: "visible", timeout: 5000 });
  await page.waitForTimeout(400);
  await ctx.close();
}

/* IPv4 da rede deste PC: pedidos por ele chegam como de outro aparelho (nao 127.0.0.1) */
function lanIp() {
  var ifs = os.networkInterfaces();
  for (var n in ifs) for (var i = 0; i < ifs[n].length; i++) {
    var a = ifs[n][i];
    if ((a.family === "IPv4" || a.family === 4) && !a.internal) return a.address;
  }
  return null;
}

/* aparelhos (2.11): primeiro acesso cria o aparelho; Conectar mostra o cartao;
   pagina nao liberada some do celular e o servidor recusa apertar */
async function aparelhos(browser, base, lanBase, token, data, errors) {
  var ctx = await browser.newContext({ viewport: { width: 640, height: 288 } });
  var page = await ctx.newPage();
  /* o 403 de proposito (pagina nao liberada) e o ping das abas guardadas para
     127.0.0.1 (o Chromium bloqueia rede publica -> loopback) nao contam */
  var mine = [];
  watchConsole(page, mine, "aparelho");
  await page.goto(lanBase + "/?k=" + token);
  await page.locator("#grid .cell", { hasText: "Copiar" }).waitFor({ state: "visible", timeout: 10000 });
  assert.strictEqual(page.url(), lanBase + "/", "codigo saiu do endereco");
  var cookies = await ctx.cookies();
  var sdk = cookies.filter(function (c) { return c.name === "sdk"; })[0];
  assert.ok(sdk && /^[0-9a-f]{32}$/.test(sdk.value) && sdk.value !== token && sdk.httpOnly, "cookie com a chave do aparelho");
  var pressed = page.waitForResponse(function (r) { return r.url().indexOf("/api/press?p=0&b=1") >= 0; });
  await page.locator("#grid .cell", { hasText: "Copiar" }).click();
  assert.strictEqual((await pressed).status(), 200, "aparelho aperta botao");
  var file = JSON.parse(fs.readFileSync(path.join(data, "aparelhos.json"), "utf8"));
  assert.strictEqual(file.devices.length, 1);
  assert.strictEqual(await page.locator("#dots span").count(), 3, "3 paginas");

  /* Conectar (no PC) mostra o aparelho; limita as paginas pelo cartao */
  var pc = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  var cp = await pc.newPage();
  watchConsole(cp, errors, "conectar");
  await cp.goto(base + "/conectar");
  var card = cp.locator("#devs .dev");
  await card.first().waitFor({ state: "visible", timeout: 10000 });
  assert.strictEqual(await card.count(), 1);
  var html = await cp.content();
  assert.ok(html.indexOf(sdk.value) < 0, "chave nao aparece no Conectar");
  var saved = cp.waitForResponse(function (r) { return r.url().indexOf("/api/local/devices") >= 0 && r.request().method() === "POST"; });
  await card.locator(".chip", { hasText: "Dois" }).click();
  assert.strictEqual((await saved).status(), 200);
  await card.locator(".badge.lim", { hasText: "2 páginas" }).waitFor({ timeout: 5000 });
  await pc.close();

  /* celular: "Dois" some (2 pontos), deslizar pula, e o servidor recusa a pagina 1 */
  await page.reload();
  await page.locator("#grid .cell", { hasText: "Copiar" }).waitFor({ state: "visible", timeout: 10000 });
  await page.waitForFunction(function () { return document.querySelectorAll("#dots span").length === 2; }, null, { timeout: 8000 });
  var shown = await page.locator("#dots span").evaluateAll(function (els) { return els.map(function (e) { return e.getAttribute("data-p"); }); });
  assert.deepStrictEqual(shown, ["0", "2"]);
  await page.evaluate(function () { window.SD.goPage(1); });
  assert.strictEqual(await page.evaluate(function () { return window.SD.page; }), 0, "pagina 1 nao abre");
  var r = await page.evaluate(function () {
    return fetch("/api/press?p=1&b=0", { headers: { "X-StreamDeck": "1" } }).then(function (x) { return x.status; });
  });
  assert.strictEqual(r, 403, "servidor recusa pagina nao liberada");
  await ctx.close();
  mine.forEach(function (e) {
    if (!/ping\.gif|ERR_FAILED|status of 403/.test(e)) errors.push(e);
  });
}

async function editor(browser, base, errors) {
  var ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  var page = await ctx.newPage();
  watchConsole(page, errors, "editor");
  await page.goto(base + "/editar");
  var tile = page.locator("#grid [data-i='1']");
  await tile.waitFor({ state: "visible", timeout: 10000 });
  await tile.click();
  var label = page.locator("#label");
  await label.waitFor({ state: "visible", timeout: 5000 });
  assert.strictEqual(await label.inputValue(), "Copiar");
  var saved = page.waitForResponse(function (r) {
    return r.url().indexOf("/api/config") >= 0 && r.request().method() === "POST";
  });
  await label.fill("Copiado E2E");
  var resp = await saved;
  assert.strictEqual(resp.status(), 200, "autosave falhou: " + (await resp.text()));
  var cfg = await (await ctx.request.get(base + "/api/config", { headers: { "X-StreamDeck": "1" } })).json();
  assert.strictEqual(cfg.pages[0].buttons[1].label, "Copiado E2E");
  assert.strictEqual(cfg.pages[0].buttons[1].action.type, "hotkey");
  await page.locator("#status", { hasText: "Salvo" }).waitFor({ timeout: 5000 });

  /* grade de cada pagina (2.10.1): toda pagina tem a sua; mudar uma nao mexe nas outras */
  async function getCfg() { return (await ctx.request.get(base + "/api/config", { headers: { "X-StreamDeck": "1" } })).json(); }
  function saveOk() {
    return page.waitForResponse(function (r) { return r.url().indexOf("/api/config") >= 0 && r.request().method() === "POST"; });
  }
  assert.strictEqual(await page.locator("#gridMode").count(), 0, "sem seletor Geral/Propria");
  cfg = await getCfg();
  assert.deepStrictEqual(cfg.pages[0].grid, { columns: 4, rows: 3 }, "migracao deu grade a pagina 1");
  assert.deepStrictEqual(cfg.pages[1].grid, { columns: 4, rows: 3 }, "migracao deu grade a pagina 2");
  await page.locator("#pages .pg").nth(2).click();
  assert.strictEqual(await page.locator("#grid [data-i]").count(), 10, "previa 5x2 na pagina 3");
  await page.locator("#pages .pg").nth(0).click();
  saved = saveOk();
  await page.locator("#sizes select[title=Colunas]").selectOption("6");
  await saved;
  cfg = await getCfg();
  assert.deepStrictEqual(cfg.pages[0].grid, { columns: 6, rows: 3 });
  assert.deepStrictEqual(cfg.pages[1].grid, { columns: 4, rows: 3 }, "pagina 2 nao muda");
  assert.deepStrictEqual(cfg.pages[2].grid, { columns: 5, rows: 2, portrait: { columns: 2, rows: 5 } });
  assert.strictEqual(cfg.columns, 4, "geral nao muda");
  await page.locator("#pages .pg").nth(1).click();
  assert.strictEqual(await page.locator("#sizes select[title=Colunas]").inputValue(), "4");
  /* pagina nova (em branco) copia a grade da pagina atual */
  await page.locator("#pages .pg").nth(2).click();
  var n0 = cfg.pages.length;
  saved = saveOk();
  await page.locator("#addPage").click();
  await page.locator("#addBlank").click();
  await saved;
  cfg = await getCfg();
  assert.strictEqual(cfg.pages.length, n0 + 1);
  assert.deepStrictEqual(cfg.pages[3].grid, { columns: 5, rows: 2, portrait: { columns: 2, rows: 5 } }, "pagina nova com grade");
  /* ids fixos: pagina nova tem id proprio; copia nao leva o id da original */
  var ids = cfg.pages.map(function (p) { return p.id; });
  ids.forEach(function (id) { assert.ok(/^[0-9a-f]{4,16}$/.test(id), "pagina com id: " + id); });
  saved = saveOk();
  await page.locator("#pages .pg").nth(0).click({ button: "right" });
  await page.locator("#pmDup").click();
  await saved;
  cfg = await getCfg();
  assert.strictEqual(cfg.pages.length, n0 + 2);
  assert.strictEqual(cfg.pages[0].id, ids[0], "original mantem o id");
  assert.ok(cfg.pages[1].id && ids.indexOf(cfg.pages[1].id) < 0, "copia ganha id novo");
  assert.deepStrictEqual(cfg.pages.slice(2).map(function (p) { return p.id; }), ids.slice(1), "mover mantem ids");
  await ctx.close();
}

async function main() {
  var data = fs.mkdtempSync(path.join(os.tmpdir(), "sd-e2e-"));
  var srv = await startServer(data);
  var token = fs.readFileSync(path.join(data, "token.txt"), "utf8").trim();
  var base = "http://127.0.0.1:" + srv.port;
  var browser = await playwright.chromium.launch();
  var errors = [], failed = null;
  try {
    await phone(browser, base, token, { width: 390, height: 844 }, errors);
    console.log("ok   celular 390x844");
    await phone(browser, base, token, { width: 1180, height: 820 }, errors);
    console.log("ok   tablet 1180x820");
    await ownGrid(browser, base, token, { width: 1180, height: 820 }, 5, 2, errors);
    await ownGrid(browser, base, token, { width: 390, height: 844 }, 2, 5, errors);
    console.log("ok   grade propria por pagina");
    await stalePc(browser, base, token, errors);
    console.log("ok   pc velho");
    await avisosFaixa(browser, base, token, errors);
    console.log("ok   avisos (faixa e central)");
    var ip = lanIp();
    if (ip) {
      await aparelhos(browser, base, "http://" + ip + ":" + srv.port, token, data, errors);
      console.log("ok   aparelhos (" + ip + ")");
    } else console.log("--   aparelhos: sem IP de rede, pulado");
    await editor(browser, base, errors);
    console.log("ok   editor 1440x900");
    assert.deepStrictEqual(errors, [], "erros no console:\n" + errors.join("\n"));
    console.log("ok   sem erros no console");
  } catch (e) {
    failed = e;
  } finally {
    await browser.close();
    srv.proc.kill();
    await sleep(300);
    try { fs.rmSync(data, { recursive: true, force: true }); } catch (e) {}
  }
  if (failed) {
    console.error("FALHA: " + (failed.stack || failed));
    if (errors.length) console.error("console:\n" + errors.join("\n"));
    console.error("--- log do servidor ---\n" + srv.log());
    process.exit(1);
  }
  console.log("smoke ok");
}

main().catch(function (e) { console.error(e); process.exit(1); });
