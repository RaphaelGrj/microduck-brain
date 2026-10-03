#!/usr/bin/env python3
"""Que fait robotd d'un ordre de marche ? demande / applique / limite + activite des jambes."""
import math
import time

from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
t0 = time.monotonic()
prev = None
dernier = -1
while time.monotonic() - t0 < 6.0:
    s = c.read_state_frame()
    c.notify("robot.move", {"vx": 0.25, "vy": 0.0, "vyaw": 0.0})
    t = time.monotonic() - t0
    legs = s["joints"][0:5] + s["joints"][10:15]
    vit = 0.0 if prev is None else max(abs(a - b) for a, b in zip(legs, prev)) / 0.02
    prev = legs
    if int(t * 2) != dernier:
        dernier = int(t * 2)
        m = s["move"]
        print(f"t={t:3.1f}s policy={s['policy']:5s} demande={[round(x, 2) for x in m['requested']]} "
              f"applique={[round(x, 2) for x in m['applied']]} limite_par={m.get('limited_by', [])} "
              f"vit_jambes_max={vit:4.2f} rad/s gyro={[round(x, 2) for x in s['imu']['gyro']]} "
              f"gain={s['safety'].get('gain')} limp={s['safety'].get('limp')}", flush=True)
for _ in range(25):
    s = c.read_state_frame()
    c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
