/* Janela da extensao: parear com o codigo do Conectar ou desparear. */
/* global chrome */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function msg(m, cb) {
    chrome.runtime.sendMessage(m, function (r) {
      if (chrome.runtime.lastError || !r) { cb({ ok: false, error: "A extensão não respondeu. Tente de novo." }); return; }
      cb(r);
    });
  }
  function show(r) {
    var s = (r && r.status) || {};
    $("parear").hidden = !!s.paired;
    $("pareada").hidden = !s.paired;
    var e = $("estado");
    e.className = s.paired && s.online ? "ok" : "";
    e.textContent = !s.paired ? "Não pareada" : s.online ? "Conectada (porta " + s.port + ")"
      : "Pareada; procurando o Stream Deck…";
    $("erro").textContent = (r && !r.ok && r.error) || s.error || "";
  }
  $("btnParear").onclick = function () {
    var b = this;
    b.disabled = true; b.textContent = "Pareando…";
    msg({ type: "pair", code: $("codigo").value, port: parseInt($("porta").value, 10) || null }, function (r) {
      b.disabled = false; b.textContent = "Parear";
      show(r);
      if (r.ok) setTimeout(refresh, 1500);
    });
  };
  $("codigo").onkeydown = function (e) { if (e.key === "Enter") $("btnParear").click(); };
  $("btnDesparear").onclick = function () { msg({ type: "unpair" }, show); };
  function refresh() { msg({ type: "status" }, show); }
  refresh();
})();
