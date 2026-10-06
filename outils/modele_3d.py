#!/usr/bin/env python3
"""Le Microduck en 3D pour le design space de l'application (interface/design/microduck.json + microduck.bin), depuis
son modele officiel (microduck_rl : MJCF exporte d'Onshape et ses STL, Apache-2.0), en pose debout.

Chaque piece garde les sommets de son STL d'ORIGINE (allege), plus la transformation qui la pose sur le robot : un STL
dessine dans le meme repere que la piece d'origine (on part de son STL) se pose donc exactement a sa place dans l'appli.

    uv run --with mujoco --with trimesh --with fast-simplification python outils/modele_3d.py ~/microduck_rl
"""
import json
import struct
import sys
from pathlib import Path

import mujoco
import numpy as np
import trimesh

SORTIE = Path(__file__).resolve().parents[1] / "interface" / "design"
GARDE = 0.6                  # pieces imprimables (celles qu'on regarde et qu'on recolore) : surfaces fideles
GARDE_CACHEES = 0.08         # pieces achetees (electronique, servos, roulements) : surtout cachees
MIN_FACES = 400              # en dessous, la piece reste telle quelle
ARETE_VIVE_DEG = 35          # au-dela, l'arete reste nette ; en dessous, la surface est lissee (pas de facettes)

# groupes recolorables : (identifiant, nom affiche, pieces) ; imprimable = on peut l'imprimer dans sa couleur
GROUPES = [
    ("dessus_tete", "Dessus de la tête", ["top_head_shell"], True),
    ("dessous_tete", "Dessous de la tête", ["bottom_head_shell"], True),
    ("face", "Face", ["face_part"], True),
    ("bec", "Bec", ["jaw"], True),
    ("bec_souple", "Bec souple", ["jaw_soft", "soft_mouth_top"], True),
    ("oeil", "Tour de l'œil", ["noenoeil"], True),
    ("coques", "Coques du corps", ["left_shell", "right_shell"], True),
    ("chassis", "Châssis", ["trunk_base", "motor_support", "yaw2roll", "yaw_roll_motion", "bearing_roll"], True),
    ("cou", "Cou", ["neck", "neck_pitch"], True),
    ("hanches", "Hanches", ["hip_l"], True),
    ("cuisses", "Cuisses", ["upper_leg_left", "upper_leg_right"], True),
    ("jambes", "Jambes", ["leg", "upper_leg_rigidity_plate"], True),
    ("pieds", "Pieds", ["foot_left", "foot_right", "ankle_left", "ankle_right"], True),
    ("semelles", "Semelles", ["sole_left", "sole_right"], True),
    ("support_batterie", "Support de batterie", ["power_support", "banana_pcb_locker"], True),
    ("moteurs", "Servomoteurs", ["xl330"], False),
    ("electronique", "Électronique", ["pcb__raspberry_pi_zero_2_w", "elec_rpi_robot_hat_pcb", "np_f970", "speaker"], False),
    ("optique", "Caméra", ["m12_lens_holder", "lens"], False),
    ("roulements", "Roulements", ["seeed_bearing__configuration__22x16x4", "seeed_bearing__configuration_default"], False),
]


def hexa(rgb):
    return "#" + "".join(f"{int(round(float(c) * 255)):02x}" for c in rgb[:3])


def main(racine):
    dossier = Path(racine).expanduser() / "src/mjlab_microduck/robot/microduck"
    m = mujoco.MjModel.from_xml_path(str(dossier / "scene_walk.xml"))
    d = mujoco.MjData(m)
    d.qpos[:] = m.key_qpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_KEY, "STAND")]
    mujoco.mj_forward(m, d)
    groupe_de = {p: g for g, _, pieces, _ in GROUPES for p in pieces}
    imprimable = {g: imp for g, _, _, imp in GROUPES}

    pieces, instances, couleurs = {}, [], {}
    positions, normales, indices = bytearray(), bytearray(), bytearray()
    for i in range(m.ngeom):
        if m.geom_type[i] != mujoco.mjtGeom.mjGEOM_MESH or m.geom_group[i] != 2:     # pieces visibles seulement
            continue
        mid = m.geom_dataid[i]
        nom = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, mid)
        if nom not in groupe_de:
            raise SystemExit(f"piece sans groupe : {nom} (a ajouter dans GROUPES)")
        if nom not in pieces:
            brut = trimesh.load(dossier / "assets" / f"{nom}.stl")
            if len(brut.faces) > MIN_FACES:
                garde = GARDE if imprimable[groupe_de[nom]] else GARDE_CACHEES
                brut = brut.simplify_quadric_decimation(face_count=max(MIN_FACES, int(len(brut.faces) * garde)))
            # normales lissees par angle : les sommets sont dedoubles le long des aretes vives seulement
            brut = trimesh.graph.smooth_shade(brut, angle=np.radians(ARETE_VIVE_DEG))
            v = np.asarray(brut.vertices, dtype="<f4")
            n = np.clip(np.round(np.asarray(brut.vertex_normals) * 127), -127, 127).astype("i1")   # 3 octets
            if len(v) >= 65536:
                raise SystemExit(f"{nom} : trop de sommets pour des indices 16 bits")
            f = np.asarray(brut.faces, dtype="<u2")                 # indices 16 bits : chaque piece < 65 536 sommets
            pieces[nom] = {"v": [len(positions) // 4, v.size], "n": len(normales), "f": [len(indices) // 2, f.size]}
            positions += v.tobytes()
            normales += n.tobytes()
            indices += f.tobytes()
            if len(indices) % 4:
                indices += b"\0\0"                              # (alignement, sans effet)
        # STL d'origine -> monde : monde = A . brut + b (MuJoCo recentre ses maillages : mesh_pos / mesh_quat)
        rm = np.zeros(9)
        mujoco.mju_quat2Mat(rm, m.mesh_quat[mid])
        a = d.geom_xmat[i].reshape(3, 3) @ rm.reshape(3, 3).T
        b = d.geom_xpos[i] - a @ m.mesh_pos[mid]
        mat = m.geom_matid[i]
        rgba = m.mat_rgba[mat] if mat >= 0 else m.geom_rgba[i]
        couleurs.setdefault(groupe_de[nom], hexa(rgba))
        instances.append({"piece": nom, "groupe": groupe_de[nom],
                          "m": [round(float(x), 6) for x in np.hstack([a, b[:, None]]).ravel()]})

    SORTIE.mkdir(parents=True, exist_ok=True)
    normales += b"\0" * (-len(normales) % 4)                # les indices 16 bits suivent, alignes
    (SORTIE / "microduck.bin").write_bytes(bytes(positions) + bytes(normales) + bytes(indices))
    modele = {
        "source": "pollen-robotics/microduck_rl (Apache-2.0), scene_walk.xml, pose STAND",
        "unite": "m", "haut": "z", "octets_positions": len(positions),
        "octets_normales": len(normales),
        "groupes": [{"id": g, "nom": n, "imprimable": imp, "origine": couleurs[g]} for g, n, _, imp in GROUPES],
        "pieces": pieces, "instances": instances,
    }
    (SORTIE / "microduck.json").write_text(json.dumps(modele, ensure_ascii=False, separators=(",", ":")))
    faces = sum(p["f"][1] for p in pieces.values()) // 3
    print(f"{len(pieces)} pieces, {len(instances)} instances, {faces} triangles, "
          f"{(len(positions) + len(indices)) // 1024} Ko")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "~/microduck_rl")
