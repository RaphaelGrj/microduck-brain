#!/usr/bin/env python3
"""Portee de la vision : jusqu'a quelle distance (et avec quelle precision) la camera localise-t-elle
la balle, selon l'inclinaison de la tete ? Compare l'estimation (geometry.py) a la VERITE TERRAIN.

Pour chaque inclinaison de tete et chaque position de balle (repere du tronc), on teleporte la
balle, on tient la tete immobile, on prend une image et on la detecte.

Usage : bash ~/run-brain.sh vis_range.py
"""
import math
import time

import geometry
import truth
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

PITCHS = (0.0, 0.5, 1.0)
XS = (0.12, 0.18, 0.25, 0.35, 0.5, 0.7, 1.0)
YS = (-0.15, 0.0, 0.15)

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
etat = {"s": None}


def tenir(secs, pitch):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        etat["s"] = c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": pitch, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})


def placer(x, y):
    gt = truth.read()
    d = gt["ducks"][0]
    yaw = truth.trunk_yaw(d["quat"])
    wx = d["pos"][0] + math.cos(yaw) * x - math.sin(yaw) * y
    wy = d["pos"][1] + math.sin(yaw) * x + math.cos(yaw) * y
    return truth.teleport("testball", wx, wy)


lignes = []
for pitch in PITCHS:
    print(f"\n=== tete baissee de {pitch:.1f} rad ===", flush=True)
    for x in XS:
        for y in YS:
            tenir(0.6, pitch)
            try:
                placer(x, y)
            except TimeoutError:
                print(f"  vrai=({x:+.2f},{y:+.2f}) : placement impossible", flush=True)
                continue
            tenir(1.6, pitch)
            gt = truth.read()
            vx, vy, vz = truth.in_trunk_frame(gt, "testball")
            s = etat["s"]
            img = vision.grab_frame()
            dets = vision.detect(img, couleurs=["orange"], aire_min=20)
            if not dets:
                print(f"  vrai=({vx:+.2f},{vy:+.2f})  -> NON VUE", flush=True)
                lignes.append((pitch, vx, vy, None))
                continue
            det = dets[0]
            est = geometry.balle_dans_tronc(det, s["frames"]["camera"], s["odom"]["position"][2])
            def fmt(p):
                return "      -       " if p is None else f"({p[0]:+.2f},{p[1]:+.2f}) e={math.hypot(p[0]-vx, p[1]-vy)*100:4.1f}cm"
            print(f"  vrai=({vx:+.2f},{vy:+.2f}) px=({det.cx:3.0f},{det.cy:3.0f}) r={det.rayon:4.1f}"
                  f"{' BORD' if det.touche_bord else ''}  rayon:{fmt(est['rayon'])}  sol:{fmt(est['sol'])}", flush=True)
            lignes.append((pitch, vx, vy, (det, est)))

print("\n=== resume : erreur moyenne (cm) par inclinaison et distance, parmi les vues ===", flush=True)
for pitch in PITCHS:
    for x in XS:
        sel = [(vx, vy, r) for (p, vx, vy, r) in lignes if p == pitch and abs(vx - x) < 0.06 and r is not None]
        tot = [1 for (p, vx, vy, r) in lignes if p == pitch and abs(vx - x) < 0.06]
        if not tot:
            continue
        def moy(cle):
            v = [math.hypot(r[1][cle][0] - vx, r[1][cle][1] - vy) * 100 for (vx, vy, r) in sel if r[1][cle] is not None]
            return f"{sum(v) / len(v):5.1f}" if v else "  -  "
        print(f"  pitch={pitch:.1f} x~{x:.2f} : vue {len(sel)}/{len(tot)}  err rayon={moy('rayon')} cm  err sol={moy('sol')} cm", flush=True)
