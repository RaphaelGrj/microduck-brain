#!/usr/bin/env python3
"""Lots 6 a 8 de l'application : parcours et balle guidee, mode photo, usure des servos et carnet d'entretien,
comparaison des batteries, codes invites, envoi d'un G-code a une Prusa."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import appli
import carnet
import diagnostic
import photos
from etats_appli import Parcours
from test_appli import CODE, requete
from test_quotidien import PNG
from test_vie_maison import Tof, cerveau, vivre


# -- parcours, balle guidee, pose ----------------------------------------------------------------------------------
def test_points_du_parcours():
    assert Parcours.lire_points("0.5,0;1,1", (0.0, 0.0)) == [(0.5, 0.0), (1.0, 1.0)]
    assert Parcours.lire_points("9,0", (0.0, 0.0)) is None, "etape de plus de 4 m : l'odometrie ne vise plus juste"
    assert Parcours.lire_points("a,b", None) is None and Parcours.lire_points("", None) is None
    assert Parcours.lire_points("nan,0", None) is None


def test_parcours_refuse_sans_capteur_de_distance():
    b, _, _ = cerveau()
    vu = []
    b.ecouteurs.append(vu.append)
    vivre(b, 1, evenements=[(0.2, "parcours:0.1,0")])
    assert b.courant.nom != "parcours" and "parcours_fini:parcours|refuse|0|0/0" in vu


def test_parcours_reussi_puis_compliment():
    b, c, _ = cerveau(tof=Tof())
    vu = []
    b.ecouteurs.append(vu.append)
    vivre(b, 3, evenements=[(0.2, "parcours:0.1,0;0.15,0.1")])     # deux points a portee : atteints l'un apres l'autre
    fin = [v for v in vu if v.startswith("parcours_fini")]
    assert fin and fin[0].startswith("parcours_fini:parcours|reussi|") and fin[0].endswith("|2/2")
    assert "etat:compliment" in vu


def test_parcours_interrompu_par_stop():
    b, _, _ = cerveau(tof=Tof())
    vu = []
    b.ecouteurs.append(vu.append)
    vivre(b, 2, evenements=[(0.2, "parcours:3,0"), (1.0, "alarme_fumee")])
    assert any(v.startswith("parcours_fini:parcours|interrompu|") for v in vu)


def test_pose_photo():
    b, _, _ = cerveau()
    vivre(b, 1, evenements=[(0.2, "pose_photo:fier")])
    assert b.courant.nom == "pose_photo"
    vivre(b, 1, evenements=[(0.2, "pose_photo:roulade")])     # pas une pose : ignore
    assert b.courant.nom == "pose_photo"


def test_appli_parcours_records_et_photo_posee(tmp_path, monkeypatch):
    a = appli.Appli(CODE, port=0, log=lambda m: None, code_enfant="petit-canard")
    a.photos = photos.Photos(tmp_path / "p", lire=lambda: PNG, log=lambda m: None)
    monkeypatch.setattr(a, "POSE_ATTENTE_S", 0.0)
    a.demarrer()
    try:
        assert requete(a.port, "/api/parcours", code="petit-canard", corps={"points": [[1, 0], [1, 1]]})[0] == 200
        assert a.source() == ["parcours:1.00,0.00;1.00,1.00"]
        assert requete(a.port, "/api/parcours", corps={"points": [[1, 0], [2, 2]], "genre": "balle"})[0] == 200
        assert a.source() == ["va_balle:1.00,0.00"]
        assert requete(a.port, "/api/parcours", corps={"points": "x"})[0] == 400
        a.sur_evenement("parcours_fini:parcours|reussi|42.3|2/2")
        a.sur_evenement("parcours_fini:parcours|reussi|50.0|2/2")
        a.sur_evenement("parcours_fini:parcours|bloque|12.0|1/3")
        d = json.loads(requete(a.port, "/api/parcours")[1])
        assert d["records"] == {"2": 42.3} and len(d["historique"]) == 3
        assert [x["texte"] for x in a.alertes] == ["42,3 s : record !", "50,0 s", "1 point(s) sur 3"]
        statut, corps = requete(a.port, "/api/photo", corps={"action": "prendre", "pose": "fier"})
        assert statut == 200 and json.loads(corps)["id"].endswith("-pose.png") and a.source() == ["pose_photo:fier"]
    finally:
        a.arreter()


# -- usure, carnet, batteries ------------------------------------------------------------------------------------
def _journees(s, debut, n, courant):
    for k in range(n):
        jour = f"2026-{debut + k:03d}"
        for _ in range(s.MESURES_MIN_JOUR):
            s.note_repos(jour, [0.0] * 15, [0.0] * 15, [courant] * 15)


def test_usure_courbes_et_servo_remplace():
    s = diagnostic.SanteServos()
    _journees(s, 1, 4, 100.0)
    _journees(s, 5, 1, 200.0)                        # le genou force : +100 %
    s.note_chaleur("2026-005", 48.5)
    assert ("right_knee", "courant", 200, 100) in s.derives()
    c = s.courbes()
    assert c["jours"][-1] == "2026-005" and c["servos"]["right_knee"]["courant"] == [100, 100, 100, 100, 200]
    assert c["chaleur"][-1] == 48.5 and "mouth" not in c["servos"]
    assert s.remplace("right_knee", "2026-005") and not s.remplace("mouth")
    assert not [d for d in s.derives() if d[0] == "right_knee"], "servo neuf : compare a lui-meme seulement"


def test_batterie_remplacee_et_courbes():
    j = diagnostic.JournalBatterie()
    j.d["cycles"] = [{"debut": 1000 * k, "de": 100, "a": 40, "h": 1.0, "batterie": "1"} for k in range(3)]
    assert j.courbes()["1"] == [{"t": 0, "autonomie_h": 1.67}, {"t": 1000, "autonomie_h": 1.67}, {"t": 2000, "autonomie_h": 1.67}]
    assert j.remplacee("1") and j.courbes()["1"] == [] and j.par_batterie()["1"]["cycles"] == 0
    assert not j.remplacee("7")


def test_carnet():
    assert carnet.valider({"type": "servo", "servo": "mouth"}) is None
    assert carnet.valider({"type": "batterie", "batterie": "4"}) is None
    assert carnet.valider({"type": "autre", "texte": ""}) is None
    e = carnet.valider({"type": "impression", "piece": "coque-superieure-origine", "date": "2026-10-07"})
    assert e == {"type": "impression", "texte": "", "date": "2026-10-07", "piece": "coque-superieure-origine"}


def test_api_carnet_et_usure():
    a = appli.Appli(CODE, port=0, log=lambda m: None)
    b, _, _ = cerveau()
    a.photographier(b, {})
    a.demarrer()
    try:
        statut, corps = requete(a.port, "/api/carnet", corps={"action": "ajouter", "type": "servo", "servo": "right_knee",
                                                              "texte": "XL330 neuf"})
        e = json.loads(corps)["entree"]
        assert statut == 200 and a.source() == ["servo_remplace:right_knee"]
        requete(a.port, "/api/carnet", corps={"type": "batterie", "batterie": "2"})
        assert a.source() == ["batterie_remplacee:2"]
        assert len(json.loads(requete(a.port, "/api/carnet")[1])["liste"]) == 2
        assert requete(a.port, "/api/carnet", corps={"action": "supprimer", "id": e["id"]})[0] == 200
        u = json.loads(requete(a.port, "/api/usure")[1])
        assert set(u) == {"servos", "batteries"} and set(u["batteries"]) == {"1", "2", "3"}
    finally:
        a.arreter()
    vivre(b, 0.2, evenements=[(0.0, "servo_remplace:right_knee")])
    assert "right_knee" in b.diagnostic.servos.d["remplaces"]


def test_alerte_servo_a_surveiller():
    a = appli.Appli(CODE, port=0, log=lambda m: None)
    e0 = {"tombe": False, "batterie": {}, "maintenance": {"diagnostic": {}, "batterie": {}, "servos": {"derives": []}}}
    e1 = json.loads(json.dumps(e0))
    e1["maintenance"]["servos"]["derives"] = ["right_knee (courant)"]
    a._surveiller(e0)
    a._surveiller(e1)
    a._surveiller(e1)
    assert [x["titre"] for x in a.alertes] == ["Servo à surveiller"]


# -- invites ----------------------------------------------------------------------------------------------------------
def test_codes_invites():
    a = appli.Appli(CODE, port=0, log=lambda m: None)
    a.demarrer()
    try:
        r = json.loads(requete(a.port, "/api/invites", corps={"heures": 3, "nom": "Mamie"})[1])
        code = r["code"]
        assert len(code) == 9 and r["nom"] == "Mamie"
        assert requete(a.port, "/api/etat", code=code)[0] == 200
        assert json.loads(requete(a.port, "/api/role", code=code)[1])["role"] == "invite"
        assert requete(a.port, "/api/reglages", code=code)[0] == 403
        assert requete(a.port, "/api/invites", code=code)[0] == 403
        assert requete(a.port, "/api/commande", code=code, corps={"commande": "avance"})[0] == 403
        assert requete(a.port, "/api/commande", code=code, corps={"commande": "salut"})[0] == 200
        assert appli.Appli(CODE, port=0, log=lambda m: None).invites.keys() == {code}, "garde au redemarrage"
        requete(a.port, "/api/invites", corps={"action": "revoquer", "code": code})
        import time
        time.sleep(1.1)                               # (un code faux freine les essais pendant 1 s)
        assert requete(a.port, "/api/etat", code=code)[0] == 401
    finally:
        a.arreter()


# -- envoi d'un G-code a une Prusa (PrusaLink) ------------------------------------------------------------------
def test_envoyer_un_gcode_a_la_prusa():
    recu = {}

    class Prusa(BaseHTTPRequestHandler):
        def log_message(self, *x):
            pass

        def do_PUT(self):
            recu.update(chemin=self.path, cle=self.headers["X-Api-Key"], lancer=self.headers["Print-After-Upload"],
                        corps=self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(201 if self.headers["X-Api-Key"] == "CLE" else 401)
            self.end_headers()

    imprimante = ThreadingHTTPServer(("127.0.0.1", 0), Prusa)
    threading.Thread(target=imprimante.serve_forever, daemon=True).start()
    a = appli.Appli(CODE, port=0, log=lambda m: None)
    a.brut = {"imprimante_directe": [{"nom": "MK4S", "type": "prusalink", "adresse": f"127.0.0.1:{imprimante.server_address[1]}",
                                      "cle_api": "CLE"}]}
    a.demarrer()
    try:
        import urllib.request
        def envoyer(fichier, nom="MK4S", lancer="1"):
            req = urllib.request.Request(f"http://127.0.0.1:{a.port}/api/imprimer", data=b"G28\n", method="POST", headers={
                "X-Microduck-Code": CODE, "X-Imprimante": nom, "X-Fichier": fichier, "X-Lancer": lancer})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code
        assert envoyer("coque viking.bgcode") == 200
        assert recu == {"chemin": "/api/v1/files/usb/coque_viking.bgcode", "cle": "CLE", "lancer": "?1", "corps": b"G28\n"}
        assert envoyer("coque.stl") == 400, "un STL n'est pas tranche"
        assert envoyer("coque.bgcode", nom="Saturn") == 404
        a.brut["imprimante_directe"][0]["cle_api"] = "FAUSSE"
        assert envoyer("coque.bgcode") == 502
    finally:
        a.arreter()
        imprimante.shutdown()
