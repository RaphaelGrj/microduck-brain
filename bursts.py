#!/usr/bin/env python3
"""Table des rafales de marche : de combien le canard se deplace-t-il pour une commande tenue T secondes ?

Pour chaque primitive (vx, vy, vyaw) et duree, mesure sur la VERITE TERRAIN le deplacement du
tronc (avant, gauche, rotation) dans son repere initial, une fois l'arret stabilise. C'est la
resolution d'un controleur d'approche qui avance par rafales : la zone morte (voir ZONE_MORTE.md)
interdit les petites vitesses, il reste a doser la DUREE.

Usage : bash ~/run-brain.sh bursts.py [repetitions=2]
"""
import math
import sys
import time

import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

import os

PRIMITIVES = [  # (vx, vy, vyaw)
    (0.3, 0.0, 0.0), (0.4, 0.0, 0.0),
    (0.0, 0.3, 0.0), (0.0, -0.3, 0.0), (0.0, 0.4, 0.0),
    (0.0, 0.0, 1.2), (0.0, 0.0, -1.2), (0.0, 0.0, 1.5),
]
DUREES = (0.25, 0.5, 1.0)
# BURSTS_REDUIT=1 : seulement vx=0.4, vy=0.4, vyaw=1.5 (inclinaison de tete : variable HEAD_PITCH, defaut 0)
if os.environ.get("BURSTS_REDUIT"):
    PRIMITIVES = [(0.4, 0.0, 0.0), (-0.4, 0.0, 0.0), (0.0, 0.4, 0.0), (0.0, -0.4, 0.0), (0.0, 0.0, 1.5)]
    DUREES = (0.5, 1.0)
if os.environ.get("BURSTS_ROT"):               # seulement la rotation, pour trouver a quelle inclinaison elle s'eteint
    PRIMITIVES = [(0.0, 0.0, 1.5), (0.0, 0.0, -1.5)]
    DUREES = (0.5, 1.0)
HEAD_PITCH = float(os.environ.get("HEAD_PITCH", "0"))
rep = int(sys.argv[1]) if len(sys.argv) > 1 else 2

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def commande(vx, vy, vyaw, secs):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": HEAD_PITCH, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": vx, "vy": vy, "vyaw": vyaw})


def pose():
    d = truth.read()["ducks"][0]
    return d["pos"][0], d["pos"][1], truth.trunk_yaw(d["quat"])


def stabilise():
    """Arret commande jusqu'a ce que la politique soit revenue en `stand` et immobile."""
    commande(0.0, 0.0, 0.0, 1.0)
    for _ in range(40):
        commande(0.0, 0.0, 0.0, 0.1)
        s = c.read_state_frame()
        if s["policy"] == "stand":
            break
    commande(0.0, 0.0, 0.0, 0.6)


stabilise()
print(f"{'commande':>22} {'duree':>5}  deplacement (avant, gauche en cm ; rotation en deg) sur {rep} essais", flush=True)
for (vx, vy, vyaw) in PRIMITIVES:
    for T in DUREES:
        res = []
        for _ in range(rep):
            truth.teleport_duck(0.0, 0.0, 0.0)
            stabilise()
            x0, y0, yaw0 = pose()
            commande(vx, vy, vyaw, T)
            stabilise()
            x1, y1, yaw1 = pose()
            dx, dy = x1 - x0, y1 - y0
            av = dx * math.cos(yaw0) + dy * math.sin(yaw0)
            ga = -dx * math.sin(yaw0) + dy * math.cos(yaw0)
            rot = (math.degrees(yaw1 - yaw0) + 180) % 360 - 180
            res.append((av * 100, ga * 100, rot))
        txt = "  |  ".join(f"{a:+5.1f} {g:+5.1f} {r:+6.1f}" for a, g, r in res)
        print(f"  vx={vx:+.1f} vy={vy:+.1f} vyaw={vyaw:+.1f} {T:5.2f}s:  {txt}", flush=True)
