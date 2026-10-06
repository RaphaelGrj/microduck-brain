#!/usr/bin/env python3
"""Lieux (lieux.py) : reconnus par le Wi-Fi, bascule automatique, archives, choix dans l'application."""
import json
import subprocess

import pytest

import lieux

MAISON = {"ssid": "Freebox-Maison", "bssid": "aa:aa:aa:aa:aa:01"}
REPETEUR = {"ssid": "Freebox-Maison", "bssid": "aa:aa:aa:aa:aa:02"}
PARENTS = {"ssid": "Livebox-Parents", "bssid": "bb:bb:bb:bb:bb:01"}


@pytest.fixture
def lx(tmp_path):
    l = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)
    l.carte_actuelle = lambda: {"case": 0.25, "cases": [[0, 0, 1.0]]}
    return l


def observer(l, reseau, fois=lieux.CONFIRMATIONS):
    for _ in range(fois):
        l.observer(reseau)


def test_week_end_chez_les_parents_puis_retour(lx, tmp_path):
    observer(lx, MAISON)
    assert lx.nom_actuel() == "Maison" and lx.source() == []            # premier reseau : celui de la maison
    lx.observer(PARENTS)
    assert lx.nom_actuel() == "Maison"                                  # un seul releve ne suffit pas
    lx.observer(PARENTS)
    assert lx.nom_actuel() == "Nouveau lieu" and lx.source() == ["lieu:nouveau|Nouveau lieu"]
    parents = lx.d["actuel"]
    assert lx.action("renommer", parents, "Chez les parents") == (True, None)
    assert lx.source() == ["lieu:renomme|Chez les parents"]
    observer(lx, MAISON)
    assert lx.nom_actuel() == "Maison" and lx.source() == ["lieu:retour|Maison"]
    assert lx.carte(parents)["cases"]                                   # la carte de chez les parents est gardee
    observer(lx, PARENTS)                                               # la fois suivante : reconnu, pas recree
    assert lx.nom_actuel() == "Chez les parents" and lx.source() == ["lieu:retour|Chez les parents"]
    assert len(lx.d["lieux"]) == 2
    relu = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)     # tout survit a un redemarrage
    assert relu.nom_actuel() == "Chez les parents" and len(relu.d["lieux"]) == 2


def test_repeteur_et_coupure_du_wifi(lx):
    observer(lx, MAISON)
    observer(lx, REPETEUR)                                              # meme maison, autre point d'acces
    assert lx.nom_actuel() == "Maison" and lx.source() == []
    assert len(lx.d["lieux"][lx.d["actuel"]]["reseaux"]) == 2
    lx.observer(PARENTS)
    lx.observer(None)                                                   # pas de Wi-Fi : on ne sait pas, on ne bouge pas
    lx.observer(PARENTS)
    assert lx.nom_actuel() == "Maison"


def test_archiver_restaurer_supprimer(lx):
    observer(lx, MAISON)
    observer(lx, PARENTS)
    parents = lx.d["actuel"]
    maison = next(k for k in lx.d["lieux"] if k != parents)
    assert lx.action("archiver", parents)[0] is False                   # pas le lieu ou il est
    observer(lx, MAISON)
    assert lx.action("archiver", parents) == (True, None)
    assert [l["archive"] for l in lx.resume()["lieux"] if l["id"] == parents] == [True]
    observer(lx, PARENTS)                                               # archive mais reconnu : il ressort des archives
    assert lx.d["actuel"] == parents and not lx.d["lieux"][parents]["archive"]
    observer(lx, MAISON)
    assert lx.action("supprimer", maison)[0] is False
    assert lx.action("supprimer", parents) == (True, None)
    observer(lx, PARENTS)                                               # supprime : un lieu neuf
    assert lx.d["actuel"] != parents and lx.nom_actuel() == "Nouveau lieu"


def test_bascule_auto_coupee_et_choix_manuel(lx):
    observer(lx, MAISON)
    observer(lx, PARENTS)
    parents = lx.d["actuel"]
    observer(lx, MAISON)
    lx.source()
    lx.action("auto_off", parents)
    observer(lx, PARENTS)
    assert lx.nom_actuel() == "Maison" and lx.resume()["suggestion"] == parents   # propose, ne bascule pas
    assert lx.action("basculer", parents) == (True, None)
    assert lx.source() == ["lieu:manuel|Nouveau lieu"]
    lx.action("nouveau", nom="Chez Paul")                               # sur le meme reseau : choix respecte
    observer(lx, PARENTS, fois=5)
    assert lx.nom_actuel() == "Chez Paul"


def test_lier_un_reseau(lx):
    observer(lx, MAISON)
    lx.action("nouveau", nom="Atelier")
    atelier = lx.d["actuel"]
    lx.observer(PARENTS)                                                # le Wi-Fi de l'atelier, vu une fois
    lx.source()
    assert lx.action("lier", atelier) == (True, None)                   # ce Wi-Fi est celui de l'atelier
    assert lx.d["actuel"] == atelier
    observer(lx, PARENTS, fois=5)
    assert lx.d["actuel"] == atelier and lx.source() == []


def test_noms_et_actions_refuses(lx):
    lid = lx.d["actuel"]
    assert lx.action("renommer", lid, "   ")[0] is False
    assert lx.action("renommer", lid, "x" * 200) == (True, None) and len(lx.nom_actuel()) == lieux.NOM_MAX
    assert lx.action("formater", lid)[0] is False
    assert lx.action("basculer", "l999")[0] is False
    assert lx.action("lier", lid)[0] is False                           # pas de Wi-Fi connu


def test_lecture_du_wifi_par_les_outils_locaux(monkeypatch):
    monkeypatch.setattr(lieux.shutil, "which", lambda c: "/usr/bin/" + c)

    def faux(sorties):
        def executer(cmd, **_):
            out = sorties.get(" ".join(cmd))
            return subprocess.CompletedProcess(cmd, 0 if out is not None else 1, out or "", "")
        return executer
    assert lieux.lire_reseau(faux({"iwgetid -r": "Freebox-Maison\n", "iwgetid -a -r": "AA:AA:AA:AA:AA:01\n"})) == MAISON
    wpa = "bssid=bb:bb:bb:bb:bb:01\nssid=Livebox-Parents\nwpa_state=COMPLETED\n"
    assert lieux.lire_reseau(faux({"wpa_cli status": wpa})) == PARENTS
    nm = "no:Voisin:CC\\:CC\\:CC\\:CC\\:CC\\:CC\nyes:Livebox-Parents:BB\\:BB\\:BB\\:BB\\:BB\\:01\n"
    assert lieux.lire_reseau(faux({"nmcli -t -f ACTIVE,SSID,BSSID dev wifi": nm})) == PARENTS
    assert lieux.lire_reseau(faux({})) is None


def test_fichier_abime(tmp_path):
    (tmp_path / "lieux.json").write_text("{pas du json")
    l = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)
    assert l.nom_actuel() == "Maison"
    json.dumps(l.resume())


def test_le_cerveau_change_de_lieu():
    from test_vie_maison import cerveau, vivre
    b, _, _ = cerveau()
    vivre(b, 2, pos=(0.5, 0.2))
    b.chargeur = (0.5, 0.2)
    vivre(b, 0.2, pos=(0.5, 0.2), evenements=[(0.0, "lieu:nouveau|Chez les parents")])
    assert b.ctx.extras["lieu"] == "Chez les parents" and b.chargeur is None
    assert len(b.exploration.passages) <= 1
