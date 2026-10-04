#!/usr/bin/env python3
"""Banc d'essai de la promenade autonome (scene appartement, verite terrain) :
  1. etalonnage du ToF : canard a distance CONNUE d'un mur, face a lui -> distance libre mesuree vs vraie ;
  2. promenade : le cerveau tourne DUREE secondes (energie haute pour favoriser `wander`) avec le ToF ; on mesure la
     distance parcourue, les arrets devant obstacle, la plus petite distance aux obstacles (obstacles.py) et les chutes.
Un canard fait ~16 cm de large : centre a moins de 10 cm d'un obstacle = contact.

Usage : bash ~/run-brain.sh eval_promenade.py [duree_s=180]
"""
import contextlib
import io
import math
import statistics
import sys
import time

import brain
import obstacles
import tof as tofmod
import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

DUREE = float(sys.argv[1]) if len(sys.argv) > 1 else 180.0
OBST = obstacles.charger()
c = RobotdClient(SOCK_PATH)
capteur = tofmod.Tof(tofmod.beams_du_robot(c))
c.request("robot.subscribe", {})
capteur.start()


def tenir(secs):
    s, vals = None, []
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        s = c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
        lib = capteur.libre(s)
        if lib and lib["devant"] < 9:
            vals.append(lib["devant"])
    return vals


def dist_obstacle(p):
    """Distance du point p au rectangle d'obstacle le plus proche (0 si dedans)."""
    best = (math.inf, None)
    for nom, x0, x1, y0, y1 in OBST:
        dx = max(x0 - p[0], 0, p[0] - x1)
        dy = max(y0 - p[1], 0, p[1] - y1)
        best = min(best, (math.hypot(dx, dy), nom))
    return best


# 1. etalonnage : cuisine, face au mur ouest (face interieure a x = -3.94)
print("=== etalonnage du ToF face a un mur ===", flush=True)
for x in (-3.1, -3.4):
    truth.teleport_duck(x, 1.2, math.pi)
    v = tenir(2.5)
    vrai = x - (-3.94)
    mes = statistics.median(v) if v else float("nan")
    print(f"  mur a {vrai:.2f} m du tronc : ToF 'devant' = {mes:.2f} m (mediane de {len(v)} lectures)", flush=True)

# 2. promenade
print(f"\n=== promenade autonome {DUREE:.0f} s depuis la cuisine ===", flush=True)
import os
_dep = [float(v) for v in os.environ.get("DEPART", "-3.0,1.2,90").split(",")]
truth.teleport_duck(_dep[0], _dep[1], math.radians(_dep[2]))
tenir(1.0)
traj, etats = [], {}
t_prec = [0.0]


def tick(b, state):
    if b.t_global - t_prec[0] >= 0.25:
        t_prec[0] = b.t_global
        gt = truth.read()
        if gt:
            traj.append((b.t_global, gt["ducks"][0]["pos"][:2], state["safety"]["fallen"]))
    etats[b.courant.nom] = etats.get(b.courant.nom, 0) + 1


with contextlib.redirect_stdout(io.StringIO()):
    b = brain.run(c, DUREE, humeur=brain.Humeur(energie=1.0, eveil=0.6), a_chaque_tick=tick, seed=5,
                  extras={"tof": capteur})
parcours = sum(math.dist(traj[i][1], traj[i - 1][1]) for i in range(1, len(traj)))
dmin, nom = min(dist_obstacle(p) for _, p, _ in traj)
contacts = sum(1 for _, p, _ in traj if dist_obstacle(p)[0] < 0.10)
chutes = sum(1 for i in range(1, len(traj)) if traj[i][2] and not traj[i - 1][2])
total = sum(etats.values())
print(f"distance parcourue : {parcours:.2f} m ; arrets devant obstacle : {getattr(b, 'obstacle_vu', 0)} ; chutes : {chutes}")
print(f"plus petite distance du centre du canard a un obstacle : {dmin:.2f} m ({nom}) ; "
      f"echantillons en contact (< 10 cm) : {contacts}/{len(traj)}")
print("temps par etat : " + ", ".join(f"{k} {100 * v / total:.0f} %" for k, v in sorted(etats.items(), key=lambda kv: -kv[1])))
