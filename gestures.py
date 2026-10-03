#!/usr/bin/env python3
"""Vocabulaire de gestes du canard, joues depuis le cerveau via l'API robotd.

Aucun entrainement RL : tout passe par des commandes que robotd accepte deja
(robot.head = decalages de tete, robot.move = vitesse, robot.do = skills).
Les gestes sont cadences sur le flux robot.state (une trame = ~20 ms), ce qui
donne en plus la mesure des joints pour verifier que le geste a bien eu lieu.

Usage : python3 gestures.py <non|oui|curieux|surpris|fatigue|tous>
"""
import math
import sys
import time

from poc_robotd_client import RobotdClient, SOCK_PATH

# Indices dans robot.state["joints"] : tete = neck_pitch, head_pitch, head_yaw, head_roll
HEAD_JOINTS = slice(5, 9)
SETTLE_S = 0.8  # retour a neutre apres un geste


def _smooth(t, t0, t1):
    """Rampe douce 0 -> 1 entre t0 et t1 (cosinus), pour eviter les a-coups."""
    if t <= t0:
        return 0.0
    if t >= t1:
        return 1.0
    return 0.5 - 0.5 * math.cos(math.pi * (t - t0) / (t1 - t0))


# Chaque geste : (duree_s, f(t) -> (neck_pitch, head_pitch, head_yaw, head_roll), move optionnel)
def non(t):
    return (0.0, 0.0, 0.9 * math.sin(2 * math.pi * t / 0.6), 0.0)


def oui(t):
    return (0.0, 0.5 * math.sin(2 * math.pi * t / 0.5), 0.0, 0.0)


def curieux(t):
    k = _smooth(t, 0.0, 0.5) * (1.0 - _smooth(t, 2.0, 2.5))
    return (0.0, 0.35 * k, 0.0, 0.3 * k)


def surpris(t):
    # Tete qui se redresse d'un coup (pitch negatif = vers le haut), puis relache.
    k = _smooth(t, 0.0, 0.15) * (1.0 - _smooth(t, 0.9, 1.6))
    return (0.0, -0.5 * k, 0.0, 0.0)


def fatigue(t):
    # Tete qui s'affaisse lentement.
    k = _smooth(t, 0.0, 2.0)
    return (0.0, 0.7 * k, 0.0, 0.0)


GESTES = {
    "non": (2.4, non),
    "oui": (1.2, oui),
    "curieux": (2.5, curieux),
    "surpris": (1.6, surpris),
    "fatigue": (2.0, fatigue),
}


def _head(c, vals):
    c.notify("robot.head", {
        "neck_pitch": vals[0], "head_pitch": vals[1],
        "head_yaw": vals[2], "head_roll": vals[3],
    })


def play(c: RobotdClient, name: str, backstep: bool = False) -> dict:
    """Joue un geste. Renvoie l'amplitude mesuree max par joint de tete (rad)."""
    duree, fn = GESTES[name]
    if name == "surpris":
        backstep = True
    base = c.read_state_frame()["joints"][HEAD_JOINTS]
    peak = [0.0] * 4

    t0 = time.monotonic()
    while True:
        t = time.monotonic() - t0
        if t >= duree:
            break
        state = c.read_state_frame()
        _head(c, fn(t))
        if backstep and 0.0 <= t <= 0.5:
            # petit recul : le deadman arrete le mouvement seul si on cesse d'envoyer
            c.notify("robot.move", {"vx": -0.1, "vy": 0.0, "vyaw": 0.0})
        j = state["joints"][HEAD_JOINTS]
        for i in range(4):
            peak[i] = max(peak[i], abs(j[i] - base[i]))

    # retour a neutre
    t1 = time.monotonic()
    while time.monotonic() - t1 < SETTLE_S:
        c.read_state_frame()
        _head(c, (0.0, 0.0, 0.0, 0.0))
    return {"amplitude_max": [round(p, 2) for p in peak]}


def fatigue_complet(c: RobotdClient):
    """Affaissement de tete, puis s'assoit (skill sit_toggle), repose, se releve."""
    play(c, "fatigue")
    c.request("robot.do", {"skill": "sit_toggle"})
    _wait(c, 4.0)
    c.request("robot.do", {"skill": "sit_toggle"})
    _wait(c, 4.0)


def _wait(c, secs):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        c.read_state_frame()


def main():
    cible = sys.argv[1] if len(sys.argv) > 1 else "tous"
    c = RobotdClient(SOCK_PATH)
    c.request("robot.subscribe", {})
    if cible == "fatigue_complet":
        fatigue_complet(c)
        print("fatigue_complet : tete affaissee, assis, puis releve", flush=True)
        return
    noms = list(GESTES) if cible == "tous" else [cible]
    for nom in noms:
        res = play(c, nom)
        print(f"{nom:8s} amplitude mesuree (neck,pitch,yaw,roll) = {res['amplitude_max']}", flush=True)


if __name__ == "__main__":
    main()
