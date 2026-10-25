"""Que voit YOLO de l'affiche du chat (scene arena_chat) selon le cote d'ou on la regarde ? Toutes classes, seuil 0,1."""
import math, time
import animaux, truth, vision
from poc_robotd_client import RobotdClient, SOCK_PATH

CHAT = (1.2, 0.0)
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
det = animaux.DetecteurCoco()
for (x, y) in [(0.0, -0.9), (0.0, 0.9), (-0.3, -0.6), (-0.3, 0.6)]:
    vers = math.atan2(CHAT[1] - y, CHAT[0] - x)
    for off in (-0.3, 0.0, 0.3):
        truth.teleport_duck(x, y, vers + off)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 1.5:
            c.read_state_frame()
            c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.15, "head_yaw": 0.0, "head_roll": 0.0})
        obj = det.detect(vision.grab_frame(), classes=None, seuil=0.1)
        top = sorted(obj, key=lambda o: -o.score)[:3]
        print(f"({x:+.1f},{y:+.1f}) chat a {math.degrees(-off):+4.0f} deg dans l'image : " +
              (", ".join(f"{o.classe} {o.score:.2f}" for o in top) or "rien"), flush=True)
