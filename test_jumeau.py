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


def test_casque_etat_et_appairage(serveur, simu):  # noqa: F811
    s, r = requete(serveur.port, "/api/casque")
    c = json.loads(r)
    assert s == 200 and not c["connecte"] and c["simulateur"] and c["scene"] == "scene_maison.xml"
    assert all(a.startswith("http://") and a.endswith(f":{serveur.port}") for a in c["adresses"])
    # le casque se presente (en-tete X-Microduck-Casque) : l'appli le voit connecte, dans son mode
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{serveur.port}/api/xr",
                                 headers={"X-Microduck-Code": CODE, "X-Microduck-Casque": "Jumeau"})
    urllib.request.urlopen(req, timeout=5).read()
    c = json.loads(requete(serveur.port, "/api/casque")[1])
    assert c["connecte"] and c["mode"] == "Jumeau" and c["ip"] == "127.0.0.1"


def test_casque_commandes_du_jumeau(serveur, simu, tmp_path, monkeypatch):  # noqa: F811
    _, ctl = simu
    assert requete(serveur.port, "/api/casque", corps={"action": "balle"})[0] == 200
    t = json.loads(ctl.read_text())["throw"]["testball"]
    assert t["pos"][0] == pytest.approx(0.6) and t["vel"][0] < 0, "devant lui, roulant vers lui"

    class Pos:
        recale = None

        def recaler(self, x, y, cap):
            Pos.recale = (x, y, cap)
    serveur.position = Pos()
    assert requete(serveur.port, "/api/casque", corps={"action": "chargeur"})[0] == 200
    assert json.loads(ctl.read_text())["teleport_duck"][0]["pos"] == [0.0, 0.0] and Pos.recale == (0.0, 0.0, 0.0)
    # changer de scene : seulement sous jumeau.sh (qui relance tout)
    assert requete(serveur.port, "/api/casque", corps={"action": "scene", "scene": "arena"})[0] == 409
    monkeypatch.setenv("MICRODUCK_JUMEAU", "1")
    monkeypatch.setenv("MICRODUCK_SCENE_VOULUE", str(tmp_path / "scene"))
    assert requete(serveur.port, "/api/casque", corps={"action": "scene", "scene": "../../etc"})[0] == 400
    assert requete(serveur.port, "/api/casque", corps={"action": "scene", "scene": "arena"})[0] == 200
    assert (tmp_path / "scene").read_text().strip() == "arena" and serveur.redemarrage_demande


def test_apercu_du_design(serveur, tmp_path):  # noqa: F811
    serveur.fichier_design = tmp_path / "design.json"
    assert requete(serveur.port, "/api/design-apercu", corps={"couleurs": {"pieds": "#2F6FD6", "bec": "rouge"}})[0] == 200
    d = json.loads(requete(serveur.port, "/api/design")[1])
    assert d["apercu"] == {"pieds": "#2f6fd6"} and d["schemas"] == []
    requete(serveur.port, "/api/design-apercu", corps={"couleurs": {}})
    assert "apercu" not in json.loads(requete(serveur.port, "/api/design")[1])
    serveur.apercu_design = {"couleurs": {"pieds": "#000000"}, "t": time.time() - 3600}
    assert "apercu" not in json.loads(requete(serveur.port, "/api/design")[1]), "un vieil apercu oublie s'efface"


def test_appairage_du_casque_par_accord_du_parent(serveur):  # noqa: F811
    """Le casque trouve le canard, demande l'acces (sans code) ; le code ne lui est remis qu'apres accord, une fois."""
    s, r = requete(serveur.port, "/api/casque-demande", code=None, corps={})
    k = json.loads(r)["id"]
    assert s == 200 and requete(serveur.port, "/api/casque-demande", code=None, corps={})[1] == r, "une seule par adresse"
    assert json.loads(requete(serveur.port, f"/api/casque-demande?id={k}", code=None)[1]) == {"etat": "attente"}
    c = json.loads(requete(serveur.port, "/api/casque")[1])
    assert [d["id"] for d in c["demandes"]] == [k] and serveur.alertes[-1]["type"] == "casque"
    assert requete(serveur.port, "/api/casque", corps={"action": "accepter", "id": "faux"})[0] == 404
    assert requete(serveur.port, "/api/casque", corps={"action": "accepter", "id": k})[0] == 200
    assert json.loads(requete(serveur.port, f"/api/casque-demande?id={k}", code=None)[1]) == {"etat": "accepte", "code": CODE}
    assert requete(serveur.port, f"/api/casque-demande?id={k}", code=None)[0] == 404, "le code ne part qu'une fois"
    # refus
    k2 = json.loads(requete(serveur.port, "/api/casque-demande", code=None, corps={})[1])["id"]
    requete(serveur.port, "/api/casque", corps={"action": "refuser", "id": k2})
    assert json.loads(requete(serveur.port, f"/api/casque-demande?id={k2}", code=None)[1]) == {"etat": "refuse"}
    # expiree
    serveur.demandes_casque[k2]["t"] -= 3600
    assert requete(serveur.port, f"/api/casque-demande?id={k2}", code=None)[0] == 404
