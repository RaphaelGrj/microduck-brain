#!/usr/bin/env python3
"""Le canard voit-il le bord d'une estrade avant de tomber ? (scene `bash ~/run-scene.sh marche` : estrade de 15 cm,
bord a x = 0,60 m, canard en (0, 0) face a +x). Il marche droit devant (0,4 m/s) et s'arrete des que tof.libre() voit
un vide a moins de ARRET m (meme regle que la promenade devant un mur). La verite terrain dit ou etait vraiment le bord.

Plusieurs essais, tete au neutre puis tete un peu baissee. Usage : bash ~/run-brain.sh essai_vide.py
"""
import math
import time

import tof
import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

BORD_X = 0.60          # bord de l'estrade (monde)
ARRET = 0.45           # seuil d'arret de la promenade (brain.LIBRE_MIN)

c = RobotdClient(SOCK_PATH)
capteur = tof.Tof(tof.beams_du_robot(c))
c.request("robot.subscribe", {})
capteur.start()


def tenir(secs, vx=0.0, tete=0.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        s = c.read_state_frame()
        capteur.noter_etat(s)
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": tete, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": vx, "vy": 0.0, "vyaw": 0.0})
    return s


def essai(depart_x, tete):
    truth.teleport_duck(depart_x, 0.0, 0.0)            # reste sur l'estrade (hauteur conservee)
    tenir(2.0, tete=tete)
    vu, t0 = None, time.monotonic()
    while time.monotonic() - t0 < 6.0:
        s = c.read_state_frame()
        lib = capteur.libre(s)
        x = truth.read()["ducks"][0]["pos"][0]
        if lib and lib["vide"] < ARRET:
            vu = (lib["vide"], BORD_X - x)
            break
        if x > BORD_X - 0.12 or s["safety"]["fallen"]:
            break                                           # garde-fou de l'essai : on ne le laisse pas tomber
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": tete, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.4, "vy": 0.0, "vyaw": 0.0})
    s = tenir(1.5, tete=tete)
    x = truth.read()["ducks"][0]["pos"][0]
    if vu:
        print(f"  depart x={depart_x:+.2f}, tete {tete:.1f} : VIDE VU a {vu[0]:.2f} m (vrai bord a {vu[1]:.2f} m) ; "
              f"arrete a {BORD_X - x:.2f} m du bord, chute={s['safety']['fallen']}", flush=True)
    else:
        print(f"  depart x={depart_x:+.2f}, tete {tete:.1f} : PAS VU ; arrete par le garde-fou a {BORD_X - x:.2f} m du bord, "
              f"chute={s['safety']['fallen']}", flush=True)
    return vu is not None


ok = 0
n = 0
for tete in (0.0, 0.3):
    for depart in (-0.6, -0.3, 0.0):
        n += 1
        ok += essai(depart, tete)
print(f"=== bord vu a temps : {ok}/{n} ===", flush=True)
