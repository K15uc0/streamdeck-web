/* Stream Deck - tela Monitor do PC (CPU, memoria, GPU, rede, disco, sistema).
   Abre por cima da grade (botao de grafico na barra ou acao "monitor") e
   consulta /api/sys a cada ~1 s enquanto estiver aberta. ES5, como o resto. */
(function () {
  "use strict";

  var SD = window.SD, $ = SD.$, esc = SD.esc;
  var wrap = null, body = null, nameEl = null, timer = null, open = false, hist = false;
  var data = null, fails = 0, cards = {}, scrub = null;

  /* cores por serie (rede tem duas: validadas para daltonismo nos dois temas) */
  function light() { return document.documentElement.className.indexOf("theme-light") >= 0; }
  function col(k) {
    var L = light();
    return {
      cpu: L ? "#007aff" : "#0a84ff", ram: L ? "#af52de" : "#bf5af2", gpu: L ? "#248a3d" : "#30d158",
      disk: L ? "#c96f00" : "#d9770b", rx: L ? "#007aff" : "#0a84ff", tx: L ? "#c96f00" : "#d9770b"
    }[k];
  }

  function pct(v) { return v == null ? "\u2014" : Math.round(v) + "%"; }
  function gb(n) {
    if (n == null) return "--";
    var g = n / 1073741824;
    return (g < 10 ? g.toFixed(1) : String(Math.round(g))).replace(".", ",") + " GB";
  }

  /* --------------------------------------------------------- estrutura --- */
  function build() {
    wrap = document.createElement("div");
    wrap.id = "mon";
    wrap.innerHTML =
      '<div class="mon-bar"><div class="nav-in">' +
        '<span class="nb mon-back" id="mon-back">' + SD.svg("chevleft", 20, SD.TINT) + "<span>Voltar</span></span>" +
        '<div class="mon-t">Monitor do PC</div><div class="mon-pc" id="mon-pc"></div>' +
      "</div></div>" +
      '<div class="mon-body" id="mon-body"></div>';
    $("app").appendChild(wrap);
    body = $("mon-body");
    nameEl = $("mon-pc");
    $("mon-back").onclick = function () { close(false); };
    body.innerHTML =
      card("cpu", "Processador", true) + card("ram", "Memória", true) + card("gpu", "Placa de vídeo", true) +
      card("net", "Rede", true) + card("disk", "Disco", true) + card("sys", "Sistema", false);
    var ids = ["cpu", "ram", "gpu", "net", "disk", "sys"];
    for (var i = 0; i < ids.length; i++) {
      var c = $("mc-" + ids[i]);
      cards[ids[i]] = {
        el: c, val: c.querySelector(".mc-v"), sub: c.querySelector(".mc-s"),
        chart: c.querySelector(".mc-ch"), extra: c.querySelector(".mc-x"), tip: c.querySelector(".mc-tip")
      };
      if (cards[ids[i]].chart) bindScrub(ids[i]);
    }
    window.addEventListener("resize", function () { if (open) layout(); }, false);
  }

  function card(id, title, chart) {
    return '<div class="mc" id="mc-' + id + '"><div class="mc-h"><span class="mc-n">' + title + '</span>' +
      '<span class="mc-tip"></span></div>' +
      '<div class="mc-v"></div><div class="mc-s"></div>' +
      (chart ? '<div class="mc-ch"></div>' : "") + '<div class="mc-x"></div></div>';
  }

  /* colunas pela largura do quadro (o #app pode estar girado por CSS) */
  function layout() {
    var w = $("app").clientWidth || window.innerWidth;
    var n = w >= 980 ? 3 : w >= 600 ? 2 : 1;
    body.className = "mon-body c" + n;
  }

  /* ---------------------------------------------------------- graficos --- */
  /* series: [{v:[...], c:cor}] ; max: topo da escala (unica para todas as series) */
  function spark(series, max) {
    var W = 300, H = 64, h = '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" width="100%" height="100%">';
    /* grade discreta: 50% e base */
    h += '<line class="mc-g" x1="0" y1="' + H / 2 + '" x2="' + W + '" y2="' + H / 2 + '"/>';
    h += '<line class="mc-g b" x1="0" y1="' + (H - 0.5) + '" x2="' + W + '" y2="' + (H - 0.5) + '"/>';
    for (var s = 0; s < series.length; s++) {
      var v = series[s].v, n = v.length, pts = [];
      if (n < 2) continue;
      for (var i = 0; i < n; i++) {
        var y = v[i] == null ? 0 : Math.max(0, Math.min(1, v[i] / max));
        pts.push((i * W / (CAP - 1) + (CAP - n) * W / (CAP - 1)).toFixed(1) + "," + (H - 1 - y * (H - 3)).toFixed(1));
      }
      var x0 = pts[0].split(",")[0];
      if (series.length === 1) {
        h += '<polygon fill="' + series[s].c + '" fill-opacity="0.16" points="' + x0 + "," + H + " " + pts.join(" ") + " " + W + "," + H + '"/>';
      }
      h += '<polyline fill="none" stroke="' + series[s].c + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" points="' + pts.join(" ") + '"/>';
    }
    if (scrub && scrub.x != null) {
      h += '<line class="mc-cur" x1="' + scrub.x * W + '" y1="0" x2="' + scrub.x * W + '" y2="' + H + '" vector-effect="non-scaling-stroke"/>';
    }
    return h + "</svg>";
  }
  var CAP = 90;   /* mesmo HIST do servidor: o grafico enche da direita para a esquerda */

  function niceMax(arrs, floor) {
    var m = floor;
    for (var a = 0; a < arrs.length; a++) for (var i = 0; i < arrs[a].length; i++) if (arrs[a][i] > m) m = arrs[a][i];
    return m * 1.15;
  }

  /* tocar/arrastar no grafico mostra o valor daquele momento */
  function bindScrub(id) {
    var ch = cards[id].chart;
    /* x no referencial do #app (que pode estar girado por CSS) */
    function left(el) {
      var x = 0, app = $("app");
      while (el && el !== app) { x += el.offsetLeft; el = el.offsetParent; }
      return x;
    }
    function at(e) {
      var t = e.touches ? e.touches[0] : e;
      var p = SD.toLocal ? SD.toLocal(t.clientX, t.clientY) : { x: t.clientX, y: t.clientY };
      var w = ch.clientWidth || 1;
      scrub = { id: id, x: Math.max(0, Math.min(1, (p.x - left(ch)) / w)) };
      paint();
    }
    function off() { if (scrub && scrub.id === id) { scrub = null; paint(); } }
    ch.addEventListener("touchstart", at, { passive: true });
    ch.addEventListener("touchmove", at, { passive: true });
    ch.addEventListener("touchend", off, false);
    ch.addEventListener("touchcancel", off, false);
    ch.addEventListener("mousemove", at, false);
    ch.addEventListener("mouseleave", off, false);
  }

  /* indice do historico sob o dedo (null se fora dos dados) */
  function scrubIdx(n) {
    var i = Math.round(scrub.x * (CAP - 1)) - (CAP - n);
    return i >= 0 && i < n ? i : null;
  }
  function ago(n, i) {
    var s = Math.round((n - 1 - i) * ((data && data.interval) || 1));
    return s <= 0 ? "agora" : "há " + s + " s";
  }

  /* ------------------------------------------------------------ pintar --- */
  function set(c, v, sub, chart, extra, tip) {
    c.val.innerHTML = v;
    c.sub.innerHTML = sub || "";
    if (c.chart) c.chart.innerHTML = chart || "";
    c.extra.innerHTML = extra || "";
    c.tip.innerHTML = tip || "";
  }

  function onePct(id, key, series) {
    var hs = (data.hist && data.hist[key]) || [];
    var tip = "";
    if (scrub && scrub.id === id) {
      var i = scrubIdx(hs.length);
      tip = i == null ? "" : ago(hs.length, i) + ": " + pct(hs[i]);
    }
    return { chart: spark(series || [{ v: hs, c: col(key) }], 100), tip: tip };
  }

  function bar(p, c) {
    p = p == null ? 0 : Math.max(0, Math.min(100, p));
    return '<div class="mc-bar"><i style="width:' + p + "%;background:" + c + '"></i></div>';
  }

  function paint() {
    if (!data || !wrap) return;
    var d = data;

    /* CPU: numero grande, historico e um traco por nucleo */
    var cpu = d.cpu || {}, ch = onePct("cpu", "cpu");
    var cores = "";
    if (cpu.cores && cpu.cores.length > 1) {
      cores = '<div class="mc-cap">Por núcleo</div><div class="mc-cores">';
      for (var i = 0; i < cpu.cores.length; i++) {
        cores += '<span><i style="height:' + Math.max(2, Math.min(100, cpu.cores[i])) + "%;background:" + col("cpu") + '"></i></span>';
      }
      cores += "</div>";
    }
    set(cards.cpu, pct(cpu.pct),
      esc(cpu.name || "") + (cpu.count ? (cpu.name ? " · " : "") + cpu.count + " núcleos" : ""),
      ch.chart, cores, ch.tip);

    /* memoria */
    var r = d.ram, rc = onePct("ram", "ram");
    set(cards.ram, r ? pct(r.pct) : "\u2014", r ? gb(r.used) + " de " + gb(r.total) + " em uso" : "Não disponível",
      rc.chart, "", rc.tip);

    /* placa de video */
    var g = d.gpu;
    if (g && g.pct != null) {
      var gc = onePct("gpu", "gpu"), vr = "";
      if (g.mem != null) {
        vr = '<div class="mc-row"><span>Memória de vídeo</span><b>' + gb(g.mem) + (g.mem_total ? " de " + gb(g.mem_total) : "") + "</b></div>";
        if (g.mem_total) vr += bar(100 * g.mem / g.mem_total, col("gpu"));
      }
      set(cards.gpu, pct(g.pct), esc(g.name || ""), gc.chart, vr, gc.tip);
    } else {
      set(cards.gpu, "\u2014", "Não disponível neste PC", "", "", "");
    }

    /* rede: duas series na mesma escala, com legenda e setas (nao so cor) */
    var net = d.net || {}, hr = (d.hist && d.hist.rx) || [], ht = (d.hist && d.hist.tx) || [];
    var ntip = "";
    if (scrub && scrub.id === "net") {
      var j = scrubIdx(hr.length);
      if (j != null) ntip = ago(hr.length, j) + ": ↓ " + SD.rateText(hr[j]) + "  ↑ " + SD.rateText(ht[j]);
    }
    set(cards.net,
      '<span class="mc-dual"><em style="color:' + col("rx") + '">↓</em>' + SD.rateText(net.rx) + "</span>" +
      '<span class="mc-dual"><em style="color:' + col("tx") + '">↑</em>' + SD.rateText(net.tx) + "</span>",
      "",
      spark([{ v: hr, c: col("rx") }, { v: ht, c: col("tx") }], niceMax([hr, ht], 10240)),
      '<div class="mc-leg"><span><i style="background:' + col("rx") + '"></i>↓ Recebendo</span>' +
      '<span><i style="background:' + col("tx") + '"></i>↑ Enviando</span></div>', ntip);

    /* disco: atividade (Windows) ou leitura+gravacao, e espaco de cada unidade */
    var dk = d.disk || {}, hdr = (d.hist && d.hist.dr) || [], hdw = (d.hist && d.hist.dw) || [];
    var rows = '<div class="mc-row"><span>Leitura</span><b>' + SD.rateText(dk.read) + "</b></div>" +
      '<div class="mc-row"><span>Gravação</span><b>' + SD.rateText(dk.write) + "</b></div>";
    var drv = dk.drives || [];
    for (var k = 0; k < drv.length; k++) {
      rows += '<div class="mc-row mc-drv"><span>' + esc(drv[k].name) + "</span><b>" + gb(drv[k].total - drv[k].used) + " livres de " + gb(drv[k].total) + "</b></div>" +
        bar(drv[k].pct, drv[k].pct >= 90 ? (light() ? "#d70015" : "#ff453a") : col("disk"));
    }
    var sum = [];
    for (var q = 0; q < hdr.length; q++) sum.push(hdr[q] == null && hdw[q] == null ? null : (hdr[q] || 0) + (hdw[q] || 0));
    var dtip = "";
    if (scrub && scrub.id === "disk") {
      var m = scrubIdx(sum.length);
      if (m != null) dtip = ago(sum.length, m) + ": " + SD.rateText(sum[m]);
    }
    set(cards.disk, dk.busy != null ? pct(dk.busy) : SD.rateText((dk.read || 0) + (dk.write || 0)),
      dk.busy != null ? "Tempo ativo" : "Leitura + gravação",
      spark([{ v: sum, c: col("disk") }], niceMax([sum], 1048576)), rows, dtip);

    /* sistema */
    var b = d.battery, sys = "";
    if (b) {
      sys += '<div class="mc-row"><span>Bateria</span><b>' + b.pct + "%" + (b.charging ? " · carregando" : "") + "</b></div>" +
        bar(b.pct, b.pct <= 15 && !b.charging ? (light() ? "#d70015" : "#ff453a") : col("gpu"));
    }
    set(cards.sys, d.uptime != null ? SD.durText(d.uptime) : "\u2014", "Ligado há", "", sys, "");
    nameEl.innerHTML = esc(d.name || "");
  }

  /* ---------------------------------------------------------- consulta --- */
  function tick() {
    clearTimeout(timer);
    if (!open) return;
    timer = setTimeout(tick, 1000);
    if (document.hidden) return;
    SD.req("GET", "/api/sys", null, function (ok, js) {
      if (!open) return;
      if (ok && js && js.ok) {
        fails = 0;
        data = js;
        SD.setClass(wrap, "stale", false);
        paint();
      } else if (++fails >= 3) {
        SD.setClass(wrap, "stale", true);   /* sem conexao: numeros apagados ate voltar */
      }
    });
  }

  /* --------------------------------------------------------- abrir/fechar */
  function openMon() {
    if (open) return;
    if (!wrap) {
      build();
      /* registrado depois do deck.js: o "voltar" do aparelho fecha so o monitor */
      window.addEventListener("popstate", function () { if (open) { hist = false; close(true); } }, false);
    }
    open = true;
    layout();
    wrap.style.display = "block";
    wrap.offsetWidth;
    SD.setClass(wrap, "in", true);
    body.scrollTop = 0;
    if (data) paint();
    try { if (window.history && history.pushState) { history.pushState({ sdMon: 1 }, ""); hist = true; } } catch (e) {}
    tick();
  }
  function close(fromPop) {
    if (!open) return;
    open = false;
    clearTimeout(timer);
    scrub = null;
    if (hist && !fromPop) { hist = false; try { history.back(); } catch (e) {} }
    hist = false;
    SD.setClass(wrap, "in", false);
    setTimeout(function () { if (!open) wrap.style.display = "none"; }, 260);
  }

  SD.openMonitor = openMon;
  SD.closeMonitor = function () { close(false); };
  SD.monitorOpen = function () { return open; };
  document.addEventListener("visibilitychange", function () { if (open && !document.hidden) tick(); }, false);
})();
