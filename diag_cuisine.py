#!/usr/bin/env python3
"""Pourquoi la balle est-elle 'non vue' dans l'appartement ? Canard replace au point DEPART, balle a plusieurs
distances droit devant, tete a 0,2 : detections + image sauvee (~/cuisine_<d>.png)."""
import math
import os
import time

import cv2

import truth
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
sx, sy, syaw = [float(v) for v in os.environ.get("DEPART", "-2.5,1.8,0").split(",")]


def tenir(secs, pitch=0.2):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": pitch, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})


for nom in ("ball_0", "ball_1", "ball_2"):
    try:
        truth.teleport(nom, 3.0 + 0.3 * int(nom[-1]), -2.2)
    except (KeyError, TimeoutError):
        pass
truth.teleport_duck(sx, sy, math.radians(syaw))
tenir(1.5)
for d in (0.5, 0.8, 1.1):
    try:
        truth.teleport("testball", sx + d * math.cos(math.radians(syaw)), sy + d * math.sin(math.radians(syaw)))
    except TimeoutError:
        print(f"d={d}: placement impossible (obstacle)")
        continue
    tenir(1.5)
    img = vision.grab_frame()
    dets = vision.detect(img, couleurs=["orange"], aire_min=10)
    gt = truth.read()
    x, y, z = truth.in_trunk_frame(gt, "testball")
    print(f"d={d}: balle reelle dans le tronc ({x:+.2f},{y:+.2f},z={z:.3f}) ; {len(dets)} detection(s) : "
          + "; ".join(f"({q.cx:.0f},{q.cy:.0f}) r={q.rayon:.0f} rond={q.rondeur:.2f}" for q in dets), flush=True)
    cv2.imwrite(f"/home/raphael/cuisine_{d}.png", vision.annotate(img, dets))
tenir(0.5, 0.0)
