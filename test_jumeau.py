#!/usr/bin/env python3
"""Canard jumeau (Quest, mode Jumeau) : verite du simulateur relayee au casque, lancer de balle, caresse, sons ; scene
MuJoCo generee depuis le plan ; modele 3D anime par corps."""
import json
import os
import time

import numpy as np
import pytest

import appli
import jumeau
import plan as P
import plan_vers_mjcf as V
from test_appli import CODE, requete, serveur  # noqa: F401 (fixture)
from test_plan_cerveau import plan_maison

CORPS = ["trunk_base", "yaw2roll", "hip_l", "upper_leg_left", "leg", "ankle_left", "neck", "neck_pitch",
         "yaw_roll_motion", "jaw_soft", "bearing_roll", "hip_l_2", "upper_leg_right", "leg_2", "ankle_right"]


def ecrire_verite(f, scene="scene_maison.xml"):
    parts = {n: [0.1 * k, 0.0, 0.1, 1, 0, 0, 0] for k, n in enumerate(CORPS)}
    f.write_text(json.dumps({"t": 12.5, "scene": scene,
                             "ducks": [{"index": 0, "pos": [0, 0, 0.1], "quat": [1, 0, 0, 0], "parts": parts}],
                             "bodies": {"testball": [0.4, 0, 0.035], "obj_0": [1, 1, 0]}}))


@pytest.fixture
def simu(tmp_path, monkeypatch):
    gt, ctl = tmp_path / "gt.json", tmp_path / "ctl.json"
    ecrire_verite(gt)
    monkeypatch.setenv("DUCK_SIM_GROUNDTRUTH", str(gt))
    monkeypatch.setenv("DUCK_SIM_CONTROL", str(ctl))
    return gt, ctl


def test_etat_relaye_et_perime(simu):
    gt, _ = simu
    e = jumeau.etat([(time.time() - 5, "chirp"), (time.time(), "coo")], depuis=time.time() - 1)
    assert e["repere"] == "plan" and len(e["corps"]) == 15 and set(e["balles"]) == {"testball"}
    assert [s[1] for s in e["sons"]] == ["coo"], "seulement les sons recents"
    ecrire_verite(gt, scene="scene_apartment_testball.xml")
    assert jumeau.etat()["repere"] == "libre"
    vieux = time.time() - 10
    os.utime(gt, (vieux, vieux))
    assert jumeau.etat() is None, "simulateur arrete : rien"


def test_lancer_valide(simu):
    _, ctl = simu
    assert jumeau.lancer({"pos": [1, "x", 0]})[0] == 400
    assert jumeau.lancer({"pos": [0.3, 0.1, -1.0], "vel": [1e9, 0, 0]})[0] == 400
    assert jumeau.lancer({"pos": [0.3, 0.1, -1.0], "vel": [2, 0, 1]}) == (200, {"ok": True})
    c = json.loads(ctl.read_text())["throw"]["testball"]
    assert c["pos"][2] == pytest.approx(0.036) and c["vel"] == [2, 0, 1]


def test_routes_de_l_appli(serveur, simu, monkeypatch):  # noqa: F811
    serveur.sons_recents.append((time.time(), "wheee"))
    s, r = requete(serveur.port, "/api/jumeau")
    e = json.loads(r)
    assert s == 200 and e["sons"][-1][1] == "wheee" and "jaw_soft" in e["corps"]
    assert requete(serveur.port, "/api/jumeau-balle", corps={"pos": [0.5, 0, 0.3], "vel": [1, 0, 0]})[0] == 200
    assert requete(serveur.port, "/api/jumeau-caresse", corps={})[0] == 200
    assert serveur.evenements.get_nowait() == "caresse:jumeau"
    monkeypatch.setenv("DUCK_SIM_GROUNDTRUTH", "/nulle/part.json")
    assert requete(serveur.port, "/api/jumeau")[0] == 404, "vrai robot : pas de jumeau"
    assert requete(serveur.port, "/api/jumeau-caresse", corps={})[0] == 404
    assert requete(serveur.port, "/api/jumeau", code="faux")[0] == 401


def test_ses_sons_sont_notes():
    import etats_base

    class Client:
        def request(self, *a):
            return {"result": "ok"}

    ctx = etats_base.Ctx.__new__(etats_base.Ctx)
    ctx.client, ctx.extras = Client(), {"sons_recents": []}
    ctx.sound("chirp")
    ctx.sound("bonjour")                    # pas un son de canard : refuse, pas note
    assert [t for _, t in ctx.extras["sons_recents"]] == ["chirp"]


def test_rectangles_couvrent_exactement():
    rng = np.random.default_rng(3)
    m = rng.random((40, 55)) < 0.3
    m[5:20, 10:30] = True
    rebati = np.zeros_like(m)
    for i0, j0, i1, j1 in V.rectangles(m):
        assert not rebati[i0:i1, j0:j1].any(), "pas de chevauchement"
        rebati[i0:i1, j0:j1] = True
    assert (rebati == m).all()


def test_scene_depuis_le_plan(tmp_path, monkeypatch):
    rl = tmp_path / "rl"
    d = rl / "src/mjlab_microduck/robot/microduck"
    d.mkdir(parents=True)
    (d / V.MODELE_KEYFRAMES).write_text("<mujoco><keyframe>\n<key name=\"SIT\" qpos=\"0\"/>\n</keyframe></mujoco>")
    monkeypatch.setattr(V, "ROBOT", d)
    pl = plan_maison()
    xml = V.scene(pl)
    assert 'name="SIT"' in xml and 'znear="0.0004"' in xml and 'class="mur"' in xml and 'class="meuble"' in xml
    bx, by = V.point_balle(pl)
    assert pl.libre(bx, by) and np.hypot(bx, by) >= 0.4
    meubles, murs = V.masques(pl)
    assert not (meubles & murs).any() and not meubles[pl.case(0, 0)], "rien la ou il nait"
    (tmp_path / "p.json").write_text(json.dumps(pl.vers_dict()))
    V.main([str(tmp_path / "p.json"), str(tmp_path / "s.xml")])
    assert (tmp_path / "s.xml").read_text().startswith("<mujoco")
    monkeypatch.setattr(V, "ROBOT", tmp_path / "nulle_part")
    with pytest.raises(SystemExit):
        V.scene(pl)


def test_modele_anime_par_corps():
    m = json.loads((appli.DOSSIER / "design" / "microduck.json").read_text())
    assert {i["corps"] for i in m["instances"]} == set(CORPS)
    for i in m["instances"]:
        l = np.array(i["l"]).reshape(3, 4)
        assert np.allclose(l[:, :3] @ l[:, :3].T, np.eye(3), atol=1e-4), "rotation pure"
        assert np.abs(l[:, 3]).max() < 0.2, "la piece reste pres de son corps"
