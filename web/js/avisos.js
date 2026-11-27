/* Stream Deck (celular) - avisos do PC (2.12): faixa no topo estilo iOS
   (4 s, vibra se ligado nos ajustes) e central de avisos (folha com o
   historico). O poll do deck.js manda since=<ultimo id> e chama
   SD.applyAlerts(st.alerts, st.alert_id). */
(function () {
  "use strict";

  var SD = window.SD, esc = SD.esc, el = SD.el, ui = SD.ui;

  /* tipo -> [icone, cor, nome] */
  var KIND = {
    ia: ["bolt", "#bf5af2", "Consumo das IAs"],
    temp: ["fire", "#ff453a", "Temperatura"],
    cpu: ["cpu", "#ff9f0a", "Processador"],
    obs: ["record", "#636366", "OBS"],
    device: ["phone", "#0a84ff", "Aparelhos"],
    schedule: ["clock", "#5e5ce6", "Agendamentos"],
    windows: ["desktop", "#0a84ff", "Windows"]
  };
  var SHOW_MS = 4000, MAX_QUEUE = 3;

  SD.alertId = null;      /* ultimo id visto (null = ainda nao perguntou) */
  SD.alerts = [];         /* recebidos nesta abertura (mais novo por ultimo) */
  SD.alertsUnread = 0;

  function kindOf(a) { return KIND[a.kind] || ["bell", "#8e8e93", "Stream Deck"]; }
  function appName(a) { return a.kind === "windows" && a.app ? a.app : kindOf(a)[2]; }

  function when(t) {
    var s = Math.max(0, Math.round(((SD.now() + (SD.skew || 0)) / 1000) - t));
    if (s < 60) return "agora";
    if (s < 3600) return Math.floor(s / 60) + " min";
    var d = new Date(t * 1000), two = function (n) { return (n < 10 ? "0" : "") + n; };
    return two(d.getHours()) + ":" + two(d.getMinutes());
  }

  /* ------------------------------------------------------ do poll --- */
  SD.applyAlerts = function (list, last) {
    if (typeof last === "number") {
      var first = SD.alertId === null;
      SD.alertId = last;
      if (first) return;      /* primeira consulta: so marca onde parou */
    }
    if (!list || !list.length) return;
    var fresh = [];
    for (var i = 0; i < list.length; i++) {
      var a = list[i], dup = false;
      for (var j = 0; j < SD.alerts.length; j++) if (SD.alerts[j].id === a.id) { dup = true; break; }
      if (!dup) { SD.alerts.push(a); fresh.push(a); }
    }
    if (SD.alerts.length > 50) SD.alerts = SD.alerts.slice(-50);
    if (!fresh.length) return;
    SD.alertsUnread += fresh.length;
    if (SD.sheet.isOpen() && SD.sheet.top() && SD.sheet.top().avisos) { SD.alertsUnread = 0; SD.sheet.refresh(); }
    for (var k = 0; k < fresh.length; k++) queue.push(fresh[k]);
    if (queue.length > MAX_QUEUE) { skipped += queue.length - MAX_QUEUE; queue = queue.slice(-MAX_QUEUE); }
    if (!showing) next();
  };

  /* ------------------------------------------------------- faixa --- */
  var queue = [], showing = null, skipped = 0, hideT = null, banner = null;

  function bannerEl() {
    if (banner) return banner;
    banner = el("div", "", null, document.getElementById("app") || document.body);
    banner.id = "banner";
    banner.setAttribute("role", "status");
    banner.onclick = function () { hide(true); SD.openAvisos(); };
    return banner;
  }

  function next() {
    var a = queue.shift();
    if (!a) { showing = null; return; }
    showing = a;
    var b = bannerEl(), k = kindOf(a), more = queue.length ? 0 : skipped;
    if (!queue.length) skipped = 0;
    b.className = "lvl-" + (a.level || "info");
    b.innerHTML = '<span class="bn-ic" style="background:' + k[1] + '">' + SD.svg(k[0], 20) + "</span>" +
      '<span class="bn-b"><span class="bn-h"><span class="bn-app">' + esc(appName(a)) + "</span>" +
      '<span class="bn-w">' + esc(when(a.t)) + "</span></span>" +
      '<span class="bn-t">' + esc(a.title) + "</span>" +
      (a.text ? '<span class="bn-x">' + esc(a.text) + "</span>" : "") +
      (more ? '<span class="bn-m">+' + more + (more === 1 ? " aviso" : " avisos") + "</span>" : "") + "</span>";
    b.style.display = "block";
    setTimeout(function () { if (showing === a) SD.setClass(b, "show", true); }, 20);
    if (SD.prefs.alertVibrate) SD.vibrate(a.level === "crit" ? [60, 80, 60] : 40);
    clearTimeout(hideT);
    hideT = setTimeout(function () { hide(false); }, SHOW_MS);
  }

  function hide(all) {
    clearTimeout(hideT);
    if (!banner) return;
    if (all) { queue = []; skipped = 0; }
    SD.setClass(banner, "show", false);
    var was = showing;
    setTimeout(function () {
      if (showing !== was) return;
      banner.style.display = "none";
      next();
    }, 300);
  }

  /* ------------------------------------------------------ central --- */
  SD.openAvisos = function () {
    var v = {
      title: "Avisos",
      avisos: true,
      right: { text: "OK", bold: true, fn: function () { SD.sheet.close(); } },
      render: renderList
    };
    SD.alertsUnread = 0;
    if (SD.sheet.isOpen()) SD.sheet.push(v); else SD.sheet.open(v);
    SD.req("GET", "/api/avisos", null, function (ok, r) {
      if (!ok || !r || !r.alerts) return;
      SD.alerts = r.alerts.slice(-50);
      if (typeof r.alert_id === "number" && (SD.alertId === null || r.alert_id > SD.alertId)) SD.alertId = r.alert_id;
      if (SD.sheet.isOpen()) SD.sheet.refresh();
    });
  };

  function renderList(body) {
    var list = SD.alerts.slice().reverse();
    if (!list.length) {
      var m = el("div", "av-empty", null, body);
      m.innerHTML = SD.svg("bell", 40, SD.lightTheme ? "rgba(60,60,67,0.35)" : "rgba(235,235,245,0.35)") +
        "<b>Nenhum aviso</b><p>Avisos do PC aparecem aqui: limite das IAs, temperatura, OBS, aparelhos novos e mais.</p>";
    } else {
      var g = ui.group(body, "Recentes");
      for (var i = 0; i < list.length; i++) {
        var a = list[i], k = kindOf(a);
        var r = ui.row(g, { icon: k[0], iconColor: k[1], title: a.title,
          sub: (a.kind === "windows" && a.app ? a.app + " · " : "") + (a.text || appName(a)), value: when(a.t) });
        r.className += " tall av-row" + (a.level === "crit" ? " crit" : "");
      }
      g.foot("Os últimos 50 avisos ficam guardados no PC até ele reiniciar.");
    }
    var o = ui.group(body, "Neste aparelho");
    var sw = ui.switchRow(o, "Vibrar com avisos", SD.prefs.alertVibrate, function (on) { SD.setPref("alertVibrate", on); });
    sw.className += " has-ic";
    sw.insertBefore(el("span", "r-ic", SD.svg("phone", 18)), sw.firstChild).style.background = "#ff375f";
    o.foot("Escolha quais avisos o PC manda em Conectar › Avisos, no PC. Os avisos chegam com a página aberta.");
    el("div", "sh-pad", null, body);
  }
})();
