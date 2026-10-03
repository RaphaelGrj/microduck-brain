#!/usr/bin/env python3
"""Geometrie camera : de la detection d'une balle (pixels) a sa position dans le repere du tronc.

La pose de la camera dans le repere du tronc (position + quaternion w,x,y,z) est fournie par
robotd dans `robot.state.frames.camera` : elle tient compte de la tete ACTUELLE. Convention
camera : x droite de l'image, y bas de l'image, z devant (axe optique) ; repere tronc : x avant,
y gauche, z haut.

Deux estimations de la position de la balle :
  - par le RAYON apparent : profondeur Z = f * R / r (la balle fait R = 3,5 cm), independante de
    l'inclinaison du tronc ; bruitee quand la balle est loin (r petit) ;
  - par le SOL : intersection du rayon avec le plan z = rayon de la balle ; depend de la hauteur
    du tronc et est tres sensible quand la balle est loin (rayon rasant).
"""
import math

import vision

RAYON_BALLE = 0.035


def quat_vers_matrice(q):
    w, x, y, z = q
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def _mat_vec(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


def rayon_pixel(cx, cy, focale=vision.FOCAL_PX):
    """Direction (non normalisee, z=1) dans le repere camera du pixel (cx, cy)."""
    return ((cx - vision.WIDTH / 2) / focale, (cy - vision.HEIGHT / 2) / focale, 1.0)


def balle_dans_tronc(det, cam, hauteur_tronc, focale=vision.FOCAL_PX):
    """Renvoie {"rayon": (x,y,z) | None, "sol": (x,y,z) | None} en m, repere du tronc.

    det : Detection (cx, cy, rayon en px) ; cam : state["frames"]["camera"] ;
    hauteur_tronc : altitude du tronc au-dessus du sol (state["odom"]["position"][2]).
    """
    r_mat = quat_vers_matrice(cam["quat"])
    p_cam = cam["pos"]
    d = rayon_pixel(det.cx, det.cy, focale)
    d_tronc = _mat_vec(r_mat, d)
    out = {"rayon": None, "sol": None}
    if det.rayon > 1.0:
        zc = focale * RAYON_BALLE / det.rayon
        out["rayon"] = tuple(p_cam[i] + zc * d_tronc[i] for i in range(3))
    z_cible = RAYON_BALLE - hauteur_tronc          # centre de la balle, dans le repere du tronc
    if d_tronc[2] < -1e-3:
        t = (z_cible - p_cam[2]) / d_tronc[2]
        if t > 0:
            out["sol"] = tuple(p_cam[i] + t * d_tronc[i] for i in range(3))
    return out


def point_au_sol(px, py, cam, hauteur_tronc, focale=vision.FOCAL_PX):
    """Position (x, y) dans le repere du tronc du point du SOL vu au pixel (px, py), ou None si le rayon ne
    descend pas. Sert aux objets qui touchent le sol par le bas de leur boite (chat, personne) : on prend
    le milieu du bord bas de la boite englobante comme point de contact (approximation de quelques cm)."""
    r_mat = quat_vers_matrice(cam["quat"])
    d = _mat_vec(r_mat, rayon_pixel(px, py, focale))
    if d[2] >= -1e-3:
        return None
    t = (-hauteur_tronc - cam["pos"][2]) / d[2]
    if t <= 0:
        return None
    return cam["pos"][0] + t * d[0], cam["pos"][1] + t * d[1]


def cap_et_distance(p):
    """(relevement en rad, positif a gauche ; distance au sol en m) d'un point du repere du tronc."""
    return math.atan2(p[1], p[0]), math.hypot(p[0], p[1])
