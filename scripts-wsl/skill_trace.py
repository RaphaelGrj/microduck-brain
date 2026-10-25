"""Joue chaque skill RL via robot.do et trace les politiques vues + hauteur du tronc (verite terrain)."""
import json, os, sys, time
from poc_robotd_client import RobotdClient, SOCK_PATH

POL = os.path.expanduser("~/.cache/duck-sim/policies")
SK = {"startle": (f"{POL}/startle/startle.onnx", 1.2), "frisson": (f"{POL}/shiver/shiver.onnx", 1.3),
      "curieux": (f"{POL}/gestes2/crouch.onnx", 1.3)}
SK = {k: v for k, v in SK.items() if k == sys.argv[1]}
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
for n, (p, d) in SK.items():
    c.request("robot.setSkill", {"name": n, "path": p, "duration": d})
time.sleep(5)
try:
    for n, (p, d) in SK.items():
        t0 = time.monotonic()
        while time.monotonic() - t0 < 3:
            c.read_state_frame()
        r = c.request("robot.do", {"skill": n})
        pols, tomb, zmin = [], False, 9
        t1 = time.monotonic()
        while time.monotonic() - t1 < d + 1.5:
            s = c.read_state_frame()
            if not pols or pols[-1] != s["policy"]:
                pols.append(s["policy"])
            tomb = tomb or s["safety"]["fallen"]
            zmin = min(zmin, s["odom"]["position"][2])
        print(n, r.get("result", r.get("error")), "politiques:", pols, "z min", round(zmin * 100, 1), "cm chute", tomb)
finally:
    for n in SK:
        c.request("robot.removeSkill", {"name": n})
