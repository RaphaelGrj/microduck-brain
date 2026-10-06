#!/usr/bin/env python3
"""Images du VRAI Microduck pour l'application (interface/microduck/*.webp), rendues depuis son modele 3D officiel
(microduck_rl : MJCF exporte d'Onshape et ses pieces STL) : poses debout / assis / tombe, plusieurs positions de tete,
fond transparent. A relancer si le modele change.

    MUJOCO_GL=osmesa uv run --with mujoco --with pillow python outils/rendu_microduck.py ~/microduck_rl

(rendu logiciel : `sudo apt install libosmesa6` si besoin ; ou MUJOCO_GL=egl avec une carte graphique)
"""
import sys
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

TAILLE = 512
SORTIE = Path(__file__).resolve().parents[1] / "interface" / "microduck"
# index qpos des articulations (freejoint 0-6, puis l'ordre du modele) - verifies sur robot_walk.xml
COU, TETE_TANGAGE, TETE_LACET, TETE_ROULIS = 12, 13, 14, 15
HANCHE_G, GENOU_G, CHEVILLE_G = 9, 10, 11
HANCHE_D, GENOU_D, CHEVILLE_D = 18, 19, 20

# (nom, keyframe, decalages de tete (cou, tangage, lacet, roulis) comme robot.head, retouches)
POSES = [
    ("debout", "STAND", (0, 0, 0, 0), {}),
    ("debout-tete-basse", "STAND", (0.25, 0.5, 0, 0), {}),
    ("debout-tete-haute", "STAND", (-0.2, -0.3, 0, 0), {}),
    ("debout-gauche", "STAND", (0, 0, 0.6, 0), {}),
    ("debout-droite", "STAND", (0, 0, -0.6, 0), {}),
    ("debout-penche", "STAND", (0, 0.1, 0, 0.35), {}),
    ("marche", "STAND", (0, 0.3, 0, 0), {HANCHE_G: -0.35, GENOU_G: 0.55, CHEVILLE_G: 0.25}),
    # la pose SIT de reference plie la tete presque a la verticale (cou 0,5 / tete 1,6) : on la ramene a l'angle debout
    ("assis", "SIT", (-0.15, -1.25, 0, 0), {}),
    ("assis-dort", "SIT", (0.1, -0.85, 0, 0.12), {}),
    ("tombe", "STAND", (0, 0, 0, 0), {"tombe": True}),
]


def charger(racine):
    xml = Path(racine).expanduser() / "src/mjlab_microduck/robot/microduck/scene_walk.xml"
    m = mujoco.MjModel.from_xml_path(str(xml))
    for i in range(m.ngeom):                    # pas de sol ni de decor : le canard seul, sur fond transparent
        if m.geom_bodyid[i] == 0:
            m.geom_rgba[i, 3] = 0.0
    m.vis.headlight.ambient[:] = (0.45, 0.45, 0.45)
    m.vis.headlight.diffuse[:] = (0.55, 0.55, 0.55)
    m.vis.quality.shadowsize = 0
    m.vis.global_.offwidth = m.vis.global_.offheight = TAILLE
    return m


def poser(m, d, cle, tete, retouches):
    d.qpos[:] = m.key_qpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_KEY, cle)]
    for idx, dq in zip((COU, TETE_TANGAGE, TETE_LACET, TETE_ROULIS), tete):
        d.qpos[idx] += dq
    for idx, v in retouches.items():
        if isinstance(idx, int):
            d.qpos[idx] += v
    if retouches.get("tombe"):
        d.qpos[2] = 0.05                        # couche sur le flanc
        d.qpos[3:7] = (np.cos(np.pi / 4), np.sin(np.pi / 4), 0, 0)
    mujoco.mj_forward(m, d)


def rendre(m, d, r):
    cam = mujoco.MjvCamera()
    cam.lookat[:] = (0.0, 0.0, 0.11)
    cam.distance, cam.azimuth, cam.elevation = 0.62, 205.0, -8.0   # trois-quarts avant, tete tournee vers la droite
    r.update_scene(d, camera=cam)
    rgb = r.render().copy()
    r.enable_depth_rendering()
    r.update_scene(d, camera=cam)
    prof = r.render().copy()
    r.disable_depth_rendering()
    alpha = (prof < prof.max() * 0.999).astype(np.uint8) * 255
    return np.dstack([rgb, alpha])


def icone(m, d, r):
    """L'icone de l'appli : la tete du Microduck en gros plan, sur le fond sombre de l'appli, 512 x 512 (PNG : iPhone)."""
    poser(m, d, "STAND", (0, -0.05, 0.25, 0), {})
    cam = mujoco.MjvCamera()
    tete = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, m.body(m.jnt_bodyid[TETE_ROULIS - 6]).name)]
    cam.lookat[:] = tete + np.array([0.0, 0.0, 0.01])
    cam.distance, cam.azimuth, cam.elevation = 0.25, 200.0, -6.0
    r.update_scene(d, camera=cam)
    rgb = r.render().copy()
    r.enable_depth_rendering()
    r.update_scene(d, camera=cam)
    prof = r.render().copy()
    r.disable_depth_rendering()
    fond = np.array([31, 42, 55], dtype=np.uint8)
    objet = (prof < prof.max() * 0.999)[:, :, None]
    Image.fromarray(np.where(objet, rgb, fond)).save(SORTIE.parent / "icone.png", optimize=True)


def main(racine):
    m = charger(racine)
    d = mujoco.MjData(m)
    r = mujoco.Renderer(m, TAILLE, TAILLE)
    SORTIE.mkdir(parents=True, exist_ok=True)
    images = {}
    for nom, cle, tete, retouches in POSES:
        poser(m, d, cle, tete, retouches)
        images[nom] = rendre(m, d, r)
    # meme cadrage pour toutes les poses (le canard ne "saute" pas d'une image a l'autre) : boite englobante commune
    masque = np.any(np.stack([im[:, :, 3] > 0 for im in images.values()]), axis=0)
    ys, xs = np.nonzero(masque)
    marge = 8
    boite = (max(0, xs.min() - marge), max(0, ys.min() - marge), min(TAILLE, xs.max() + marge), min(TAILLE, ys.max() + marge))
    for nom, im in images.items():
        Image.fromarray(im, "RGBA").crop(boite).save(SORTIE / f"{nom}.webp", "WEBP", quality=88, method=6)
        print(nom, (SORTIE / f"{nom}.webp").stat().st_size // 1024, "Ko")
    icone(m, d, r)
    print("icone", (SORTIE.parent / "icone.png").stat().st_size // 1024, "Ko")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "~/microduck_rl")
