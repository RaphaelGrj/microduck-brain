#!/usr/bin/env python3
"""Liste des modules du cerveau a copier sur le canard : la fermeture des imports locaux de canard.py (rien de plus, ni
tests, ni diagnostics, ni outils du simulateur). Usage : python3 deploy/robot/modules.py  -> un nom de fichier par ligne."""
import ast
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def imports_locaux(fichier):
    noms = set()
    for n in ast.walk(ast.parse(fichier.read_text())):
        if isinstance(n, ast.Import):
            noms |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            noms.add(n.module.split(".")[0])
    return {m for m in noms if (RACINE / f"{m}.py").exists()}


def fermeture(depart="canard"):
    vus, a_voir = set(), [depart]
    while a_voir:
        m = a_voir.pop()
        if m in vus:
            continue
        vus.add(m)
        a_voir += sorted(imports_locaux(RACINE / f"{m}.py") - vus)
    return sorted(f"{m}.py" for m in vus)


if __name__ == "__main__":
    print("\n".join(fermeture(*sys.argv[1:])))
