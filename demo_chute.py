#!/usr/bin/env python3
"""Le cerveau face a une vraie chute (simulation) : il tourne ; a 5 s on relache le canard (robot.relax) et on le couche ;
a 9 s on le reactive (robot.enable) ; robotd le releve ; le cerveau doit attendre sans rien commander, puis s'ebrouer.
Usage : bash ~/run-brain.sh demo_chute.py"""
import contextlib
import io
import math
import threading
import time

import brain
import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
etats, sortie = [], io.StringIO()


def scenario():
    # requetes via une 2e connexion (le cerveau lit la 1re) ; robot.relax / enable = la "main" de l'experimentateur
    c2 = RobotdClient(SOCK_PATH)
    time.sleep(5)
    c2.request("robot.relax", {})
    time.sleep(2)
    truth.coucher_duck(pitch=math.pi / 2, z=0.05)
    time.sleep(2)
    c2.request("robot.enable", {"on": True})


def tick(b, s):
    nom = ("TOMBE/" if b.tombe else "") + b.courant.nom
    if not etats or etats[-1][1] != nom:
        etats.append((round(b.t_global, 1), nom, s["policy"]))


threading.Thread(target=scenario, daemon=True).start()
with contextlib.redirect_stdout(sortie):
    brain.run(c, 20.0, a_chaque_tick=tick, seed=3, humeur=brain.Humeur(energie=0.9, eveil=0.2))
print("journal du cerveau :")
print("\n".join("  " + l for l in sortie.getvalue().splitlines() if "CHUTE" in l or "releve" in l or "->" in l))
print("etats (t, etat, politique robotd) :", etats)
ok = any("ebouriffe" == n for _, n, _ in etats) and any(n.startswith("TOMBE") for _, n, _ in etats)
print("RESULTAT :", "pause pendant la chute, puis s'ebroue une fois releve" if ok else "ECHEC")
