#!/usr/bin/env python3
"""Demo de bout en bout dans la simulation (scene arena_chat) : camera -> YOLO -> veille -> evenement -> cerveau ->
regard (robot.look) -> memoire. Le canard est replace a l'origine, tourne de CAP degres : l'affiche (x = 1,2 m, y = 0)
est donc sur le cote ; on verifie qu'il la regarde. Memoire de demo : ~/.cache/duck-sim/memoire_demo.json.

Usage : bash ~/run-brain.sh demo_chat.py [duree_s=20] [cap_deg=-17]"""
import math
import os
import sys
import time

os.environ.setdefault("MICRODUCK_MEMOIRE", os.path.expanduser("~/.cache/duck-sim/memoire_demo.json"))
import animaux  # noqa: E402
import brain  # noqa: E402
import chat  # noqa: E402
import memoire  # noqa: E402
import truth  # noqa: E402
import vision  # noqa: E402
from poc_robotd_client import RobotdClient, SOCK_PATH  # noqa: E402

DUREE = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
CAP = math.radians(float(sys.argv[2])) if len(sys.argv) > 2 else math.radians(-17)
mem = memoire.Memoire(os.environ["MICRODUCK_MEMOIRE"])
avant = mem.donnees["etres"].get("chat", {}).get("rencontres", 0)
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
truth.teleport_duck(0.0, 0.0, CAP)
gt = truth.read()
d = gt["ducks"][0]
attendu = math.degrees(math.atan2(0.0 - d["pos"][1], 1.2 - d["pos"][0]) - truth.trunk_yaw(d["quat"]))
veille = chat.VeilleChat(animaux.DetecteurCoco(), vision.grab_frame, periode_s=0.5, seuil=0.5, memoire=mem)
veille.start()
vus, lacet = [], []


def tick(b, state):
    veille.etat_robot_hook(b, state)
    if not vus or vus[-1][1] != b.courant.nom:
        vus.append((round(b.t_global, 1), b.courant.nom))
    if b.courant.nom == "regarde_chat":
        lacet.append(state["joints"][7])                 # joint head_yaw


b = brain.run(c, DUREE, source=veille.source, a_chaque_tick=tick, seed=2, extras={"chat": veille})
veille.actif = False
etat = b.etats["regarde_chat"]
fin = lacet[len(lacet) // 2:] or [0.0]
print("etats traverses (t, etat) :", vus)
print(f"affiche a {attendu:+.0f} deg du cap du canard ; pendant regarde_chat : {etat.n_look} appel(s) robot.look, "
      f"lacet de tete moyen (2e moitie) {math.degrees(sum(fin) / len(fin)):+.0f} deg (joint, sans le cou ni le corps)")
e = veille.estimation
if e:
    print(f"derniere position estimee du chat : ({e[1]:+.2f}, {e[2]:+.2f}) m dans le repere du tronc")
apres = mem.donnees["etres"].get("chat", {})
print(f"memoire : rencontres {avant} -> {apres.get('rencontres')}, familiarite {mem.familiarite('chat'):.2f}")
ok = any(n == "regarde_chat" for _, n in vus) and etat.n_look > 0
print("RESULTAT :", "le canard a vu le chat et l'a suivi des yeux" if ok else "ECHEC")
