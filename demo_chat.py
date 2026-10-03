#!/usr/bin/env python3
"""Demo de bout en bout dans la simulation (scene arena_chat) : camera -> YOLO -> veille -> evenement -> cerveau.
Le canard est replace face a l'affiche du chat ; on attend que le cerveau passe en etat `curious` et on mesure
l'amplitude de la tete. Usage : bash ~/run-brain.sh demo_chat.py [duree_s=20]"""
import sys
import time

import animaux
import brain
import chat
import truth
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

DUREE = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
truth.teleport_duck(0.0, 0.0, 0.0)
veille = chat.VeilleChat(animaux.DetecteurCoco(), vision.grab_frame, periode_s=0.5, seuil=0.5)
veille.start()
vus = []


def tick(b, state):
    if not vus or vus[-1][1] != b.courant.nom:
        vus.append((round(b.t_global, 1), b.courant.nom))


b = brain.run(c, DUREE, source=veille.source, a_chaque_tick=tick, seed=2)
veille.actif = False
print("etats traverses (t, etat) :", vus)
print("apparitions du chat memorisees :", veille.suivi.nb_apparitions, "; derniere vue : score",
      None if not veille.suivi.derniere_vue else round(veille.suivi.derniere_vue[1].score, 2))
ok = any(n == "curious" for _, n in vus)
print("RESULTAT :", "le canard a reagi a la vue du chat (etat curious)" if ok else "AUCUNE reaction")
