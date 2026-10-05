#!/usr/bin/env python3
"""Tests de la navigation vers un point (navigation.py) et du coin de sieste (etat va_au_coin de brain.py), sans
robot : un canard cinematique simplifie (vitesses reelles ~ ZONE_MORTE.md : 0,15 m/s, ~1 rad/s)."""
import math

from brain import Brain, Humeur
from navigation import AllerVers
from test_brain import FauxClient

LIBRE = {"devant": 3.0, "gauche": 3.0, "droite": 3.0, "vide": math.inf, "n": 0}


def roule(nav, x, y, yaw, secondes=60.0, libre=LIBRE):
    statuts = []
    for _ in range(int(secondes / 0.02)):
        statut, vx, vyaw = nav.commande(x, y, yaw, libre)
        statuts.append(statut)
        if statut in ("arrive", "bloque"):
            break
        yaw += 0.65 * vyaw * 0.02
        x += 0.375 * vx * math.cos(yaw) * 0.02
        y += 0.375 * vx * math.sin(yaw) * 0.02
    return statuts, (x, y, yaw)


def test_va_au_point_derriere_lui():
    statuts, (x, y, _) = roule(AllerVers((-1.5, 1.0)), 0.0, 0.0, 0.0)
    assert statuts[-1] == "arrive" and math.hypot(x + 1.5, y - 1.0) <= 0.25
    assert statuts[0] == "pivote", "il doit d'abord se tourner vers le point"
    changements = sum(1 for a, b in zip(statuts, statuts[1:]) if a != b)
    assert changements <= 4, f"oscillation pivote/avance : {changements} changements"


def test_bloque_par_un_obstacle_ou_sans_capteur():
    mur = {**LIBRE, "devant": 0.3}
    assert roule(AllerVers((2.0, 0.0)), 0.0, 0.0, 0.0, libre=mur)[0][-1] == "bloque"
    assert roule(AllerVers((2.0, 0.0)), 0.0, 0.0, 0.0, libre=None)[0][-1] == "bloque"
    assert AllerVers((2.0, 0.0)).commande(0.0, 0.0, 0.0, None)[1] == 0.0, "jamais de marche a l'aveugle"


class FauxTofLibre:
    def __init__(self):
        self.devant = 3.0

    def noter_etat(self, s):
        pass

    def libre(self, s):
        return {**LIBRE, "devant": self.devant}


def simule(b, c, secondes, monde, t0=0.0):
    for i in range(int(secondes / 0.02)):
        moves = [p for m, p in c.appels[-6:] if m == "robot.move"]
        if moves:
            mv = moves[-1]
            monde["yaw"] += 0.65 * mv["vyaw"] * 0.02
            monde["x"] += 0.375 * mv["vx"] * math.cos(monde["yaw"]) * 0.02
            monde["y"] += 0.375 * mv["vx"] * math.sin(monde["yaw"]) * 0.02
        b.tick({"t": t0 + i * 0.02, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [monde["x"], monde["y"], 0.11], "yaw": monde["yaw"]}}, 0.02)


def cerveau_fatigue(seed, tof=True):
    c = FauxClient()
    extras = {"tof": FauxTofLibre(), "exploration": False} if tof else {"exploration": False}
    b = Brain(c, Humeur(energie=0.2), seed=seed, extras=extras)
    b.exploration.preference(2.1, 0.6, "nap", 3600.0, 0.0)       # une heure de sieste deja passee la-bas
    return b, c


def test_fatigue_rejoint_son_coin_puis_sieste():
    b, c = cerveau_fatigue(70)
    monde = {"x": 0.0, "y": 0.0, "yaw": math.pi}
    simule(b, c, 60.0, monde)
    noms = [e[1] for e in b.journal]
    assert "va_au_coin" in noms and noms[noms.index("va_au_coin") + 1] == "nap", noms
    coin = b.exploration.coin_favori("nap", b.t_global)
    assert math.hypot(monde["x"] - coin[0], monde["y"] - coin[1]) <= 0.3, (monde, coin)
    assert b.etats["va_au_coin"].issue == "arrive"


def test_pas_de_coin_sans_capteur_ni_trop_pres_ni_batterie_basse():
    b, c = cerveau_fatigue(71, tof=False)
    simule(b, c, 20.0, {"x": 0.0, "y": 0.0, "yaw": 0.0})
    assert "va_au_coin" not in {e[1] for e in b.journal}, "sans capteur de distance, on ne marche pas"
    b, c = cerveau_fatigue(72)
    simule(b, c, 20.0, {"x": 2.0, "y": 0.6, "yaw": 0.0})
    assert "va_au_coin" not in {e[1] for e in b.journal}, "deja dans son coin"
    b, c = cerveau_fatigue(73)
    b.humeur.energie = 0.9
    for i in range(int(20.0 / 0.02)):
        b.tick({"t": i * 0.02, "safety": {"fallen": False}, "policy": "stand", "battery": {"percent": 10.0},
                "odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0}}, 0.02)
    noms = {e[1] for e in b.journal}
    assert "nap" in noms and "va_au_coin" not in noms, "batterie basse : sieste sur place"


def test_obstacle_sur_le_chemin_sieste_sur_place():
    b, c = cerveau_fatigue(74)
    b.ctx.extras["tof"].devant = 0.3
    simule(b, c, 30.0, {"x": 0.0, "y": 0.0, "yaw": 0.3})
    noms = [e[1] for e in b.journal]
    assert "va_au_coin" in noms and noms[noms.index("va_au_coin") + 1] == "nap", noms
    assert b.etats["va_au_coin"].issue == "bloque"
