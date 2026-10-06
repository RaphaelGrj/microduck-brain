#!/usr/bin/env python3
"""Application Microduck (appli.py + appli/) : serveur sur le reseau local, code d'appairage, commandes en liste
fermee, instantane du cerveau ; telecommande (pas et regard guides) avec les garde-fous du cerveau."""
import json
import math
import urllib.error
import urllib.request

import pytest

import appli
from test_vie_maison import cerveau, vivre

CODE = "canard-test-42"


def requete(port, chemin, code=CODE, corps=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{chemin}", method="POST" if corps is not None else "GET",
                                 data=json.dumps(corps).encode() if corps is not None else None,
                                 headers={"X-Microduck-Code": code, "Content-Type": "application/json"} if code else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture
def serveur():
    a = appli.Appli(CODE, port=0, log=lambda m: None, version="abc1234 2026-10-06")
    a.demarrer()
    yield a
    a.arreter()


def test_code_trop_court_refuse():
    with pytest.raises(ValueError):
        appli.Appli("12345")


def test_sante_etat_et_code(serveur):
    b, _, _ = cerveau()
    vivre(b, 1)
    serveur.photographier(b, {"battery": {"percent": 77.0, "volts": 7.7}})
    assert requete(serveur.port, "/api/sante", code=None)[0] == 200
    assert requete(serveur.port, "/api/etat", code=None)[0] == 401
    import time
    time.sleep(1.1)                                         # un code faux freine l'essai suivant d'1 s
    statut, corps = requete(serveur.port, "/api/etat")
    e = json.loads(corps)
    assert statut == 200 and e["etat"] == b.courant.nom and e["batterie"]["pourcent"] == 77.0
    assert e["version"] == "abc1234 2026-10-06" and "maintenance" in e and "caractere" in e
    assert set(e["maintenance"]) == {"diagnostic", "batterie", "servos", "chutes"}


def test_commandes_en_liste_fermee(serveur):
    assert requete(serveur.port, "/api/commande", corps={"commande": "diagnostic"})[0] == 200
    assert requete(serveur.port, "/api/commande", corps={"commande": "avance"})[0] == 200
    assert requete(serveur.port, "/api/commande", corps={"commande": "alarme_fumee"})[0] == 400
    assert requete(serveur.port, "/api/commande", corps={"commande": "calme_on"})[0] == 200
    assert serveur.source() == ["diagnostic", "guide:avance", "calme_on"]


def test_fichiers_de_l_interface_et_pas_d_evasion(serveur):
    for chemin in ("/", "/app.js", "/style.css", "/manifest.webmanifest", "/icone.svg"):
        statut, corps = requete(serveur.port, chemin, code=None)
        assert statut == 200 and corps, chemin
    assert requete(serveur.port, "/../appli.py", code=None)[0] == 404
    assert requete(serveur.port, "/%2e%2e/ha.exemple.toml", code=None)[0] == 404


def test_flux_en_direct(serveur):
    b, _, _ = cerveau()
    serveur.photographier(b, {})
    with urllib.request.urlopen(f"http://127.0.0.1:{serveur.port}/api/flux?code={CODE}", timeout=5) as r:
        ligne = r.readline().decode()
    assert ligne.startswith("data: ") and json.loads(ligne[6:])["etat"] == b.courant.nom


def test_reseau_local_seulement():
    for ip in ("192.168.1.20", "10.0.0.5", "127.0.0.1", "::1", "fe80::1", "::ffff:192.168.1.3"):
        assert appli.adresse_locale(ip), ip
    for ip in ("8.8.8.8", "2001:4860:4860::8888", "n'importe quoi"):
        assert not appli.adresse_locale(ip), ip


# -- telecommande -------------------------------------------------------------------------------------------------
class Tof:
    def __init__(self, devant=3.0, vide=math.inf):
        self.devant, self.vide = devant, vide

    def noter_etat(self, s):
        pass

    def points(self, s):
        return []

    def libre(self, s):
        return {"devant": self.devant, "gauche": 3.0, "droite": 3.0, "vide": self.vide, "n": 3}


def marches(c):
    return [p for m, p in c.appels if m == "robot.move" and (p["vx"] or p["vyaw"])]


def test_pas_guide_avance_seulement_si_libre():
    b, c, _ = cerveau(tof=Tof())
    vivre(b, 1, evenements=[(0.1, "guide:avance")])
    assert any(p["vx"] >= 0.3 for p in marches(c)), "au-dessus de la zone morte"
    for tof in (Tof(devant=0.4), Tof(vide=0.3)):
        b, c, _ = cerveau(tof=tof)
        vivre(b, 2, evenements=[(0.1, "guide:avance")])
        assert not marches(c) and ("robot.sound", {"tag": "inquire"}) in c.appels
    b, c, _ = cerveau()                                         # sans capteur de distance : pas un pas
    vivre(b, 2, evenements=[(0.1, "guide:avance")])
    assert "pas_guide" not in [e[1] for e in b.journal]


def test_pas_guide_tourne_et_refuse_en_calme():
    b, c, _ = cerveau(tof=Tof())
    vivre(b, 1, evenements=[(0.1, "guide:gauche")])
    assert any(p["vyaw"] >= 1.2 for p in marches(c))
    b, c, _ = cerveau(tof=Tof())
    vivre(b, 20, evenements=[(0.1, "calme_on")])
    n = len(c.appels)
    vivre(b, 2, evenements=[(0.1, "guide:avance"), (0.5, "guide:droite")])
    assert not marches(type("C", (), {"appels": c.appels[n:]})())


def test_regard_guide_par_crans():
    b, c, _ = cerveau()
    vivre(b, 0.5, evenements=[(0.1, "regard:gauche"), (0.2, "regard:gauche"), (0.3, "regard:haut")])
    rg = b.etats["regard_guide"]
    assert b.courant.nom == "regard_guide" and abs(rg.lacet - 0.6) < 1e-9 and rg.tangage < 0
    tete = [p for m, p in c.appels if m == "robot.head"][-1]
    assert abs(tete["head_yaw"] - 0.6) < 1e-9
    vivre(b, 0.2, evenements=[(0.1, "regard:centre")])
    assert rg.lacet == 0.0 and rg.tangage == 0.0
    vivre(b, 8)
    assert b.courant.nom != "regard_guide", "il reprend sa vie"


def test_garde_activee_depuis_l_appli():
    b, _, _ = cerveau()
    vivre(b, 0.2, evenements=[(0.1, "garde_on")])
    assert b.ctx.extras["garde"]
    vivre(b, 0.2, evenements=[(0.1, "garde_off")])
    assert not b.ctx.extras["garde"]
