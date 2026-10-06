#!/usr/bin/env python3
"""Detection de mouvement par difference d'images (ROADMAP Phase 3 : "priorite a tout ce qui se fait sans deep
learning ... detection de mouvement par difference d'images"). Sert au jeu "1-2-3 soleil" (brain.py, etat `soleil`) :
le canard se retourne et "voit" qui bouge encore.

Ne marche QUE si la camera est immobile (le canard ne bouge ni le corps ni la tete) : c'est l'appelant qui arme le
detecteur une fois le canard stabilise, et le desarme des qu'il bouge. Image reduite (90x160), floutee, difference
avec l'image precedente, seuil, ouverture morphologique (le bruit du capteur fait des points isoles, une personne qui
bouge fait une tache) : la fraction de pixels qui ont change dit s'il y a du mouvement. Leger : quelques ms par image
sur la carte du canard (RK3566) a 5 images/s (et seulement pendant le jeu).

`DetecteurMouvement` est la logique pure (tests sur images synthetiques) ; `VeilleMouvement` le fil qui lui donne les
images de la camera quand il est arme.
"""
import collections
import threading
import time

import cv2
import numpy as np

TAILLE = (90, 160)             # (largeur, hauteur) de l'image analysee (portrait 360x640 divise par 4)
SEUIL_PIXEL = 25               # niveau de gris : en dessous, bruit / variation de lumiere
FRACTION_MOUVEMENT = 0.004     # 0,4 % de l'image (~58 pixels reduits) : un bras qui bouge a 2-3 m
SEUIL_RYTHME = 0.4             # autocorrelation au battement : au-dessus, le mouvement suit la musique
RYTHME_MIN_S = 3.0             # duree d'observation minimale pour juger un rythme


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


def rythme_correspond(echantillons, bpm, pas_s=0.05):
    """ROADMAP "rythme visible" : quelqu'un bouge-t-il EN RYTHME avec la musique entendue (audio.py, `musique:<bpm>`) ?
    `echantillons` : [(t, fraction de l'image qui a change)] pris camera immobile (VeilleMouvement.historique).

    La difference d'images mesure la VITESSE du mouvement, sans son signe : un hochement par battement comme un
    balancement sur deux battements donnent un signal qui se repete a chaque battement. On reechantillonne donc le
    signal sur une grille reguliere et on mesure son autocorrelation normalisee a un decalage d'UN battement : proche
    de 1 si le mouvement suit le tempo, faible pour un mouvement au hasard ou a un autre tempo. Il faut aussi que
    quelqu'un bouge vraiment (fraction moyenne au-dessus du seuil de mouvement)."""
    if not bpm or len(echantillons) < 8:
        return False
    t = np.array([e[0] for e in echantillons], dtype=float)
    f = np.array([e[1] for e in echantillons], dtype=float)
    periode = 60.0 / bpm
    if t[-1] - t[0] < max(RYTHME_MIN_S, 2.5 * periode) or f.mean() < FRACTION_MOUVEMENT:
        return False
    grille = np.arange(t[0], t[-1] - periode, pas_s)
    x = np.interp(grille, t, f)
    y = np.interp(grille + periode, t, f)
    x, y = x - x.mean(), y - y.mean()
    norme = np.sqrt((x * x).sum() * (y * y).sum())
    return bool(norme > 0 and (x * y).sum() / norme >= SEUIL_RYTHME)


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
        self.historique = collections.deque(maxlen=200)   # (instant, fraction) depuis l'armement : rythme visible
        self.dernier_centre = None             # (instant, x, fraction) du dernier mouvement : mouvement peripherique
        self._periode_normale = periode_s

    def armer(self, periode_s=None):
        """`periode_s` : cadence plus rapide le temps d'un armement (rythme visible : 10 images/s pour suivre un
        battement ; 5 images/s suffisent a 1-2-3 soleil)."""
        with self.verrou:
            self.detecteur.reinitialiser()
            self.dernier_mouvement = None
            self.dernier_centre = None
            self.historique.clear()
            self.periode_s = periode_s or self._periode_normale
            self.arme = True

    def desarmer(self):
        with self.verrou:
            self.arme = False
            self.periode_s = self._periode_normale

    def run(self):
        while self.actif:
            t0 = time.monotonic()
            if self.arme:
                try:
                    image = self.grab()
                    with self.verrou:
                        if self.arme:
                            bouge, fraction, centre = self.detecteur.mise_a_jour(image)
                            self.historique.append((time.monotonic(), fraction))
                            if bouge:
                                self.dernier_centre = (time.monotonic(), centre[0], fraction)
                                self.dernier_mouvement = time.monotonic()
                except Exception:
                    pass                       # une image ratee ne doit pas arreter la veille
            time.sleep(max(0.0, self.periode_s - (time.monotonic() - t0)))

    def a_bouge(self):
        """Vrai si un mouvement a ete vu depuis le dernier armement."""
        return self.dernier_mouvement is not None

    def en_rythme(self, bpm):
        """Quelqu'un bouge-t-il en rythme depuis l'armement (rythme_correspond) ?"""
        with self.verrou:
            echantillons = list(self.historique)
        return rythme_correspond(echantillons, bpm)
