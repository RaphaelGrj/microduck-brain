#!/usr/bin/env python3
"""Latence image : apres un saut de commande de tete, au bout de combien de temps l'image /frame change-t-elle,
et quand se stabilise-t-elle ? Compare l'arene et l'appartement (rendu plus lourd)."""
import time

import numpy as np

import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def tenir(secs, yaw):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.2, "head_yaw": yaw, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})


tenir(2.0, 0.0)
ref = vision.grab_frame().astype(np.int16)
t_cmd = time.monotonic()
mesures = []
t_fin = t_cmd + 3.0
while time.monotonic() < t_fin:
    c.read_state_frame()
    c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.2, "head_yaw": 0.6, "head_roll": 0.0})
    t0 = time.monotonic()
    img = vision.grab_frame().astype(np.int16)
    t1 = time.monotonic()
    mesures.append((t0 - t_cmd, t1 - t_cmd, float(np.abs(img - ref).mean())))
fin = mesures[-1][2]
premier = next((m[0] for m in mesures if m[2] > 0.1 * fin), None)
stable = next((m[0] for m in mesures if m[2] > 0.9 * fin), None)
print(f"{len(mesures)} images en 3 s ({len(mesures) / 3:.1f} /s), duree d'un grab_frame ~{np.mean([m[1] - m[0] for m in mesures]) * 1000:.0f} ms")
print(f"1er changement visible : {premier}  ;  90 % du changement final : {stable}  (secondes apres la commande)")
for m in mesures[:: max(1, len(mesures) // 12)]:
    print(f"   t={m[0]:.2f}s  difference moyenne avec l'image de depart : {m[2]:.1f}")
tenir(1.0, 0.0)
