#!/usr/bin/env python3
"""Reglages du cerveau modifiables depuis l'application : heures calmes, bonjour du matin (semaine, week-end), heures
des repas, auto-test du matin, rythme de la journee.

Ils sont gardes dans reglages.json (a cote de la memoire, MICRODUCK_REGLAGES pour un autre chemin), qui PREND LE DESSUS
sur la section [cerveau] de ha.toml : ha.toml (et son jeton) n'est jamais reecrit. Valeur null = desactive.
"""
import json
import os
from pathlib import Path

import memoire

CHEMIN_DEFAUT = Path(os.environ.get("MICRODUCK_REGLAGES", memoire.CHEMIN_DEFAUT.parent / "reglages.json"))
CLES = ("heures_calmes", "bonjour", "bonjour_weekend", "repas", "autotest", "circadien", "routines")
# routines programmables (liste fermee) : action de l'appli -> evenement du cerveau
ROUTINES = {"vient_me_voir": "routine_compagnie", "salut": "tour_salut", "danse": "commande:danse",
            "toupie": "tour_toupie", "jouer_balle": "jeu_balle", "jouer_soleil": "jeu_soleil", "jouer_cache": "jeu_cache",
            "ou_es_tu": "ou_es_tu", "diagnostic": "diagnostic", "calme_on": "calme_on", "calme_off": "calme_off"}


def heure(v):
    """12, "12", "12:30" -> (12, 0) / (12, 30) ; None si illisible."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return (v, 0) if 0 <= v < 24 else None
    h, _, m = str(v).strip().partition(":")
    if h.isdigit() and (m.isdigit() or not m) and 0 <= int(h) < 24 and 0 <= int(m or 0) < 60:
        return (int(h), int(m or 0))
    return None


def texte_heure(hm):
    return None if hm is None else f"{hm[0]:02d}:{hm[1]:02d}"


def valider(d):
    """Reglages envoyes par l'appli -> forme propre (celle de [cerveau] dans ha.toml), seulement les cles connues."""
    if not isinstance(d, dict):
        return None
    out = {}
    if "heures_calmes" in d:
        hc = d["heures_calmes"]
        ok = (isinstance(hc, (list, tuple)) and len(hc) == 2
              and all(isinstance(h, int) and not isinstance(h, bool) and 0 <= h < 24 for h in hc) and hc[0] != hc[1])
        out["heures_calmes"] = [hc[0], hc[1]] if ok else None
    for cle in ("bonjour", "bonjour_weekend"):
        if cle in d:
            out[cle] = texte_heure(heure(d[cle]))
    if "repas" in d:
        repas = d["repas"] if isinstance(d["repas"], list) else []
        out["repas"] = sorted({texte_heure(heure(r)) for r in repas[:6] if heure(r) is not None})
    for cle in ("autotest", "circadien"):
        if cle in d:
            out[cle] = bool(d[cle])
    if "routines" in d:
        out["routines"] = []
        for r in (d["routines"] if isinstance(d["routines"], list) else [])[:20]:
            if not isinstance(r, dict) or r.get("action") not in ROUTINES or heure(r.get("heure")) is None:
                continue
            jours = sorted({j for j in (r.get("jours") or []) if isinstance(j, int) and not isinstance(j, bool) and 0 <= j < 7})
            if jours:
                out["routines"].append({"heure": texte_heure(heure(r["heure"])), "jours": jours, "action": r["action"]})
    return out


def lire(chemin=CHEMIN_DEFAUT):
    try:
        return valider(json.loads(Path(chemin).read_text())) or {}
    except (OSError, ValueError):
        return {}


def ecrire(reglages, chemin=CHEMIN_DEFAUT):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(reglages, ensure_ascii=False))
    os.replace(tmp, chemin)


def pour_appli(cerveau):
    """Section [cerveau] (deja fusionnee) -> valeurs affichees dans l'appli."""
    hc = cerveau.get("heures_calmes")
    if isinstance(hc, str) and "-" in hc:
        a, _, b = hc.partition("-")
        hc = [int(a), int(b)] if a.strip().isdigit() and b.strip().isdigit() else None
    return {
        "heures_calmes": list(hc) if isinstance(hc, (list, tuple)) and len(hc) == 2 else None,
        "bonjour": texte_heure(heure(cerveau.get("bonjour"))),
        "bonjour_weekend": texte_heure(heure(cerveau.get("bonjour_weekend"))),
        "repas": sorted({texte_heure(heure(r)) for r in (cerveau.get("repas") or []) if heure(r) is not None}),
        "autotest": bool(cerveau.get("autotest", True)),
        "circadien": bool(cerveau.get("circadien", True)),
        "routines": (valider({"routines": cerveau.get("routines") or []}) or {}).get("routines", []),
    }


def appliquer(brain, cerveau):
    """Dans la boucle du cerveau : les reglages prennent effet tout de suite, sans redemarrer."""
    v = pour_appli(cerveau)
    brain.heures_calmes = tuple(v["heures_calmes"]) if v["heures_calmes"] else None
    brain.bonjour = heure(v["bonjour"])
    brain.bonjour_weekend = heure(v["bonjour_weekend"])
    brain.ctx.extras["repas"] = [heure(r) for r in v["repas"]]
    brain.ctx.extras["autotest"] = v["autotest"]
    brain.ctx.extras["circadien"] = v["circadien"]
    brain.routines = [(*heure(r["heure"]), tuple(r["jours"]), ROUTINES[r["action"]]) for r in v["routines"]]
