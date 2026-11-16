"""Extrai do CHANGELOG.md as notas de uma versao (usado na publicacao)."""
import sys

ver = sys.argv[1].lstrip("vV")
out, on = [], False
for line in open("CHANGELOG.md", encoding="utf-8"):
    if line.startswith("## "):
        if on:
            break
        on = line[3:].strip().split(" ")[0].lstrip("vV") == ver
        continue
    if on:
        out.append(line.rstrip("\n"))
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(out).strip() or "Versão %s" % ver)
