#!/usr/bin/env python3
"""Jeu de balle avec un joueur (le chat ou une personne) : trouver le joueur, trouver la balle, la lui passer.

Une manche :
  1. CHERCHER LE JOUEUR : tete qui balaie (gauche - centre - droite), corps qui tourne d'un quart de tour si rien ;
     detection YOLO (animaux.py : "cat" ou "person"), point au sol sous la boite (geometry.point_au_sol), converti
     dans le repere de l'ODOMETRIE (le joueur reste a peu pres la ou il est pendant que le canard va a la balle).
  2. GARDE-FOUS (ROADMAP, non negociables) : le chat peut toujours partir -> joueur introuvable pendant ABANDON_S =
     fin de la partie, jamais de poursuite ; jamais de passe vers un chat a moins de D_MIN_CHAT de la balle (on
     attend qu'il s'eloigne, sinon on arrete : ne jamais le coincer) ; sons moderes (chirp, pas d'alarme).
  3. PASSE : approach.Approche avec `cible_vise` = position du joueur (la ligne de tir part de la balle vers lui).
  4. Petite celebration, puis on attend que la balle revienne (ou pas) avant la manche suivante.

Le tir actuel est FORT (1 a 3 m/s) : la vraie passe douce attend la politique BallKickPasse (fork, entrainement
prevu). Usage : bash ~/run-brain.sh jeu.py [chat|personne] [manches=3]
"""
import math
import sys
import time

import animaux
import approach
import geometry
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

CLASSE = {"chat": "cat", "personne": "person"}
ABANDON_S = 20.0             # joueur introuvable aussi longtemps : il est parti, on ne le poursuit pas
D_MIN_CHAT = 0.8             # jamais de passe vers un chat a moins de 80 cm de la balle
# lacets de tete pour chercher le joueur (rad de commande, ~1,3 rad de regard par rad) : la camera ne voit que +-22 deg,
# donc des pas de 0,3 (~23 deg) sans trou (jeu_eval : avec 0 / +-0,9 un chat a 25-40 deg n'etait jamais vu)
BALAYAGE = (0.0, 0.3, -0.3, 0.6, -0.6, 0.9, -0.9)
SEUIL_RECHERCHE = 0.4
TETE_PITCH = 0.15            # un peu baissee : un chat assis et une personne debout restent dans le champ
ATTENTE_RETOUR_S = 6.0


class Partie:
    def __init__(self, client, joueur="chat", log=print, arret=None, detecteur=None, verite=False):
        self.c = client
        self.joueur = joueur
        self.classe = CLASSE[joueur]
        self.log = log
        self.arret = arret or (lambda: False)
        self.det = detecteur or animaux.DetecteurCoco()
        self.verite = verite
        self.position = None             # (x, y) du joueur, repere de l'odometrie
        self.journal = []

    # --- bas niveau ----------------------------------------------------------------------------------
    def tenir(self, secs, tete=(0.0, 0.0), vyaw=0.0):
        t0 = time.monotonic()
        s = None
        while time.monotonic() - t0 < secs:
            s = self.c.read_state_frame()
            self.c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": tete[1], "head_yaw": tete[0], "head_roll": 0.0})
            self.c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": vyaw})
        return s

    def regarder(self, yaw):
        """Tete tournee de `yaw`, stabilisee ; renvoie la position du joueur (odometrie) ou None."""
        s = self.tenir(0.7, (yaw, TETE_PITCH))
        try:
            objets = self.det.detect(vision.grab_frame(), classes=(self.classe,), seuil=SEUIL_RECHERCHE)
        except Exception as e:
            self.log(f"  (image indisponible : {e})")
            return None
        if not objets:
            return None
        o = max(objets, key=lambda q: q.score)
        p = geometry.point_au_sol(o.pied[0], o.pied[1], s["frames"]["camera"], s["odom"]["position"][2])
        if p is None:
            return None
        ox, oy, oyaw = s["odom"]["position"][0], s["odom"]["position"][1], s["odom"]["yaw"]
        pos = (ox + math.cos(oyaw) * p[0] - math.sin(oyaw) * p[1], oy + math.sin(oyaw) * p[0] + math.cos(oyaw) * p[1])
        self.log(f"  {self.joueur} vu (score {o.score:.2f}) a {math.hypot(*p):.2f} m, "
                 f"{math.degrees(math.atan2(p[1], p[0])):+.0f} deg")
        return pos

    def chercher_joueur(self):
        """Balayage de tete, puis quarts de tour du corps, pendant ABANDON_S au plus."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < ABANDON_S and not self.arret():
            for yaw in BALAYAGE:
                pos = self.regarder(yaw)
                if pos is not None:
                    self.tenir(0.5)                         # tete au neutre avant de repartir
                    return pos
            self.tenir(approach.duree_rotation(math.pi / 2), vyaw=approach.V_ROT)
            self.tenir(0.6)
        return None

    def distance_balle_joueur_ok(self, balle_odom):
        if self.joueur != "chat" or balle_odom is None or self.position is None:
            return True
        return math.hypot(balle_odom[0] - self.position[0], balle_odom[1] - self.position[1]) >= D_MIN_CHAT

    def son(self, tag):
        try:
            self.c.request("robot.sound", {"tag": tag})
        except Exception:
            pass

    # --- une manche ----------------------------------------------------------------------------------
    def manche(self, i):
        self.log(f"\n=== manche {i} : cherche le {self.joueur}")
        self.position = self.chercher_joueur()
        if self.position is None:
            self.log(f"  {self.joueur} introuvable depuis {ABANDON_S:.0f} s : il est parti, fin de la partie")
            return "parti"
        self.son("chirp")                                   # petite invitation, son modere
        ap = approach.Approche(self.c, "orange", verite=self.verite, log=self.log, cible_vise=self.position,
                               arret=self.arret)
        garde = ap.decider
        trop_pres = []

        def decider_avec_garde(est, vue=True):
            # garde-fou chat : pas de passe vers un chat trop pres de la balle (on ne le coince jamais)
            if ap.balle_odom is not None and not self.distance_balle_joueur_ok(ap.balle_odom):
                ap.log("  le chat est trop pres de la balle : pas de passe")
                trop_pres.append(True)
                ap.etat = "FINI"                            # sort de la boucle d'approche, sans tirer
                return
            garde(est, vue)
        ap.decider = decider_avec_garde
        if self.verite:
            import truth
            ap.avant_tir = lambda: {"gt": truth.read()}
        res = ap.run(90.0)
        ap.vis.run_flag = False
        self.journal.append({"manche": i, "joueur": self.position, **res})
        if trop_pres:
            self.c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
            return "trop_pres"
        if res.get("etat") != "FINI":
            return "rate"
        self.son("greet")
        self.tenir(ATTENTE_RETOUR_S)                        # la balle roule ; le joueur la renvoie (ou pas)
        return "passe"

    def run(self, manches=3):
        for i in range(1, manches + 1):
            if self.arret():
                return "interrompu"
            r = self.manche(i)
            if r in ("parti", "trop_pres"):
                return r
        return "fini"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    joueur = args[0] if args else "chat"
    manches = int(args[1]) if len(args) > 1 else 3
    c = RobotdClient(SOCK_PATH)
    c.request("robot.subscribe", {})
    p = Partie(c, joueur, log=lambda m: print(m, flush=True), verite="--verite" in sys.argv)
    print("fin de la partie :", p.run(manches), flush=True)


if __name__ == "__main__":
    main()
