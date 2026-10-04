#!/usr/bin/env python3
"""Detection de vide du ToF (tof.py) : 1) test synthetique (un rayon qui plonge sous le sol = marche) ; 2) dans duck-sim,
en LECTURE SEULE (aucune commande envoyee), compte les faux vides sur un sol plat pendant `duree` secondes.

Usage : bash ~/run-brain.sh diag_vide.py [duree_s=20]
"""
import math
import sys
import time

import tof


def test_synthetique():
    a = math.radians(30)
    beams = [(math.cos(a), 0.0, -math.sin(a))] * 64                    # 64 rayons plongeant de 30 deg, droit devant
    t = tof.Tof(beams)
    etat = {"t_ns": 1000, "frames": {"tof": {"pos": [0.05, 0.0, 0.10], "quat": [1.0, 0.0, 0.0, 0.0]}},
            "odom": {"position": [0.0, 0.0, 0.115]}}
    sol = 0.215 / math.sin(a)                                            # le rayon touche le sol a 0,43 m
    t.derniere = (time.monotonic(), {"distance_mm": [int(sol * 1000)] * 64, "status": [5] * 64, "t_ns": 1000})
    l1 = t.libre(etat)
    assert l1["vide"] == math.inf and l1["devant"] == math.inf, l1      # sol plat : ni obstacle ni vide
    t.derniere = (time.monotonic(), {"distance_mm": [800] * 64, "status": [5] * 64, "t_ns": 1000})
    l2 = t.libre(etat)
    bord = 0.05 + sol * math.cos(a)
    assert abs(l2["vide"] - bord) < 0.01 and abs(l2["devant"] - bord) < 0.01, (l2, bord)
    t.derniere = (time.monotonic(), {"distance_mm": [int((sol + 0.03) * 1000)] * 64, "status": [5] * 64, "t_ns": 1000})
    assert t.libre(etat)["vide"] == math.inf, "un tapis ou un seuil de 1-2 cm n'est pas un vide"
    print(f"synthetique : OK (sol plat ignore, marche vue a {l2['vide']:.2f} m = traversee du sol, petit creux ignore)")


def sim(duree):
    from poc_robotd_client import RobotdClient, SOCK_PATH
    c = RobotdClient(SOCK_PATH)
    t = tof.Tof(tof.beams_du_robot(c))
    c.request("robot.subscribe", {})
    t.start()
    t0, n, n_vide, pire = time.monotonic(), 0, 0, math.inf
    while time.monotonic() - t0 < duree:
        s = c.read_state_frame()
        lib = t.libre(s)
        if lib is None:
            continue
        n += 1
        if lib["vide"] < math.inf:
            n_vide += 1
            pire = min(pire, lib["vide"])
    print(f"duck-sim (sol plat, lecture seule) : {n_vide} trames avec un vide sur {n}"
          + (f" (le plus proche a {pire:.2f} m)" if n_vide else ""))


if __name__ == "__main__":
    test_synthetique()
    sim(float(sys.argv[1]) if len(sys.argv) > 1 else 20.0)
