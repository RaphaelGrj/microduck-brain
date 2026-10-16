#!/usr/bin/env python3
"""Atelier : programmer le canard avec des blocs (façon Scratch) - SANS jamais executer de code sur le robot.

Les blocs envoyes par l'appli sont une arborescence de donnees ; ce module les « compile » en etapes de chorégraphie
(choregraphies.py) : la meme liste fermee de moyens d'expression (tete bornee, sons de canard, gestes, s'asseoir, pause),
validee et bornee par choregraphies.valider_etape. Un bloc « repeter » est deroule a la compilation. Rien d'autre n'est
possible : pas de vitesse brute, pas de roulade ni de tir, pas de son hors de la banque du canard (regle d'identite).

Blocs : {"type": "tete"|"son"|"geste"|"assis"|"pause", ...champs de choregraphies...}
        {"type": "repeter", "n": 1..MAX_REPETITIONS, "blocs": [...]}
"""
import choregraphies

MAX_REPETITIONS = 10
PROFONDEUR_MAX = 3                     # repeter dans repeter dans repeter, pas plus
MAX_BLOCS = 120                        # taille de l'arbre accepte (avant deroulage)


def compiler(blocs):
    """-> {"etapes": [...], "duree": s, "tronque": bool, "ignores": n}. `tronque` : le deroulage a depasse la limite
    d'etapes ou de duree des chorégraphies (le debut est garde). `ignores` : blocs inconnus ou mal formes."""
    etat = {"etapes": [], "total": 0.0, "tronque": False, "ignores": 0, "vus": 0}
    _derouler(blocs if isinstance(blocs, list) else [], 0, etat)
    return {"etapes": etat["etapes"], "duree": round(etat["total"], 2), "tronque": etat["tronque"],
            "ignores": etat["ignores"]}


def _derouler(blocs, profondeur, etat):
    for b in blocs:
        if etat["tronque"]:
            return
        etat["vus"] += 1
        if etat["vus"] > MAX_BLOCS:
            etat["tronque"] = True
            return
        if not isinstance(b, dict):
            etat["ignores"] += 1
            continue
        if b.get("type") == "repeter":
            if profondeur >= PROFONDEUR_MAX - 1 or not isinstance(b.get("blocs"), list):
                etat["ignores"] += 1
                continue
            try:
                n = int(b.get("n", 1))
            except (TypeError, ValueError):
                n = 1
            for _ in range(max(1, min(MAX_REPETITIONS, n))):
                _derouler(b["blocs"], profondeur + 1, etat)
                if etat["tronque"]:
                    return
            continue
        e = choregraphies.valider_etape(b)
        if e is None:
            etat["ignores"] += 1
            continue
        d = choregraphies.duree_etape(e)
        if len(etat["etapes"]) >= choregraphies.MAX_ETAPES or etat["total"] + d > choregraphies.DUREE_MAX_S:
            etat["tronque"] = True
            return
        etat["etapes"].append(e)
        etat["total"] += d


def catalogue():
    """Ce que l'appli propose dans sa palette (et les bornes a afficher)."""
    return {"sons": sorted(choregraphies.SONS_CANARD), "gestes": choregraphies.GESTES, "bornes": choregraphies.BORNES,
            "max_repetitions": MAX_REPETITIONS, "max_etapes": choregraphies.MAX_ETAPES,
            "duree_max": choregraphies.DUREE_MAX_S}
