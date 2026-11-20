/* Stream Deck (celular) - ajustes deste aparelho: tela cheia, orientacao, computadores (abas),
   atualizacoes. Editar botoes e so no PC (editar.html). */
(function () {
  "use strict";

  var SD = window.SD, esc = SD.esc, el = SD.el, ui = SD.ui, clone = SD.clone, trim = SD.trim;

  /* ======================================================== ajustes === */
  SD.openSettings = function () {
    if (!SD.info) SD.loadInfo(function () { if (SD.sheet.isOpen()) SD.sheet.refresh(); });
    SD.sheet.open({
      title: "Ajustes",
      left: null,
      right: { text: "OK", bold: true, fn: function () { SD.sheet.close(); } },
      render: renderSettings
    });
  };

  function platform() {
    var ua = navigator.userAgent || "";
    if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return "ios";
    if (/Android/.test(ua)) return "android";
    return "";
  }

  function iconRow(row, icon, color) {
    row.insertBefore(el("span", "r-ic", SD.svg(icon, 18)), row.firstChild).style.background = color;
    row.className += " has-ic";
    return row;
  }

  function renderSettings(body) {
    /* tela */
    var tg;
    if (SD.fsAvailable()) {
      tg = ui.group(body, "Tela");
      iconRow(ui.switchRow(tg, "Tela cheia", SD.isFullscreen(), function (on) {
        SD.setFullscreen(on);
        setTimeout(function () { if (SD.sheet.isOpen()) SD.sheet.refresh(); }, 700);
      }), "expand", "#5e5ce6");
      iconRow(ui.switchRow(tg, "Abrir sempre em tela cheia", SD.prefs.autoFullscreen, function (on) {
        SD.setPref("autoFullscreen", on);
      }), "bolt", "#ff9f0a").className += " tall";
      tg.foot("O navegador só deixa entrar em tela cheia depois de um toque: ao abrir, o primeiro toque na tela já liga a tela cheia (e o botão tocado funciona normalmente).");
    } else if (SD.isStandalone()) {
      tg = ui.group(body, "Tela");
      ui.row(tg, { icon: "expand", iconColor: "#5e5ce6", title: "Tela cheia", value: "app instalado" });
      tg.foot("Aberto pela tela de início: o Stream Deck já ocupa a tela toda.");
    }
    if (!SD.isStandalone()) {
      var os = platform(), hs = ui.group(body, "Tela de início");
      var ios = "No iPhone/iPad (Safari): toque em Compartilhar e depois em “Adicionar à Tela de Início”. Abrindo pelo ícone, o Stream Deck ocupa a tela toda, sem a barra do navegador.";
      var andr = "No Android (Chrome): menu ⋮ › “Adicionar à tela inicial” ou “Instalar app”. Abrindo pelo ícone, ele já abre em tela cheia.";
      ui.row(hs, { icon: os === "android" ? "phone" : "share", iconColor: "#0a84ff",
        title: os === "android" ? "Instalar como app" : "Adicionar à Tela de Início",
        sub: os === "ios" ? ios : os === "android" ? andr : ios + " " + andr }).className += " tall";
    }

    /* toque e paginas */
    var tp = ui.group(body, "Toque e páginas");
    iconRow(ui.switchRow(tp, "Vibrar ao tocar", SD.prefs.vibrate, function (on) {
      SD.setPref("vibrate", on);
    }), "phone", "#ff375f");
    iconRow(ui.switchRow(tp, "Trocar de página pelo app em foco", SD.prefs.autoPage, function (on) {
      SD.setPref("autoPage", on);
    }), "pages", "#0a84ff").className += " tall";
    tp.foot("Vibrar só funciona onde o navegador permite (Android). A troca automática vai para a página ligada ao programa aberto no PC (definida no editor do PC), só quando o programa em foco muda.");

    /* orientacao */
    el("div", "grp-h", "Orientação", body);
    var sw = el("div", "seg-wrap", null, body);
    ui.segmented(sw, [["auto", "Automática"], ["portrait", "Vertical"], ["landscape", "Horizontal"]], SD.prefs.orientation, function (v) {
      SD.setPref("orientation", v);
    });
    el("div", "grp-f", esc("Vale só para este aparelho. Automática segue o aparelho. Vertical/Horizontal travam a tela " +
      "(em tela cheia ou no app instalado); onde o sistema não deixa travar, a tela é girada pelo Stream Deck."), body);

    /* aparencia */
    el("div", "grp-h", "Aparência", body);
    var tw = el("div", "seg-wrap", null, body);
    ui.segmented(tw, [["auto", "Automático"], ["escuro", "Escuro"], ["claro", "Claro"]], SD.prefs.theme || "auto", function (v) {
      SD.setPref("theme", v);
    });
    el("div", "grp-f", esc("Automático segue o modo claro/escuro do aparelho. Os blocos coloridos mantêm suas cores."), body);

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
    ui.row(gg, { icon: "qr", iconColor: "#30d158", title: "Como conectar", chevron: true, onTap: openHowto });
    gg.foot("Para criar ou editar botões, abra o Stream Deck no PC (Conectar › Editar botões).");

    var foot = el("div", "about", null, body);
    foot.innerHTML = "Stream Deck" + (SD.info && SD.info.version ? " " + esc(SD.info.version) : "") +
      (SD.info && SD.info.name ? " · " + esc(SD.info.name) : "");
    el("div", "sh-pad", null, body);
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
