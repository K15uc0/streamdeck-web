# -*- coding: utf-8 -*-
"""
Stream Deck caseiro: servidor que roda no PC (Windows).
O tablet abre a pagina no navegador e cada botao dispara uma acao aqui.
Sem dependencias: so a biblioteca padrao do Python 3.8+.
O codigo fica no pacote streamdeck/ (veja docs/ARQUITETURA.md).
"""
import os
import sys
import traceback


def _falha(texto):
    """Erro fatal na partida: o .exe nao tem janela, entao grava um arquivo
    e mostra uma caixa de mensagem (senao parece que "nao abriu")."""
    pasta = os.environ.get("STREAMDECK_DATA") or os.path.join(os.path.expanduser("~"), "Documents", "StreamDeck")
    caminho = os.path.join(pasta, "erro-ao-abrir.txt")
    try:
        os.makedirs(pasta, exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(texto)
    except OSError:
        caminho = "(nao foi possivel gravar o arquivo)"
    if sys.platform.startswith("win") and "--sem-bandeja" not in sys.argv:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, "O Stream Deck nao conseguiu abrir.\n\nDetalhes em:\n%s\n\n%s"
                % (caminho, texto[-1500:]), "Stream Deck", 0x10)
        except Exception:
            pass
    try:
        sys.__stderr__.write(texto)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        from streamdeck.app import main
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException:
        _falha(traceback.format_exc())
        sys.exit(1)
