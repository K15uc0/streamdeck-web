/* Stream Deck - ajustes: grade, paginas, computadores (abas), atualizacoes, tela cheia. */
(function () {
  "use strict";

  var SD = window.SD, esc = SD.esc, el = SD.el, ui = SD.ui, clone = SD.clone, trim = SD.trim;

  /* ======================================================== ajustes === */
  var gridT = null, gridCfg = null, gridOrig = null;

  SD.openSettings = function () {
    if (!SD.info) SD.loadInfo(function () { if (SD.sheet.isOpen()) SD.sheet.refresh(); });
    SD.sheet.open({
      title: "Ajustes",
      left: null,
      right: { text: "OK", bold: true, fn: function () { SD.sheet.close(); } },
      render: renderSettings,
      onLeave: flushGrid
    });
  };

  /* colunas/linhas: aplica na hora e salva depois de parar de tocar */
  function changeGrid(cols, rows) {
    if (!gridCfg) { gridOrig = SD.cfg; gridCfg = clone(SD.cfg); }
    gridCfg.columns = cols; gridCfg.rows = rows;
    SD.cfg = gridCfg;
    SD.render();
    clearTimeout(gridT);
    gridT = setTimeout(flushGrid, 900);
  }
  function flushGrid() {
    clearTimeout(gridT);
    if (!gridCfg) return;
    var c = gridCfg;
    gridCfg = null;
    SD.cfg = gridOrig;
    SD.saveCfg(c, null, true);
  }

  function renderSettings(body) {
    var cfg = SD.cfg;

    /* grade */
    var g = ui.group(body, "Grade de botões");
    ui.stepperRow(g, "Colunas", cfg.columns, 1, 10, function (v) { changeGrid(v, (gridCfg || SD.cfg).rows); });
    ui.stepperRow(g, "Linhas", cfg.rows, 1, 8, function (v) { changeGrid((gridCfg || SD.cfg).columns, v); });
    g.foot("Em pé, o celular pode trocar colunas por linhas para os botões ficarem maiores.");

    /* paginas */
    var pg = ui.group(body, "Páginas");
    for (var i = 0; i < cfg.pages.length; i++) (function (idx) {
      var p = cfg.pages[idx];
      ui.row(pg, { icon: "page", iconColor: idx === SD.page ? SD.TINT : "#636366", title: p.name || "Página " + (idx + 1),
        value: idx === SD.page ? "atual" : "", chevron: true, onTap: function () { openPage(idx); } });
    })(i);
    ui.row(pg, { iconHtml: '<span class="r-add">' + SD.svg("plus", 12) + "</span>", title: "Adicionar página", tint: true, onTap: addPage });
    pg.foot("Deslize para os lados na tela principal para trocar de página.");

    /* computadores */
    var cg = ui.group(body, "Computadores");
    for (var j = 0; j < SD.conns.length; j++) (function (idx) {
      var c = SD.conns[idx], isHere = c.host === SD.here;
      var up = isHere ? SD.online : SD.alive[c.host];
      ui.row(cg, { icon: "desktop", iconColor: up === true ? SD.GREEN : up === false ? "#ff453a" : "#636366",
        title: c.name || c.host, sub: c.host + (isHere ? " · este" : ""), chevron: true, onTap: function () { openConn(idx); } });
    })(j);
    ui.row(cg, { iconHtml: '<span class="r-add">' + SD.svg("plus", 12) + "</span>", title: "Adicionar computador", tint: true, onTap: function () { openConn(-1); } });
    cg.foot("Com mais de um PC, as abas aparecem no alto da tela. Só a aba aberta controla o PC dela.");

    /* geral */
    var gg = ui.group(body, "Geral");
    var u = SD.info && SD.info.update;
    ui.row(gg, { icon: "download", iconColor: "#8e8e93", title: "Atualizações", badge: SD.updAvail() ? "1" : "",
      value: SD.info ? (SD.info.version || (u && u.version) || "") : "", chevron: true, onTap: openUpdates });
    if (SD.canFullscreen()) {
      var fr = ui.switchRow(gg, "Tela cheia", SD.isFullscreen(), function () {
        SD.toggleFullscreen();
        setTimeout(function () { if (SD.sheet.isOpen()) SD.sheet.refresh(); }, 600);
      });
      fr.insertBefore(el("span", "r-ic", SD.svg("expand", 18)), fr.firstChild).style.background = "#5e5ce6";
    }
    ui.row(gg, { icon: "qr", iconColor: "#30d158", title: "Como conectar", chevron: true, onTap: openHowto });

    var foot = el("div", "about", null, body);
    foot.innerHTML = "Stream Deck" + (SD.info && SD.info.version ? " " + esc(SD.info.version) : "") +
      (SD.info && SD.info.name ? " · " + esc(SD.info.name) : "");
    el("div", "sh-pad", null, body);
  }

  /* ======================================================== paginas === */
  function addPage() {
    var c = clone(SD.cfg), bs = [], n = c.columns * c.rows;
    for (var i = 0; i < n; i++) bs.push(SD.emptyButton());
    c.pages.push({ name: "Página " + (c.pages.length + 1), buttons: bs });
    var idx = c.pages.length - 1;
    SD.saveCfg(c, function (ok) {
      if (!ok) return;
      SD.page = idx;
      SD.render();
      SD.sheet.refresh();
      openPage(idx);
    });
  }

  function movePage(from, to) {
    var c = clone(SD.cfg), map = {};
    var p = c.pages.splice(from, 1)[0];
    c.pages.splice(to, 0, p);
    for (var i = 0; i < SD.cfg.pages.length; i++) {
      var n = i;
      if (i === from) n = to;
      else if (from < to && i > from && i <= to) n = i - 1;
      else if (from > to && i >= to && i < from) n = i + 1;
      map[i] = n;
    }
    SD.remapPages(c, map);
    var t = {};
    for (var k in SD.toggles) if (SD.toggles.hasOwnProperty(k)) {
      var parts = k.split(":");
      t[map[parseInt(parts[0], 10)] + ":" + parts[1]] = SD.toggles[k];
    }
    SD.toggles = t;
    SD.page = map[SD.page];
    SD.saveCfg(c, null, true);
    return to;
  }

  function deletePage(idx, done) {
    if (SD.cfg.pages.length < 2) return SD.toast("Precisa ficar ao menos uma página.", true);
    var name = SD.cfg.pages[idx].name || "Página " + (idx + 1);
    SD.confirm("Excluir “" + name + "”?", "A página e todos os botões dela serão apagados. Botões que levavam a ela ficam vazios.",
      "Excluir", true, function () {
        var c = clone(SD.cfg), map = {};
        c.pages.splice(idx, 1);
        for (var i = 0; i < SD.cfg.pages.length; i++) map[i] = i < idx ? i : i === idx ? -1 : i - 1;
        SD.remapPages(c, map);
        SD.toggles = {};
        if (SD.page >= idx && SD.page > 0) SD.page--;
        SD.saveCfg(c, function (ok) { if (ok && done) done(); }, true);
      });
  }

  function openPage(idx) {
    var name = null;
    SD.sheet.push({
      title: "Página",
      render: function (body) {
        var p = SD.cfg.pages[idx];
        if (!p) return;
        var g = ui.group(body, "Nome");
        ui.input(g, null, name != null ? name : (p.name || ""), { placeholder: "Página " + (idx + 1), maxlength: 30, autocap: true,
          onInput: function (v) { name = v; } });
        var a = ui.group(body);
        if (idx !== SD.page) ui.row(a, { title: "Mostrar esta página", tint: true, onTap: function () { SD.goPage(idx); SD.sheet.refresh(); } });
        ui.row(a, { title: "Mover para cima", tint: idx > 0, dim: idx === 0, onTap: idx > 0 ? function () { saveName(); idx = movePage(idx, idx - 1); SD.sheet.refresh(); } : null });
        ui.row(a, { title: "Mover para baixo", tint: idx < SD.cfg.pages.length - 1, dim: idx >= SD.cfg.pages.length - 1,
          onTap: idx < SD.cfg.pages.length - 1 ? function () { saveName(); idx = movePage(idx, idx + 1); SD.sheet.refresh(); } : null });
        var d = ui.group(body);
        ui.row(d, { title: "Excluir página", red: true, center: true, onTap: function () {
          name = null;
          deletePage(idx, function () { SD.sheet.pop(); });
        } });
      },
      onLeave: saveName
    });
    function saveName() {
      if (name == null) return;
      var n = trim(name);
      name = null;
      var p = SD.cfg.pages[idx];
      if (!p || n === (p.name || "")) return;
      var c = clone(SD.cfg);
      c.pages[idx].name = n;
      SD.saveCfg(c, null, true);
    }
  }

  /* =================================================== computadores === */
  function openConn(idx) {
    var c = idx >= 0 ? clone(SD.conns[idx]) : { name: "", host: "", code: "" };
    var isHere = idx >= 0 && c.host === SD.here;
    SD.sheet.push({
      title: idx >= 0 ? (c.name || c.host) : "Novo computador",
      right: { text: "Salvar", bold: true, fn: save },
      render: function (body) {
        var g = ui.group(body);
        ui.input(g, "Nome", c.name, { placeholder: "Casa, Trabalho, Rádio…", maxlength: 30, autocap: true, onInput: function (v) { c.name = v; } });
        if (isHere) {
          g.foot("Este é o PC aberto agora (" + SD.here + "). Só o nome pode ser mudado.");
        } else {
          ui.input(g, "Endereço", c.host, { placeholder: "192.168.0.20:8765", onInput: function (v) { c.host = v; } });
          ui.input(g, "Código", c.code, { placeholder: "código de acesso", onInput: function (v) { c.code = v; } });
          g.foot("Os dois aparecem na tela Conectar daquele PC: http://IP:porta/?k=código.");
          if (idx >= 0) {
            var a = ui.group(body);
            ui.row(a, { title: "Abrir este computador", tint: true, onTap: function () { SD.switchTo(idx); } });
            var d = ui.group(body);
            ui.row(d, { title: "Remover computador", red: true, center: true, onTap: function () {
              SD.confirm("Remover “" + (c.name || c.host) + "”?", "A aba deste PC sai da lista.", "Remover", true, function () {
                SD.conns.splice(idx, 1); SD.saveConns(); SD.renderNav(); SD.layoutSoon(); SD.sheet.pop();
              });
            } });
          }
        }
      }
    });
    function save() {
      var n = { name: trim(c.name), host: c.host, code: c.code };
      if (!isHere) {
        n.host = trim(c.host).replace(/^https?:\/\//, "").replace(/\/.*$/, "");
        n.code = trim(c.code);
        if (!/^[A-Za-z0-9.\-]+(:\d{1,5})?$/.test(n.host)) return SD.toast("Endereço inválido. Ex.: 192.168.0.20:8765", true);
        if (!n.code) return SD.toast("Informe o código de acesso.", true);
        for (var j = 0; j < SD.conns.length; j++) {
          if (j !== idx && SD.conns[j].host === n.host) return SD.toast("Já existe um computador com esse endereço.", true);
        }
      }
      if (!n.name) n.name = n.host;
      if (idx >= 0) SD.conns[idx] = n; else SD.conns.push(n);
      SD.saveConns(); SD.renderNav(); SD.layoutSoon(); SD.pingAll();
      SD.sheet.pop();
    }
  }

  /* =================================================== atualizacoes === */
  var updPoll = null, checking = false;

  function openUpdates() {
    SD.sheet.push({ title: "Atualizações", render: renderUpdates });
    SD.req("GET", "/api/update", null, function (ok, u) {
      if (ok && u) { if (!SD.info) SD.info = {}; SD.info.update = u; if (SD.sheet.isOpen()) SD.sheet.refresh(); }
    });
  }

  function renderUpdates(body) {
    var u = SD.info && SD.info.update;
    var g = ui.group(body);
    if (!u) { ui.row(g, { title: "Verificando…", dim: true }); return; }
    ui.row(g, { title: "Versão instalada", value: u.version || "" });
    if (u.latest) ui.row(g, { title: "Última publicada", value: u.latest });
    var st = "";
    if (u.state === "downloading") st = "Baixando a atualização no PC…";
    else if (u.state === "restarting") st = "Reiniciando com a versão nova…";
    else if (u.available) st = "Há uma versão nova. Seus botões, abas e sons são mantidos.";
    else if (u.latest) st = "Você está na versão mais recente.";
    if (u.error) st += (st ? " " : "") + "Não foi possível verificar: " + u.error;
    if (u.checked) st += (st ? " " : "") + "Última verificação: " + u.checked + ".";
    if (st) g.foot(st, u.available ? "ok" : "");

    if (u.available && u.notes) {
      var ng = ui.group(body, "O que mudou");
      el("div", "notes", esc(u.notes), el("div", "row ta", null, ng));
    }

    var a = ui.group(body);
    ui.row(a, { title: checking ? "Verificando…" : "Verificar agora", tint: !checking, dim: checking, onTap: checking ? null : function () {
      checking = true; SD.sheet.refresh();
      SD.req("POST", "/api/update/check", "{}", function (ok, r, status) {
        checking = false;
        if (ok && r) { SD.info.update = r; SD.renderNav(); }
        else SD.toast("Não verificou: " + SD.errText(r, status), true);
        if (SD.sheet.isOpen()) SD.sheet.refresh();
      });
    } });
    var busy = u.state === "downloading" || u.state === "restarting";
    if (u.available && u.auto && !busy) ui.row(a, { title: "Atualizar agora", tint: true, bold: true, onTap: apply });
    if (u.available && !u.auto) a.foot("Para atualizar, baixe a versão nova no PC: " + (u.page || ""));
  }

  function apply() {
    SD.confirm("Atualizar o Stream Deck?", "O programa no PC reinicia sozinho e seus botões são mantidos.", "Atualizar", false, function () {
      SD.req("POST", "/api/update/apply", "{}", function (ok, r, status) {
        if (!ok) return SD.toast("Não atualizou: " + SD.errText(r, status), true);
        var from = SD.info.update.version;
        SD.info.update.state = "downloading";
        if (SD.sheet.isOpen()) SD.sheet.refresh();
        clearInterval(updPoll);
        updPoll = setInterval(function () {
          SD.req("GET", "/api/update", null, function (ok2, u2) {
            if (ok2 && u2 && u2.version !== from) { clearInterval(updPoll); location.reload(); }
            else if (ok2 && u2) { SD.info.update = u2; if (SD.sheet.isOpen()) SD.sheet.refresh(); }
          });
        }, 3000);
      });
    });
  }

  /* =================================================== como conectar === */
  function openHowto() {
    SD.sheet.push({
      title: "Como conectar",
      render: function (body) {
        var steps = [
          ["wifi", "#0a84ff", "Mesmo Wi-Fi", "Deixe o celular ou tablet na mesma rede Wi-Fi do PC."],
          ["qr", "#30d158", "Leia o QR code", "No PC, abra o Stream Deck: a tela Conectar mostra um QR code. Aponte a câmera e abra o link."],
          ["star", "#ff9f0a", "Salve na tela de início", "Depois do primeiro acesso, basta abrir o endereço curto. Adicione à tela de início para abrir como app."],
          ["desktop", "#5e5ce6", "Outros PCs", "Para controlar mais de um PC, leia o QR code de cada um ou adicione em Ajustes › Computadores."]
        ];
        var g = ui.group(body);
        for (var i = 0; i < steps.length; i++) {
          ui.row(g, { icon: steps[i][0], iconColor: steps[i][1], title: steps[i][2], sub: steps[i][3] }).className += " tall";
        }
        g.foot("Não abriu? Na primeira vez, o Windows pergunta sobre o firewall: marque Redes privadas e públicas e clique em Permitir.");
      }
    });
  }

  if (SD.start) SD.start();
})();
