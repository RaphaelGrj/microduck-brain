#!/usr/bin/env python3
"""Controleur d'approche : voit la balle, marche jusqu'a elle, s'ajuste, declenche le tir.

Principe "arret - regard - rafale" (dicte par les mesures, voir ZONE_MORTE.md et bursts.py) :
  1. La TETE garde la balle au centre de l'image (suivi du regard, sans zone morte), et est
     PRE-POSITIONNEE avant chaque rafale sur l'endroit ou la balle sera apres (sinon la balle
     sort du champ par le bas pendant la marche).
  2. Quand le canard est immobile et la tete stabilisee, on localise la balle dans le repere du
     tronc (geometry.py : pose camera de robotd + intersection avec le sol, erreur 0,5-2 cm).
  3. On decide UNE rafale du corps (marche vx>=0,4 / rotation |vyaw|>=1,5 / pas de cote vy=0,4 :
     en dessous, la zone morte de la politique de marche fige les jambes), dont la DUREE dose
     l'amplitude, puis on s'arrete et on regarde a nouveau. L'image arrive avec 0,2 s de retard :
     decider pendant le mouvement integrerait des images perimees.
  4. Phases : CHERCHER (rotation par rafales) -> VISER (tourner/avancer jusqu'a ~35 cm) ->
     AJUSTER (placer la balle dans la fenetre de tir d'entrainement, +-2 cm) -> TIRER
     (`robot.do kick_left|kick_right` selon le cote de la balle).
  5. Si la balle sort du champ en phase AJUSTER, sa position est propagee depuis la derniere
     mesure par l'ODOMETRIE de robotd (state.odom) au lieu d'etre supposee immobile.

Le cerveau n'utilise JAMAIS la verite terrain pour decider : elle n'est lue (option --verite) que
pour comparer l'estimation visuelle a la realite.

Usage : bash ~/run-brain.sh approach.py [couleur=orange] [duree_max_s=90] [--verite]
"""
import math
import sys
import time

import geometry
import track
import vision
from poc_robotd_client import RobotdClient, SOCK_PATH

K_YAW, K_PITCH = 572.0, -348.0          # px par rad de commande de tete (mesures par track.py)
CENTRE_X, CENTRE_Y = vision.WIDTH / 2, vision.HEIGHT / 2
GAIN_TETE, SETTLE_TETE, SETTLE_CORPS = 0.5, 0.55, 0.9
YAW_MAX, PITCH_MIN, PITCH_MAX = 1.2, -0.5, 1.5     # le joint sature vers 1,57 rad (commande 1,5)
P_MARCHE = 0.4                           # inclinaison de tete tolerable PENDANT une rafale : la rotation du corps
                                         # marche jusqu'a 0,5, se degrade a 0,7 et est morte a 1,0 (bursts.py)
GAIN_LACET_TETE = 1.3                    # rad de regard par rad de commande de lacet de tete (mesure)

# Inclinaison de tete (commande) qui CENTRE une balle posee au sol a la distance d (mesures
# vis_range.py / vis_near.py) : plus elle est proche, plus il faut baisser la tete.
TABLE_PITCH = ((0.09, 1.50), (0.12, 1.37), (0.18, 0.92), (0.25, 0.62), (0.35, 0.45), (0.5, 0.22), (0.7, 0.05), (1.5, 0.0))

# Fenetre de tir MESUREE (kick_sweep.py, arene, canard remis a l'origine a chaque essai) : balle dans
# le repere du tronc a x = 0,07 m (2 cm plus pres que le point d'entrainement 0,09 : a +2 cm ou plus
# le pied ne touche rien, a -4 cm le coup est mou) ; en lateral, y = +-0,042 +-3 cm passent.
CIBLE_X, CIBLE_Y = 0.071, 0.042
TOL_X = 0.017                              # x dans [0,054 ; 0,088] : a 5 cm le coup est mou, a 9 cm limite haute
TOL_Y_INT, TOL_Y_EXT = 0.02, 0.035       # lateral : cote axe du canard (pied gauche : balle trop a droite) / cote exterieur
X_MIN_BALLE, Y_MIN_BALLE = 0.05, 0.09    # zone occupee par le canard : aucune balle reelle ne peut y etre
D_ENTREE_AJUST = 0.35                    # on passe en AJUSTER sous cette distance
D_SORTIE_AJUST = 0.45                    # et on repasse en VISER au-dela (balle repoussee)
MAX_AJUSTEMENTS = 10
MAX_PROPAGATIONS = 2                     # mesures "a l'odometrie" consecutives avant de chercher
T_TETE_NEUTRE = 1.4                      # attente, tete ramenee au neutre, avant de lancer le tir

V_MARCHE, V_ROT, V_COTE = 0.4, 1.5, 0.4  # au-dessus de la zone morte


def duree_marche(d):
    """Duree de rafale vx=0,4 pour avancer de d metres (mesure : ~18 cm/s apres 0,14 s de demarrage)."""
    return d / 0.18 + 0.14


def avance_marche(duree):
    return max(0.0, 0.18 * (duree - 0.14))


def duree_rotation(angle_rad):
    """Duree de rafale vyaw=1,5 pour tourner de `angle_rad` (mesure : ~50 deg/s, rien en dessous de 0,4 s)."""
    return abs(math.degrees(angle_rad)) / 50.0


def pitch_pour(d):
    if d <= TABLE_PITCH[0][0]:
        return TABLE_PITCH[0][1]
    for (d0, p0), (d1, p1) in zip(TABLE_PITCH, TABLE_PITCH[1:]):
        if d <= d1:
            return p0 + (p1 - p0) * (d - d0) / (d1 - d0)
    return TABLE_PITCH[-1][1]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Approche:
    def __init__(self, client, couleur="orange", verite=False, log=print):
        self.c = client
        self.couleur = couleur
        self.log = log
        self.verite = None
        if verite:
            import truth
            self.verite = truth
        self.vis = track.Vision(couleur)
        self.vis.start()
        self.yaw, self.pitch = 0.0, 0.0           # offsets de tete commandes
        self.burst = None                          # (vx, vy, vyaw, t_fin)
        self.t_pret = 0.0                          # images capturees avant : refusees (tete / corps en mouvement)
        self.t_traite = 0.0
        self.etat = None
        self.cote = None                           # pied choisi en phase d'ajustement
        self.manques = 0
        self.mesure = None                         # (estimation (x, y), odom (x, y), odom yaw) a l'instant de la mesure
        self.n_propag = 0
        self.sens_recherche = +1.0
        self.n_ajust = 0
        self.t_tir = 0.0
        self.avant_tir = None
        self.resultat = {}

    # --- boucle bas niveau -------------------------------------------------------------
    def pas(self):
        """Un tour de boucle cadence sur le flux d'etat : renvoie la trame, envoie tete et corps."""
        s = self.c.read_state_frame()
        now = time.monotonic()
        vx = vy = vyaw = 0.0
        yaw, pitch = self.yaw, self.pitch                           # posture de REGARD
        if self.burst:
            (bvx, bvy, bvyaw), t_debut, t_fin, fin = self.burst[:3], self.burst[3], self.burst[4], self.burst[5]
            if now < t_fin:
                yaw, pitch = 0.0, min(self.pitch, P_MARCHE)         # posture de MARCHE pendant la rafale
                if now >= t_debut:
                    vx, vy, vyaw = bvx, bvy, bvyaw
            else:                                                   # fin de rafale : retour a la posture de regard
                self.burst = None
                if fin is not None:
                    self.yaw, self.pitch = fin
                    yaw, pitch = fin
        self.c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": pitch, "head_yaw": yaw, "head_roll": 0.0})
        self.c.notify("robot.move", {"vx": vx, "vy": vy, "vyaw": vyaw})
        return s

    def lancer_rafale(self, vx, vy, vyaw, duree, est=None):
        """Lance une rafale en posture de MARCHE (tete relevee : tete baissee, la rotation du corps
        est morte, voir bursts.py) puis revient a la posture de REGARD. Si on connait la balle (x, y),
        la posture de regard finale est pre-positionnee sur l'endroit ou elle sera apres la rafale
        (modeles de rotation / avance / pas de cote issus de bursts.py)."""
        duree = max(0.0, duree)
        fin = None
        regard = (self.yaw, self.pitch)
        if est is not None:
            x, y = est
            ang = math.copysign(math.radians(50.0) * duree, vyaw) if vyaw else 0.0
            c, s_ = math.cos(ang), math.sin(ang)
            x, y = c * x + s_ * y, -s_ * x + c * y                 # le repere tourne de `ang`
            if vx:
                x -= math.copysign(avance_marche(duree), vx)
            if vy:
                y -= math.copysign(0.03 * duree / 0.5, vy)
            fin = (clamp(math.atan2(y, max(x, 0.03)) / GAIN_LACET_TETE, -YAW_MAX, YAW_MAX),
                   clamp(pitch_pour(math.hypot(x, y)), PITCH_MIN, PITCH_MAX))
            regard = fin
        # temps pour passer de la posture de regard a celle de marche, puis retour
        dpos = max(abs(self.yaw), abs(self.pitch - min(self.pitch, P_MARCHE)))
        prep = 0.0 if dpos < 0.15 else 0.4 + 0.5 * dpos
        retour = 0.3 * max(abs(regard[0]), abs(regard[1] - min(self.pitch, P_MARCHE)))
        now = time.monotonic()
        self.burst = (vx, vy, vyaw, now + prep, now + prep + duree, fin)
        self.t_pret = now + prep + duree + SETTLE_CORPS + retour

    def suivre_du_regard(self, det):
        err_x, err_y = det.cx - CENTRE_X, det.cy - CENTRE_Y
        self.yaw = clamp(self.yaw - GAIN_TETE * err_x / K_YAW, -YAW_MAX, YAW_MAX)
        self.pitch = clamp(self.pitch - GAIN_TETE * err_y / K_PITCH, PITCH_MIN, PITCH_MAX)
        self.t_pret = max(self.t_pret, time.monotonic() + SETTLE_TETE)

    # --- perception -------------------------------------------------------------------
    def estimer(self, det, s):
        """Position (x, y) de la balle dans le repere du tronc, en m (None si inutilisable)."""
        e = geometry.balle_dans_tronc(det, s["frames"]["camera"], s["odom"]["position"][2])
        sol, ray = e["sol"], (None if det.touche_bord else e["rayon"])   # le rayon apparent est faux si le disque est tronque
        if sol is not None and ray is not None:
            p = (0.5 * (sol[0] + ray[0]), 0.5 * (sol[1] + ray[1]))
        else:
            p = sol if sol is not None else ray
            p = None if p is None else (p[0], p[1])
        if p is not None and p[0] < X_MIN_BALLE and abs(p[1]) < Y_MIN_BALLE:
            # Une balle ne peut pas etre SOUS le canard : c'est lui-meme (pieds orange visibles au bord bas de
            # l'image quand la tete est baissee a fond). Sans ce filtre l'asservissement s'y accroche et
            # croit la balle au pied alors qu'elle roule a 1,5 m (diag_beak.py, essai d'evaluation 1).
            return None
        return p

    def enregistrer(self, est, s):
        self.mesure = (est, tuple(s["odom"]["position"][:2]), s["odom"]["yaw"])

    def propager(self, s):
        """Position de la balle dans le repere du tronc ACTUEL, deduite de la derniere mesure et du
        deplacement du canard selon l'odometrie (la balle est supposee immobile)."""
        (bx, by), (ox, oy), oyaw = self.mesure
        px, py = s["odom"]["position"][:2]
        dpsi = s["odom"]["yaw"] - oyaw
        dxw, dyw = px - ox, py - oy
        dx = math.cos(oyaw) * dxw + math.sin(oyaw) * dyw          # deplacement dans l'ancien repere
        dy = -math.sin(oyaw) * dxw + math.cos(oyaw) * dyw
        rx, ry = bx - dx, by - dy
        return math.cos(dpsi) * rx + math.sin(dpsi) * ry, -math.sin(dpsi) * rx + math.cos(dpsi) * ry

    def comparer_verite(self, est):
        if self.verite is None or est is None:
            return ""
        try:
            gt = self.verite.read()
            x, y, _ = self.verite.in_trunk_frame(gt, "testball")
            return f"  [verite ({x:+.3f},{y:+.3f}) ecart {math.hypot(est[0] - x, est[1] - y) * 100:.1f} cm]"
        except Exception:
            return ""

    # --- decision ---------------------------------------------------------------------
    def decider(self, est, vue=True):
        x, y = est
        beta, d = math.atan2(y, x), math.hypot(x, y)
        tag = "" if vue else " (odometrie)"
        # hysteresis : on entre en AJUSTER sous 35 cm, on n'en sort qu'au-dela de 45 cm (balle repoussee)
        if self.etat == "AJUSTER" and d > D_SORTIE_AJUST:
            self.etat = "VISER"
            self.log(f"--> VISER (balle repartie a {d:.2f} m)")
        elif self.etat != "AJUSTER" and d < D_ENTREE_AJUST:
            self.etat = "AJUSTER"
            self.n_ajust = 0
            self.log(f"--> AJUSTER (balle a {d:.2f} m)")
        if self.etat in (None, "CHERCHER"):
            self.etat = "VISER"
            self.log("--> VISER")

        if self.etat == "VISER":
            if abs(beta) > math.radians(20):
                T = clamp(duree_rotation(beta), 0.5, 1.2)
                self.log(f"  balle ({x:+.2f},{y:+.2f}) cap {math.degrees(beta):+.0f} deg, {d:.2f} m : rotation {T:.2f} s{tag}{self.comparer_verite(est)}")
                self.lancer_rafale(0.0, 0.0, math.copysign(V_ROT, beta), T, est)
            else:
                T = clamp(duree_marche(0.85 * (d - 0.28)), 0.4, 1.2)
                self.log(f"  balle ({x:+.2f},{y:+.2f}) cap {math.degrees(beta):+.0f} deg, {d:.2f} m : marche {T:.2f} s{tag}{self.comparer_verite(est)}")
                self.lancer_rafale(V_MARCHE, 0.0, 0.0, T, est)
            return

        # AJUSTER : placer la balle dans la fenetre de tir du pied le plus proche
        if self.cote is None or abs(y) > 0.04:
            self.cote = "left" if y > 0 else "right"
        ty = CIBLE_Y if self.cote == "left" else -CIBLE_Y
        ex, ey = x - CIBLE_X, y - ty
        self.log(f"  [{self.n_ajust}] balle ({x:+.3f},{y:+.3f}) pied {self.cote} erreur ({ex * 100:+.1f},{ey * 100:+.1f}) cm{tag}{self.comparer_verite(est)}")
        e_int = -ey if self.cote == "left" else ey          # > 0 : balle trop pres de l'axe du canard
        if abs(ex) <= TOL_X and -TOL_Y_EXT <= e_int <= TOL_Y_INT:
            self.tirer(est, "dans la fenetre")
            return
        if self.n_ajust >= MAX_AJUSTEMENTS:
            if d < 0.15 and abs(ex) < 0.05 and abs(ey) < 0.05:
                self.tirer(est, "meilleur effort")
            else:                                                # trop de tentatives : on recule et on recommence
                self.log("  trop d'ajustements : on recule et on recommence")
                self.n_ajust = 0
                self.lancer_rafale(-V_MARCHE, 0.0, 0.0, 0.8, est)
            return
        self.n_ajust += 1
        if x < 0.13 and abs(y) > 0.075:                          # balle a COTE du pied : un pas de cote vers elle la pousserait,
            self.log("  balle a cote du pied : on tourne vers elle")   # une rotation la ramene vers l'axe (4 cm pour 25 deg a 10 cm)
            self.lancer_rafale(0.0, 0.0, math.copysign(V_ROT, beta), 0.5, est)
        elif abs(beta) > math.radians(20) and d > 0.15:          # de travers : on se retourne vers la balle
            self.lancer_rafale(0.0, 0.0, math.copysign(V_ROT, beta), clamp(duree_rotation(beta), 0.5, 1.0), est)
        elif ex > TOL_X:                                         # en avance de peu : on stoppe un peu court
            self.lancer_rafale(V_MARCHE, 0.0, 0.0, clamp(duree_marche(0.85 * ex), 0.25, 0.75), est)
        elif ex < -TOL_X:                                        # trop pres : marche arriere (rien en dessous de 0,5 s)
            self.lancer_rafale(-V_MARCHE, 0.0, 0.0, clamp(duree_marche(-ex), 0.5, 0.8), est)
        elif ey > 0:                                             # balle trop a gauche : pas de cote GAUCHE, faible (1 s ~ 5 cm)
            self.lancer_rafale(0.0, V_COTE, 0.0, 1.0, est)
        else:                                                    # balle trop a droite : pas de cote DROIT, fort (0,5 s ~ 5 cm)
            self.lancer_rafale(0.0, -V_COTE, 0.0, 0.5 if ey > -0.06 else 1.0, est)

    def tirer(self, est, motif):
        """Decision de tir. Le coup n'est lance qu'apres avoir ramene la tete au NEUTRE : tete baissee
        de seulement 0,5 rad le pied ne touche plus la balle (kick_sweep.py : 0 m/s au lieu de 1,2)."""
        self.log(f"=== TIR kick_{self.cote} ({motif}) ; balle estimee ({est[0]:+.3f},{est[1]:+.3f}){self.comparer_verite(est)}")
        self.resultat["tir"] = {"cote": self.cote, "est": est, "motif": motif, "n_ajust": self.n_ajust}
        self.burst = None
        self.yaw = self.pitch = 0.0
        self.t_tir = time.monotonic() + T_TETE_NEUTRE
        self.etat = "TIR"

    def declencher_tir(self):
        if self.avant_tir:                       # mesure externe (evaluation), jamais utilisee pour decider
            self.resultat["avant_tir"] = self.avant_tir()
        r = self.c.request("robot.do", {"skill": f"kick_{self.cote}"})
        self.log(f"robot.do kick_{self.cote} -> {r.get('result', r.get('error'))}")
        self.etat = "FINI"

    # --- boucle principale --------------------------------------------------------------
    def run(self, duree_max=90.0):
        t0 = time.monotonic()
        self.pas()
        while time.monotonic() - t0 < duree_max and self.etat != "FINI":
            s = self.pas()
            if self.etat == "TIR":                    # tete au neutre pendant T_TETE_NEUTRE, puis coup
                if time.monotonic() >= self.t_tir:
                    self.declencher_tir()
                continue
            if self.burst:
                continue
            r = self.vis.get_apres(self.t_pret)
            if r is None or r[0] <= self.t_traite:
                continue
            self.t_traite = r[0]
            det = r[1]
            est = self.estimer(det, s) if det is not None else None
            if est is None:
                self.balle_perdue(s)
                continue
            self.manques = self.n_propag = 0
            self.suivre_du_regard(det)
            if det.touche_bord and det.cy < 0.5 * vision.HEIGHT:
                # disque coupe par le haut ou le cote : le centre mesure est faux (erreurs de 6 a 14 cm) et
                # y croire entretiendrait l'erreur ; on recentre la tete et on regarde a nouveau
                self.log("  balle coupee par le bord de l'image : on recentre la tete")
                continue
            self.sens_recherche = +1.0 if est[1] >= 0 else -1.0
            self.enregistrer(est, s)
            self.decider(est)
        if self.etat != "FINI":
            self.log("=== temps ecoule sans tir")
        self.resultat["etat"] = self.etat
        self.resultat["duree"] = time.monotonic() - t0
        return self.resultat

    def balle_perdue(self, s):
        """Pas de detection exploitable apres stabilisation. Tout pres du pied, la balle est sortie du
        champ : on la suit a l'odometrie. Sinon (ou si ca dure) on la cherche en tournant."""
        if self.etat == "AJUSTER" and self.mesure and self.n_propag < MAX_PROPAGATIONS:
            self.n_propag += 1
            est = self.propager(s)
            self.enregistrer(est, s)
            self.decider(est, vue=False)
            return
        self.manques += 1
        if self.manques < 2:
            return
        if self.etat != "CHERCHER":
            self.log("--> CHERCHER (balle non vue)")
        self.etat = "CHERCHER"
        self.cote = None
        self.mesure = None
        self.yaw *= 0.5
        self.pitch *= 0.5
        self.manques = 0
        self.lancer_rafale(0.0, 0.0, self.sens_recherche * V_ROT, 0.6)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    couleur = args[0] if args else "orange"
    duree = float(args[1]) if len(args) > 1 else 90.0
    c = RobotdClient(SOCK_PATH)
    c.request("robot.subscribe", {})
    ap = Approche(c, couleur, verite="--verite" in sys.argv)
    res = ap.run(duree)
    print("resultat :", res, flush=True)
    ap.vis.run_flag = False
    ap.burst = None
    for _ in range(25):
        ap.pas()


if __name__ == "__main__":
    main()
