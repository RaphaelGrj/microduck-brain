#!/usr/bin/env python3
"""Studio de chorégraphies de l'application : des tours composés pas à pas, avec ses seuls moyens d'expression
(règle d'identité) : positions de tête, sons de canard, gestes de gestures.py, s'asseoir / se relever, pauses.

Gardées dans choregraphies.json (à côté de la mémoire). Le cerveau les joue dans l'état « choregraphie » ; on peut
aussi les programmer dans une routine (« choregraphie:<nom> »). Les mouvements du corps qui risquent une chute
(roulade, tir) ne sont pas proposés ici : seulement s'asseoir et se relever.
"""
import json
import os
from pathlib import Path

import gestures
import memoire
from etats_base import SONS_CANARD, Etat

CHEMIN_DEFAUT = Path(os.environ.get("MICRODUCK_CHOREGRAPHIES", memoire.CHEMIN_DEFAUT.parent / "choregraphies.json"))
MAX_CHOREGRAPHIES, MAX_ETAPES, DUREE_MAX_S = 30, 40, 60.0
# bornes de tete (decalages robot.head, rad) : celles du regard guide, un peu elargies
BORNES = {"cou": (-0.3, 0.4), "tangage": (-0.5, 0.6), "lacet": (-0.9, 0.9), "roulis": (-0.4, 0.4)}
GESTES = sorted(g for g in gestures.GESTES if g.isalpha())


def _nombre(v, bas, haut, defaut=0.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return defaut
    return max(bas, min(haut, x)) if x == x else defaut


def valider_etape(e):
    if not isinstance(e, dict):
        return None
    t = e.get("type")
    if t == "tete":
        return {"type": "tete", **{k: round(_nombre(e.get(k), *b), 3) for k, b in BORNES.items()},
                "duree": round(_nombre(e.get("duree"), 0.2, 5.0, 1.0), 2)}
    if t == "son" and e.get("son") in SONS_CANARD:
        return {"type": "son", "son": e["son"]}
    if t == "geste" and e.get("geste") in GESTES:
        return {"type": "geste", "geste": e["geste"]}
    if t == "assis":
        return {"type": "assis"}
    if t == "pause":
        return {"type": "pause", "duree": round(_nombre(e.get("duree"), 0.2, 10.0, 1.0), 2)}
    return None


def duree_etape(e):
    if e["type"] in ("tete", "pause"):
        return e["duree"]
    if e["type"] == "geste":
        return gestures.GESTES[e["geste"]][0]
    if e["type"] == "assis":
        return 2.5
    return 0.4                                          # un son


def valider(liste):
    """Liste envoyee par l'appli -> [{"nom", "etapes"}] propres (noms uniques, duree totale bornee)."""
    out, noms = [], set()
    for c in (liste if isinstance(liste, list) else [])[:MAX_CHOREGRAPHIES]:
        if not isinstance(c, dict):
            continue
        nom = "".join(x for x in str(c.get("nom") or "") if x.isprintable() and x not in "|:").strip()[:40]
        if not nom or nom.lower() in noms:
            continue
        etapes, total = [], 0.0
        for e in (c.get("etapes") or [])[:MAX_ETAPES]:
            p = valider_etape(e)
            if p is not None and total + duree_etape(p) <= DUREE_MAX_S:
                etapes.append(p)
                total += duree_etape(p)
        if etapes:
            noms.add(nom.lower())
            out.append({"nom": nom, "etapes": etapes})
    return out


def lire(chemin=None):
    try:
        return valider(json.loads(Path(chemin or CHEMIN_DEFAUT).read_text()))
    except (OSError, ValueError):
        return []


def ecrire(liste, chemin=None):
    chemin = Path(chemin or CHEMIN_DEFAUT)
    propre = valider(liste)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(propre, ensure_ascii=False))
    os.replace(tmp, chemin)
    return propre


class Choregraphie(Etat):
    """Joue une chorégraphie : la tête glisse d'une position à la suivante, les sons partent à leur tour."""
    nom = "choregraphie"

    def __init__(self):
        self.etapes, self.titre = [], None

    def charger(self, titre, etapes):
        self.titre, self.etapes = titre, list(etapes)

    def entre(self, brain):
        self.plan, t = [], 0.0
        for e in self.etapes:
            d = duree_etape(e)
            self.plan.append((t, d, e))
            t += d
        self.total = t
        self.faits = set()
        self.tete = (0.0, 0.0, 0.0, 0.0)
        self.depart = self.tete

    def duree(self, brain):
        return self.total + 0.5

    def pas(self, brain, t):
        tete = self.tete
        for i, (t0, d, e) in enumerate(self.plan):
            if not (t0 <= t < t0 + d):
                continue
            if i not in self.faits:
                self.faits.add(i)
                self.depart = self.tete
                if e["type"] == "son":
                    brain.ctx.sound(e["son"])
                elif e["type"] == "assis":
                    brain.ctx.toggle_sit()
            if e["type"] == "tete":
                k = min(1.0, (t - t0) / max(0.2, d * 0.6))     # glisse vers la position, puis la tient
                cible = (e["cou"], e["tangage"], e["lacet"], e["roulis"])
                tete = tuple(a + (b - a) * k for a, b in zip(self.depart, cible))
            elif e["type"] == "geste":
                tete = gestures.GESTES[e["geste"]][1](t - t0)
        self.tete = tete                                    # (point de depart de l'etape suivante)
        brain.ctx.head(tete)
        brain.ctx.move()

    def sort(self, brain):
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))
