#!/usr/bin/env python3
"""Les modules du 'pont + cerveau' tournent-ils sous Python 3.11 (Debian/Armbian du canard) ? Test STATIQUE :
grammaire 3.11 et f-strings a guillemets imbriques identiques (autorises seulement depuis 3.12, PEP 701).
Ne remplace pas un vrai essai sur un Pi, mais attrape les erreurs de syntaxe."""
import ast
import io
import sys
import tokenize
from pathlib import Path

FICHIERS = sys.argv[1:] or ["pont_ha.py", "brain.py", "gestures.py", "poc_robotd_client.py"]
total = 0
for nom in FICHIERS:
    src = Path(nom).read_text(encoding="utf-8")
    try:
        ast.parse(src, feature_version=(3, 11))
    except SyntaxError as e:
        print(f"{nom}: grammaire 3.11 refusee : {e}")
        total += 1
    pile = []                                   # guillemets des f-strings ouvertes
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.FSTRING_START:
            pile.append(tok.string[-1])
        elif tok.type == tokenize.FSTRING_END:
            pile.pop()
        elif tok.type == tokenize.STRING and pile and tok.string.lstrip("rbfuRBFU")[0] == pile[-1]:
            print(f"{nom}:{tok.start[0]}: guillemet imbrique identique dans une f-string (illegal avant 3.12)")
            total += 1
    imports = sorted({l.split()[1].split(".")[0] for l in src.splitlines() if l.startswith(("import ", "from "))})
    print(f"{nom}: imports = {imports}")
print("compatible 3.11 (test statique)" if total == 0 else f"{total} probleme(s)")
