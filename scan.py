#!/usr/bin/env python3
"""Balayage : le canard pivote sur place, on detecte a chaque image et on loggue.

Premiere boucle perception -> action : verifie que le detecteur voit les balles / cubes de
l'appartement quand on les met dans le champ, et donne leur cap (yaw odom) pour calibrer.

Usage : bash ~/run-brain.sh scan.py [duree_s] [vyaw]   (defaut 14 s a 0.5 rad/s ~ 400 deg)
"""
import math
import os
import sys
import time

import cv2

import vision
from poc_robotd_client import RobotdClient, SOCK_PATH


def main():
    duree = float(sys.argv[1]) if len(sys.argv) > 1 else 14.0
    vyaw = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
    c = RobotdClient(SOCK_PATH)
    c.request("robot.subscribe", {})
    t0 = time.monotonic()
    derniere_capture = 0.0
    vus = {}
    state = c.read_state_frame()

    # Le canard demarre dans son dock (panneau devant, barres autour) : il ne peut pas pivoter
    # sur place. On recule d'abord jusqu'a `sortie` metres (odometrie), comme un vrai canard.
    # (Le dock n'etait PAS la cause : sa geometrie est purement visuelle. Le canard ne bougeait
    # pas parce que alpha_walking a une zone morte : voir ZONE_MORTE.md.) Etape de recul
    # conservee en option : SORTIE_DOCK=<metres>, desactivee par defaut.
    sortie = float(os.environ.get("SORTIE_DOCK", "0"))
    if sortie > 0:
        p0 = state["odom"]["position"]
        tb = time.monotonic()
        dist = 0.0
        while time.monotonic() - tb < 12.0 and dist < sortie:
            state = c.read_state_frame()
            p = state["odom"]["position"]
            dist = math.hypot(p[0] - p0[0], p[1] - p0[1])
            c.notify("robot.move", {"vx": -0.4, "vy": 0.0, "vyaw": 0.0})
        print(f"recule de {dist:.2f} m en {time.monotonic() - tb:.1f}s", flush=True)
        for _ in range(25):                      # laisse le canard se stabiliser
            state = c.read_state_frame()
            c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})

    yaw0 = state["odom"]["yaw"]
    t0 = time.monotonic()
    print(f"balayage {duree:.0f}s a vyaw={vyaw} rad/s, cap initial {math.degrees(yaw0):.0f} deg", flush=True)

    while time.monotonic() - t0 < duree:
        state = c.read_state_frame()          # cadence = flux d'etat (50 Hz)
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": vyaw})
        now = time.monotonic() - t0
        if now - derniere_capture >= 0.3:      # ~2 images/s suffisent pour un balayage
            derniere_capture = now
            img = vision.grab_frame()
            cap = math.degrees(state["odom"]["yaw"] - yaw0)
            if os.environ.get("VERBOSE"):
                n = int(now / 0.5)
                print(f"  [t={now:4.1f}s] cap={cap:+6.0f} deg  policy={state['policy']} "
                      f"move_applique={[round(x, 2) for x in state['move']['applied']]}", flush=True)
                if n % 4 == 0:
                    cv2.imwrite(f"/home/raphael/scan_raw_{n:02d}.png", img)
            for d in vision.detect(img, aire_min=40):
                ya, _ = vision.pixel_to_angles(d.cx, d.cy)
                print(f"  t={now:4.1f}s cap={cap:+6.0f} deg  {d.couleur:7s} centre=({d.cx:.0f},{d.cy:.0f}) "
                      f"r={d.rayon:.0f}px rondeur={d.rondeur:.2f} ecart_cap={math.degrees(ya):+.1f} deg", flush=True)
                cle = d.couleur
                if cle not in vus or d.aire > vus[cle][0]:
                    vus[cle] = (d.aire, now, cap)
                    cv2.imwrite(f"/home/raphael/scan_{cle}.png", vision.annotate(img, [d]))
    c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
    c.request("robot.stop")
    print("--- resume : meilleure vue par couleur (aire, t, cap) ---", flush=True)
    for k, (a, t, cap) in sorted(vus.items()):
        print(f"  {k:7s} aire={a:.0f}  a t={t:.1f}s  cap={cap:+.0f} deg", flush=True)
    if not vus:
        print("  rien detecte", flush=True)


if __name__ == "__main__":
    main()
