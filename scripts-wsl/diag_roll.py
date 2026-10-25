import math, time
import animaux, truth, vision
from poc_robotd_client import RobotdClient, SOCK_PATH
c = RobotdClient(SOCK_PATH); c.request("robot.subscribe", {})
det = animaux.DetecteurCoco()
def att(yaw, roll, pitch=0.15):
    t0 = time.monotonic()
    while time.monotonic() - t0 < 1.6:
        c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": pitch, "head_yaw": yaw, "head_roll": roll})
for (x, y, yaw) in [(0.0, 0.9, -0.6), (0.0, -0.9, 0.6)]:
    truth.teleport_duck(x, y, 0.0)
    for k in (-0.5, -0.3, 0.0, 0.3, 0.5):
        att(yaw, k * yaw)
        o = sorted(det.detect(vision.grab_frame(), classes=None, seuil=0.1), key=lambda o: -o.score)[:2]
        print(f"tete {yaw:+.1f} roll {k*yaw:+.2f} : " + (", ".join(f"{q.classe} {q.score:.2f}" for q in o) or "rien"), flush=True)
