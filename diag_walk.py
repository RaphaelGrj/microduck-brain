#!/usr/bin/env python3
"""Le canard marche-t-il vraiment ? Amplitude des jambes + images avant/apres."""
import math
import time

import cv2

import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
s = c.read_state_frame()
cv2.imwrite("/home/raphael/walk_avant.png", vision.grab_frame())
p0 = s["odom"]["position"]
print(f"depart: policy={s['policy']} odom=({p0[0]:.3f},{p0[1]:.3f}) trunk_z={p0[2]:.3f}", flush=True)

mins = [9.0] * 15
maxs = [-9.0] * 15
t0 = time.monotonic()
politiques = set()
while time.monotonic() - t0 < 6.0:
    s = c.read_state_frame()
    c.notify("robot.move", {"vx": 0.2, "vy": 0.0, "vyaw": 0.0})
    politiques.add(s["policy"])
    for i, q in enumerate(s["joints"]):
        mins[i] = min(mins[i], q)
        maxs[i] = max(maxs[i], q)
    if int((time.monotonic() - t0) * 2) != int((time.monotonic() - t0 - 0.02) * 2):
        pass
p1 = s["odom"]["position"]
print(f"fin   : politiques vues={sorted(politiques)} odom=({p1[0]:.3f},{p1[1]:.3f}) "
      f"deplacement={math.hypot(p1[0]-p0[0], p1[1]-p0[1]):.3f} m", flush=True)
print("amplitude des articulations (max-min, rad) : "
      + " ".join(f"{i}:{(maxs[i]-mins[i]):.2f}" for i in range(15)), flush=True)
print("deplacement demande ~ 0.2 m/s * 6 s = 1.2 m", flush=True)
for _ in range(50):
    s = c.read_state_frame()
    c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
cv2.imwrite("/home/raphael/walk_apres.png", vision.grab_frame())
print("images: ~/walk_avant.png  ~/walk_apres.png", flush=True)
