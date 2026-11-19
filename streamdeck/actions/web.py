# -*- coding: utf-8 -*-
"""Acao web: chamar a API de um programa (ex.: programa de radio)."""
import urllib.request

from . import action, Field


def http_request(method, url, body=""):
    data = body.encode("utf-8") if body and method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        ctype = "application/json" if body.strip()[:1] in "{[" else "application/x-www-form-urlencoded"
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=5) as r:
        r.read(1024)
        print("  http %s %s -> %d" % (method, url, r.status))


def _validate(a):
    if not str(a.get("url", "")).startswith(("http://", "https://")):
        raise ValueError("o endereco deve comecar com http:// ou https://")


@action("http", "Chamar API do programa", group="Rádio", icon="radio",
        help="Para programas de rádio que têm API web (veja no manual do programa o endereço e os "
             "comandos). A chamada sai do PC, então 127.0.0.1 aponta para o próprio PC. Se o programa "
             "não tiver API, use “Atalho de teclado” com as teclas de atalho configuradas nele.",
        validate=_validate,
        fields=[Field("method", "Método", "select", default="GET",
                      options=[("GET", "GET"), ("POST", "POST")]),
                Field("url", "Endereço da API", "text", required=True, placeholder="http://127.0.0.1:porta/…"),
                Field("body", "Corpo (só para POST, opcional)", "textarea")])
def http(a):
    http_request(a.get("method", "GET").upper(), a["url"], a.get("body", ""))
