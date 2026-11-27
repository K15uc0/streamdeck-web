# -*- coding: utf-8 -*-
"""Registro das acoes dos botoes.

Cada acao e uma funcao decorada com @action(...), que descreve os campos do
formulario (o editor do aparelho monta a tela a partir de /api/actions).
Para criar uma nova: um arquivo em streamdeck/actions/ e um import em _load().
Veja docs/ARQUITETURA.md."""
import re
import threading

from ..winapi import vk_of

FIELD_KINDS = ("text", "textarea", "keys", "number", "bool", "select", "sound", "page", "steps",
               "app", "color", "obs_scene", "obs_input")
NO_STEP = ("page", "multi")   # tipos que nao podem ser passos de uma sequencia

REGISTRY = {}   # tipo -> Action (na ordem de registro)
# ordem no editor das acoes que vem com o programa; as novas vao no fim
ORDER = ("none", "hotkey", "open", "command", "page", "multi",
         "sound", "stopsound", "text", "http", "mute",
         "app", "apphotkey", "site", "tab", "browser",
         "obs_scene", "obs_stream", "obs_record", "obs_mute")
CONTEXT = threading.local()   # CONTEXT.key = "p:b[:f]" do botao que disparou (ou None)


class Field(object):
    """Um campo do formulario de uma acao (chave dentro do dict da acao)."""

    def __init__(self, key, label, kind="text", required=False, default=None,
                 placeholder=None, help=None, min=None, max=None, step=None, options=None, when=None):
        if kind not in FIELD_KINDS:
            raise ValueError("tipo de campo desconhecido: %s" % kind)
        self.key, self.label, self.kind = key, label, kind
        self.required, self.default = required, default
        self.placeholder, self.help = placeholder, help
        self.min, self.max, self.step = min, max, step
        self.when = when      # {"campo": valor}: o editor so mostra o campo nesse caso
        # options: [(valor, rotulo)] ou [{"value", "label"}]
        self.options = [o if isinstance(o, dict) else {"value": o[0], "label": o[1]}
                        for o in (options or [])]

    def schema(self):
        out = {"key": self.key, "label": self.label, "kind": self.kind}
        for name in ("required", "default", "placeholder", "help", "min", "max", "step", "when"):
            v = getattr(self, name)
            if v is not None and v is not False:
                out[name] = v
        if self.options:
            out["options"] = list(self.options)
        return out


class Action(object):
    def __init__(self, type, label, fn, group, icon, help, fields, validate):
        self.type, self.label, self.fn = type, label, fn
        self.group, self.icon, self.help = group, icon, help
        self.fields = list(fields or [])
        self.extra_validate = validate

    def schema(self):
        return {"type": self.type, "label": self.label, "group": self.group,
                "icon": self.icon, "help": self.help or "",
                "fields": [f.schema() for f in self.fields]}


def action(type, label, group="Geral", icon="", help="", fields=None, validate=None):
    """Registra uma acao. validate: funcao(a) que levanta ValueError("mensagem")
    para regras alem das dos campos. (A edicao so acontece no proprio PC.)"""
    def deco(fn):
        if type in REGISTRY:
            raise ValueError("acao repetida: %s" % type)
        REGISTRY[type] = Action(type, label, fn, group, icon, help, fields, validate)
        return fn
    return deco


def get(type):
    return REGISTRY.get(type)


def run(a, key=None):
    """Executa a acao (dict com "type"). key: botao de origem ("p:b[:f]"),
    visivel para a acao em current_key() (passos de sequencia herdam)."""
    act = REGISTRY.get(a.get("type")) if isinstance(a, dict) else None
    if act is None:
        raise ValueError("tipo de acao desconhecido: %s" % (a.get("type") if isinstance(a, dict) else a))
    if key is None:
        return act.fn(a)
    old = getattr(CONTEXT, "key", None)
    CONTEXT.key = key
    try:
        return act.fn(a)
    finally:
        CONTEXT.key = old


def current_key():
    return getattr(CONTEXT, "key", None)


def schema():
    first = [REGISTRY[t] for t in ORDER if t in REGISTRY]
    rest = [act for t, act in REGISTRY.items() if t not in ORDER]
    return [act.schema() for act in first + rest]


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _empty(v):
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, (list, dict)) and not v)


def _check_field(f, a, n_pages, where):
    v = a.get(f.key)
    if _empty(v):
        if f.required:
            if f.kind in ("sound", "select", "page"):
                raise ValueError("%s: escolha \"%s\"" % (where, f.label))
            raise ValueError("%s: preencha \"%s\"" % (where, f.label))
        return
    name = "\"%s\"" % f.label
    if f.kind in ("text", "textarea", "sound"):
        if not isinstance(v, (str, int, float)):
            raise ValueError("%s: %s invalido" % (where, name))
    elif f.kind in ("obs_scene", "obs_input"):
        if not isinstance(v, str) or len(v) > 120 or "\n" in v:
            raise ValueError("%s: %s invalido" % (where, name))
    elif f.kind == "app":
        if not isinstance(v, str) or len(v) > 260 or "\n" in v:
            raise ValueError("%s: %s invalido" % (where, name))
    elif f.kind == "color":
        if not isinstance(v, str) or not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError("%s: %s deve ser uma cor #rrggbb" % (where, name))
    elif f.kind == "keys":
        if not isinstance(v, list):
            raise ValueError("%s: informe as teclas" % where)
        for k in v:
            try:
                vk_of(str(k))
            except ValueError as e:
                raise ValueError("%s: %s" % (where, e))
    elif f.kind == "number":
        if not _num(v):
            raise ValueError("%s: %s deve ser um numero" % (where, name))
        if (f.min is not None and v < f.min) or (f.max is not None and v > f.max):
            raise ValueError("%s: %s deve ficar entre %s e %s" % (where, name, f.min, f.max))
    elif f.kind == "select":
        if v not in [o["value"] for o in f.options]:
            raise ValueError("%s: %s invalido" % (where, name))
    elif f.kind == "page":
        if not isinstance(v, int) or isinstance(v, bool) or not (0 <= v < n_pages):
            raise ValueError("%s: pagina de destino invalida" % where)
    elif f.kind == "steps":
        if not isinstance(v, list):
            raise ValueError("%s: sequencia invalida" % where)
        for s in v:
            if isinstance(s, dict) and s.get("type") in NO_STEP:
                raise ValueError("%s: sequencia nao aceita pagina/sequencia" % where)
            validate(s, n_pages, where)
    # bool: aceita qualquer valor (na hora de rodar vira bool)


def validate(a, n_pages, where):
    """Confere uma acao antes de salvar. Levanta ValueError com mensagem."""
    if not isinstance(a, dict) or a.get("type") not in REGISTRY:
        raise ValueError("%s: tipo de acao invalido" % where)
    act = REGISTRY[a["type"]]
    for f in act.fields:
        _check_field(f, a, n_pages, where)
    if act.extra_validate:
        try:
            act.extra_validate(a)
        except ValueError as e:
            raise ValueError("%s: %s" % (where, e))


def _load():
    # imports explicitos: o PyInstaller enxerga e inclui os modulos
    from . import flow, keyboard, system, audio, web, apps, browser, obs  # noqa: F401  (ordem = ordem no editor)


_load()
