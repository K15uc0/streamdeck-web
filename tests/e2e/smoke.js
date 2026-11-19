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
      { label: "Ir 2", icon: "forward", action: { type: "page", to: 1 } }
    ] },
    { name: "Dois", buttons: [{ label: "Voltar", icon: "back", action: { type: "page", to: 0 } }] }
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

  /* folha de ajustes */
  await page.locator("[aria-label=Ajustes]").click();
  await page.locator("#sheetwrap.show").waitFor({ timeout: 5000 });
  await page.waitForTimeout(400);
  await ctx.close();
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
