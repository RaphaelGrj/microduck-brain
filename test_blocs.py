"""Atelier (blocs.py) : les blocs se compilent en etapes sures, jamais en code ; tout est borne."""
import blocs
import choregraphies
from etats_base import SONS_CANARD


def test_blocs_simples_et_repetition_deroulee():
    r = blocs.compiler([{"type": "son", "son": "greet"},
                        {"type": "repeter", "n": 3, "blocs": [{"type": "geste", "geste": "oui"}, {"type": "pause", "duree": 0.5}]},
                        {"type": "assis"}])
    assert [e["type"] for e in r["etapes"]] == ["son"] + ["geste", "pause"] * 3 + ["assis"]
    assert not r["tronque"] and r["ignores"] == 0
    assert abs(r["duree"] - (0.4 + 3 * (choregraphies.duree_etape({"type": "geste", "geste": "oui"}) + 0.5) + 2.5)) < 0.01


def test_valeurs_bornees_comme_le_studio():
    e = blocs.compiler([{"type": "tete", "cou": 9, "tangage": -9, "lacet": 9, "roulis": 9, "duree": 99}])["etapes"][0]
    for k, (bas, haut) in choregraphies.BORNES.items():
        assert bas <= e[k] <= haut
    assert e["duree"] <= 5.0


def test_rien_hors_de_la_liste_fermee():
    r = blocs.compiler([{"type": "roulade"}, {"type": "tir"}, {"type": "move", "vx": 5}, {"type": "son", "son": "parole"},
                        {"type": "exec", "code": "import os"}, "pas un bloc", 42, None, {"type": "geste", "geste": "inconnu"}])
    assert r["etapes"] == [] and r["ignores"] == 9
    assert all(s in SONS_CANARD for s in blocs.catalogue()["sons"])


def test_repetitions_et_profondeur_limitees():
    # n enorme -> MAX_REPETITIONS ; trop d'imbrications -> ignore ; duree totale bornee
    r = blocs.compiler([{"type": "repeter", "n": 10 ** 9, "blocs": [{"type": "son", "son": "chirp"}]}])
    assert len(r["etapes"]) == blocs.MAX_REPETITIONS
    prof = {"type": "son", "son": "chirp"}
    for _ in range(6):
        prof = {"type": "repeter", "n": 2, "blocs": [prof]}
    assert blocs.compiler([prof])["ignores"] >= 1
    long = blocs.compiler([{"type": "repeter", "n": 10, "blocs": [{"type": "repeter", "n": 10, "blocs": [
        {"type": "pause", "duree": 10}]}]}])
    assert long["tronque"] and long["duree"] <= choregraphies.DUREE_MAX_S and len(long["etapes"]) <= choregraphies.MAX_ETAPES


def test_entrees_absurdes_ne_plantent_pas():
    for x in (None, 3, "x", {}, [[]], [{"type": "repeter"}], [{"type": "repeter", "n": "a", "blocs": "b"}],
              [{"type": "repeter", "n": None, "blocs": [{"type": "assis"}]}]):
        r = blocs.compiler(x)
        assert isinstance(r["etapes"], list)
    assert len(blocs.compiler([{"type": "repeter", "n": None, "blocs": [{"type": "assis"}]}])["etapes"]) == 1


def test_arbre_geant_refuse_sans_boucle_infinie():
    r = blocs.compiler([{"type": "pause", "duree": 0.2}] * 5000)
    assert r["tronque"] and len(r["etapes"]) <= choregraphies.MAX_ETAPES


# -- la route /api/atelier ------------------------------------------------------------------------------------------
import json  # noqa: E402

import appli as appli_mod  # noqa: E402
from test_appli import requete, serveur  # noqa: E402,F401  (fixture)

PROGRAMME = [{"type": "son", "son": "greet"}, {"type": "repeter", "n": 2, "blocs": [{"type": "geste", "geste": "oui"}]}]


def test_route_atelier_catalogue_compiler_jouer(serveur, monkeypatch, tmp_path):
    monkeypatch.setattr(choregraphies, "CHEMIN_DEFAUT", tmp_path / "choregraphies.json")
    cat = json.loads(requete(serveur.port, "/api/atelier")[1])
    assert "greet" in cat["sons"] and "oui" in cat["gestes"]
    r = json.loads(requete(serveur.port, "/api/atelier", corps={"blocs": PROGRAMME})[1])    # compiler : rien ne part
    assert [e["type"] for e in r["etapes"]] == ["son", "geste", "geste"] and serveur.evenements.empty()
    statut, corps = requete(serveur.port, "/api/atelier", corps={"blocs": PROGRAMME, "action": "jouer"})
    assert statut == 200 and serveur.evenements.get_nowait() == f"choregraphie:{appli_mod.ESSAI_ATELIER}"
    assert appli_mod.ESSAI_ATELIER in serveur.choregraphies
    assert not (tmp_path / "choregraphies.json").exists()                  # l'essai ne s'ecrit jamais sur disque


def test_route_atelier_enregistrer_et_refus(serveur, monkeypatch, tmp_path):
    monkeypatch.setattr(choregraphies, "CHEMIN_DEFAUT", tmp_path / "choregraphies.json")
    r = json.loads(requete(serveur.port, "/api/atelier", corps={"blocs": PROGRAMME, "action": "enregistrer", "nom": "Mon salut"})[1])
    assert r["enregistre"] and "Mon salut" in serveur.choregraphies and appli_mod.ESSAI_ATELIER not in serveur.choregraphies
    assert [c["nom"] for c in choregraphies.lire()] == ["Mon salut"]
    assert requete(serveur.port, "/api/atelier", corps={"blocs": [{"type": "roulade"}], "action": "jouer"})[0] == 400
    assert requete(serveur.port, "/api/atelier", corps={"blocs": PROGRAMME, "action": "detruire"})[0] == 400
    assert requete(serveur.port, "/api/atelier", code=None)[0] == 401
