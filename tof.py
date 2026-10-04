#!/usr/bin/env python3
"""Capteur de distance de la tete (ToF 8x8, VL53L5CX) -> obstacles dans le repere du tronc, pour se promener sans se
cogner (regle de vie : un canard autonome ne fonce pas dans les murs).

Lit `tofd` (socket Unix, JSON-RPC/NDJSON : requete `tof.stream`, puis notifications `tof.frame` {rows, cols,
distance_mm, status}). Chaque zone valide (status 5 ou 9, distance > 0) est un rayon `tof_beams[i]` (repere du capteur :
+x axe optique, +y gauche, +z haut ; `robot.model`) place dans le repere du tronc avec la pose `frames.tof` de
`robot.state` (qui suit la tete). On garde les points entre 3 et 30 cm au-dessus du sol (le sol lui-meme et le dessus
des meubles ne genent pas) et on resume en distances libres devant / a gauche / a droite.

Usage : bash ~/run-brain.sh tof.py   (affiche les distances libres pendant 5 s)
"""
import json
import math
import os
import socket
import threading
import time
from pathlib import Path

import geometry

SOCK_TOF = Path(os.environ.get("TOFD_SOCK") or Path.home() / ".cache/duck-sim/duck-a-tof.sock")
STATUS_VALIDES = (5, 9)
HAUTEUR_UTILE = (0.03, 0.30)     # au-dessus du sol, en m
DEMI_LARGEUR = 0.12              # couloir devant le canard (il fait ~16 cm de large) + marge
PORTEE_MAX = 4.0                 # au-dela, le VL53L5CX ne repond pas de facon fiable


class Tof(threading.Thread):
    def __init__(self, beams, chemin=SOCK_TOF):
        super().__init__(daemon=True)
        self.beams = beams                       # 64 directions unitaires (robot.model -> tof_beams)
        self.chemin = chemin
        self.derniere = None                     # (instant monotonic, trame)
        self.actif = True

    def run(self):
        while self.actif:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(str(self.chemin))
                s.sendall((json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tof.stream"}) + "\n").encode())
                tampon = b""
                while self.actif:
                    bloc = s.recv(65536)
                    if not bloc:
                        break
                    tampon += bloc
                    while b"\n" in tampon:
                        ligne, tampon = tampon.split(b"\n", 1)
                        msg = json.loads(ligne)
                        if msg.get("method") == "tof.frame":
                            self.derniere = (time.monotonic(), msg["params"])
            except (OSError, ValueError):
                time.sleep(1.0)                  # tofd absent ou redemarre : on reessaie

    def points(self, etat, age_max=0.5):
        """Points d'obstacle (x, y, hauteur au-dessus du sol) dans le repere du tronc, ou None si pas de trame fraiche."""
        d = self.derniere
        if d is None or time.monotonic() - d[0] > age_max:
            return None
        trame = d[1]
        pose = etat["frames"]["tof"]
        r = geometry.quat_vers_matrice(pose["quat"])
        h_tronc = etat["odom"]["position"][2]
        out = []
        for i, (mm, st) in enumerate(zip(trame["distance_mm"], trame["status"])):
            if st not in STATUS_VALIDES or mm <= 0 or mm / 1000 > PORTEE_MAX:
                continue
            dist = mm / 1000
            b = self.beams[i]
            p = [pose["pos"][k] + dist * sum(r[k][j] * b[j] for j in range(3)) for k in range(3)]
            hauteur = p[2] + h_tronc
            if HAUTEUR_UTILE[0] <= hauteur <= HAUTEUR_UTILE[1]:
                out.append((p[0], p[1], hauteur))
        return out

    def libre(self, etat):
        """{'devant', 'gauche', 'droite'} : distance au plus proche obstacle dans chaque secteur (m, inf si rien vu),
        ou None si le capteur ne repond pas (prudence : l'appelant doit alors ne pas avancer)."""
        pts = self.points(etat)
        if pts is None:
            return None
        devant = gauche = droite = math.inf
        for x, y, _ in pts:
            if x <= 0:
                continue
            if abs(y) <= DEMI_LARGEUR:
                devant = min(devant, x)
            elif y > 0:
                gauche = min(gauche, math.hypot(x, y))
            else:
                droite = min(droite, math.hypot(x, y))
        return {"devant": devant, "gauche": gauche, "droite": droite, "n": len(pts)}


def beams_du_robot(client):
    r = client.request("robot.model", {})
    return r["result"]["tof_beams"]


def main():
    from poc_robotd_client import RobotdClient, SOCK_PATH
    c = RobotdClient(SOCK_PATH)
    tof = Tof(beams_du_robot(c))
    c.request("robot.subscribe", {})
    tof.start()
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5:
        s = c.read_state_frame()
        if int((time.monotonic() - t0) * 2) != int((time.monotonic() - t0 - 0.02) * 2):
            print(tof.libre(s), flush=True)


if __name__ == "__main__":
    main()
