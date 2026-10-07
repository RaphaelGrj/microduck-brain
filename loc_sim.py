#!/usr/bin/env python3
"""Banc de la localisation dans duck-sim (PC, WSL) : le cerveau promene le canard dans l'appartement pendant que la
localisation (localisation.py) le situe sur le plan de la scene (plan.depuis_mjcf) ; la verite terrain du simulateur
(DUCK_SIM_GROUNDTRUTH, truth.py) sert de regle - jamais pour decider.

    bash ~/run-scene.sh apartment            # (autre terminal) duck-sim, scene appartement, verite terrain active
    bash ~/run-brain.sh loc_sim.py 300       # 5 min de promenade ; resume a la fin

Affiche toutes les 10 s l'erreur du filtre et celle de l'odometrie seule ; a la fin : moyenne, 95e centile, pire.
Option : --scene <chemin de apartment.xml> (defaut : ~/microduck_rl/.../apartment.xml).
"""
import math
import sys
import time
from pathlib import Path

import numpy as np

import brain as brain_mod
import localisation
import plan as plan_mod
import tof as tof_mod
import truth
from brain import Humeur

SCENE = Path.home() / "microduck_rl/src/mjlab_microduck/robot/microduck/apartment.xml"


def pose_vraie():
    gt = truth.read()
    if not gt or not gt.get("ducks"):
        return None
    d = gt["ducks"][0]
    return d["pos"][0], d["pos"][1], truth.trunk_yaw(d["quat"])


def main(argv):
    duree = float(next((a for a in argv if a.replace(".", "").isdigit()), 300))
    scene = Path(argv[argv.index("--scene") + 1]) if "--scene" in argv else SCENE
    pl = plan_mod.depuis_mjcf(scene)
    print(f"plan : {pl.largeur * pl.resolution:.1f} x {pl.hauteur * pl.resolution:.1f} m", flush=True)
    depart = pose_vraie()
    if depart is None:
        sys.exit("pas de verite terrain : lancer duck-sim avec DUCK_SIM_GROUNDTRUTH (run-scene.sh)")
    from poc_robotd_client import RobotdClient, SOCK_PATH
    c = RobotdClient(SOCK_PATH)
    capteur = tof_mod.Tof(tof_mod.beams_du_robot(c))
    c.request("robot.subscribe", {})
    capteur.start()
    loc = localisation.Localisation(pl, graine=0)
    loc.depuis(*depart)                     # comme au depart du chargeur : position connue
    odo0 = {}
    erreurs, erreurs_odo, couts = [], [], []
    dernier = [time.monotonic()]

    def a_chaque_tick(b, state):
        o = state.get("odom")
        if not o:
            return
        ox, oy, ocap = o["position"][0], o["position"][1], o.get("yaw") or 0.0
        if not odo0:
            odo0.update(o=(ox, oy, ocap))
        t = time.perf_counter()
        if loc.mouvement(ox, oy, ocap):
            loc.mesure(capteur.points(state) or [])
            couts.append(time.perf_counter() - t)
        if time.monotonic() - dernier[0] < 1.0:
            return
        dernier[0] = time.monotonic()
        vrai = pose_vraie()
        if vrai is None:
            return
        x, y, cap, ecart = loc.estimation()
        e = math.hypot(x - vrai[0], y - vrai[1])
        # odometrie seule, recalee sur le depart : ou elle croit qu'il est
        x0, y0, c0 = odo0["o"]
        dc = depart[2] - c0
        dx, dy = ox - x0, oy - y0
        ex = depart[0] + math.cos(dc) * dx - math.sin(dc) * dy
        ey = depart[1] + math.sin(dc) * dx + math.cos(dc) * dy
        eo = math.hypot(ex - vrai[0], ey - vrai[1])
        erreurs.append(e)
        erreurs_odo.append(eo)
        if len(erreurs) % 10 == 0:
            print(f"[{len(erreurs):4d}s] filtre {e:.2f} m (dispersion {ecart:.2f}) | odometrie seule {eo:.2f} m "
                  f"| etat {b.courant.nom}", flush=True)

    try:
        brain_mod.run(c, duree, Humeur(energie=0.9), extras={"tof": capteur}, a_chaque_tick=a_chaque_tick)
    finally:
        capteur.actif = False
    if erreurs:
        e, eo = np.array(erreurs), np.array(erreurs_odo)
        print(f"\nfiltre    : moyenne {e.mean():.2f} m, 95 % sous {np.percentile(e, 95):.2f} m, pire {e.max():.2f} m")
        print(f"odometrie : moyenne {eo.mean():.2f} m, fin {eo[-1]:.2f} m")
        if couts:
            print(f"cout : {1000 * np.mean(couts):.1f} ms par mise a jour ({len(couts)} mises a jour)")


if __name__ == "__main__":
    main(sys.argv[1:])
