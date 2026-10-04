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
import collections
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
SEUIL_VIDE = 0.04                # un point plus de 4 cm sous le sol = une marche vers le bas (tapis et seuils : < 2 cm)
VIDE_MIN_RAYONS = 2              # rayons qui doivent voir le vide dans la meme trame (duck-sim : faux vides isoles ~1 %)
ECART_POSE_NS = 40_000_000       # pose de tete acceptee jusqu'a 40 ms de l'instant de la trame ToF


def haut(etat):
    """Verticale (vers le haut) dans le repere du tronc, d'apres la gravite mesuree (safety.gravity) ; (0, 0, 1) sinon."""
    g = (etat.get("safety") or {}).get("gravity")
    if not g:
        return (0.0, 0.0, 1.0)
    n = math.sqrt(sum(v * v for v in g)) or 1.0
    return tuple(-v / n for v in g)


class Tof(threading.Thread):
    def __init__(self, beams, chemin=SOCK_TOF):
        super().__init__(daemon=True)
        self.beams = beams                       # 64 directions unitaires (robot.model -> tof_beams)
        self.chemin = chemin
        self.derniere = None                     # (instant monotonic, trame)
        self.actif = True
        self.historique = collections.deque(maxlen=60)   # (t_ns, pose tof, hauteur du tronc) des dernieres trames d'etat

    def noter_etat(self, etat):
        """A appeler a CHAQUE trame robot.state : garde la pose du capteur pour la retrouver a l'instant exact de la
        trame ToF (la tete bouge : la pose courante, plus recente, place mal les points, surtout vers le sol)."""
        if etat and etat.get("t_ns") and etat.get("frames", {}).get("tof"):
            self.historique.append((etat["t_ns"], etat["frames"]["tof"], etat["odom"]["position"][2], haut(etat)))

    def _pose_a(self, t_ns):
        """Pose du capteur la plus proche de t_ns (None si l'historique n'a rien a moins de ECART_POSE_NS)."""
        h = list(self.historique)
        if not h or t_ns is None:
            return None
        meilleur = min(h, key=lambda e: abs(e[0] - t_ns))
        return meilleur if abs(meilleur[0] - t_ns) <= ECART_POSE_NS else None

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

    def points(self, etat, age_max=0.5, vides=None):
        """Points d'obstacle (x, y, hauteur au-dessus du sol) dans le repere du tronc, ou None si pas de trame fraiche.
        Si `vides` est une liste, y ajoute les VIDES vus (marche, escalier, trou) : un rayon qui touche quelque chose
        nettement SOUS le niveau du sol (robotd n'a aucune protection contre les chutes, voir QUACKSAT_QUACKNAV.md).
        Le bord est au plus loin la ou le rayon traverse le niveau du sol : c'est ce point (x, y) qui est ajoute."""
        d = self.derniere
        if d is None or time.monotonic() - d[0] > age_max:
            return None
        trame = d[1]
        self.noter_etat(etat)
        synchro = self._pose_a(trame.get("t_ns"))
        if synchro is not None:
            _, pose, h_tronc, up = synchro               # pose de la tete (et du tronc) a l'instant de la mesure
        else:
            pose, h_tronc, up = etat["frames"]["tof"], etat["odom"]["position"][2], haut(etat)
            vides = None                                 # pose incertaine : pas de verdict de vide (trop de faux)
        r = geometry.quat_vers_matrice(pose["quat"])
        out = []
        for i, (mm, st) in enumerate(zip(trame["distance_mm"], trame["status"])):
            if st not in STATUS_VALIDES or mm <= 0 or mm / 1000 > PORTEE_MAX:
                continue
            dist = mm / 1000
            b = self.beams[i]
            u = [sum(r[k][j] * b[j] for j in range(3)) for k in range(3)]       # direction du rayon (tronc)
            p = [pose["pos"][k] + dist * u[k] for k in range(3)]
            hauteur = h_tronc + sum(p[k] * up[k] for k in range(3))           # le tronc penche en marchant
            if HAUTEUR_UTILE[0] <= hauteur <= HAUTEUR_UTILE[1]:
                out.append((p[0], p[1], hauteur))
            elif vides is not None and hauteur < -SEUIL_VIDE and (u_up := sum(u[k] * up[k] for k in range(3))) < 0:
                s = (h_tronc + sum(pose["pos"][k] * up[k] for k in range(3))) / -u_up   # traversee du niveau du sol
                vides.append((pose["pos"][0] + s * u[0], pose["pos"][1] + s * u[1]))
        return out

    def libre(self, etat):
        """{'devant', 'gauche', 'droite', 'vide'} : distance au plus proche obstacle OU vide dans chaque secteur (m, inf
        si rien vu), 'vide' = distance du bord de vide le plus proche devant (inf si aucun) ; None si le capteur ne
        repond pas (prudence : l'appelant doit alors ne pas avancer). Un vide compte comme un obstacle : la promenade
        s'arrete devant un escalier comme devant un mur."""
        vides = []
        pts = self.points(etat, vides=vides)
        if pts is None:
            return None
        if len(vides) < VIDE_MIN_RAYONS:
            vides = []                          # un rayon isole (bruit, tete en mouvement) : un vrai bord en couvre plusieurs
        vide = min((x for x, y in vides if x > 0 and abs(y) <= DEMI_LARGEUR), default=math.inf)
        pts = pts + [(x, y, 0.0) for x, y in vides]
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
        return {"devant": devant, "gauche": gauche, "droite": droite, "vide": vide, "n": len(pts)}


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
