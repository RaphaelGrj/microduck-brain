#!/usr/bin/env python3
"""Personnalite (personnalite.py + brain.py) : temperament unique et persistant, faconne par les experiences, retour
lent vers la base, effets sur les envies ; neutre sans memoire."""
import random
import tempfile
from pathlib import Path

import memoire
from brain import Brain, Humeur
from personnalite import TRAITS, Personnalite
from test_brain import FauxClient, FauxHorloge, simule


def test_neutre_sans_memoire_unique_avec():
    p = Personnalite()
    assert all(p.trait(t) == 0.5 for t in TRAITS)
    assert p.envie_promenade() == 1.0 and p.envie_taquiner() == 1.0 and p.patience_seul() == 1.0
    a = Personnalite({}, rng=random.Random(1))
    b = Personnalite({}, rng=random.Random(2))
    assert a.d["base"] != b.d["base"], "deux canards n'ont pas le meme temperament"
    assert all(0.3 <= v <= 0.7 for v in a.d["base"].values())


def test_experiences_et_retour_vers_la_base():
    p = Personnalite({}, rng=random.Random(3))
    base = p.trait("sociabilite")
    for _ in range(10):
        p.vit("caresse")
    assert abs(p.trait("sociabilite") - (base + 0.2)) < 1e-9
    p.vit("stop")
    assert p.trait("espieglerie") < p.d["base"]["espieglerie"]
    p.avance(0.0)
    p.avance(3 * 86400.0)                          # trois jours sans experience : moitie du chemin
    assert abs(p.trait("sociabilite") - (base + 0.1)) < 1e-6


def test_effets_sur_les_envies():
    p = Personnalite()
    p.d["traits"]["espieglerie"] = 0.9
    p.d["traits"]["sociabilite"] = 0.9
    assert p.envie_taquiner() > 1.0 and p.patience_seul() < 1.0
    p.d["traits"]["prudence"] = 0.95
    assert p.envie_promenade() < 1.0


def test_sauvegardee_et_faconnee_par_la_vie_du_canard():
    with tempfile.TemporaryDirectory() as d:
        mem = memoire.Memoire(Path(d) / "m.json")
        b = Brain(FauxClient(), Humeur(energie=0.9), seed=800, horloge=FauxHorloge(15), extras={"memoire": mem})
        base = dict(b.perso.d["base"])
        simule(b, 30, evenements=[(1.0, "caresse"), (10.0, "caresse"), (20.0, "stop_taquinerie")])
        assert b.perso.trait("sociabilite") > base["sociabilite"]
        assert b.perso.trait("espieglerie") < base["espieglerie"]
        simule(b, 3700)                           # une heure : sauvegarde
        relu = memoire.Memoire(Path(d) / "m.json")
        assert relu.donnees["personnalite"]["base"] == base, "le temperament de base ne change jamais"


def test_un_canard_tres_sociable_cherche_la_compagnie_plus_tot():
    def premiere_recherche(sociabilite):
        b = Brain(FauxClient(), Humeur(energie=0.9), seed=801, horloge=FauxHorloge(15))
        b.presents.add("Raphael")
        b.P_ATTENTE = b.P_SIGNATURE = b.P_REGARD_MYSTERE = b.P_GAG = 0.0
        b.perso.d["traits"]["sociabilite"] = sociabilite
        simule(b, 900)
        return next((e[0] for e in b.journal if e[1] == "cherche_attention"), None)
    sociable, solitaire = premiere_recherche(0.95), premiere_recherche(0.5)
    assert sociable is not None and solitaire is not None and sociable < solitaire, (sociable, solitaire)
