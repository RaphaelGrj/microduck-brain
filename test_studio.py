#!/usr/bin/env python3
"""Lot « vivre avec lui » : studio de choregraphies, regard au pave tactile, curseurs de caractere, statistiques du
jeu de balle, catalogue des comportements (robotd)."""
import json

import appli
import choregraphies
import reglages
from test_appli import requete, serveur  # noqa: F401  (fixture)
from test_vie_maison import cerveau, vivre


def test_choregraphies_valides_et_bornees():
    propre = choregraphies.valider([
        {"nom": "Salut|pirate", "etapes": [{"type": "tete", "lacet": 5, "tangage": -9, "duree": 0.01},
                                           {"type": "son", "son": "bonjour"}, {"type": "son", "son": "greet"},
                                           {"type": "geste", "geste": "rm"}, {"type": "geste", "geste": "oui"},
                                           {"type": "assis"}, {"type": "roulade"}]},
        {"nom": "salutpirate", "etapes": [{"type": "son", "son": "coo"}]},           # meme nom (casse) : ignoree
        {"nom": "Longue", "etapes": [{"type": "pause", "duree": 10}] * 40},
        {"nom": "", "etapes": [{"type": "son", "son": "coo"}]}])
    assert [c["nom"] for c in propre] == ["Salutpirate", "Longue"]
    e = propre[0]["etapes"]
    assert e[0] == {"type": "tete", "cou": 0.0, "tangage": -0.5, "lacet": 0.9, "roulis": 0.0, "duree": 0.2}
    assert [x["type"] for x in e] == ["tete", "son", "geste", "assis"]          # son humain, geste inconnu, roulade : non
    assert sum(choregraphies.duree_etape(x) for x in propre[1]["etapes"]) <= choregraphies.DUREE_MAX_S


def test_le_cerveau_joue_une_choregraphie():
    etapes = choregraphies.valider([{"nom": "Coucou", "etapes": [
        {"type": "son", "son": "greet"}, {"type": "tete", "lacet": 0.6, "duree": 1.0}, {"type": "geste", "geste": "oui"},
        {"type": "son", "son": "wheee"}]}])[0]["etapes"]
    b, c, _ = cerveau(choregraphies={"Coucou": etapes})
    vivre(b, 0.5)
    vivre(b, 0.2, evenements=[(0.0, "choregraphie:Coucou")])
    assert b.courant.nom == "choregraphie"
    vivre(b, 4)
    sons = [p["tag"] for m, p in c.appels if m == "robot.sound"]
    assert sons[:2] == ["greet", "wheee"]
    lacets = [p["head_yaw"] for m, p in c.appels if m == "robot.head" and "head_yaw" in p]
    assert max(lacets) <= 0.9 + 1e-6 and max(lacets) > 0.5
    b.evenement("calme_on")
    vivre(b, 0.5)
    vivre(b, 0.2, evenements=[(0.0, "choregraphie:Coucou")])
    assert b.courant.nom != "choregraphie"                                      # mode calme : non
    vivre(b, 0.2, evenements=[(0.0, "choregraphie:Inconnue")])


def test_regard_au_pave_borne():
    b, c, _ = cerveau()
    vivre(b, 0.5)
    vivre(b, 0.3, evenements=[(0.0, "regard:abs|2.5|-3")])
    assert b.courant.nom == "regard_guide"
    rg = b.etats["regard_guide"]
    assert (rg.lacet, rg.tangage) == (0.8, -0.4)
    vivre(b, 0.1, evenements=[(0.0, "regard:abs|nan|x")])                        # illisible : rien ne change


def test_curseurs_de_caractere():
    b, _, _ = cerveau()
    reglages.appliquer(b, {"caractere": {"joueur": 1.0, "bavard": 0.0, "taquin": 0.0}})
    assert b.perso.bavardage() == 0.0 and abs(b.perso.curseur("taquin") - 0.2) < 1e-9
    assert b.perso.curseur("joueur") > 1.7
    b.ctx.sound = lambda tag: (_ for _ in ()).throw(AssertionError("babil alors que bavard = 0"))
    b._t_babil = -1e9
    for _ in range(2000):
        b._babille(1.0)
    assert reglages.valider({"caractere": {"joueur": "x", "bavard": 9}})["caractere"] == {"joueur": 0.5, "bavard": 1.0, "taquin": 0.5}


def test_statistiques_de_balle():
    class Mem:
        donnees = {}

        def sauver(self):
            pass
    b, _, _ = cerveau(memoire=Mem())
    jeu = b.etats["balle"]
    for resultat, manches in (("reussi", 1), ("reussi", 2), ("rate", 3), ("arrete", 1)):
        jeu.manche = manches
        jeu._fin(b, 0.0, resultat)
    st = Mem.donnees["balle"]
    assert (st["parties"], st["reussies"], st["tirs"], st["record"], st["serie"]) == (3, 2, 6, 2, 0)


class FauxRobotd:
    appels = []

    def request(self, methode, params=None, timeout_s=5.0):
        FauxRobotd.appels.append((methode, params))
        return {"result": {"robot.policies": ["walk", "stand"], "robot.skills": ["roulade"],
                           "policy.search": [{"repo": "x/microduck-salto"}], "policy.install": "ok"}[methode]}

    class sock:
        @staticmethod
        def close():
            pass


def test_studio_et_comportements_depuis_l_appli(serveur, tmp_path, monkeypatch):  # noqa: F811
    import time
    monkeypatch.setattr(choregraphies, "CHEMIN_DEFAUT", tmp_path / "choregraphies.json")
    statut, corps = requete(serveur.port, "/api/comportements")
    assert json.loads(corps)["ok"] is False                                     # pas de robotd : dit simplement
    serveur.robotd = FauxRobotd
    assert json.loads(requete(serveur.port, "/api/comportements")[1])["politiques"] == ["walk", "stand"]
    r = json.loads(requete(serveur.port, "/api/comportement", corps={"action": "chercher", "texte": "salto"})[1])
    assert r["resultat"] == [{"repo": "x/microduck-salto"}]
    requete(serveur.port, "/api/comportement", corps={"action": "essayer", "nom": "roulade"})
    r = json.loads(requete(serveur.port, "/api/choregraphies", corps={"liste": [
        {"nom": "Coucou", "etapes": [{"type": "son", "son": "greet"}]}]})[1])
    assert r["liste"][0]["nom"] == "Coucou" and "Coucou" in serveur.choregraphies
    assert requete(serveur.port, "/api/choregraphies", corps={"jouer": "Absente"})[0] == 404
    requete(serveur.port, "/api/choregraphies", corps={"jouer": "Coucou"})
    requete(serveur.port, "/api/regard", corps={"lacet": 0.3, "tangage": 0.1})
    assert requete(serveur.port, "/api/regard", corps={"lacet": "a"})[0] == 400
    assert serveur.source() == ["skill_essai:roulade", "choregraphie:Coucou", "regard:abs|0.300|0.100"]
    assert reglages.valider({"routines": [{"heure": "9:00", "jours": [0], "action": "choregraphie:Coucou"}]})["routines"]
    time.sleep(1.1)
