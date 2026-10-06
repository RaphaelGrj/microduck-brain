#!/usr/bin/env python3
"""Perception classique (sans entrainement) sur le flux camera du canard.

- grab_frame()      : image BGR via la route /frame de mediad (PNG a la demande).
- detect()          : blobs de couleur "ronds" (balle, cible) par seuillage HSV.
- pixel_to_angles() : pixel -> (yaw, pitch) relatif a l'axe optique, pour le suivi du regard.

Geometrie (simulateur) : MuJoCo rend 640x360 avec fovy=45 deg (defaut) ; mediad fait pivoter
d'un quart de tour -> image portrait 360x640. Horizontalement on a donc le champ etroit
(45 deg sur 360 px), verticalement le large (72 deg sur 640 px). Focale ~ 434.6 px.

Usage : uv run python vision.py [chemin_sortie.png]   -> detecte et sauvegarde l'image annotee
"""
import math
import os
import sys
import urllib.request
from dataclasses import dataclass

import cv2
import numpy as np

FRAME_URL = os.environ.get("MICRODUCK_FRAME_URL", "http://127.0.0.1:8080/frame")
WIDTH, HEIGHT = 360, 640
FOVY_DEG = 45.0  # champ vertical du rendu avant rotation = champ HORIZONTAL de l'image portrait
FOCAL_PX = (WIDTH / 2) / math.tan(math.radians(FOVY_DEG / 2))  # ~434.6 px


@dataclass(frozen=True)
class Couleur:
    nom: str
    h: tuple  # (h_min, h_max) en echelle OpenCV 0..179
    s_min: int
    v_min: int


# Couleurs de l'appartement simulé. Le sol est saumon (S~130) et le bois brun (V~140) :
# on exige donc une forte saturation ET luminosite pour l'orange.
COULEURS = {
    # V min bas : la face ombree d'une balle orange tombe vers V~100 ; le sol/bois restent exclus par S>=190.
    "orange": Couleur("orange", (8, 22), 190, 90),
    "vert": Couleur("vert", (50, 75), 130, 90),
    "rose": Couleur("rose", (150, 172), 120, 110),
    "cyan": Couleur("cyan", (80, 100), 150, 110),
    "rouge": Couleur("rouge", (0, 6), 170, 110),
    "jaune": Couleur("jaune", (24, 34), 150, 150),
    "bleu": Couleur("bleu", (105, 125), 170, 110),
}


@dataclass
class Detection:
    couleur: str
    cx: float
    cy: float
    rayon: float
    aire: float
    rondeur: float  # aire / (pi r^2) du cercle englobant, 1.0 = disque parfait
    touche_bord: bool = False  # coupe par le bord de l'image : centre/rayon sont approximatifs


def luminosite(img) -> float:
    """Luminosite moyenne de l'image, 0 (noir) a 1 (blanc) : lumiere allumee ou eteinte dans la piece."""
    gris = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(gris.mean()) / 255.0


def grab_frame(url: str = FRAME_URL, timeout: float = 5.0) -> np.ndarray:
    # Regle du projet : la camera du canard est lue et analysee SUR le canard - jamais une camera distante.
    from urllib.parse import urlparse
    if urlparse(url).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError(f"camera distante refusee ({url}) : tout est analyse sur le canard")
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = np.frombuffer(r.read(), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("image illisible depuis /frame")
    return img


def detect(img: np.ndarray, couleurs=None, aire_min: float = 60.0, rondeur_min: float = 0.55,
           rondeur_min_bord: float = 0.0):
    """Renvoie les blobs ronds de chaque couleur demandee, du plus gros au plus petit."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    noyau = np.ones((3, 3), np.uint8)
    out = []
    for nom in couleurs or COULEURS:
        c = COULEURS[nom]
        masque = cv2.inRange(hsv, (c.h[0], c.s_min, c.v_min), (c.h[1], 255, 255))
        masque = cv2.morphologyEx(masque, cv2.MORPH_OPEN, noyau)
        masque = cv2.morphologyEx(masque, cv2.MORPH_CLOSE, noyau)
        contours, _ = cv2.findContours(masque, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            aire = cv2.contourArea(cnt)
            if aire < aire_min:
                continue
            (x, y), r = cv2.minEnclosingCircle(cnt)
            rondeur = aire / (math.pi * r * r) if r > 0 else 0.0
            bx, by, bw, bh = cv2.boundingRect(cnt)
            touche_bord = bx <= 1 or by <= 1 or bx + bw >= img.shape[1] - 1 or by + bh >= img.shape[0] - 1
            # Un objet coupe par le bord de l'image n'est pas un disque entier : seuil de rondeur
            # separe (0 par defaut = pas de filtre). On ne peut pas le relever : la balle tronquee au
            # pied (rondeur 0,28-0,39) et les pieds orange du canard, visibles au bord bas de l'image
            # tete baissee a fond (0,22-0,35, diag_beak.py), ne se distinguent pas par la rondeur.
            # C'est le controleur qui rejette ce faux positif (zone occupee par le canard).
            if rondeur < (rondeur_min_bord if touche_bord else rondeur_min):
                continue
            out.append(Detection(nom, x, y, r, aire, rondeur, touche_bord))
    return sorted(out, key=lambda d: -d.aire)


def pixel_to_angles(cx: float, cy: float):
    """Pixel -> (yaw, pitch) en rad relatifs a l'axe optique.

    yaw > 0 : l'objet est a DROITE de l'image ; pitch > 0 : l'objet est EN BAS.
    (Convention image ; le signe vers les commandes robot est a calibrer par l'appelant.)
    """
    yaw = math.atan2(cx - WIDTH / 2, FOCAL_PX)
    pitch = math.atan2(cy - HEIGHT / 2, FOCAL_PX)
    return yaw, pitch


def annotate(img: np.ndarray, dets) -> np.ndarray:
    out = img.copy()
    for d in dets:
        cv2.circle(out, (int(d.cx), int(d.cy)), int(d.rayon) + 3, (255, 255, 255), 2)
        cv2.putText(out, f"{d.couleur} r={d.rayon:.0f}", (int(d.cx) + 6, int(d.cy) - int(d.rayon) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    return out


def main():
    sortie = sys.argv[1] if len(sys.argv) > 1 else "vision_out.png"
    img = grab_frame()
    dets = detect(img)
    print(f"image {img.shape[1]}x{img.shape[0]}, {len(dets)} detection(s)")
    for d in dets:
        yaw, pitch = pixel_to_angles(d.cx, d.cy)
        print(f"  {d.couleur:7s} centre=({d.cx:.0f},{d.cy:.0f}) rayon={d.rayon:.0f}px aire={d.aire:.0f} "
              f"rondeur={d.rondeur:.2f}  -> yaw={math.degrees(yaw):+.1f} deg pitch={math.degrees(pitch):+.1f} deg")
    cv2.imwrite(sortie, annotate(img, dets))
    print("sauvegarde:", sortie)


if __name__ == "__main__":
    main()
