"""Gera build/version_info.txt (informacoes de versao do StreamDeck.exe)
a partir de VERSION em streamdeck/__init__.py. Usado na publicacao."""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(RAIZ, "streamdeck", "__init__.py"), encoding="utf-8") as f:
    ver = re.search(r'^VERSION = "([^"]+)"', f.read(), re.M).group(1)
nums = [int("".join(c for c in p if c.isdigit()) or 0) for p in ver.split(".")][:4]
nums += [0] * (4 - len(nums))
tup = "(%d, %d, %d, %d)" % tuple(nums)
txt = "%d.%d.%d.%d" % tuple(nums)

conteudo = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(tup)s, prodvers=%(tup)s, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('041604B0', [
        StringStruct('CompanyName', 'Stream Deck caseiro'),
        StringStruct('FileDescription', 'Stream Deck - painel de botoes pelo celular'),
        StringStruct('FileVersion', '%(txt)s'),
        StringStruct('InternalName', 'StreamDeck'),
        StringStruct('OriginalFilename', 'StreamDeck.exe'),
        StringStruct('ProductName', 'Stream Deck'),
        StringStruct('ProductVersion', '%(ver)s')])
    ]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])
  ]
)
""" % {"tup": tup, "txt": txt, "ver": ver}

os.makedirs(os.path.join(RAIZ, "build"), exist_ok=True)
saida = os.path.join(RAIZ, "build", "version_info.txt")
with open(saida, "w", encoding="utf-8") as f:
    f.write(conteudo)
print("versao %s -> %s" % (ver, saida))
