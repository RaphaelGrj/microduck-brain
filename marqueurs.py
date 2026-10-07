#!/usr/bin/env python3
"""Marqueurs imprimes (AprilTag 36h11) colles en bas des murs : quand la camera en voit un, le canard sait EXACTEMENT
ou il est sur le plan. C'est ce qui corrige la derive et le retrouve apres qu'on l'a porte ailleurs (le capteur de
distance seul ne suffit pas : plusieurs endroits d'une maison se ressemblent dans un champ de 45 degres).

- Ou les coller : au bas d'un mur, centre a ~10-12 cm du sol (la camera du canard est basse), bien a plat, un par
  piece au moins, la ou il passe souvent. Leur position est relevee avec la manette du Quest pendant le scan (quest/).
- Taille : TAILLE_M de cote pour le carre noir (pas la marge blanche). `python3 marqueurs.py imprimer` ecrit une page
  A4 a imprimer « taille reelle ».

Tout est analyse sur le canard (image de sa camera locale, comme la balle) ; rien ne sort.
"""
import math
import sys

import cv2
import numpy as np

import geometry
import vision

TAILLE_M = 0.10
DICO = cv2.aruco.DICT_APRILTAG_36h11
DISTANCE_MAX = 2.5               # au-dela, la pose d'un marqueur de 10 cm est trop imprecise


def detecteur():
    d = cv2.aruco.getPredefinedDictionary(DICO)
    return cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())


def detecter(img, cam, focale=vision.FOCAL_PX, taille=TAILLE_M, det=None):
    """Marqueurs vus dans l'image. `cam` : pose de la camera dans le repere du tronc (robot.state.frames.camera :
    {"pos": [x, y, z], "quat": [w, x, y, z]}, convention camera x droite / y bas / z devant).
    -> [(id, x, y, cap_normale)] dans le repere du tronc : centre du marqueur et direction de sa face (vers la piece)."""
    gris = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    coins, ids, _ = (det or detecteur()).detectMarkers(gris)
    if ids is None:
        return []
    h, l = gris.shape[:2]
    k = np.array([[focale, 0, l / 2.0], [0, focale, h / 2.0], [0, 0, 1]], dtype=np.float64)
    s = taille / 2.0
    objet = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], dtype=np.float64)
    r_tc = np.array(geometry.quat_vers_matrice(cam["quat"]), dtype=np.float64)
    p_c = np.array(cam["pos"], dtype=np.float64)
    out = []
    for c, i in zip(coins, ids.ravel()):
        ok, rvec, tvec = cv2.solvePnP(objet, c.reshape(4, 2).astype(np.float64), k, None,
                                      flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if not ok or float(np.linalg.norm(tvec)) > DISTANCE_MAX:
            continue
        r_cam, _ = cv2.Rodrigues(rvec)
        centre = p_c + r_tc @ tvec.ravel()
        normale = r_tc @ (r_cam @ np.array([0.0, 0.0, 1.0]))      # face du marqueur, vers celui qui le regarde
        out.append((int(i), float(centre[0]), float(centre[1]), math.atan2(normale[1], normale[0])))
    return out


def pose_du_canard(vu, sur_le_plan):
    """`vu` : (x, y, cap_normale) du marqueur dans le repere du tronc ; `sur_le_plan` : (X, Y, cap_normale) du meme
    marqueur sur le plan. -> (x, y, cap) du canard sur le plan."""
    x, y, cn = vu
    X, Y, CN = sur_le_plan
    cap = (CN - cn + math.pi) % (2 * math.pi) - math.pi
    c, s = math.cos(cap), math.sin(cap)
    return X - (c * x - s * y), Y - (s * x + c * y), cap


def page_a_imprimer(chemin="marqueurs_a_imprimer.png", ids=range(6), dpi=300):
    """Une page A4 (300 dpi) avec des marqueurs de TAILLE_M de cote et leur numero. Imprimer « taille reelle »."""
    mm = dpi / 25.4
    page = np.full((int(297 * mm), int(210 * mm)), 255, np.uint8)
    d = cv2.aruco.getPredefinedDictionary(DICO)
    cote = int(round(TAILLE_M * 1000 * mm))
    marge = int(15 * mm)
    for n, i in enumerate(ids):
        lig, col = divmod(n, 2)
        y0, x0 = marge + lig * (cote + int(25 * mm)), marge + col * (cote + int(30 * mm))
        if y0 + cote > page.shape[0] or x0 + cote > page.shape[1]:
            break
        page[y0:y0 + cote, x0:x0 + cote] = cv2.aruco.generateImageMarker(d, int(i), cote)
        cv2.putText(page, f"n {i}  ({int(TAILLE_M * 100)} cm)", (x0, y0 + cote + int(8 * mm)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.6, 0, 3)
    cv2.imwrite(chemin, page)
    return chemin


if __name__ == "__main__":
    if sys.argv[1:2] == ["imprimer"]:
        print(page_a_imprimer(*(sys.argv[2:3] or [])))
    else:
        print(__doc__)
