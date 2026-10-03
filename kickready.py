#!/usr/bin/env python3
"""Experience de tir : un tir a la position d'entrainement frappe-t-il vraiment la balle ?

Utilise la VERITE TERRAIN du simulateur (truth.py) pour mesurer : position de la balle dans le
repere du tronc avant le tir, et son deplacement apres. La camera ne voit pas la balle a cette
position (elle est sous la tete), d'ou la regle externe.

Usage : bash ~/run-brain.sh kickready.py right|left   (scene kick_right / kick_left conseillee)
"""
import math
import sys
import time

import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

cote = sys.argv[1] if len(sys.argv) > 1 else "right"
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def tenir(secs):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})


tenir(2.0)
# Le canard demarre assis et repousse une balle posee a cote de lui en se levant : on ne la place
# qu'une fois debout, directement dans son repere actuel (position d'entrainement exacte).
bruit = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (0.0, 0.0)
gt0 = truth.place_devant_pied("testball", cote, bruit=bruit)
tenir(1.0)  # laisse la balle se poser
gt0 = truth.read()
print("AVANT :", truth.describe(gt0), flush=True)
x0, y0, _ = truth.in_trunk_frame(gt0, "testball")
print(f"        cible d'entrainement : x=+0.090 y={'-' if cote == 'right' else '+'}0.042 "
      f"(erreur de placement : dx={x0-0.09:+.3f} dy={y0-(-0.042 if cote == 'right' else 0.042):+.3f})", flush=True)

r = c.request("robot.do", {"skill": f"kick_{cote}"})
print("robot.do ->", r.get("result", r.get("error")), flush=True)
t0 = time.monotonic()
vmax = 0.0
prev = gt0["bodies"]["testball"]
while time.monotonic() - t0 < 4.0:
    s = c.read_state_frame()
    c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
    g = truth.read()
    if g:
        p = g["bodies"]["testball"]
        vmax = max(vmax, math.dist(p, prev) / 0.1 if p != prev else vmax)
        prev = p
tenir(0.5)
gt1 = truth.read()
b0, b1 = gt0["bodies"]["testball"], gt1["bodies"]["testball"]
d0, d1 = gt0["ducks"][0], gt1["ducks"][0]
yaw0 = truth.trunk_yaw(d0["quat"])
dx, dy = b1[0] - b0[0], b1[1] - b0[1]
avant = dx * math.cos(yaw0) + dy * math.sin(yaw0)       # deplacement le long du cap initial du canard
lateral = -dx * math.sin(yaw0) + dy * math.cos(yaw0)
print("APRES :", truth.describe(gt1), flush=True)
print(f"balle deplacee de {math.hypot(dx, dy):.2f} m (avant {avant:+.2f} m, lateral {lateral:+.2f} m) ; "
      f"vitesse max ~{vmax:.2f} m/s ; canard deplace de {math.dist(d1['pos'][:2], d0['pos'][:2]):.2f} m ; "
      f"chute={c.read_state_frame()['safety']['fallen']}", flush=True)
print("RESULTAT :", "TIR REUSSI (balle partie vers l'avant)" if avant > 0.3 else "tir rate / balle peu deplacee", flush=True)
