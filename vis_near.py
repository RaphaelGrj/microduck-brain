#!/usr/bin/env python3
"""Vision de pres : la balle est-elle visible dans la fenetre de tir (0,09 ; +-0,042) selon la tete ?

Teste plusieurs combinaisons (neck_pitch, head_pitch, head_yaw) et dit pour chacune si la balle
est detectee, tronquee par le bord, et l'erreur d'estimation (geometry.py) par rapport a la verite.

Usage : bash ~/run-brain.sh vis_near.py
"""
import math
import time

import geometry
import truth
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

POSITIONS = [(0.09, 0.042), (0.09, -0.042), (0.12, 0.0), (0.15, 0.0)]
TETES = [(0.0, 1.0), (0.5, 1.0), (1.0, 1.0), (0.5, 0.5), (1.0, 0.5), (1.5, 0.5), (1.0, 1.5)]   # (neck_pitch, head_pitch)

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
etat = {"s": None}


def tenir(secs, neck, pitch, yaw):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        etat["s"] = c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": neck, "head_pitch": pitch, "head_yaw": yaw, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})


for (x, y) in POSITIONS:
    print(f"\n=== balle a ({x:+.3f},{y:+.3f}) dans le repere du tronc ===", flush=True)
    for (neck, pitch) in TETES:
        yaw = math.atan2(y, x) * 0.8
        tenir(0.5, neck, pitch, yaw)
        gt = truth.read()
        d = gt["ducks"][0]
        th = truth.trunk_yaw(d["quat"])
        truth.teleport("testball", d["pos"][0] + math.cos(th) * x - math.sin(th) * y,
                       d["pos"][1] + math.sin(th) * x + math.cos(th) * y)
        tenir(1.5, neck, pitch, yaw)
        s = etat["s"]
        dets = vision.detect(vision.grab_frame(), couleurs=["orange"], aire_min=20, rondeur_min_bord=0.0)
        tete = [round(j, 2) for j in s["joints"][5:9]]
        if not dets:
            print(f"  cou={neck:.1f} tete={pitch:.1f} yaw={yaw:+.2f} (joints {tete}) -> NON VUE", flush=True)
            continue
        det = dets[0]
        est = geometry.balle_dans_tronc(det, s["frames"]["camera"], s["odom"]["position"][2])["sol"]
        err = "-" if est is None else f"{math.hypot(est[0] - x, est[1] - y) * 100:.1f} cm"
        print(f"  cou={neck:.1f} tete={pitch:.1f} yaw={yaw:+.2f} (joints {tete}) -> vue px=({det.cx:.0f},{det.cy:.0f}) r={det.rayon:.0f} aire={det.aire:.0f} rond={det.rondeur:.2f}"
              f"{' BORD' if det.touche_bord else ''}  erreur sol {err}", flush=True)
tenir(0.5, 0.0, 0.0, 0.0)
