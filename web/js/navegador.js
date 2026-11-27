/* Stream Deck (celular) - bloco Navegador (2.12): folha com as abas do PC
   (tocar = ir para a aba; deslizar para a esquerda = fechar) e botoes de
   rolar, pausar o YouTube, voltar, avancar, recarregar e abrir site.
   Sem a extensao no PC os botoes viram atalhos de teclado no navegador da frente. */
(function () {
  "use strict";

  var SD = window.SD, esc = SD.esc, el = SD.el, ui = SD.ui;
  var COLORS = ["#0a84ff", "#30d158", "#ff9f0a", "#ff453a", "#bf5af2", "#5e5ce6", "#64d2ff", "#ff375f"];

  function send(cmd, ok, quiet) {
    SD.req("POST", "/api/navegador", JSON.stringify(cmd), function (good, data, status) {
      if (good) { if (ok) ok(data); return; }
      if (status === 403 && data && data.reason === "full") SD.toast("Precisa de Controle total (Conectar > Aparelhos, no PC)", true);
      else if (!quiet) SD.toast(SD.errText(data, status, "Não funcionou"), true);
    });
  }

  function avatar(t) {
    var h = t.host || "", c = 0;
    for (var i = 0; i < h.length; i++) c = (c * 31 + h.charCodeAt(i)) >>> 0;
    var letter = (h.replace(/^www\./, "")[0] || (t.title || "?")[0] || "?").toUpperCase();
    return '<span class="r-ic nav-av" style="background:' + (h ? COLORS[c % COLORS.length] : "#8e8e93") + '">' + esc(letter) + "</span>";
  }

  SD.openBrowser = function () {
    var v = {
      title: "Navegador",
      right: { text: "OK", bold: true, fn: function () { SD.sheet.close(); } },
      render: render,
      onLeave: function () { v.dead = true; clearInterval(v.tm); v.tm = null; }
    };
    SD.sheet.open(v);
  };

  function render(body, v) {
    v.dead = false; v.seq = 0; v.touching = false; v.openId = null;
    clearInterval(v.tm);
    var data = v.data || null;

    /* aviso sem extensao */
    var warn = el("div", "nav-warn", null, body);

    /* controles */
    var pad = el("div", "nav-pad", null, body);
    var BTNS = [
      ["back", "Voltar", { op: "back" }], ["forward", "Avançar", { op: "forward" }],
      ["refresh", "Recarregar", { op: "reload" }], ["playpause", "YouTube", { op: "yt_toggle" }],
      ["up", "Subir", { op: "scroll", dir: "up" }], ["down", "Descer", { op: "scroll", dir: "down" }],
      ["upload", "Topo", { op: "scroll", dir: "top" }], ["download", "Fim", { op: "scroll", dir: "bottom" }]
    ];
    BTNS.forEach(function (x) {
      var b = el("button", "nav-b", '<span class="nav-bi">' + SD.svg(x[0], 22, SD.TINT) + "</span><span>" + esc(x[1]) + "</span>", pad);
      b.type = "button";
      b.onclick = function () { SD.buzz && SD.buzz(8); send(x[2], function () { setTimeout(v.load, 600); }); };
    });

    /* abas */
    var tg = ui.group(body, "Abas");
    var list = el("div", "mon-list", null, tg);
    var tfoot = null;

    /* abrir site */
    var og = ui.group(body, "Abrir site");
    var url = ui.input(og, "", "", { placeholder: "https://…", type: "url", inputmode: "url", maxlength: 2000 });
    url.className += " nav-url";
    var go = el("button", "nav-go", "Abrir", url.parentNode);
    go.type = "button";
    function open() {
      var u = SD.trim(url.value);
      if (!u) return;
      if (!/^https?:\/\//i.test(u)) u = "https://" + u;
      send({ op: "open_url", url: u }, function () { url.value = ""; url.blur(); SD.toast("Abrindo no PC"); setTimeout(v.load, 900); });
    }
    go.onclick = open;
    url.onkeydown = function (e) { if (e.keyCode === 13) { e.preventDefault(); open(); } };
    var ofoot = null;

    function closeAll() {
      var rs = list.childNodes;
      for (var i = 0; i < rs.length; i++) SD.setClass(rs[i], "open", false);
      v.openId = null;
    }
    function closeTab(t) {
      send({ op: "close_tab", tab: t.id }, function () {
        v.openId = null;
        if (v.data) v.data.tabs = v.data.tabs.filter(function (x) { return x.id !== t.id; });
        fill(v.data);
        setTimeout(v.load, 700);
      });
    }
    function row(t, canClose) {
      var r = el("div", "prow nav-row" + (canClose && t.id === v.openId ? " open" : ""), null, list);
      var kill = canClose ? el("div", "pr-kill", "Fechar", r) : null;
      var m = el("div", "pr-main", null, r);
      m.innerHTML = avatar(t) + '<span class="nav-tx"><span class="nav-ti">' + esc(t.title || t.host || "Sem título") + "</span>" +
        '<span class="nav-ho">' + esc(t.host || "página interna") + "</span></span>" +
        (t.audible ? '<span class="nav-snd">' + SD.svg("sound", 16, SD.TINT) + "</span>" : "") +
        (t.current ? '<span class="nav-cur">' + SD.svg("check", 16, SD.TINT) + "</span>" : "");
      if (kill) kill.onclick = function () { closeTab(t); };
      var sx = 0, sy = 0, moved = false;
      function pt(e) { var q = e.touches[0]; return SD.toLocal ? SD.toLocal(q.clientX, q.clientY) : { x: q.clientX, y: q.clientY }; }
      if (canClose) {
        m.addEventListener("touchstart", function (e) { var q = pt(e); sx = q.x; sy = q.y; moved = false; v.touching = true; }, false);
        m.addEventListener("touchmove", function (e) {
          var q = pt(e), dx = q.x - sx, dy = q.y - sy;
          if (Math.abs(dx) < 12 || Math.abs(dx) < Math.abs(dy)) return;
          moved = true;
          if (dx < -24 && !SD.hasClass(r, "open")) { closeAll(); SD.setClass(r, "open", true); v.openId = t.id; }
          else if (dx > 24 && SD.hasClass(r, "open")) { SD.setClass(r, "open", false); v.openId = null; }
        }, false);
        var endT = function () { setTimeout(function () { v.touching = false; }, 300); };
        m.addEventListener("touchend", endT, false);
        m.addEventListener("touchcancel", endT, false);
      }
      m.onclick = function () {
        if (moved) { moved = false; return; }
        if (SD.hasClass(r, "open")) { closeAll(); return; }
        SD.buzz && SD.buzz(8);
        send({ op: "activate", tab: t.id }, function () { setTimeout(v.load, 500); });
      };
    }

    function fill(d) {
      data = d;
      var conn = !!(d && d.connected), full = !!(d && d.full);
      warn.innerHTML = "";
      warn.style.display = d && !conn ? "" : "none";
      if (d && !conn) {
        warn.innerHTML = '<span class="nav-wi">' + SD.svg("globe", 20, "#fff") + '</span><span><b>Instale a extensão (Conectar &gt; Navegador)</b>' +
          "<br>Sem ela os botões viram atalhos de teclado no navegador que estiver na frente do PC.</span>";
      }
      /* sem Controle total: nada de endereco digitado nem fechar aba */
      url.disabled = go.disabled = !full;
      url.placeholder = full ? "https://…" : "Precisa de Controle total";
      if (ofoot) { ofoot.parentNode.removeChild(ofoot); ofoot = null; }
      if (d && !full) ofoot = og.foot("Abrir endereço digitado e fechar abas precisam de “Controle total” (Conectar > Aparelhos, no PC).");

      list.innerHTML = "";
      if (tfoot) { tfoot.parentNode.removeChild(tfoot); tfoot = null; }
      if (!d) { el("div", "mon-empty", "Carregando…", list); return; }
      if (!conn) {
        /* sem lista: so os atalhos de aba */
        [["back", "Aba anterior", { op: "tab_prev" }], ["forward", "Próxima aba", { op: "tab_next" }]].forEach(function (x) {
          ui.row(list, { icon: x[0], iconColor: "#5e5ce6", title: x[1], onTap: function () { send(x[2]); } });
        });
        if (full) ui.row(list, { icon: "close", iconColor: "#ff453a", title: "Fechar aba", red: true, onTap: function () { send({ op: "close_tab" }); } });
        tfoot = tg.foot("A lista de abas aparece com a extensão instalada e pareada.");
        return;
      }
      var tabs = d.tabs || [];
      if (!tabs.length) el("div", "mon-empty", "Nenhuma aba", list);
      for (var i = 0; i < tabs.length; i++) row(tabs[i], full);
      if (full && tabs.length) tfoot = tg.foot("Toque para ir à aba. Deslize para a esquerda para fechar.");
      else if (tabs.length) tfoot = tg.foot("Toque para ir à aba.");
    }

    v.load = function () {
      if (v.dead) return;
      var seq = ++v.seq;
      SD.req("GET", "/api/navegador", null, function (ok, d, status) {
        if (v.dead || seq !== v.seq) return;
        if (!ok) {
          list.innerHTML = "";
          el("div", "mon-empty", status === 403 ? esc(SD.errText(d, status)) : "Sem conexão com o PC", list);
          return;
        }
        v.data = d;
        if (!v.touching && !v.openId) fill(d);
      });
    };
    fill(data);
    v.tm = setInterval(function () { if (!document.hidden && !SD.alertOpen()) v.load(); }, 2500);
    v.load();
  }
})();
