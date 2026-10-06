#!/usr/bin/env python3
"""Lot 5 de l'application : journal photo (opt-in, sur le canard), messages a transmettre, mode vacances, « ou l'a-t-il
vu ? », arrivee par le telephone."""
import json
import time

import pytest

import appli
import photos
import reglages
from test_appli import CODE, requete
from test_vie_maison import cerveau, vivre

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# -- cerveau -----------------------------------------------------------------------------------------------------
def test_arrivee_par_le_telephone_accueille_sauf_deja_present():
    b, _, _ = cerveau()
    vu = []
    b.ecouteurs.append(vu.append)
    vivre(b, 1, evenements=[(0.1, "arrivee:Léa")])
    assert "etat:accueil" in vu and "Léa" in b.presents
    vu.clear()
    vivre(b, 6)
    vivre(b, 1, evenements=[(0.1, "arrivee:Léa")])
    assert "etat:accueil" not in vu, "deja compte present (Home Assistant) : pas de second accueil"


def test_message_signale_au_retour_puis_tout_de_suite_si_present():
    b, _, _ = cerveau()
    vu = []
    b.ecouteurs.append(vu.append)
    vivre(b, 1, evenements=[(0.1, "message:m1|Léa"), (0.2, "message:m2|Paul")])
    assert not [v for v in vu if v.startswith("message_transmis")]
    vivre(b, 1, evenements=[(0.1, "retour:Léa|7200")])
    assert "message_transmis:m1" in vu and "message_transmis:m2" not in vu
    assert b.etats["accueil"].messages == ["message_perso"], "l'accueil ajoute « il y a du nouveau »"
    vivre(b, 8)
    vu.clear()
    vivre(b, 1, evenements=[(0.1, "message:m3|Léa")])          # elle est la : il le signale aussitot
    assert "message_transmis:m3" in vu and "etat:messager" in vu
    vivre(b, 1, evenements=[(0.1, "message_annule:m2")])
    assert b.messages_perso == []


def test_vacances_calme_et_garde():
    b, _, _ = cerveau()
    vivre(b, 1, evenements=[(0.1, "vacances_on")])
    assert b.vacances and b.mode_calme and b.ctx.extras.get("garde")
    vivre(b, 1, evenements=[(0.1, "vacances_off")])
    assert not b.vacances and not b.mode_calme and not b.ctx.extras.get("garde")


def test_vacances_reglage_persistant_applique_au_demarrage():
    b, _, _ = cerveau()
    reglages.appliquer(b, {"vacances": True})
    vivre(b, 0.5)
    assert b.vacances and b.mode_calme
    assert reglages.valider({"vacances": 1, "photos": "oui"}) == {"vacances": True, "photos": True}
    assert reglages.pour_appli({})["photos"] is False, "journal photo : desactive par defaut"


class Balle:
    def position(self):
        return (0.5, 0.0)                   # 50 cm devant lui


def test_ou_l_a_t_il_vu():
    b, _, _ = cerveau(balle=Balle(), mur=lambda: 1000.0)
    vivre(b, 1, pos=(1.0, 2.0), evenements=[(0.5, "chat")])
    assert b.vus["chat"] == (1000, 1.0, 2.0)
    assert b.vus["balle"] == (1000, 1.5, 2.0), "la balle est situee par la camera, pas a sa place a lui"
    c = appli.carte(b, {"odom": {"position": [1.0, 2.0, 0.1], "yaw": 0.0}})
    assert c["vus"]["chat"] == {"t": 1000, "x": 1.0, "y": 2.0}


# -- photos ------------------------------------------------------------------------------------------------------
def test_photos_opt_in_espacees_et_effacees(tmp_path):
    t = [1_000_000.0]
    lues = []
    p = photos.Photos(tmp_path / "photos", lire=lambda: lues.append(1) or PNG, log=lambda m: None, mur=lambda: t[0])
    p.prendre = lambda motif, attendre=False: p._prendre(motif)       # (synchrone pour le test)
    p.sur_evenement("etat:regarde_chat")
    assert lues == [], "desactive par defaut"
    p.actif = True
    p.sur_evenement("etat:regarde_chat")
    p.sur_evenement("etat:regarde_chat")
    p.sur_evenement("etat:chill")
    p.sur_evenement("impression_finie:MK4S")
    assert len(lues) == 2 and [x["motif"] for x in p.liste()] == ["impression", "chat"]
    ident = p.liste()[0]["id"]
    assert p.lire_photo(ident)[0] == PNG and p.lire_photo("../memoire.json") is None
    t[0] += photos.JOURS_GARDES * 86400 + 10
    assert p.liste() == [], "effacees apres une semaine"


def test_camera_du_canard_seulement():
    with pytest.raises(RuntimeError):
        photos.lire_camera("http://192.168.1.20:8080/frame")


def test_api_photos_et_messages(tmp_path):
    a = appli.Appli(CODE, port=0, log=lambda m: None, code_enfant="petit-canard")
    a.photos = photos.Photos(tmp_path / "photos", lire=lambda: PNG, log=lambda m: None)
    a.demarrer()
    try:
        statut, corps = requete(a.port, "/api/photo", corps={"action": "prendre"})
        ident = json.loads(corps)["id"]
        assert statut == 200 and ident.endswith("-photo.png")
        assert json.loads(requete(a.port, "/api/photos")[1])["liste"][0]["id"] == ident
        assert requete(a.port, f"/api/photo?id={ident}")[1] == PNG
        assert requete(a.port, f"/api/photo?id={ident}", code="petit-canard")[0] == 403, "photos : parents seulement"
        assert requete(a.port, "/api/photo", corps={"action": "tout_supprimer"})[0] == 200
        assert json.loads(requete(a.port, "/api/photos")[1])["liste"] == []

        statut, corps = requete(a.port, "/api/message", code="petit-canard",
                                corps={"pour": "Papa", "texte": "Il y a des crêpes", "de": "Léa"})
        m = json.loads(corps)["message"]
        assert statut == 200 and a.source() == [f"message:{m['id']}|Papa"]
        assert requete(a.port, "/api/message", corps={"pour": "", "texte": "x"})[0] == 400
        a.sur_evenement(f"message_transmis:{m['id']}")
        assert a.alertes[-1]["titre"] == "Message transmis" and "Papa" in a.alertes[-1]["texte"]
        liste = json.loads(requete(a.port, "/api/messages", code="petit-canard")[1])["liste"]
        assert liste[0]["transmis"] and liste[0]["texte"] == "Il y a des crêpes"
    finally:
        a.arreter()


def test_messages_redonnes_au_cerveau_apres_redemarrage():
    a = appli.Appli(CODE, port=0, log=lambda m: None)
    m = a.messages.ajouter("Léa", "Rappelle-moi")
    a2 = appli.Appli(CODE, port=0, log=lambda m: None)              # (le canard a redemarre)
    b, _, _ = cerveau()
    a2.photographier(b, {})
    assert a2.source() == [f"message:{m['id']}|Léa"]


def test_resume_quotidien_des_vacances():
    a = appli.Appli(CODE, port=0, log=lambda m: None)
    a.horloge = lambda: time.struct_time((2026, 10, 7, 20, 5, 0, 2, 280, 0))
    e = {"modes": {"vacances": True}, "batterie": {"pourcent": 81.0}}
    a._resume_vacances(e)
    a._resume_vacances(e)
    assert [x["titre"] for x in a.alertes] == ["Nouvelles du canard"]
    assert a.alertes[0]["texte"] == "Tout va bien : batterie 81 %, rien d'anormal entendu."
