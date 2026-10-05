#!/usr/bin/env python3
"""Detection de mouvement par difference d'images (ROADMAP Phase 3 : "priorite a tout ce qui se fait sans deep
learning ... detection de mouvement par difference d'images"). Sert au jeu "1-2-3 soleil" (brain.py, etat `soleil`) :
le canard se retourne et "voit" qui bouge encore.

Ne marche QUE si la camera est immobile (le canard ne bouge ni le corps ni la tete) : c'est l'appelant qui arme le
detecteur une fois le canard stabilise, et le desarme des qu'il bouge. Image reduite (90x160), floutee, difference
avec l'image precedente, seuil, ouverture morphologique (le bruit du capteur fait des points isoles, une personne qui
bouge fait une tache) : la fraction de pixels qui ont change dit s'il y a du mouvement. Leger : quelques ms par image
sur un Raspberry Pi 3B+ a 5 images/s (et seulement pendant le jeu).

`DetecteurMouvement` est la logique pure (tests sur images synthetiques) ; `VeilleMouvement` le fil qui lui donne les
images de la camera quand il est arme.
"""
import threading
import time

import cv2
import numpy as np

TAILLE = (90, 160)             # (largeur, hauteur) de l'image analysee (portrait 360x640 divise par 4)
SEUIL_PIXEL = 25               # niveau de gris : en dessous, bruit / variation de lumiere
FRACTION_MOUVEMENT = 0.004     # 0,4 % de l'image (~58 pixels reduits) : un bras qui bouge a 2-3 m


class DetecteurMouvement:
    def __init__(self, seuil_pixel=SEUIL_PIXEL, fraction=FRACTION_MOUVEMENT):
        self.seuil_pixel, self.fraction = seuil_pixel, fraction
        self.noyau = np.ones((3, 3), np.uint8)
        self.precedente = None

    def reinitialiser(self):
        self.precedente = None

    def _prepare(self, image):
        gris = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(cv2.resize(gris, TAILLE, interpolation=cv2.INTER_AREA), (5, 5), 0)

    def mise_a_jour(self, image):
        """-> (bouge: bool, fraction de l'image qui a change, centre (x, y) en fraction de l'image ou None).
        La premiere image apres reinitialiser() sert de reference : (False, 0.0, None)."""
        img = self._prepare(image)
        prec, self.precedente = self.precedente, img
        if prec is None:
            return False, 0.0, None
        masque = (cv2.absdiff(img, prec) > self.seuil_pixel).astype(np.uint8)
        masque = cv2.morphologyEx(masque, cv2.MORPH_OPEN, self.noyau)
        n = int(masque.sum())
        fraction = n / masque.size
        if n == 0:
            return False, 0.0, None
        ys, xs = np.nonzero(masque)
        return fraction >= self.fraction, fraction, (float(xs.mean()) / TAILLE[0], float(ys.mean()) / TAILLE[1])


class VeilleMouvement(threading.Thread):
    """Fil qui analyse la camera SEULEMENT quand il est arme (le reste du temps, il ne consomme rien)."""

    def __init__(self, grab_frame, periode_s=0.2, **detecteur):
        super().__init__(daemon=True)
        self.grab, self.periode_s = grab_frame, periode_s
        self.detecteur = DetecteurMouvement(**detecteur)
        self.verrou = threading.Lock()
        self.arme = False
        self.actif = True
        self.dernier_mouvement = None          # instant (monotonic) du dernier mouvement vu depuis l'armement

    def armer(self):
        with self.verrou:
            self.detecteur.reinitialiser()
            self.dernier_mouvement = None
            self.arme = True

    def desarmer(self):
        with self.verrou:
            self.arme = False

    def run(self):
        while self.actif:
            t0 = time.monotonic()
            if self.arme:
                try:
                    image = self.grab()
                    with self.verrou:
                        if self.arme:
                            bouge, _, _ = self.detecteur.mise_a_jour(image)
                            if bouge:
                                self.dernier_mouvement = time.monotonic()
                except Exception:
                    pass                       # une image ratee ne doit pas arreter la veille
            time.sleep(max(0.0, self.periode_s - (time.monotonic() - t0)))

    def a_bouge(self):
        """Vrai si un mouvement a ete vu depuis le dernier armement."""
        return self.dernier_mouvement is not None
