#!/usr/bin/env python3
"""Lot 9 de l'application : minuteur, rappels a heure fixe, reveil doux (etat Signal), bilan du mois et graphique
d'humeur (statistiques gardees par le canard)."""
import json
import time

import appli
import planning
import reglages
from memoire import Memoire
from test_appli import CODE, requete
from test_vie_maison import cerveau, sons, vivre


# -- planning (minuteurs, rappels) --------------------------------------------------------------------------------
def test_minuteurs_et_rappels(tmp_path):
    t = [1_000_000.0]
    p = planning.Planning(tmp_path / "p.json", mur=lambda: t[0])
    assert p.minuteur(2) is None and p.minuteur(25 * 3600) is None and p.minuteur("x") is None
    m = p.minuteur(600, "Les pâtes")
    r = p.rappel("Arroser les plantes", "18:00", pour="Clémence", quotidien=True)
    assert p.rappel("", "18:00") is None and p.rappel("x", "25:00") is None
    assert planning.Planning(tmp_path / "p.json").minuteurs[0]["nom"] == "Les pâtes", "garde au redemarrage"
    assert p.echus() == ([], [])
    t[0] += 601
    finis, arrives = p.echus()
    assert finis == [m] and arrives == [] and p.minuteurs == []
    t[0] = r["quand"] + 1
    finis, arrives = p.echus()
    assert arrives[0]["id"] == r["id"] and p.rappels[0]["quand"] > t[0], "quotidien : reprogramme au lendemain"
    assert p.annuler(r["id"]) and not p.annuler("absent")


def test_prochaine_heure():
    h = lambda t: time.struct_time((2026, 10, 7, 19, 0, 0, 2, 280, 0))   # il est 19 h
    t0 = time.mktime((2026, 10, 7, 19, 0, 0, 0, 0, -1))
    assert planning.prochaine(20, 0, t0, h) - t0 == 3600
    assert planning.prochaine(18, 0, t0, h) - t0 == 23 * 3600, "18 h est passee : demain"


# -- cerveau : Signal ---------------------------------------------------------------------------------------------
def test_minuteur_signale_meme_en_mode_calme_puis_arrete_par_l_appli():
    b, c, _ = cerveau()
    vu = []
    b.ecouteurs.append(vu.append)
    vivre(b, 1, evenements=[(0.1, "calme_on")])
    n = len(c.appels)
    vivre(b, 3, evenements=[(0.1, "signal:minuteur|m1")])
    assert b.courant.nom == "signal" and "chirp" in sons(c, n), "demande expresse : meme en mode calme"
    vivre(b, 1, evenements=[(0.1, "signal_stop")])
    assert "signal_fin:minuteur|m1|arrete" in vu and b.courant.nom != "signal"


def test_signal_jamais_a_terre_et_caresse_l_arrete():
    b, _, _ = cerveau()
    b.evenement("signal:reveil|reveil")
    for i in range(25):                                                   # a terre
        b.tick({"t": i * 0.02, "safety": {"fallen": True}, "policy": None}, 0.02)
    assert b.tombe and b.courant.nom != "signal"
    b2, _, _ = cerveau()
    vu = []
    b2.ecouteurs.append(vu.append)
    vivre(b2, 10, evenements=[(0.1, "signal:reveil|reveil")])            # pendant la pause entre deux cycles
    assert b2.courant.nom == "signal" and b2.etats["signal"].au_repos(b2.t_etat)
    vivre(b2, 0.5, evenements=[(0.1, "caresse")])
    assert any(v.startswith("signal_fin:reveil|reveil|caresse") for v in vu)


def test_reveil_doux_monte_progressivement():
    b, c, _ = cerveau()
    vivre(b, 120, evenements=[(0.1, "signal:reveil|reveil")])
    s = sons(c)
    assert s.index("coo") < s.index("chirp") < s.index("greet"), "roucoulements, puis pepiements, puis bonjour"
    assert reglages.valider({"routines": [{"heure": "6:45", "jours": [0, 1, 2, 3, 4], "action": "reveil"}]})["routines"]
    assert reglages.ROUTINES["reveil"] == "signal:reveil|reveil"


# -- appli : planning, statistiques -------------------------------------------------------------------------------
def test_appli_minuteur_rappel_et_enfant(tmp_path):
    a = appli.Appli(CODE, port=0, log=lambda m: None, code_enfant="petit-canard")
    a.demarrer()
    try:
        statut, corps = requete(a.port, "/api/minuteur", code="petit-canard", corps={"secondes": 60, "nom": "Œufs"})
        m = json.loads(corps)["element"]
        assert statut == 200 and m["nom"] == "Œufs"
        assert requete(a.port, "/api/rappel", code="petit-canard", corps={"texte": "x", "heure": "18:00"})[0] == 403
        assert requete(a.port, "/api/rappel", corps={"texte": "Arroser", "heure": "18:00", "pour": "Clémence"})[0] == 200
        assert requete(a.port, "/api/minuteur", corps={"secondes": 1})[0] == 400
        e = json.loads(requete(a.port, "/api/planning", code="petit-canard")[1])
        assert len(e["minuteurs"]) == 1 and e["rappels"][0]["pour"] == "Clémence"
        assert requete(a.port, "/api/commande", code="petit-canard", corps={"commande": "signal_stop"})[0] == 200
    finally:
        a.arreter()
    a.planning.mur = lambda: time.time() + 2 * 86400                    # tout est echu
    a._verifier_planning()
    src = a.source()
    assert f"signal:minuteur|{m['id']}" in src and any(x.startswith("message:") and x.endswith("|Clémence") for x in src)
    assert [x["titre"] for x in a.alertes][-2:] == ["Minuteur : Œufs", "Rappel pour Clémence"]
    assert a.messages.en_attente()[0]["de"] == "Rappel"


def test_humeur_et_bilan(tmp_path):
    t = [1_000_000.0]
    mem = Memoire(tmp_path / "m.json")
    b, _, _ = cerveau(memoire=mem, mur=lambda: t[0])
    for _ in range(3):
        vivre(b, 0.1)
        t[0] += 15 * 60
    assert len(mem.donnees["humeur"]) == 3 and mem.donnees["humeur"][1][0] - mem.donnees["humeur"][0][0] == 900
    a = appli.Appli(CODE, port=0, log=lambda m: None)
    a.photographier(b, {})
    assert len(a.stats["humeur"]) == 3 and a.stats["jours"] and "balle" in a.stats
