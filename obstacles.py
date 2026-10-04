#!/usr/bin/env python3
"""Obstacles statiques d'une scene MuJoCo, vus de dessus (outil du BANC D'ESSAI, pas du cerveau).

Sert a poser la balle a un endroit valide pendant une evaluation : pas dans un mur ou un meuble, et avec une ligne
droite libre entre le canard et la balle (sinon l'essai mesure le placement, pas le controleur). Lit les geoms de
premier niveau du `worldbody` (murs, meubles) : boites, cylindres, spheres... ramenes a leur rectangle englobant au sol,
en ignorant ceux qui ne touchent pas la tranche 0-15 cm (sols, plateaux de table, tapis sans collision).

Usage : python obstacles.py [scene.xml]   (affiche le nombre d'obstacles et teste quelques points)
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MODELE = Path.home() / "microduck_rl/src/mjlab_microduck/robot/microduck"
TRANCHE = (0.005, 0.15)          # hauteur ou un obstacle gene une balle de 7 cm ou la camera du canard (~12 cm)


def charger(scene=MODELE / "apartment.xml"):
    """Liste de (nom, xmin, xmax, ymin, ymax)."""
    racine = ET.parse(scene).getroot()
    rects = []
    for g in racine.find("worldbody").findall("geom"):
        if g.get("contype", "1") == "0" and g.get("conaffinity", "1") == "0":
            continue                                   # visuel seulement (tapis, sols decoratifs)
        typ = g.get("type", "sphere")
        if typ == "plane":
            continue
        size = [float(v) for v in g.get("size", "0").split()]
        pos = [float(v) for v in g.get("pos", "0 0 0").split()]
        if typ == "box":
            hx, hy, hz = size[0], size[1], size[2]
        elif typ in ("cylinder", "capsule"):
            hx = hy = size[0]
            hz = size[1] + (size[0] if typ == "capsule" else 0.0)
        elif typ == "ellipsoid":
            hx, hy, hz = size
        else:                                          # sphere
            hx = hy = hz = size[0]
        bas, haut = pos[2] - hz, pos[2] + hz
        if haut < TRANCHE[0] or bas > TRANCHE[1]:
            continue                                   # sous le sol ou au-dessus de la tranche utile
        rects.append((g.get("name", typ), pos[0] - hx, pos[0] + hx, pos[1] - hy, pos[1] + hy))
    return rects


def dedans(p, rects, marge=0.06):
    return next((r[0] for r in rects
                 if r[1] - marge <= p[0] <= r[2] + marge and r[3] - marge <= p[1] <= r[4] + marge), None)


def _coupe(a, b, r, marge):
    """Le segment a-b traverse-t-il le rectangle r elargi de `marge` ? (Liang-Barsky)"""
    xmin, xmax, ymin, ymax = r[1] - marge, r[2] + marge, r[3] - marge, r[4] + marge
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - xmin), (dx, xmax - a[0]), (-dy, a[1] - ymin), (dy, ymax - a[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def ligne_libre(a, b, rects, marge=0.06):
    """Nom du premier obstacle entre a et b, ou None si la ligne est libre."""
    return next((r[0] for r in rects if _coupe(a, b, r, marge)), None)


def main():
    scene = Path(sys.argv[1]) if len(sys.argv) > 1 else MODELE / "apartment.xml"
    rects = charger(scene)
    print(f"{len(rects)} obstacles au sol dans {scene.name}")
    for p in ((-2.5, 1.8), (-2.5, -1.0), (0.0, 0.0), (-4.0, 0.0), (-3.5, 0.5)):
        print(f"  point {p} : {dedans(p, rects) or 'libre'}")
    print("  ligne (-2.5,1.8)->(-2.5,-1.0) :", ligne_libre((-2.5, 1.8), (-2.5, -1.0), rects) or "libre")


if __name__ == "__main__":
    main()
