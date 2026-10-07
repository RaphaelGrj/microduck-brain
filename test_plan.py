#!/usr/bin/env python3
"""Plan de la maison (plan.py), scan Quest (plan_quest.py), localisation (localisation.py), marqueurs (marqueurs.py),
plans par lieu (lieux.py) et appli (appli.py)."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

import localisation
import plan as P
import plan_quest

SCENE = Path(__file__).resolve().parent.parent / "microduck_rl/src/mjlab_microduck/robot/microduck/apartment.xml"


def mat(cx, cy, cz, tx, ty, tz, x=(1, 0, 0), y=(0, 1, 0), z=(0, 0, 1)):
    """Matrice Unity (ligne par ligne) : colonnes = axes locaux x, y, z dans le monde, puis la translation."""
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, y, z, (tx, ty, tz)
    return [float(v) for v in m.ravel()]


def export_piece():
    """Une piece de 4 x 3 m (Unity : x de 0 a 4, z de 0 a 3), un canape, une table, une porte, un marqueur."""
    sol = {"label": "FLOOR", "matrice": mat(0, 0, 0, 2, 0, 1.5, x=(1, 0, 0), y=(0, 0, 1), z=(0, -1, 0)),
           "plan": [-2, -1.5, 4, 3], "volume": None, "contour": [[-2, -1.5], [2, -1.5], [2, 1.5], [-2, 1.5]]}
    murs = [
        {"label": "WALL_FACE", "matrice": mat(0, 0, 0, 2, 1.25, 0), "plan": [-2, -1.25, 4, 2.5]},          # sud
        {"label": "WALL_FACE", "matrice": mat(0, 0, 0, 2, 1.25, 3), "plan": [-2, -1.25, 4, 2.5]},          # nord
        {"label": "WALL_FACE", "matrice": mat(0, 0, 0, 0, 1.25, 1.5, x=(0, 0, 1), z=(-1, 0, 0)), "plan": [-1.5, -1.25, 3, 2.5]},
        {"label": "WALL_FACE", "matrice": mat(0, 0, 0, 4, 1.25, 1.5, x=(0, 0, 1), z=(-1, 0, 0)), "plan": [-1.5, -1.25, 3, 2.5]},
    ]
    canape = {"label": "COUCH", "matrice": mat(0, 0, 0, 2, 0.4, 2.5), "volume": [-0.9, -0.4, -0.4, 0.9, 0.4, 0.4]}
    table = {"label": "TABLE", "matrice": mat(0, 0, 0, 1, 0.375, 1), "volume": [-0.5, -0.375, -0.3, 0.5, 0.375, 0.3]}
    porte = {"label": "DOOR_FRAME", "matrice": mat(0, 0, 0, 0, 1.0, 1.5, x=(0, 0, 1), z=(-1, 0, 0)), "plan": [-0.4, -1.0, 0.8, 2.0]}
    return {"format": "microduck-quest-1", "date": "2026-10-10",
            "reperes": [{"nom": "chargeur", "pos": [0.3, 0.0, 0.3]}, {"nom": "devant", "pos": [0.3, 0.0, 1.3]},
                        {"nom": "entree", "pos": [0.2, 0.0, 1.5]}, {"nom": "marqueur", "id": 2, "pos": [3.99, 0.12, 2.0]}],
            "pieces": [{"nom": "Salon", "ancres": [sol, *murs, canape, table, porte]}]}


def test_conversion_d_un_scan_quest():
    p, av = plan_quest.convertir(export_piece(), "Maison")
    assert not av, av
    # repere du canard : origine au chargeur (Unity x=0,3 z=0,3), x vers « devant » (+z Unity), y a gauche (-x Unity)
    assert p.libre(0.0, 0.0) and p.reperes["chargeur"] == [0.0, 0.0, 0.0]
    assert p.valeur(1.0, 0.0) == P.LIBRE
    # le canape (Unity x 1,1..2,9, z 2,1..2,9) : plan x = z - 0,3, y = -(x - 0,3)
    assert p.valeur(2.2, -1.7) == P.OBSTACLE
    # la table : seulement ses pieds ; dessous, c'est libre
    assert p.valeur(0.7, -0.7) == P.LIBRE and p.valeur(0.4, -0.2) == P.OBSTACLE
    # le mur ouest (Unity x = 0) est en plan y = +0,3 ; la porte (z 1,1..1,9 -> plan x 0,8..1,6) l'ouvre
    assert p.valeur(0.3, 0.3) == P.OBSTACLE and p.valeur(1.2, 0.3) == P.LIBRE
    # le marqueur sur le mur est (Unity x = 4) regarde vers l'interieur (Unity -x = plan +y)
    x, y, cap = p.reperes["marqueurs"]["2"]
    assert abs(x - 1.7) < 0.02 and abs(y + 3.69) < 0.02 and abs(cap - math.pi / 2) < 0.05
    assert {o["nom"] for o in p.objets} >= {"canapé", "table", "porte"}
    assert p.pieces[0]["nom"] == "Salon" and p.reperes["entree"] == [1.2, 0.1]


def test_scan_sans_reperes_et_mauvais_fichiers():
    e = export_piece()
    e["reperes"] = []
    p, av = plan_quest.convertir(e)
    assert av and "chargeur" not in p.reperes
    with pytest.raises(ValueError):
        plan_quest.convertir({"format": "autre"})
    with pytest.raises(ValueError):
        plan_quest.convertir({"format": "microduck-quest-1", "pieces": []})


def test_aller_retour_fichier():
    p, _ = plan_quest.convertir(export_piece())
    q = P.Plan.depuis_dict(json.loads(json.dumps(p.vers_dict())))
    assert (q.grille == p.grille).all() and q.origine == pytest.approx(p.origine) and q.reperes == p.reperes
    d = p.vers_dict()
    d["rle"][-1] += 1
    with pytest.raises(ValueError):
        P.Plan.depuis_dict(d)


@pytest.mark.skipif(not SCENE.exists(), reason="depot microduck_rl absent (scene de l'appartement)")
def test_plan_de_la_scene_et_localisation():
    p = P.depuis_mjcf(SCENE)
    assert 7.5 < p.largeur * p.resolution < 9 and 5.5 < p.hauteur * p.resolution < 7
    assert p.reperes["chargeur"][:2] == [-3.8, -2.78]
    rng = np.random.default_rng(3)

    def libre_devant(x, y, cap):
        return next((d / 50 for d in range(1, 50) if not p.libre(x + d / 50 * math.cos(cap), y + d / 50 * math.sin(cap))), 1.0)

    def tof(x, y, cap):
        pts = []
        for a in np.linspace(-math.radians(22), math.radians(22), 8):
            d = p.rayon(x, y, cap + a, 2.0)
            if d < 2.0:
                d += rng.normal(0, 0.01)
                pts += [(d * math.cos(a), d * math.sin(a), 0.1)] * 3
        return pts

    x, y, cap = -2.5, -2.0, 0.0
    ox = oy = ocap = 0.0
    loc = localisation.Localisation(p, graine=1)
    loc.depuis(x, y, cap)
    loc.mouvement(ox, oy, ocap)
    pire = 0.0
    for k in range(1200):                                   # 2 min de promenade, odometrie qui derive (6 %, cap)
        v, w = (0.0, 1.5) if libre_devant(x, y, cap) < 0.45 else (0.3, 0.0)
        cap += w * 0.1
        x, y = x + v * 0.1 * math.cos(cap), y + v * 0.1 * math.sin(cap)
        ocap += (w * 1.03 + (0.02 if v else 0.0)) * 0.1
        ox, oy = ox + 1.06 * v * 0.1 * math.cos(ocap), oy + 1.06 * v * 0.1 * math.sin(ocap)
        if loc.mouvement(ox, oy, ocap):
            loc.mesure(tof(x, y, cap))
        ex, ey, _, _ = loc.estimation()
        pire = max(pire, math.hypot(ex - x, ey - y))
    assert pire < 0.3, pire
    assert math.hypot(-2.5 + ox - x, -2.0 + oy - y) > 1.0, "l'odometrie seule, elle, s'est perdue"
    # on l'a porte ailleurs : un marqueur vu le remet en place
    assert loc.recaler(2.0, 1.0, 0.5) == "reparti" and math.hypot(loc.estimation()[0] - 2.0, loc.estimation()[1] - 1.0) < 0.1


def test_marqueur_vu_par_la_camera():
    import cv2
    import marqueurs
    r = np.array([[0, 0, 1], [-1, 0, 0], [0, -1, 0]], float)      # camera (x droite, y bas, z devant) -> tronc
    cam = {"pos": [0.05, 0.0, 0.15], "quat": [0.5, -0.5, 0.5, -0.5]}
    import geometry
    assert np.allclose(geometry.quat_vers_matrice(cam["quat"]), r)
    cn = math.pi + math.radians(20)
    centre, n = np.array([1.0, 0.2, 0.10]), np.array([math.cos(cn), math.sin(cn), 0.0])
    haut = np.array([0.0, 0.0, 1.0])
    droite = np.cross(haut, n)
    s = marqueurs.TAILLE_M / 2
    coins = [r.T @ (centre + a * s * droite + b * s * haut - np.array(cam["pos"])) for a, b in ((-1, 1), (1, 1), (1, -1), (-1, -1))]
    f, l, h = marqueurs.vision.FOCAL_PX, 360, 640
    px = np.array([[f * c[0] / c[2] + l / 2, f * c[1] / c[2] + h / 2] for c in coins], np.float32)
    m = cv2.copyMakeBorder(cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(marqueurs.DICO), 4, 200),
                           40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    t = cv2.getPerspectiveTransform(np.array([[40, 40], [240, 40], [240, 240], [40, 240]], np.float32), px)
    img = np.full((h, l), 180, np.uint8)
    masque = cv2.warpPerspective(np.full_like(m, 255), t, (l, h)) > 0
    img[masque] = cv2.warpPerspective(m, t, (l, h))[masque]
    (ident, x, y, c), = marqueurs.detecter(img, cam)
    assert ident == 4 and abs(x - 1.0) < 0.03 and abs(y - 0.2) < 0.03
    assert abs((c - cn + math.pi) % (2 * math.pi) - math.pi) < math.radians(5)
    # le canard en (2, 1), cap 0,5 : le meme marqueur sur le plan -> sa pose
    X, Y = 2 + math.cos(.5) * 1.0 - math.sin(.5) * 0.2, 1 + math.sin(.5) * 1.0 + math.cos(.5) * 0.2
    px_, py_, pc_ = marqueurs.pose_du_canard((x, y, c), (X, Y, cn + 0.5))
    assert math.hypot(px_ - 2, py_ - 1) < 0.08 and abs(pc_ - 0.5) < math.radians(5)


# -- un plan par lieu (demenagement), appli ----------------------------------------------------------------------------
def test_un_plan_par_lieu(tmp_path):
    import lieux
    li = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)
    maison = li.d["actuel"]
    resume, av = li.importer_plan(maison, export_piece())
    assert resume["source"] == "quest" and resume["chargeur"] and li.plan()["format"] == P.FORMAT
    sauvegarde = li.plan(maison)
    # demenagement : un nouveau lieu (nouveau Wi-Fi), son propre scan ; l'ancien garde le sien
    li.action("nouveau", nom="Nouvel appart")
    nouveau = li.d["actuel"]
    assert li.plan() is None and li.plan(maison) == sauvegarde
    li.importer_plan(nouveau, sauvegarde, nom="Copie")          # un plan sauvegarde se reimporte tel quel
    assert P.Plan.depuis_dict(li.plan()).nom == "Copie"
    rel = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)
    assert rel.plan(maison) == sauvegarde, "garde au redemarrage"
    assert li.supprimer_plan(nouveau) and li.plan() is None
    assert "plan_donnees" in json.loads((tmp_path / "lieux.json").read_text())["lieux"][maison], "dans la sauvegarde"
    li.action("supprimer", maison)
    assert maison not in json.loads((tmp_path / "lieux.json").read_text())["lieux"], "le plan part avec le lieu"
    with pytest.raises(ValueError):
        li.importer_plan(nouveau, {"format": "n'importe quoi"})


def test_appli_importe_et_rend_le_plan(tmp_path):
    import appli
    import lieux
    from test_appli import CODE, requete
    a = appli.Appli(CODE, port=0, log=lambda m: None)
    a.lieux = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)
    a.demarrer()
    try:
        assert requete(a.port, "/api/plan")[0] == 404
        statut, corps = requete(a.port, "/api/plan", corps={"contenu": export_piece(), "nom": "Maison"})
        r = json.loads(corps)
        assert statut == 200 and r["plan"]["objets"] >= 3 and r["avertissements"] == []
        lid = a.lieux.d["actuel"]
        p = json.loads(requete(a.port, f"/api/plan?id={lid}")[1])
        assert p["format"] == P.FORMAT and json.loads(requete(a.port, "/api/lieux")[1])["lieux"][0]["plan"]["chargeur"]
        assert requete(a.port, "/api/plan", corps={"contenu": {"format": "?"}})[0] == 400
        assert requete(a.port, "/api/plan-supprimer", corps={"id": lid})[0] == 200
        assert requete(a.port, "/api/plan")[0] == 404
    finally:
        a.arreter()
