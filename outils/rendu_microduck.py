#!/usr/bin/env python3
"""Images du VRAI Microduck pour l'application (interface/microduck/*.webp), rendues depuis son modele 3D officiel
(microduck_rl : MJCF exporte d'Onshape et ses pieces STL) : poses debout / assis / tombe, plusieurs positions de tete,
fond transparent ; plus, par pose, l'ombrage et la carte des groupes de pieces (son « look » recolore sur l'accueil).
A relancer si le modele change. (L'icone de l'appli vient de outils/icone_logo.py.)

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


def calques(m, d, r, groupe_geom):
    """Pour son « look » sur l'accueil (schema de couleurs du design) : l'ombrage seul (pieces toutes blanches) et,
    pour chaque pixel, le numero du groupe de pieces (outils/modele_3d.py GROUPES, 1..n ; 0 = rien)."""
    cam = mujoco.MjvCamera()
    cam.lookat[:] = (0.0, 0.0, 0.11)
    cam.distance, cam.azimuth, cam.elevation = 0.62, 205.0, -8.0
    couleurs = m.mat_rgba.copy()
    m.mat_rgba[:, :3] = 0.92                        # blanc : il ne reste que la lumiere
    r.update_scene(d, camera=cam)
    ombre = r.render().copy().mean(axis=2).astype(np.uint8)
    m.mat_rgba[:] = couleurs
    r.enable_segmentation_rendering()
    r.update_scene(d, camera=cam)
    seg = r.render().copy()
    r.disable_segmentation_rendering()
    geom = seg[:, :, 0]
    groupes = np.zeros(geom.shape, np.uint8)
    est_geom = seg[:, :, 1] == int(mujoco.mjtObj.mjOBJ_GEOM)
    groupes[est_geom] = groupe_geom[np.clip(geom[est_geom], 0, len(groupe_geom) - 1)]
    return ombre, groupes


def main(racine):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from modele_3d import GROUPES
    m = charger(racine)
    d = mujoco.MjData(m)
    r = mujoco.Renderer(m, TAILLE, TAILLE)
    SORTIE.mkdir(parents=True, exist_ok=True)
    numero = {p: k + 1 for k, (_, _, pieces, _) in enumerate(GROUPES) for p in pieces}
    groupe_geom = np.zeros(m.ngeom, np.uint8)
    for i in range(m.ngeom):
        if m.geom_type[i] == mujoco.mjtGeom.mjGEOM_MESH and m.geom_group[i] == 2:
            groupe_geom[i] = numero.get(mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, m.geom_dataid[i]), 0)
    images, couches = {}, {}
    for nom, cle, tete, retouches in POSES:
        poser(m, d, cle, tete, retouches)
        images[nom] = rendre(m, d, r)
        couches[nom] = calques(m, d, r, groupe_geom)
    # meme cadrage pour toutes les poses (le canard ne "saute" pas d'une image a l'autre) : boite englobante commune
    masque = np.any(np.stack([im[:, :, 3] > 0 for im in images.values()]), axis=0)
    ys, xs = np.nonzero(masque)
    marge = 8
    boite = (max(0, xs.min() - marge), max(0, ys.min() - marge), min(TAILLE, xs.max() + marge), min(TAILLE, ys.max() + marge))
    for nom, im in images.items():
        Image.fromarray(im, "RGBA").crop(boite).save(SORTIE / f"{nom}.webp", "WEBP", quality=88, method=6)
        print(nom, (SORTIE / f"{nom}.webp").stat().st_size // 1024, "Ko")
        ombre, groupes = couches[nom]
        groupes = np.where(im[:, :, 3] > 0, groupes, 0).astype(np.uint8)
        Image.fromarray(np.dstack([ombre, ombre, ombre, im[:, :, 3]]), "RGBA").crop(boite).save(
            SORTIE / f"{nom}-ombre.webp", "WEBP", quality=90, method=6)
        Image.fromarray(groupes, "L").crop(boite).save(SORTIE / f"{nom}-groupes.png", optimize=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "~/microduck_rl")
