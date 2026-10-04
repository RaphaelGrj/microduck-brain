#!/usr/bin/env python3
"""Resume un journal d'evaluation (approach_eval.py) : pour chaque essai sans tir, combien de fois le controleur est passe
par chaque etat et combien de fois il a perdu la balle de vue. Usage : python resume_eval.py <journal.out>"""
import re
import sys
from collections import Counter

essai, c = None, Counter()
for ligne in open(sys.argv[1], encoding="utf-8", errors="replace"):
    if ligne.startswith("#####"):
        essai, c = ligne.strip("# \n"), Counter()
    elif "-->" in ligne:
        c[ligne.split("-->")[1].split()[0]] += 1
    elif "[perte" in ligne:
        c["pertes de vue"] += 1
    elif "coupee par le bord" in ligne:
        c["balle coupee"] += 1
    elif "trop d'ajustements" in ligne:
        c["trop d'ajustements"] += 1
    elif "balle a cote du pied" in ligne:
        c["balle a cote du pied"] += 1
    elif re.search(r"^\s+\[\d+\] balle", ligne):
        c["ajustements"] += 1
    elif "temps ecoule" in ligne and essai:
        print(f"{essai[:50]:50s} | " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
