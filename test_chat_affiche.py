#!/usr/bin/env python3
"""L'affiche du chat (scene arena_chat) est-elle detectee par YOLO dans l'image du simulateur, et ou la place-t-on ?
Compare la position estimee au sol (bas de la boite) a la position reelle de l'affiche (verite : x = distance, y = 0)."""
import sys
import time

import cv2

import animaux
import geometry
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
det = animaux.DetecteurCoco()
etat = {}
import truth
truth.teleport_duck(0.0, 0.0, 0.0)          # face a l affiche (x = +1,2)
t0 = time.monotonic()
while time.monotonic() - t0 < 3.5:                       # tete legerement baissee, canard immobile
    etat["s"] = c.read_state_frame()
    c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.2, "head_yaw": 0.0, "head_roll": 0.0})
    c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
img = vision.grab_frame()
t1 = time.perf_counter()
objets = det.detect(img, classes=("cat",), seuil=0.25)
dt = time.perf_counter() - t1
print(f"{len(objets)} chat(s) en {dt * 1000:.0f} ms")
for o in objets:
    s = etat["s"]
    p = geometry.point_au_sol(o.pied[0], o.pied[1], s["frames"]["camera"], s["odom"]["position"][2])
    print(f"  score {o.score:.2f}  boite x={o.x:.0f} y={o.y:.0f} w={o.w:.0f} h={o.h:.0f}  pied estime au sol : "
          + ("-" if p is None else f"({p[0]:+.2f}, {p[1]:+.2f}) m  (vrai : ~ (1.2, 0))"))
    cv2.rectangle(img, (int(o.x), int(o.y)), (int(o.x + o.w), int(o.y + o.h)), (0, 255, 0), 2)
cv2.imwrite("/home/raphael/microduck-brain/photos_chat/sim_affiche.png", img)
