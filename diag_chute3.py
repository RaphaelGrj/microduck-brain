#!/usr/bin/env python3
"""Chute realiste : on relache le canard (robot.relax, moteurs mous), il s'effondre ; puis on le reactive
(robot.enable) et on regarde s'il se releve tout seul ou reste a terre. Usage : bash ~/run-brain.sh diag_chute3.py [--skill X]"""
import math
import sys
import time

import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

skill = sys.argv[sys.argv.index("--skill") + 1] if "--skill" in sys.argv else None
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def incl(q):
    w, x, y, z = q
    return math.degrees(math.acos(max(-1.0, min(1.0, 1 - 2 * (x * x + y * y)))))


def observer(secs, titre):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        s = c.read_state_frame()
        t = time.monotonic() - t0
        if int(t * 2) != int((t - 0.02) * 2):
            d = truth.read()["ducks"][0]
            print(f"  [{titre}] t={t:4.1f}s chute={s['safety']['fallen']!s:5} mou={s['safety']['limp']!s:5} politique={s['policy']:9s} "
                  f"incl={incl(d['quat']):5.1f} tronc={d['pos'][2]:.3f}", flush=True)


print("robot.relax ->", c.request("robot.relax", {}), flush=True)
observer(3.0, "mou")
if "cote" in sys.argv:
    truth.coucher_duck(pitch=0.0, roll=math.pi / 2, z=0.06)   # sur le cote
else:
    truth.coucher_duck(pitch=(-1 if "dos" in sys.argv else 1) * math.pi / 2, z=0.05)   # ventre (defaut) ou dos
observer(2.0, "couche")
print("robot.enable ->", c.request("robot.enable", {"on": True}), flush=True)
observer(6.0, "reactive")
if skill:
    print(f"robot.do {skill} ->", c.request("robot.do", {"skill": skill}), flush=True)
    observer(6.0, skill)
