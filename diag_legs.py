#!/usr/bin/env python3
"""Echantillonne finement les articulations des jambes pendant une marche (3 s)."""
import time

from poc_robotd_client import RobotdClient, SOCK_PATH

NOMS = ["gHipYaw?", "gHipRoll?", "gHipPitch", "gKnee", "gAnkle"]
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
t0 = time.monotonic()
log = []
while time.monotonic() - t0 < 4.0:
    s = c.read_state_frame()
    c.notify("robot.move", {"vx": 0.25, "vy": 0.0, "vyaw": 0.0})
    log.append((time.monotonic() - t0, list(s["joints"]), list(s["odom"]["position"]), s.get("t")))
for _ in range(25):
    c.read_state_frame()
    c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})

print(f"{len(log)} trames en 4 s ({len(log)/4:.0f}/s) ; valeurs distinctes de t_state: "
      f"{len({round(x[3], 3) for x in log if x[3] is not None})}")
print("joints (indices 0-4 jambe gauche, 10-14 jambe droite), min / max / ecart-type sur 4 s :")
import statistics
for idx in list(range(0, 5)) + list(range(10, 15)):
    v = [row[1][idx] for row in log]
    print(f"  joint {idx:2d}: min={min(v):+.3f} max={max(v):+.3f} sigma={statistics.pstdev(v):.3f}")
print("echantillons joint 2 (toutes les 0.25 s) :",
      [round(log[i][1][2], 3) for i in range(0, len(log), 12)])
print("odom x au debut/fin :", round(log[0][2][0], 3), round(log[-1][2][0], 3))
