#!/usr/bin/env python3
"""Mode calme sur le canard simule : calme_on a 5 s, calme_off a 50 s. On releve chaque seconde la politique active
(sit = assis) et la hauteur du tronc. Usage : bash ~/run-brain.sh demo_calme.py"""
import contextlib
import io

import brain
from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
releve, t_prec = [], [-1.0]


def tick(b, s):
    if b.t_global - t_prec[0] >= 1.0:
        t_prec[0] = b.t_global
        releve.append((round(b.t_global), b.courant.nom, s["policy"], round(s["odom"]["position"][2], 3)))


with contextlib.redirect_stdout(io.StringIO()):
    brain.run(c, 70.0, evenements=[(5.0, "calme_on"), (50.0, "calme_off")], a_chaque_tick=tick, seed=4)
for t, etat, pol, z in releve:
    if t % 5 == 0:
        print(f"t={t:3d}s  etat cerveau={etat:10s} politique={pol:6s} tronc={z:.3f} m")
assis = [pol for t, _, pol, _ in releve if 20 <= t <= 48]
print("RESULTAT :", "assis et immobile pendant tout le mode calme" if assis and all(p == "sit" for p in assis)
      else f"politiques pendant le calme : {set(assis)}")
