#!/usr/bin/env python3
"""Un pas en avant pousse-t-il la balle ? Balle posee a x (devant le tronc), y (lateral), rafale vx=0,4 de duree T, tete
en posture de marche : on mesure de combien la balle a bouge (verite terrain). But : trouver d'ou l'on peut avancer
sans toucher la balle, pour le dernier pas avant le tir. Usage : bash ~/run-brain.sh diag_pousse.py (arene conseillee)"""
import math
import time

import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

XS = (0.12, 0.15, 0.18, 0.22)
YS = (0.0, 0.042, 0.08)
TS = (0.25, 0.40)
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def commande(vx, secs):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        s = c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.4, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": vx, "vy": 0.0, "vyaw": 0.0})
    return s


print(f"{'x':>5} {'y':>6} {'T':>5}  balle deplacee (cm)  [avance du canard (cm)]", flush=True)
for T in TS:
    for y in YS:
        for x in XS:
            commande(0.0, 1.2)
            gt = truth.teleport_duck(0.0, 0.0, 0.0)
            commande(0.0, 0.8)
            gt = truth.read()
            d = gt["ducks"][0]
            truth.teleport("testball", d["pos"][0] + x, d["pos"][1] + y)
            commande(0.0, 0.6)
            g0 = truth.read()
            b0, d0 = g0["bodies"]["testball"], g0["ducks"][0]["pos"]
            commande(0.4, T)
            commande(0.0, 1.5)
            g1 = truth.read()
            b1, d1 = g1["bodies"]["testball"], g1["ducks"][0]["pos"]
            depl = math.dist(b0[:2], b1[:2]) * 100
            print(f"{x:5.2f} {y:+6.3f} {T:5.2f}  {depl:6.1f}{'  <- POUSSEE' if depl > 1.5 else ''}   [{(d1[0] - d0[0]) * 100:+.1f}]",
                  flush=True)
