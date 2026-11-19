# -*- coding: utf-8 -*-
"""
Stream Deck caseiro: servidor que roda no PC (Windows).
O tablet abre a pagina no navegador e cada botao dispara uma acao aqui.
Sem dependencias: so a biblioteca padrao do Python 3.8+.
O codigo fica no pacote streamdeck/ (veja docs/ARQUITETURA.md).
"""
from streamdeck.app import main

if __name__ == "__main__":
    main()
