#!/usr/bin/env python3
"""Que fait robotd quand le canard tombe ? (et, plus tard, la competence de relevement via robot.do)
Couche le canard (ventre / dos), puis releve chaque 0,5 s : chute signalee, politique active, inclinaison et hauteur
reelles. Option : `--skill <nom>` declenche robot.do une fois couche. Usage : bash ~/run-brain.sh diag_chute.py [ventre|dos] [--skill roulade]"""
import math
import sys
import time

import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

pose = "dos" if "dos" in sys.argv else "ventre"
skill = sys.argv[sys.argv.index("--skill") + 1] if "--skill" in sys.argv else None
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def inclinaison(q):
    w, x, y, z = q
    return math.degrees(math.acos(max(-1.0, min(1.0, 1 - 2 * (x * x + y * y)))))   # angle entre l'axe z du tronc et la verticale


truth.coucher_duck(pitch=math.pi / 2 if pose == "ventre" else -math.pi / 2)
time.sleep(0.5)
t0 = time.monotonic()
lance = False
while time.monotonic() - t0 < 8.0:
    s = c.read_state_frame()
    c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
    t = time.monotonic() - t0
    if skill and not lance and t > 1.0:
        print("robot.do", skill, "->", c.request("robot.do", {"skill": skill}).get("result"), flush=True)
        lance = True
    if int(t * 2) != int((t - 0.02) * 2):
        d = truth.read()["ducks"][0]
        print(f"t={t:4.1f}s  chute={s['safety']['fallen']!s:5} politique={s['policy']:8s} inclinaison={inclinaison(d['quat']):5.1f} deg "
              f"tronc={d['pos'][2]:.3f} m", flush=True)
