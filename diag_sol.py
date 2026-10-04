#!/usr/bin/env python3
"""La balle est-elle detectee de PRES sur les sols de l'appartement (cuisine, salon) comme en arene ?
Canard replace au point de depart de l'evaluation, balle a 10-30 cm devant, tete baissee : detection + image.
Images : ~/microduck-brain/photos_chat/../diag_sol_<piece>_<x>_<pitch>.png (dossier ignore par git)."""
import math
import time

import cv2

import geometry
import truth
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

PIECES = {"cuisine": (-3.0, 1.2, 90), "salon": (-2.0, -2.3, 90), "arene_ou_couloir": (-0.2, 1.5, 90)}
POSITIONS = [(0.10, 0.0), (0.15, 0.0), (0.20, 0.0), (0.30, 0.0), (0.12, 0.05)]
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
etat = {}


def tenir(secs, pitch):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        etat["s"] = c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": pitch, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})


for piece, (sx, sy, cap) in PIECES.items():
    truth.teleport_duck(sx, sy, math.radians(cap))
    tenir(1.0, 0.0)
    print(f"=== {piece} ===", flush=True)
    for pitch in (1.0, 1.5):
        for (x, y) in POSITIONS:
            tenir(0.4, pitch)
            gt = truth.read()
            d = gt["ducks"][0]
            th = truth.trunk_yaw(d["quat"])
            try:
                truth.teleport("testball", d["pos"][0] + math.cos(th) * x - math.sin(th) * y,
                               d["pos"][1] + math.sin(th) * x + math.cos(th) * y)
            except TimeoutError:
                print(f"  ({x:.2f},{y:+.2f}) pitch {pitch}: placement impossible")
                continue
            tenir(1.2, pitch)
            img = vision.grab_frame()
            dets = vision.detect(img, couleurs=["orange"], aire_min=20)
            s = etat["s"]
            if dets:
                q = dets[0]
                e = geometry.balle_dans_tronc(q, s["frames"]["camera"], s["odom"]["position"][2])["sol"]
                err = "-" if e is None else f"{math.hypot(e[0] - x, e[1] - y) * 100:.1f} cm"
                txt = f"vue r={q.rayon:.0f} rond={q.rondeur:.2f}{' BORD' if q.touche_bord else ''} err={err}"
            else:
                txt = "NON VUE"
            print(f"  ({x:.2f},{y:+.2f}) pitch {pitch}: {txt}", flush=True)
            cv2.imwrite(f"/home/raphael/microduck-brain/photos_chat/diag_sol_{piece}_{x:.2f}_{y:+.2f}_{pitch}.png",
                        vision.annotate(img, dets))
tenir(0.5, 0.0)
