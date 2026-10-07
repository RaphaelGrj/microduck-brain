#!/usr/bin/env python3
"""Veille de la balle (ou de tout petit objet rond de couleur) pour le cerveau : ou est-elle, au sol, dans le repere du
tronc ? Sert aux taquineries du lot B (pousser la balle hors de portee, mime de vol) - le jeu de balle complet reste
dans approach.py, qui utilise la meme estimation (`estimer`).

`estimer` est la logique pure (detection HSV de vision.py + geometrie de la camera) ; `VeilleBalle` le fil qui lui donne
des images a basse cadence (2 par seconde par defaut : leger pour la carte du canard (RK3566)).
"""
import threading
import time

import geometry

X_MIN_BALLE, Y_MIN_BALLE = 0.05, 0.09    # zone occupee par le canard : aucune balle reelle ne peut y etre


HAUTEUR_LEVEE = 0.15            # balle a plus de 15 cm du sol : quelqu'un la tient (va-t-on la lancer ?)


def hauteur(det, s):
    """Hauteur du centre de la balle au-dessus du sol (m), par sa profondeur (rayon apparent) ; None si inutilisable."""
    if det.touche_bord:
        return None
    e = geometry.balle_dans_tronc(det, s["frames"]["camera"], s["odom"]["position"][2])
    return None if e["rayon"] is None else e["rayon"][2] + s["odom"]["position"][2]


def estimer(det, s):
    """Position (x, y) de la balle dans le repere du tronc, en m (None si inutilisable). Moyenne du point au sol et de
    la profondeur par le rayon apparent (0,5-2 cm d'erreur de 11 cm a 1 m, vis_range.py) ; rayon ignore si le disque
    est coupe par le bord de l'image."""
    e = geometry.balle_dans_tronc(det, s["frames"]["camera"], s["odom"]["position"][2])
    sol, ray = e["sol"], (None if det.touche_bord else e["rayon"])
    if sol is not None and ray is not None:
        p = (0.5 * (sol[0] + ray[0]), 0.5 * (sol[1] + ray[1]))
    else:
        p = sol if sol is not None else ray
        p = None if p is None else (p[0], p[1])
    if p is not None and p[0] < X_MIN_BALLE and abs(p[1]) < Y_MIN_BALLE:
        # Une balle ne peut pas etre SOUS le canard : c'est lui-meme (pieds orange visibles au bord bas de l'image quand
        # la tete est baissee a fond, diag_beak.py).
        return None
    return p


class VeilleBalle(threading.Thread):
    def __init__(self, grab_frame, couleur="orange", periode_s=0.5):
        super().__init__(daemon=True)
        self.grab, self.couleur, self.periode_s = grab_frame, couleur, periode_s
        self.actif = True
        self.etat_robot = None
        self.estimation = None                   # (instant monotonic, x, y) repere du tronc
        self.pause = False                       # carte trop chaude (Brain._verifie_sante) : on n'analyse plus
        self.t_levee = None                      # derniere fois qu'on l'a vue tenue en l'air (excitation : vivant)

    def etat_robot_hook(self, brain, state):
        self.etat_robot = state

    def run(self):
        import vision
        while self.actif:
            t0 = time.monotonic()
            try:
                etat = self.etat_robot
                if not self.pause and etat is not None and (etat.get("frames") or {}).get("camera"):
                    dets = vision.detect(self.grab(), couleurs=(self.couleur,))
                    p = estimer(dets[0], etat) if dets else None
                    if p is not None:
                        self.estimation = (time.monotonic(), float(p[0]), float(p[1]))
                    hz = hauteur(dets[0], etat) if dets else None
                    if hz is not None and hz >= HAUTEUR_LEVEE:
                        self.t_levee = time.monotonic()
            except Exception:
                pass
            time.sleep(max(0.0, self.periode_s - (time.monotonic() - t0)))

    def levee(self, age_max=1.0):
        """True si quelqu'un tient la balle en l'air (vue a l'instant)."""
        return self.t_levee is not None and time.monotonic() - self.t_levee <= age_max

    def position(self, age_max=1.5):
        """(x, y) si la balle a ete vue recemment, sinon None."""
        e = self.estimation
        if e is None or time.monotonic() - e[0] > age_max:
            return None
        return e[1], e[2]
