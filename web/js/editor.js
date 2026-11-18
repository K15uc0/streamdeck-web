/* Stream Deck - modo edicao (tremer, remover, arrastar) e editor de botao.
   O formulario de cada acao e montado a partir do esquema (GET /api/actions):
   o frontend nao conhece as acoes, so os tipos de campo. */
(function () {
  "use strict";

  var SD = window.SD, esc = SD.esc, el = SD.el, ui = SD.ui, clone = SD.clone, trim = SD.trim;

  /* ===================================================== modo edicao === */
  SD.setEditing = function (on) {
    SD.editing = !!on;
    if (on) { SD.loadActions(); if (!SD.info) SD.loadInfo(); }
    SD.render();
    if (!on) SD.pollSoon();
  };

  SD.removeButton = function (idx) {
    var pg = SD.curPage(), b = pg.buttons[idx];
    if (SD.isEmpty(b)) return;
    var name = trim(b.label) || (b.kind === "fader" ? "este fader" : "este botão");
    SD.confirm("Remover " + (trim(b.label) ? "“" + name + "”" : name) + "?",
      "O espaço fica vazio. Você pode criar outro botão nele depois.", "Remover", true, function () {
        var c = clone(SD.cfg);
        SD.padButtons(c.pages[SD.page], c.columns * c.rows);
        c.pages[SD.page].buttons[idx] = SD.emptyButton();
        delete SD.toggles[SD.page + ":" + idx];
        SD.saveCfg(c, null, true);
      });
  };

  /* ========================================================= campos === */
  function parseKeys(v) {
    var parts = String(v || "").toLowerCase().split("+"), ks = [];
    for (var i = 0; i < parts.length; i++) { var p = trim(parts[i]); if (p) ks.push(p); }
    return ks;
  }

  /* acao nova com os valores padrao dos campos */
  function defaults(schema) {
    var a = { type: schema.type }, fs = schema.fields || [];
    for (var i = 0; i < fs.length; i++) {
      var f = fs[i];
      if (f["default"] !== undefined) a[f.key] = clone(f["default"]);
      else if (f.kind === "steps") a[f.key] = [];
      else if (f.kind === "bool") a[f.key] = false;
      else if (f.kind === "page" && f.required) a[f.key] = 0;
      else if (f.kind === "select" && f.required && f.options && f.options.length) a[f.key] = f.options[0].value;
    }
    return a;
  }

  function iconFor(schema) { return schema && SD.hasIcon(schema.icon) ? schema.icon : "bolt"; }

  /* cor do quadradinho de cada grupo de acoes (como no app Ajustes) */
  var GROUP_COLORS = ["#0a84ff", "#ff9f0a", "#30d158", "#bf5af2", "#ff375f", "#5e5ce6", "#40c8e0", "#ac8e68"];
  function groupColor(group) {
    var list = SD.actions || [], seen = [], i;
    for (i = 0; i < list.length; i++) {
      var g = list[i].group || "";
      if (seen.indexOf(g) < 0) seen.push(g);
    }
    i = seen.indexOf(group || "");
    return GROUP_COLORS[(i < 0 ? 0 : i) % GROUP_COLORS.length];
  }
  function actionBadge(schema) {
    return '<span class="r-ic" style="background:' + groupColor(schema && schema.group) + '">' + SD.svg(iconFor(schema), 18) + "</span>";
  }

  function fieldValueText(f, v) {
    if (v == null || v === "") return "";
    if (f.kind === "keys") return (v.join ? v.join("+") : String(v));
    if (f.kind === "bool") return v ? "sim" : "";
    if (f.kind === "page") { var p = SD.cfg.pages[v]; return p ? p.name || "Página " + (v + 1) : ""; }
    if (f.kind === "steps") return v.length ? v.length + (v.length === 1 ? " passo" : " passos") : "";
    if (f.kind === "select" && f.options) for (var i = 0; i < f.options.length; i++) if (String(f.options[i].value) === String(v)) return f.options[i].label;
    return String(v);
  }
  function summary(a) {
    var s = SD.schemaOf(a);
    if (!s) return a.type;
    var fs = s.fields || [];
    for (var i = 0; i < fs.length; i++) { var t = fieldValueText(fs[i], a[fs[i].key]); if (t && fs[i].kind !== "bool") return t; }
    return "";
  }

  /* desenha os campos de uma acao (a) a partir do esquema. ctx.nested = dentro de uma sequencia */
  function renderFields(body, a, schema, ctx) {
    var fs = schema.fields || [], g = null;
    function grp(header) { return ui.group(body, header); }
    for (var i = 0; i < fs.length; i++) (function (f) {
      var key = f.key, label = f.label || key, ph = f.placeholder || "";
      var useLabel = label + (f.required ? "" : "");
      if (f.kind === "steps") {
        g = null;
        if (ctx.nested) return;
        renderSteps(body, a, f);
        return;
      }
      if (f.kind === "textarea") {
        g = null;
        var tg = grp(label);
        ui.textarea(tg, a[key], { placeholder: ph, onInput: function (v) { a[key] = v; } });
        if (f.help) tg.foot(f.help);
        return;
      }
      if (f.kind === "select" && f.options && f.options.length <= 4) {
        g = null;
        var sg = grp(label);
        for (var j = 0; j < f.options.length; j++) (function (o) {
          ui.row(sg, { title: o.label, check: String(a[key]) === String(o.value), onTap: function () { a[key] = o.value; SD.sheet.refresh(); } });
        })(f.options[j]);
        if (f.help) sg.foot(f.help);
        return;
      }
      if (!g) g = grp(null);
      switch (f.kind) {
        case "keys":
          ui.input(g, useLabel, a[key] && a[key].join ? a[key].join("+") : (a[key] || ""),
            { placeholder: ph || "ctrl+shift+m", onInput: function (v) { a[key] = parseKeys(v); } });
          break;
        case "number":
          ui.input(g, useLabel, a[key] == null ? "" : a[key], {
            type: "number", inputmode: "decimal", min: f.min, max: f.max, step: f.step, placeholder: ph,
            onInput: function (v) { a[key] = v === "" ? undefined : Number(v); }
          });
          break;
        case "bool":
          ui.switchRow(g, label, !!a[key], function (on) { a[key] = on; });
          break;
        case "select":
          var opts = [];
          if (!f.required || a[key] == null) opts.push({ value: "", label: "—" });
          for (var k = 0; k < (f.options || []).length; k++) opts.push(f.options[k]);
          ui.selectRow(g, label, opts, a[key] == null ? "" : a[key], function (v) {
            var o = null;
            for (var q = 0; q < f.options.length; q++) if (String(f.options[q].value) === v) o = f.options[q];
            a[key] = o ? o.value : undefined;
          });
          break;
        case "page":
          var pages = [];
          for (var p = 0; p < SD.cfg.pages.length; p++) pages.push({ value: p, label: (p + 1) + ". " + (SD.cfg.pages[p].name || "Página " + (p + 1)) });
          if (a[key] == null) a[key] = 0;
          ui.selectRow(g, label, pages, a[key], function (v) { a[key] = parseInt(v, 10) || 0; });
          break;
        case "sound":
          renderSound(g, a, f);
          break;
        default:   /* text e tipos desconhecidos */
          ui.input(g, useLabel, a[key] == null ? "" : a[key], { placeholder: ph, onInput: function (v) { a[key] = v; } });
      }
      if (f.help) { g.foot(f.help); g = null; }
    })(fs[i]);
  }

  /* som: lista da pasta "sons" do PC, com campo livre para outro arquivo */
  function renderSound(g, a, f) {
    var key = f.key, sounds = (SD.info && SD.info.sounds) || [], cur = a[key] || "";
    var inList = false, i;
    for (i = 0; i < sounds.length; i++) if (sounds[i] === cur) inList = true;
    var other = !!cur && !inList;
    if (sounds.length) {
      var opts = [{ value: "", label: "Escolher…" }];
      for (i = 0; i < sounds.length; i++) opts.push({ value: sounds[i], label: sounds[i] });
      opts.push({ value: "\u0000outro", label: "Outro arquivo…" });
      ui.selectRow(g, f.label || "Arquivo", opts, other ? "\u0000outro" : cur, function (v) {
        if (v === "\u0000outro") { a[key] = a[key] && !inListOf(a[key]) ? a[key] : ""; a._otherSound = true; }
        else { a[key] = v; a._otherSound = false; }
        SD.sheet.refresh();
      });
    }
    if (!sounds.length || other || a._otherSound) {
      ui.input(g, sounds.length ? "Caminho" : (f.label || "Arquivo"), cur,
        { placeholder: f.placeholder || "vinheta.mp3 ou C:\\Sons\\aplausos.wav", onInput: function (v) { a[key] = trim(v); } });
    }
    function inListOf(v) { for (var j = 0; j < sounds.length; j++) if (sounds[j] === v) return true; return false; }
  }

  /* lista de passos (sequencia): cada passo e uma acao com os mesmos campos */
  function renderSteps(body, a, f) {
    var key = f.key;
    if (!a[key] || a[key].length == null) a[key] = [];
    var steps = a[key];
    var g = ui.group(body, f.label || "Passos");
    for (var i = 0; i < steps.length; i++) (function (idx) {
      var st = steps[idx], s = SD.schemaOf(st);
      var r = ui.row(g, {
        iconHtml: '<span class="r-del">' + SD.svg("minus", 12) + "</span>" + actionBadge(s),
        title: (idx + 1) + ". " + (s ? s.label : st.type), sub: summary(st), chevron: true,
        onTap: function () { openStep(a, key, idx); }
      });
      r.firstChild.onclick = function (e) {
        e.stopPropagation();
        steps.splice(idx, 1);
        SD.sheet.refresh();
      };
    })(i);
    ui.row(g, { iconHtml: '<span class="r-add">' + SD.svg("plus", 12) + "</span>", title: "Adicionar passo", tint: true,
      onTap: function () {
        pickAction(null, true, function (schema) {
          steps.push(defaults(schema));
          openStep(a, key, steps.length - 1, true);
        });
      } });
    if (f.help) g.foot(f.help);
  }

  function openStep(parent, key, idx, replace) {
    var view = {
      title: "Passo " + (idx + 1),
      render: function (body) {
        var st = parent[key][idx];
        if (!st) return;
        var s = SD.schemaOf(st);
        var g = ui.group(body, "Ação");
        ui.row(g, { iconHtml: actionBadge(s), title: s ? s.label : st.type, chevron: true, onTap: function () {
          pickAction(st.type, true, function (schema) {
            if (schema.type !== st.type) parent[key][idx] = defaults(schema);
          });
        } });
        if (s && s.help) g.foot(s.help);
        if (s) renderFields(body, st, s, { nested: true });
        else rawJson(body, parent[key], idx);
      }
    };
    if (replace) setTimeout(function () { SD.sheet.push(view); }, 340);   /* depois de fechar a lista de acoes */
    else SD.sheet.push(view);
  }

  /* sem esquema (servidor antigo ou acao desconhecida): edita o JSON da acao */
  function rawJson(body, holder, key) {
    var g = ui.group(body, "Ação (JSON)");
    ui.textarea(g, JSON.stringify(holder[key], null, 1), { mono: true, onInput: function (v) {
      try { holder[key] = JSON.parse(v); holder._bad = false; } catch (e) { holder._bad = true; }
    } });
    g.foot("A lista de ações do PC não está disponível. Edite a ação como JSON, por exemplo {\"type\":\"hotkey\",\"keys\":[\"ctrl\",\"c\"]}.");
  }

  /* ================================================ escolher acao === */
  function excludedInSteps(s) {
    if (s.type === "none" || s.type === "page" || s.type === "multi") return true;
    var fs = s.fields || [];
    for (var i = 0; i < fs.length; i++) if (fs[i].kind === "page" || fs[i].kind === "steps") return true;
    return false;
  }

  function pickAction(current, forStep, onPick) {
    SD.sheet.push({
      title: forStep ? "Ação do passo" : "Ação",
      render: function (body) {
        if (!SD.actions) {
          var g0 = ui.group(body);
          ui.row(g0, { title: "Carregando ações…", dim: true });
          SD.loadActions(function (ok) {
            if (ok) SD.sheet.refresh();
            else {
              body.innerHTML = "";
              var g1 = ui.group(body);
              ui.row(g1, { title: "Não foi possível carregar a lista de ações", dim: true });
              ui.row(g1, { title: "Tentar de novo", tint: true, onTap: function () { SD.sheet.refresh(); } });
            }
          });
          return;
        }
        var groups = [], byGroup = {}, i;
        for (i = 0; i < SD.actions.length; i++) {
          var s = SD.actions[i];
          if (forStep && excludedInSteps(s)) continue;
          var gname = s.group || "Geral";
          if (!byGroup[gname]) { byGroup[gname] = []; groups.push(gname); }
          byGroup[gname].push(s);
        }
        for (i = 0; i < groups.length; i++) {
          var g = ui.group(body, groups[i]);
          for (var j = 0; j < byGroup[groups[i]].length; j++) (function (sc) {
            ui.row(g, { iconHtml: actionBadge(sc), title: sc.label || sc.type, check: sc.type === current,
              onTap: function () { onPick(sc); SD.sheet.pop(); } });
          })(byGroup[groups[i]][j]);
        }
      }
    });
  }

  /* ===================================================== validacao === */
  function validate(a, s, prefix) {
    if (!s) return a && a._bad ? "JSON inválido na ação." : "";
    var fs = s.fields || [];
    for (var i = 0; i < fs.length; i++) {
      var f = fs[i], v = a[f.key], name = prefix + "“" + (f.label || f.key) + "”";
      var empty = v == null || (typeof v === "string" && !trim(v)) || (v.length === 0 && f.kind !== "steps");
      if (f.required && empty && f.kind !== "bool") return "Preencha " + name + ".";
      if (f.kind === "number" && v != null) {
        if (isNaN(v)) return name + " precisa ser um número.";
        if (f.min != null && v < f.min) return name + " deve ser no mínimo " + f.min + ".";
        if (f.max != null && v > f.max) return name + " deve ser no máximo " + f.max + ".";
      }
      if (f.kind === "steps" && v && v.length) {
        if (v._bad) return "JSON inválido em um passo.";
        for (var j = 0; j < v.length; j++) {
          var e = validate(v[j], SD.schemaOf(v[j]), "Passo " + (j + 1) + ": ");
          if (e) return e;
        }
        if (f.required && !v.length) return "Adicione ao menos um passo.";
      }
    }
    return "";
  }

  /* remove marcas internas do rascunho */
  function cleanAction(a) {
    if (!a || typeof a !== "object") return a;
    delete a._otherSound; delete a._bad;
    for (var k in a) if (a.hasOwnProperty(k) && a[k] && a[k].length != null && typeof a[k] !== "string") {
      for (var i = 0; i < a[k].length; i++) if (a[k][i] && typeof a[k][i] === "object") cleanAction(a[k][i]);
    }
    for (var k2 in a) if (a.hasOwnProperty(k2) && a[k2] === undefined) delete a[k2];
    return a;
  }

  /* ======================================================== editor === */
  var draft = null, draftIdx = -1, draftPage = 0, isNew = false, preview = null, holder = null;

  SD.openEditor = function (idx) {
    var pg = SD.curPage(), b = pg.buttons && pg.buttons[idx];
    isNew = SD.isEmpty(b);
    draft = isNew ? { kind: "button", label: "", icon: "", color: "#0a84ff", action: { type: "none" } } : clone(b);
    if (!draft.kind) draft.kind = "button";
    if (draft.kind === "button" && !draft.action) draft.action = { type: "none" };
    holder = { action: draft.action };
    draftIdx = idx; draftPage = SD.page;
    SD.loadActions(function () { if (draft && SD.sheet.isOpen()) SD.sheet.refresh(); });
    if (!SD.info) SD.loadInfo(function () { if (draft && SD.sheet.isOpen()) SD.sheet.refresh(); });
    SD.sheet.open({
      title: isNew ? "Novo botão" : (draft.kind === "fader" ? "Editar fader" : "Editar botão"),
      backTitle: "Botão",
      left: { text: "Cancelar", fn: function () { SD.sheet.close(); } },
      right: { text: "Salvar", bold: true, fn: save },
      render: renderEditor,
      onClosed: function () { draft = null; }
    });
  };

  function updatePreview() {
    if (!preview) return;
    preview.innerHTML = "";
    var b = clone(draft), states = b.kind !== "fader" && b.toggle ? [false, true] : [false];
    for (var i = 0; i < states.length; i++) {
      var wrap = el("div", "pv-t", null, preview);
      var t = SD.buildTile(b);
      t.empty = false;   /* a pre-visualizacao mostra a cor mesmo sem acao */
      t.lit = states[i];
      wrap.appendChild(t.el);
      if (t.kind === "fader") {
        var lv = SD.levelOf(b.target || "master");
        t.level = lv && lv.v != null ? lv : { v: 60, muted: false };
        SD.paintTile(t, 92, 120);
      } else SD.paintTile(t, 104, 104);
      if (states.length > 1) el("div", "pv-c", states[i] ? "Ligado" : "Desligado", wrap);
    }
  }

  function renderEditor(body) {
    if (!draft) return;
    var isFader = draft.kind === "fader";

    /* pre-visualizacao */
    preview = el("div", "pv", null, body);
    updatePreview();

    /* tipo */
    var segBox = el("div", "seg-wrap", null, body);
    ui.segmented(segBox, [["button", "Botão"], ["toggle", "Liga/desliga"], ["fader", "Fader"]],
      isFader ? "fader" : draft.toggle ? "toggle" : "button", function (v) {
        if (v === "fader") {
          if (draft.kind !== "fader") holder.action = draft.action;
          draft.kind = "fader"; delete draft.action; delete draft.toggle;
          if (!draft.target) draft.target = "master";
        } else {
          draft.kind = "button";
          draft.action = draft.action || holder.action || { type: "none" };
          if (v === "toggle") draft.toggle = true; else delete draft.toggle;
        }
        SD.sheet.refresh();
      });
    if (draft.toggle) el("div", "grp-f", "Cada toque executa a ação e alterna entre aceso e apagado. O estado aparece em todos os aparelhos.", body);

    if (isFader) {
      var fg = ui.group(body, "Controla");
      for (var i = 0; i < SD.FADER_TARGETS.length; i++) (function (tg) {
        ui.row(fg, { title: tg[1], check: (draft.target || "master") === tg[0], onTap: function () { draft.target = tg[0]; SD.sheet.refresh(); } });
      })(SD.FADER_TARGETS[i]);
      fg.foot("Arraste para cima ou para baixo para mudar o volume. Toque no ícone para silenciar.");
    }

    /* rotulo */
    var lg = ui.group(body, "Rótulo");
    ui.input(lg, null, draft.label || "", { placeholder: isFader ? "Ex.: Master" : "Sem rótulo", maxlength: 40, autocap: true,
      onInput: function (v) { draft.label = v; updatePreview(); } });

    /* acao */
    if (!isFader) {
      var a = draft.action, s = SD.schemaOf(a);
      var ag = ui.group(body, "Ação");
      var title = a.type === "none" ? "Escolher ação…" : (s ? s.label : (SD.actions || SD.actionsFailed ? a.type : "Carregando…"));
      ui.row(ag, { iconHtml: a.type === "none" ? null : actionBadge(s), title: title, tint: a.type === "none", chevron: true,
        onTap: function () {
          pickAction(a.type, false, function (schema) {
            if (schema.type === draft.action.type) return;
            var old = SD.schemaOf(draft.action);
            draft.action = defaults(schema);
            if (SD.hasIcon(schema.icon) && (!draft.icon || (old && draft.icon === old.icon))) draft.icon = schema.icon;
          });
        } });
      var notes = [];
      if (s && s.dangerous && SD.info && !SD.info.local && !SD.info.remote_admin) {
        ag.foot(SD.svg("warn", 13, "#ff9f0a") + " Por segurança, esta ação só pode ser criada ou alterada no próprio PC, ou se você liberar em Conectar › Segurança, no PC. Abrir sites (http/https) é permitido.", "warn", true);
      }
      if (s && s.help) notes.push(s.help);
      if (notes.length) ag.foot(notes.join(" "));
      if (a.type !== "none") {
        if (s) renderFields(body, a, s, { nested: false });
        else if (SD.actions || SD.actionsFailed) rawJson(body, draft, "action");
      }
    }

    /* icone */
    var ig = ui.group(body, "Ícone");
    var grid = el("div", "icons", null, ig);
    var none = el("span", draft.icon ? "" : "sel", "<b><i>sem</i></b>", grid);
    none.onclick = function () { draft.icon = ""; mark(grid, none); updatePreview(); };
    for (var name in SD.ICONS) if (SD.ICONS.hasOwnProperty(name)) (function (n) {
      var sp = el("span", draft.icon === n ? "sel" : "", "<b>" + SD.svg(n, 22) + "</b>", grid);
      sp.onclick = function () { draft.icon = n; mark(grid, sp); updatePreview(); };
    })(name);

    /* cor */
    var cg = ui.group(body, "Cor");
    var sw = el("div", "colors", null, cg);
    var hex;
    for (var c = 0; c < SD.COLORS.length; c++) (function (col) {
      var sp = el("span", sameColor(draft.color, col[1]) ? "sel" : "", "<i style=\"background:" + col[1] + "\"></i>", sw);
      sp.title = col[0];
      sp.onclick = function () { draft.color = col[1]; mark(sw, sp); if (hex) hex.value = col[1]; updatePreview(); };
    })(SD.COLORS[c]);
    hex = ui.input(cg, "Outra cor", draft.color || "", { placeholder: "#0a84ff", maxlength: 7,
      onInput: function (v) {
        draft.color = trim(v);
        var sps = sw.childNodes;
        for (var q = 0; q < sps.length; q++) sps[q].className = sameColor(draft.color, SD.COLORS[q][1]) ? "sel" : "";
        if (SD.validColor(draft.color)) updatePreview();
      } });

    if (!isNew) {
      var dg = ui.group(body);
      ui.row(dg, { title: isFader ? "Remover fader" : "Remover botão", red: true, center: true, onTap: function () {
        SD.confirm("Remover?", "O espaço fica vazio.", "Remover", true, function () { commit(SD.emptyButton()); });
      } });
    }
    el("div", "sh-pad", null, body);
  }

  function sameColor(a, b) { return String(a || "").toLowerCase() === String(b || "").toLowerCase(); }
  function mark(box, sel) {
    var sp = box.childNodes;
    for (var i = 0; i < sp.length; i++) sp[i].className = sp[i] === sel ? "sel" : "";
  }

  function save() {
    var b = clone(draft);
    if (b.color && !SD.validColor(b.color)) return SD.toast("Cor inválida (use #rrggbb).", true);
    if (b.kind === "fader") {
      delete b.action; delete b.toggle;
      if (!b.target) b.target = "master";
    } else {
      b.kind = "button";
      delete b.target;
      if (!b.toggle) delete b.toggle;
      if (draft._bad) return SD.toast("JSON inválido na ação.", true);
      delete b._bad;
      var err = validate(draft.action, SD.schemaOf(draft.action), "");
      if (err) return SD.toast(err, true);
      cleanAction(b.action);
      if (!b.action || b.action.type === "none") {
        if (isNew) { SD.sheet.close(); return; }
        b = SD.emptyButton();
      }
    }
    commit(b);
  }

  function commit(b) {
    var c = clone(SD.cfg), pg = c.pages[draftPage];
    if (!pg) return SD.sheet.close();
    SD.padButtons(pg, Math.max(c.columns * c.rows, draftIdx + 1));
    pg.buttons[draftIdx] = b;
    SD.sheet.setRight(false);
    SD.saveCfg(c, function (ok) {
      SD.sheet.setRight(true);
      if (ok) { SD.sheet.close(); SD.toast("Salvo"); }
    });
  }
})();
