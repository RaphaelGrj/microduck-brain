#!/usr/bin/env python3
"""Ce que robot.state apporte deja (ou apportera) au cerveau : micro de robotd (champ audio, patch contrib/), canard
pris dans les bras (safety.picked_up), courant des servos de tete (currents_ma) pour la caresse."""
import random

from brain import Brain, Humeur
from caresse import DetecteurCaresse
from test_brain import FauxClient


def etat(t, **extra):
    s = {"t": t, "safety": {"fallen": False, "picked_up": extra.pop("porte", False)}, "policy": "stand",
         "odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0}}
    s.update(extra)
    return s


def roule(b, t0, secondes, **extra):
    for i in range(int(secondes / 0.02)):
        b.tick(etat(t0 + i * 0.02, **{k: (v(t0 + i * 0.02) if callable(v) else v) for k, v in extra.items()}), 0.02)


def test_compteurs_audio_de_robotd():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=400)
    b.fin_etat = 1e9
    audio = lambda t: {"petting": 2 < t < 4, "pettings": 7 + (t > 2), "noises": 3 + (t > 9), "voices": 1 + (t > 11)}
    roule(b, 0.0, 12.0, audio=audio)
    noms = [e[1] for e in b.journal]
    assert noms.count("caresse") == 1, noms                    # un seul : les compteurs initiaux ne comptent pas
    assert "son_bref" in noms
    sons = [p["tag"] for m, p in c.appels if m == "robot.sound"]
    assert sons.count("coo") >= 1


def test_pris_dans_les_bras_puis_repose():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=401)
    roule(b, 0.0, 2.0)
    n_avant = len([1 for m, p in c.appels if m == "robot.move" and (p["vx"] or p["vyaw"])])
    roule(b, 2.0, 20.0, porte=True)
    assert b.courant.nom == "porte"
    assert len([1 for m, p in c.appels if m == "robot.move" and (p["vx"] or p["vyaw"])]) == n_avant, \
        "aucune commande de marche dans les bras"
    b.evenement("tour_toupie")
    roule(b, 22.0, 2.0, porte=True)
    assert b.courant.nom == "porte", "dans les bras, une demande de toupie attend"
    roule(b, 24.0, 3.0)
    noms = [e[1] for e in b.journal]
    assert noms[noms.index("porte") + 1] == "ebouriffe", noms
    assert "toupie" in noms[noms.index("porte"):], "la demande en attente est jouee une fois repose"


def test_caresse_par_le_courant_des_servos():
    rng = random.Random(3)
    d = DetecteurCaresse()
    ev = []
    for i in range(500):
        t = i * 0.02
        joints = [0.0 + rng.gauss(0, 0.003) for _ in range(4)]          # la tete ne bouge pas (servo raide)...
        courants = [80 + rng.gauss(0, 5) + (90 if 5 < t < 7 and k == 1 else 0) for k in range(4)]  # ...mais force
        ev += [t] if d.mise_a_jour(t, (0, 0, 0, 0), joints, True, courants) else []
    assert len(ev) == 1 and 5.3 <= ev[0] < 5.5, ev
    d = DetecteurCaresse()
    assert not any(d.mise_a_jour(i * 0.02, (0, 0, 0, 0), [0.0] * 4, True, [80 + rng.gauss(0, 5)] * 4)
                   for i in range(500)), "bruit de courant seul : rien"
