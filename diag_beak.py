#!/usr/bin/env python3
"""La camera voit-elle le canard lui-meme (bec orange ?) quand la tete est baissee ? Balle eloignee,
tete a differentes inclinaisons : que detecte-t-on ?  Sauve ~/beak_<pitch>.png (annote)."""
import time

import cv2

import truth
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def tenir(secs, pitch, yaw=0.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": pitch, "head_yaw": yaw, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})


gt = truth.read()
d = gt["ducks"][0]
truth.teleport("testball", d["pos"][0] - 3.0, d["pos"][1] + 3.0)     # balle loin et derriere : hors champ
for pitch in (0.0, 0.5, 1.0, 1.5):
    for yaw in (0.0, 0.5):
        tenir(1.6, pitch, yaw)
        img = vision.grab_frame()
        dets = vision.detect(img, couleurs=["orange"], aire_min=20)
        print(f"pitch={pitch} yaw={yaw}: {len(dets)} detection(s) orange sans balle visible", flush=True)
        for dd in dets:
            print(f"    centre=({dd.cx:.0f},{dd.cy:.0f}) rayon={dd.rayon:.0f} aire={dd.aire:.0f} rondeur={dd.rondeur:.2f} bord={dd.touche_bord}", flush=True)
        cv2.imwrite(f"/home/raphael/beak_{pitch}_{yaw}.png", vision.annotate(img, dets))
tenir(0.5, 0.0)
