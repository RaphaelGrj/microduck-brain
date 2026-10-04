#!/usr/bin/env python3
"""Pourquoi le chat (affiche) n'est-il pas trouve quand il est sur le cote ? Canard en (0, -0,9) cap 0 (chat a +37 deg),
pour chaque lacet de tete : meilleur score YOLO "cat" (seuil 0,05), point au sol, et image annotee ~/diag_jeu_<yaw>.png.

Usage (scene arena_chat) : bash ~/run-brain.sh diag_jeu.py
"""
import math

import cv2

import animaux
import geometry
import jeu
import truth
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
p = jeu.Partie(c, "chat", log=print)
p.tenir(1.0)
truth.teleport_duck(0.0, -0.9, 0.0)
p.tenir(1.0)
for yaw in jeu.BALAYAGE + (1.2, -1.2):
    s = p.tenir(1.0, (yaw, jeu.TETE_PITCH))
    img = vision.grab_frame()
    objets = p.det.detect(img, classes=None, seuil=0.05)
    chats = [o for o in objets if o.classe == "cat"]
    head = [round(v, 2) for v in s["joints"][5:9]]
    meilleur = max(chats, key=lambda o: o.score) if chats else None
    txt = f"yaw {yaw:+.1f} (joints tete {head}) : "
    if meilleur:
        pt = geometry.point_au_sol(meilleur.pied[0], meilleur.pied[1], s["frames"]["camera"], s["odom"]["position"][2])
        txt += f"chat score {meilleur.score:.2f} boite ({meilleur.x:.0f},{meilleur.y:.0f},{meilleur.w:.0f}x{meilleur.h:.0f}) sol {pt}"
    else:
        txt += "pas de chat ; autres : " + ", ".join(f"{o.classe} {o.score:.2f}" for o in objets[:3])
    print(txt, flush=True)
    for o in objets:
        cv2.rectangle(img, (int(o.x), int(o.y)), (int(o.x + o.w), int(o.y + o.h)), (0, 255, 0), 2)
        cv2.putText(img, f"{o.classe} {o.score:.2f}", (int(o.x), int(o.y) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.imwrite(f"/home/raphael/diag_jeu_{yaw:+.1f}.png", img)
p.tenir(0.5)
