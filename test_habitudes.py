#!/usr/bin/env python3
"""Habitudes sonores (habitudes.py) : heures d'habitude animees apprises par jour, semaine / week-end separes,
silence inhabituel -> petit tour ; bonjour du week-end."""
import math
import tempfile
from pathlib import Path

import memoire
from brain import Brain, Humeur
from habitudes import Habitudes
from test_brain import FauxClient, FauxHorloge, simule


def apprend(h, horloge, jours, heure=14, voix_par_heure=30, semaine=2):
    """Simule `jours` jours : `voix_par_heure` voix a l'heure donnee, puis l'heure suivante (cloture)."""
    for j in range(jours):
        horloge.jour, horloge.semaine, horloge.heure = 100 + j, semaine, heure
        for k in range(voix_par_heure):
            h.voix(float(k))
        horloge.heure = heure + 1
        h.avance()


def test_heure_animee_apres_trois_jours_et_semaine_separee():
    horloge = FauxHorloge(14)
    h = Habitudes(horloge=horloge)
    apprend(h, horloge, 2)
    horloge.heure, horloge.semaine = 14, 2
    assert not h.animee(), "pas d'habitude avant 3 jours"
    apprend(h, horloge, 1)
    horloge.heure = 14
    assert h.animee()
    horloge.semaine = 6
    assert not h.animee(), "le week-end a ses propres habitudes"
    horloge.semaine, horloge.heure = 2, 3
    assert not h.animee(), "3 h du matin : jamais animee"


def test_habitudes_sauvegardees_dans_la_memoire():
    with tempfile.TemporaryDirectory() as d:
        mem = memoire.Memoire(Path(d) / "m.json")
        horloge = FauxHorloge(14)
        h = Habitudes(mem.donnees.setdefault("ambiance", {}), horloge=horloge, sauver=mem.sauver)
        apprend(h, horloge, 3)
        relu = memoire.Memoire(Path(d) / "m.json")
        horloge.heure, horloge.semaine = 14, 2
        assert Habitudes(relu.donnees.get("ambiance"), horloge=horloge).animee()


class Tof:
    def noter_etat(self, s):
        pass

    def libre(self, s):
        return {"devant": 2.0, "gauche": 2.0, "droite": 2.0, "vide": math.inf, "n": 0}


def test_silence_inhabituel_petit_tour():
    horloge = FauxHorloge(14, semaine=2)
    b = Brain(FauxClient(), Humeur(energie=0.9), seed=700, horloge=horloge, extras={"tof": Tof(), "exploration": False})
    b.presents.add("Raphael")
    apprend(b.habitudes, horloge, 4)
    horloge.jour, horloge.semaine, horloge.heure = 200, 2, 14
    b.P_ATTENTE = b.P_SIGNATURE = b.P_REGARD_MYSTERE = b.P_GAG = b.P_OBSERVER = 0.0
    simule(b, 1700)
    assert "silence_curieux" not in [e[1] for e in b.journal], "moins de 30 min : pas encore inhabituel"
    simule(b, 400)
    noms = [e[1] for e in b.journal]
    assert noms.count("silence_curieux") == 1 and noms[noms.index("silence_curieux") + 1] == "wander", noms[-6:]


def test_bonjour_du_week_end():
    horloge = FauxHorloge(8, 0, semaine=5)       # samedi 8 h
    b = Brain(FauxClient(), Humeur(energie=0.9), seed=701, horloge=horloge, bonjour=(7, 30), bonjour_weekend=(9, 30))
    simule(b, 60)
    assert "bonjour" not in [e[1] for e in b.journal], "le samedi, pas avant 9 h 30"
    horloge.heure, horloge.minute = 9, 35
    simule(b, 60)
    assert "bonjour" in [e[1] for e in b.journal]
