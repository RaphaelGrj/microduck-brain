#!/usr/bin/env python3
"""A partir de quelle commande le canard marche-t-il / tourne-t-il vraiment ?

Arguments : x<vx> (avance/recul, m/s) ou r<vyaw> (rotation, rad/s), ex. : x0.3 x-0.3 r1.0 r1.5
Pour chaque essai : amplitude crete-a-crete des jambes par seconde, deplacement et rotation odometriques.
"""
import math
import sys
import time

from poc_robotd_client import RobotdClient, SOCK_PATH

LEGS = list(range(0, 5)) + list(range(10, 15))
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def pause(secs):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        c.read_state_frame()
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})


def essai(vx, vyaw, secs=5.0):
    s = c.read_state_frame()
    p0, y0 = s["odom"]["position"], s["odom"]["yaw"]
    t0 = time.monotonic()
    fenetre, amp = [], []
    while time.monotonic() - t0 < secs:
        s = c.read_state_frame()
        c.notify("robot.move", {"vx": vx, "vy": 0.0, "vyaw": vyaw})
        fenetre.append([s["joints"][i] for i in LEGS])
        if len(fenetre) >= 50:
            amp.append(max(max(col) - min(col) for col in zip(*fenetre)))
            fenetre = []
    p1, y1 = s["odom"]["position"], s["odom"]["yaw"]
    dx = (p1[0] - p0[0]) * math.cos(-y0) - (p1[1] - p0[1]) * math.sin(-y0)  # le long du cap initial
    print(f"vx={vx:+.2f} vyaw={vyaw:+.2f}: jambes/s={[round(a, 2) for a in amp]} "
          f"avance={dx:+.3f} m (attendu {vx*secs:+.2f}) rotation={math.degrees(y1-y0):+6.1f} deg "
          f"(attendu {math.degrees(vyaw*secs):+.0f})", flush=True)


for tok in sys.argv[1:]:
    v = float(tok[1:])
    essai(v if tok[0] == "x" else 0.0, v if tok[0] == "r" else 0.0)
    pause(3.0)
