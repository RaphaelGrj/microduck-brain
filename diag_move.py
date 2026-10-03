#!/usr/bin/env python3
"""Diagnostic : le canard avance-t-il vraiment quand on le lui demande ?
Mesure odometrie, vitesse des jambes (activite de marche) et comparaison d'images."""
import math
import time

import cv2
import numpy as np

import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def essai(vx, vyaw, secs, tag):
    s = c.read_state_frame()
    p0, y0 = s["odom"]["position"], s["odom"]["yaw"]
    img0 = vision.grab_frame()
    t0 = time.monotonic()
    vmax = 0.0
    while time.monotonic() - t0 < secs:
        s = c.read_state_frame()
        c.notify("robot.move", {"vx": vx, "vy": 0.0, "vyaw": vyaw})
        j = s["joints"]
        vmax = max(vmax, max(abs(x) for x in j[0:5] + j[10:15]))  # amplitude des jambes
    p1, y1 = s["odom"]["position"], s["odom"]["yaw"]
    for _ in range(25):
        s = c.read_state_frame()
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
    img1 = vision.grab_frame()
    diff = float(np.mean(cv2.absdiff(img0, img1)))
    print(f"{tag:14s} cmd(vx={vx:+.2f}, vyaw={vyaw:+.2f}) -> odom dx={p1[0]-p0[0]:+.3f} dy={p1[1]-p0[1]:+.3f} "
          f"dyaw={math.degrees(y1-y0):+5.1f} deg | policy={s['policy']} fallen={s['safety']['fallen']} "
          f"| image changee={diff:.1f}", flush=True)


essai(+0.15, 0.0, 4, "avant")
essai(-0.15, 0.0, 4, "arriere")
essai(0.0, +0.8, 4, "rotation +")
essai(0.0, -0.8, 4, "rotation -")
