#!/usr/bin/env python3
"""Tests de la caresse (caresse.py + etat caresse de brain.py), sans robot : joints de tete synthetiques."""
import random

from brain import Brain, Humeur
from caresse import DetecteurCaresse
from test_brain import FauxClient

CONSIGNE = (0.0, 0.0, 0.0, 0.0)
REPOS = [0.02, -0.01, 0.0, 0.005]


def joints(rng, appui=0.0):
    return [r + rng.gauss(0, 0.004) + (appui if i == 1 else 0.0) for i, r in enumerate(REPOS)]


def deroule(det, secondes, appui_entre=None, appui=0.1, t0=0.0, consigne=CONSIGNE, immobile=True, seed=0):
    rng, ev = random.Random(seed), []
    for i in range(int(secondes / 0.02)):
        t = t0 + i * 0.02
        a = appui if appui_entre and appui_entre[0] <= t < appui_entre[1] else 0.0
        if det.mise_a_jour(t, consigne, joints(rng, a), immobile):
            ev.append(round(t, 2))
    return ev


def test_bruit_seul_ne_declenche_rien():
    assert deroule(DetecteurCaresse(), 60.0) == []


def test_main_sur_la_tete():
    ev = deroule(DetecteurCaresse(), 10.0, appui_entre=(4.0, 6.0))
    assert len(ev) == 1 and 4.3 <= ev[0] < 4.5, ev


def test_appui_bref_ou_faible_ignore():
    assert deroule(DetecteurCaresse(), 10.0, appui_entre=(4.0, 4.15)) == [], "un choc n'est pas une caresse"
    assert deroule(DetecteurCaresse(), 10.0, appui_entre=(4.0, 8.0), appui=0.03) == [], "sous le seuil"


def test_pas_de_mesure_pendant_l_etablissement():
    # une main deja posee pendant que la tete rejoint sa consigne fausserait le repos : rien avant 1,5 s, et un
    # appui qui commence a 0,5 s fait partie du "repos" (pas d'evenement) - limite assumee.
    assert deroule(DetecteurCaresse(), 6.0, appui_entre=(0.5, 6.0)) == []


def test_corps_en_mouvement_ou_consigne_qui_change():
    assert deroule(DetecteurCaresse(), 10.0, appui_entre=(4.0, 6.0), immobile=False) == []
    det = DetecteurCaresse()
    rng = random.Random(1)
    for i in range(500):                    # consigne qui bouge a chaque trame (LookAround) : jamais de repos mesure
        t = i * 0.02
        assert det.mise_a_jour(t, (0.0, 0.0, 0.1 * (i % 7), 0.0), joints(rng, 0.1 if t > 4 else 0.0)) == []


def test_delai_entre_deux_caresses():
    det2 = DetecteurCaresse(delai_s=15.0)
    rng = random.Random(2)
    n = 0
    for i in range(int(40 / 0.02)):
        t = i * 0.02
        appui = 0.1 if (4 <= t < 6 or 9 <= t < 11 or 25 <= t < 27) else 0.0
        n += len(det2.mise_a_jour(t, CONSIGNE, joints(rng, appui)))
    assert n == 2, f"{n} caresses (attendu 2 : la 2e est trop proche de la 1re)"


def simule(b, secondes, appui_entre=None, t0=0.0, seed=0):
    rng = random.Random(seed)
    for i in range(int(secondes / 0.02)):
        t = t0 + i * 0.02
        a = 0.1 if appui_entre and appui_entre[0] <= t < appui_entre[1] else 0.0
        b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand",
                "joints": [0.0] * 5 + joints(rng, a) + [0.0] * 6}, 0.02)


def test_cerveau_roucoule_et_se_tremousse():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9, eveil=0.5), seed=50)
    b.fin_etat = 1e9
    simule(b, 8.0, appui_entre=(4.0, 6.0))
    assert "caresse" in {e[1] for e in b.journal}, b.journal
    assert any(m == "robot.sound" and p == {"tag": "coo"} for m, p in c.appels)
    assert any(m == "robot.pose" and p["active"] for m, p in c.appels), "pas de tremoussement de contentement"


def test_caresse_externe_pendant_la_sieste_ne_reveille_pas():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.1), seed=51)
    simule(b, 18.0)
    assert b.courant.nom == "nap"
    coo = lambda: sum(1 for m, p in c.appels if m == "robot.sound" and p == {"tag": "coo"})
    avant = coo()
    b.evenement("caresse")                  # pet-detect officiel, plus tard
    simule(b, 0.1, t0=18.0)
    assert b.courant.nom == "nap", "une caresse ne doit pas reveiller"
    assert coo() == avant + 1, "un roucoulement dans son sommeil"
