#!/usr/bin/env python3
"""Le plan de la maison (scan Quest) -> une scene MuJoCo pour duck-sim : le canard simule vit dans TA maison.

Murs et meubles deviennent des boites (fusion des cases du plan en rectangles) : son capteur de distance simule les
voit comme le vrai verrait les vrais, et sa localisation, ses trajets, ses zones interdites s'essaient sur la vraie
disposition. Le repere de la scene EST celui du plan : origine au chargeur, x = devant. Le canard y nait, face a x ;
la balle d'entrainement (BallKick) est posee devant lui, la ou c'est libre.

C'est la base du « canard jumeau » (Quest, mode Jumeau) : le canard simule est dessine dans ta piece, a sa place.

    bash ~/run-brain.sh plan_vers_mjcf.py                 # plan du lieu actuel -> scene_maison.xml du fork
    bash ~/run-brain.sh plan_vers_mjcf.py plan.json [sortie.xml]
    bash ~/run-scene.sh maison                            # (fait les deux : genere puis lance duck-sim dessus)

La scene est ecrite a cote des modeles du fork (ses <include> sont relatifs) et n'est pas versionnee.
"""
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np

import plan as P

ROBOT = Path(os.environ.get("MICRODUCK_RL", Path.home() / "microduck_rl")).expanduser() / "src/mjlab_microduck/robot/microduck"
SORTIE = ROBOT / "scene_maison.xml"
MODELE_KEYFRAMES = "scene_arena_testball.xml"   # memes poses (INIT, STAND, SIT, FOLD) que les autres scenes du fork
HAUT_MEUBLE = 0.35
HAUT_MUR = 0.9
BANDE_MUR = 0.3                 # du « dehors » du plan, seule la bande contre la maison devient mur
DEGAGE_NAISSANCE = 0.14         # rien d'encombrant la ou le canard nait (le chargeur est souvent contre un mur)


def rectangles(masque):
    """Masque booleen (lignes, colonnes) -> rectangles (i0, j0, i1, j1) (bornes exclusives) qui le couvrent : segments
    par ligne, fusionnes avec la ligne precedente quand ils ont les memes bornes."""
    ouverts, finis = {}, []
    for i in range(masque.shape[0]):
        ligne = np.concatenate([[False], masque[i], [False]])
        d = np.flatnonzero(np.diff(ligne.astype(np.int8)))
        segs = set(zip(d[::2].tolist(), d[1::2].tolist()))
        nouveaux = {}
        for seg in segs:
            nouveaux[seg] = ouverts.pop(seg, i)
        for (j0, j1), i0 in ouverts.items():
            finis.append((i0, j0, i, j1))
        ouverts = nouveaux
    for (j0, j1), i0 in ouverts.items():
        finis.append((i0, j0, masque.shape[0], j1))
    return finis


def masques(pl):
    """(meubles, murs) : masques des cases a remplir."""
    g = pl.grille
    meubles = g == P.OBSTACLE
    dehors = g == P.DEHORS
    # bande de dehors au contact de la maison : distance au plus proche non-dehors
    import cv2
    d = cv2.distanceTransform(dehors.astype(np.uint8), cv2.DIST_L2, 5) * pl.resolution
    murs = dehors & (d <= BANDE_MUR)
    X, Y = pl.centres()
    pres = np.hypot(X, Y) < DEGAGE_NAISSANCE
    return meubles & ~pres, murs & ~pres


def point_balle(pl):
    """Devant le chargeur, a ~50 cm, sur une case bien libre."""
    dist = pl.distance()
    for r in (0.5, 0.6, 0.4, 0.7, 0.8, 1.0):
        for a in (0.0, 0.3, -0.3, 0.6, -0.6, 1.0, -1.0):
            x, y = r * math.cos(a), r * math.sin(a)
            i, j = pl.case(x, y)
            if 0 <= i < pl.hauteur and 0 <= j < pl.largeur and pl.grille[i, j] == P.LIBRE and dist[i, j] >= 0.08:
                return x, y
    return 0.5, 0.0


def keyframes():
    """Les poses de depart du fork (duck-sim demarre sur SIT) : sans elles, la scene ne sert a rien."""
    f = ROBOT / MODELE_KEYFRAMES
    m = re.search(r"<keyframe>.*?</keyframe>", f.read_text(), re.S) if f.exists() else None
    if m is None:
        raise SystemExit(f"poses de depart introuvables dans {f} (fork microduck_rl ? variable MICRODUCK_RL)")
    return m.group(0)


def scene(pl):
    meubles, murs = masques(pl)
    r = pl.resolution
    boites = []

    def ajouter(masque, haut, classe):
        for i0, j0, i1, j1 in rectangles(masque):
            x0, y0 = pl.origine[0] + j0 * r, pl.origine[1] + i0 * r
            sx, sy = (j1 - j0) * r / 2, (i1 - i0) * r / 2
            boites.append(f'        <geom type="box" class="{classe}" pos="{x0 + sx:.3f} {y0 + sy:.3f} {haut / 2:.3f}" '
                          f'size="{sx:.3f} {sy:.3f} {haut / 2:.3f}" />')

    ajouter(murs, HAUT_MUR, "mur")
    ajouter(meubles, HAUT_MEUBLE, "meuble")
    bx, by = point_balle(pl)
    nom = re.sub(r"[^\w -]", "", str(pl.nom))[:40]
    return f'''<mujoco model="scene_maison">
    <!-- GENERE par microduck-brain/plan_vers_mjcf.py depuis le plan « {nom} » (scan Quest) : ne pas modifier a la
         main, regenerer. Repere = celui du plan (origine au chargeur, x = devant). {len(boites)} boites. -->
    <include file="robot_allcollisions.xml" />

    <visual>
        <headlight diffuse="0.6 0.6 0.6" ambient="0.3 0.3 0.3" specular="0 0 0" />
        <map znear="0.0004" />
        <global azimuth="160" elevation="-20" />
    </visual>

    <default>
        <default class="mur"><geom rgba="0.86 0.83 0.76 1" friction="0.8 0.005 0.0001" /></default>
        <default class="meuble"><geom rgba="0.55 0.40 0.28 1" friction="0.8 0.005 0.0001" /></default>
    </default>

    <asset>
        <texture type="2d" name="sol" builtin="checker" mark="edge" rgb1="0.62 0.55 0.45" rgb2="0.56 0.50 0.41"
            markrgb="0.7 0.65 0.55" width="300" height="300" />
        <material name="sol" texture="sol" texuniform="true" texrepeat="20 20" reflectance="0.0" />
    </asset>

    <worldbody>
        <light pos="0 0 3" dir="0 0 -1" directional="true" />
        <geom name="floor" size="0 0 0.05" pos="0 0 0" type="plane" material="sol" />
{chr(10).join(boites)}
        <body name="testball" pos="{bx:.3f} {by:.3f} 0.035">
            <freejoint name="testball_free" />
            <inertial pos="0 0 0" mass="0.015" diaginertia="1.225e-5 1.225e-5 1.225e-5" />
            <geom name="testball_geom" type="sphere" size="0.035" rgba="1 0.55 0 1" friction="0.5 0.005 0.0001" />
        </body>
    </worldbody>
    {keyframes()}
</mujoco>
'''


def lire_plan(source=None):
    if source:
        return P.Plan.depuis_dict(json.loads(Path(source).read_text()))
    import lieux
    d = lieux.Lieux(log=lambda m: None).plan()
    if not d:
        raise SystemExit("le lieu actuel n'a pas de plan (Reglages -> Lieux -> Importer un plan)")
    return P.Plan.depuis_dict(d)


def main(argv):
    pl = lire_plan(argv[0] if argv else None)
    sortie = Path(argv[1]) if len(argv) > 1 else SORTIE
    sortie.write_text(scene(pl))
    print(f"{sortie} : plan « {pl.nom} », {pl.largeur * pl.resolution:.1f} x {pl.hauteur * pl.resolution:.1f} m")


if __name__ == "__main__":
    main(sys.argv[1:])
