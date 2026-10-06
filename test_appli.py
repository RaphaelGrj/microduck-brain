#!/usr/bin/env python3
"""Application Microduck (appli.py + appli/) : serveur sur le reseau local, code d'appairage, commandes en liste
fermee, instantane du cerveau ; telecommande (pas et regard guides) avec les garde-fous du cerveau."""
import json
import math
import re
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
    statut, corps = requete(serveur.port, "/api/sante", code=None)
    assert statut == 200 and json.loads(corps)["appli"] == "microduck"   # l'appli Android reconnait le canard ainsi
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
    for chemin in ("/", "/app.js", "/style.css", "/manifest.webmanifest", "/icone.png", "/microduck/debout.webp",
                   "/microduck/assis-dort.webp"):
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


def test_demo_inerte_hors_mode_demo():
    """demo.js (canard imaginaire de l'appli Android) ne s'active que sur l'hote de demo ou avec ?demo."""
    js = (appli.DOSSIER / "demo.js").read_text(encoding="utf-8")
    assert 'location.hostname !== "demo.microduck.local"' in js
    assert "fetch(" not in js and "XMLHttpRequest" not in js and "WebSocket" not in js   # rien ne sort du telephone
    html = (appli.DOSSIER / "index.html").read_text(encoding="utf-8")
    assert html.index("/demo.js") < html.index("/app.js")


def test_manifeste_android():
    """L'APK ne demande que l'acces reseau, et vise une version d'Android installable aujourd'hui."""
    from pathlib import Path
    m = (Path(__file__).parent / "android" / "AndroidManifest.xml").read_text(encoding="utf-8")
    permissions = set(re.findall(r'uses-permission android:name="([^"]+)"', m))
    assert permissions == {"android.permission.INTERNET", "android.permission.POST_NOTIFICATIONS",
                           "android.permission.RECEIVE_BOOT_COMPLETED"}      # reseau, notifications, veille apres redemarrage
    assert 'android:targetSdkVersion="34"' in m and 'android:allowBackup="false"' in m


def test_carte_des_zones():
    """La carte vient de la memoire d'exploration du canard (odometrie + ToF), sur le robot ; l'appli ne fait que l'afficher."""
    from types import SimpleNamespace
    from exploration import Exploration
    ex = Exploration()
    for k in range(12):
        ex.noter(0.1 * k, 0.0, 100.0 + k)
    ex.obstacle(1.6, 0.3, 120.0)
    ex.chute(0.5, -0.5, 121.0)
    ex.preference(0.2, 0.0, "nap", 60.0, 122.0)
    b = SimpleNamespace(exploration=ex, t_global=130.0, chargeur=(0.0, 0.1), objets_au_sol=[(0, 1.2, 0.4)],
                        _derniere_position=None)
    c = appli.carte(b, {"odom": {"position": [1.1, 0.0, 0.1], "yaw": 0.5}})
    assert c["case"] == 0.25 and c["canard"] == {"x": 1.1, "y": 0.0, "cap": 0.5}
    assert {(i, j) for i, j, _ in c["cases"]} == {(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)}
    assert all(0.0 < f <= 1.0 for *_, f in c["cases"])
    assert c["obstacles"] == [[6, 1]] and c["chutes"] == [[2, -2]]
    assert c["coins"] == {"nap": [0.12, 0.12]} and c["chargeur"] == [0.0, 0.1] and c["objets"] == [[1.2, 0.4]]
    json.dumps(c)                                            # envoyable tel quel
    assert appli.carte(SimpleNamespace(), {}) == {}          # pas d'exploration : carte vide, pas d'erreur


def test_carte_servie_avec_le_code(serveur):
    b, _, _ = cerveau()
    vivre(b, 1)
    serveur.photographier(b, {"odom": {"position": [0.0, 0.0, 0.1], "yaw": 0.0}})
    assert requete(serveur.port, "/api/carte", code=None)[0] == 401
    import time
    time.sleep(1.1)
    statut, corps = requete(serveur.port, "/api/carte")
    assert statut == 200 and json.loads(corps)["case"] == 0.25


def test_effacer_la_carte():
    """« Effacer sa carte » (meubles deplaces, autre endroit) : carte, coins et chargeur oublies, le reste garde."""
    b, _, _ = cerveau()
    vivre(b, 2, pos=(0.5, 0.2))
    b.exploration.preference(0.5, 0.2, "nap", 60.0, b.t_global)
    b.chargeur = (0.5, 0.2)
    perso = b.perso
    assert b.exploration.passages and b.exploration.coin_favori("nap", b.t_global)
    vivre(b, 0.1, pos=(0.5, 0.2), evenements=[(0.0, appli.COMMANDES["oublier_carte"])])
    assert b.chargeur is None and b.exploration.coin_favori("nap", b.t_global) is None
    assert len(b.exploration.passages) <= 1                 # seulement la case ou il se trouve, notee depuis
    assert b.perso is perso


def test_lieux_depuis_l_appli(serveur, tmp_path):
    import time
    import lieux
    assert requete(serveur.port, "/api/lieux")[0] == 404                 # pas de lieux branches : la section se cache
    serveur.lieux = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)
    statut, corps = requete(serveur.port, "/api/lieux")
    d = json.loads(corps)
    assert statut == 200 and [l["nom"] for l in d["lieux"]] == ["Maison"]
    assert requete(serveur.port, "/api/lieu", corps={"action": "nouveau", "nom": "Chez les parents"})[0] == 200
    assert serveur.lieux.nom_actuel() == "Chez les parents"
    assert requete(serveur.port, "/api/lieu", corps={"action": "archiver", "id": serveur.lieux.d["actuel"]})[0] == 400
    assert requete(serveur.port, "/api/lieu", corps={"action": "renommer", "id": ["l1"], "nom": 3})[0] == 400
    assert requete(serveur.port, "/api/lieu-carte?id=l1")[0] == 200
    assert requete(serveur.port, "/api/lieu", corps={"action": "nouveau"}, code="mauvais-code")[0] == 401
    time.sleep(1.1)


def test_design_valide_et_garde(serveur, tmp_path):
    """Schemas de couleurs et filaments du design space : nettoyes, gardes sur le canard, relus."""
    import time
    serveur.fichier_design = tmp_path / "design.json"
    assert json.loads(requete(serveur.port, "/api/design")[1]) == appli.DESIGN_VIDE
    envoi = {"filaments": [{"nom": "PLA orange", "couleur": "#f26a1b"}, {"nom": "", "couleur": "#000000"},
                           {"nom": "Faux", "couleur": "rouge"}],
             "schemas": [{"nom": "Noir et orange", "couleurs": {"coques": "#222222", "bec": "javascript:"}},
                         {"nom": 3, "couleurs": {}}],
             "actif": "Noir et orange", "pirate": "<script>"}
    assert requete(serveur.port, "/api/design", corps=envoi)[0] == 200
    relu = json.loads(requete(serveur.port, "/api/design")[1])
    assert relu == {"filaments": [{"nom": "PLA orange", "couleur": "#f26a1b"}], "couleurs": [],
                    "schemas": [{"nom": "Noir et orange", "couleurs": {"coques": "#222222"}}], "actif": "Noir et orange"}
    assert requete(serveur.port, "/api/design", corps=[1, 2])[0] == 400
    assert appli.valider_design({"schemas": [], "actif": "absent"})["actif"] is None
    time.sleep(1.1)


def test_modele_3d_coherent():
    """Le modele 3D du design space (outils/modele_3d.py) : chaque instance pointe une piece et un groupe connus, et le
    binaire contient exactement les positions et les indices annonces."""
    m = json.loads((appli.DOSSIER / "design" / "microduck.json").read_text())
    taille = (appli.DOSSIER / "design" / "microduck.bin").stat().st_size
    groupes = {g["id"] for g in m["groupes"]}
    assert {i["groupe"] for i in m["instances"]} <= groupes and {i["piece"] for i in m["instances"]} == set(m["pieces"])
    indices0 = m["octets_positions"] + m["octets_normales"]
    assert indices0 % 2 == 0
    for p in m["pieces"].values():
        assert (p["v"][0] + p["v"][1]) * 4 <= m["octets_positions"]
        assert p["n"] + p["v"][1] <= m["octets_normales"]                    # une normale (3 octets) par sommet
        assert indices0 + (p["f"][0] + p["f"][1]) * 2 <= taille
        assert p["v"][1] % 3 == 0 and p["f"][1] % 3 == 0
    assert all(len(i["m"]) == 12 for i in m["instances"])
    assert {g["id"] for g in m["groupes"] if g["imprimable"]} >= {"dessus_tete", "coques", "pieds", "bec"}



def test_alertes_pour_les_notifications(serveur):
    """Chute, batterie faible (une fois par decharge), garde, incendie, impression : le canard tient les alertes ;
    le telephone les lit avec un curseur (pas de doublon)."""
    import time
    b, _, _ = cerveau()
    vivre(b, 1)
    serveur.photographier(b, {"battery": {"percent": 25.0}})
    assert serveur.sur_evenement in b.ecouteurs                       # branche au cerveau a la premiere trame
    serveur._t_photo = -1e9
    b.tombe = True
    serveur.photographier(b, {"battery": {"percent": 19.0}})
    b.evenement("garde:voix")                                         # ce que le cerveau envoie aux ecouteurs
    serveur.sur_evenement("impression_finie:MK4S")
    serveur.sur_evenement("sonnette")                                 # pas une alerte
    types = [a["type"] for a in serveur.alertes]
    assert types == ["chute", "batterie", "garde", "impression_finie"], types
    assert serveur.alertes[-1]["texte"] == "MK4S" and serveur.alertes[0]["importante"]
    serveur._t_photo = -1e9
    serveur.photographier(b, {"battery": {"percent": 18.0}})          # toujours faible : pas de seconde alerte
    assert [a["type"] for a in serveur.alertes].count("batterie") == 1
    t = serveur.alertes[1]["t"]
    statut, corps = requete(serveur.port, f"/api/alertes?depuis={t}")
    assert statut == 200 and [a["type"] for a in json.loads(corps)["alertes"]] == ["garde", "impression_finie"]
    time.sleep(1.1)


def test_reglages_depuis_l_appli(serveur, tmp_path):
    """Heures calmes, bonjour, repas... : valides, gardes a part (ha.toml jamais reecrit), appliques sans redemarrer."""
    import time
    import reglages
    b, _, _ = cerveau()
    vivre(b, 1)
    serveur.cerveau = {"heures_calmes": [23, 7], "bonjour": "7:30", "autotest": True}
    serveur.fichier_reglages = tmp_path / "reglages.json"
    lu = json.loads(requete(serveur.port, "/api/reglages")[1])
    assert lu["heures_calmes"] == [23, 7] and lu["bonjour"] == "07:30" and lu["repas"] == [] and lu["circadien"]
    envoi = {"heures_calmes": [22, 6], "bonjour": "08:15", "bonjour_weekend": None, "repas": ["12:30", "19:30", "12:30", "x"],
             "autotest": False, "jeton": "pirate"}
    statut, corps = requete(serveur.port, "/api/reglages", corps=envoi)
    assert statut == 200 and json.loads(corps)["repas"] == ["12:30", "19:30"]
    garde = json.loads((tmp_path / "reglages.json").read_text())
    assert "jeton" not in garde and garde["bonjour"] == "08:15" and garde["heures_calmes"] == [22, 6]
    serveur._t_photo = -1e9
    serveur.photographier(b, {})                                      # applique dans la boucle du cerveau
    assert b.heures_calmes == (22, 6) and b.bonjour == (8, 15) and b.bonjour_weekend is None
    assert b.ctx.extras["repas"] == [(12, 30), (19, 30)] and b.ctx.extras["autotest"] is False
    assert reglages.valider({"heures_calmes": [5, 5]})["heures_calmes"] is None
    assert reglages.valider({"heures_calmes": [True, 7]})["heures_calmes"] is None
    assert requete(serveur.port, "/api/reglages", corps={"inconnu": 1})[0] == 400
    time.sleep(1.1)


def test_semaine_et_batteries_dans_l_instantane():
    b, _, _ = cerveau()
    vivre(b, 1)
    e = appli.instantane(b, {"battery": {"percent": 80.0}})
    assert e["semaine"] and e["semaine"][-1]["compte"] == e["du_jour"]
    bt = e["maintenance"]["batterie"]
    assert bt["actuelle"] == "1" and bt["a_nommer"] is False and set(bt["batteries"]) == {"1", "2", "3"}


def test_ou_es_tu_et_routines():
    """« Ou es-tu ? » : trois chirp, sauf en mode calme. Routines : a l'heure dite, les jours dits, une seule fois."""
    import reglages
    b, c, horloge = cerveau()
    vivre(b, 0.5)
    vivre(b, 0.2, evenements=[(0.0, appli.COMMANDES["ou_es_tu"])])
    assert b.courant.nom == "ou_es_tu"
    vivre(b, 6)
    b.evenement("calme_on")
    vivre(b, 0.5)
    vivre(b, 0.2, evenements=[(0.0, "ou_es_tu")])
    assert b.courant.nom != "ou_es_tu"                                # silence promis en mode calme
    b.evenement("calme_off")
    vivre(b, 0.5)
    reglages.appliquer(b, {"routines": [{"heure": "18:00", "jours": [horloge.jour % 7], "action": "ou_es_tu"},
                                        {"heure": "18:00", "jours": [(horloge.jour + 1) % 7], "action": "danse"},
                                        {"heure": "25:00", "jours": [0], "action": "danse"},
                                        {"heure": "18:00", "jours": [0], "action": "formater"}]})
    assert len(b.routines) == 2
    horloge.heure, horloge.minute = 18, 0
    vus = []
    b.ecouteurs.append(vus.append)
    vivre(b, 3)
    assert vus.count("ou_es_tu") == 1 and "commande:danse" not in vus  # une fois, et seulement le bon jour


def test_presence_sauvegarde_restauration(serveur, tmp_path, monkeypatch):
    import time
    import lieux
    import memoire
    import reglages
    monkeypatch.setattr(memoire, "CHEMIN_DEFAUT", tmp_path / "memoire.json")
    monkeypatch.setattr(lieux, "CHEMIN_DEFAUT", tmp_path / "lieux.json")
    monkeypatch.setattr(reglages, "CHEMIN_DEFAUT", tmp_path / "reglages.json")
    serveur.fichier_design = tmp_path / "design.json"
    (tmp_path / "memoire.json").write_text(json.dumps({"etres": {"Raphael": {"rencontres": 3}}}))
    (tmp_path / "design.json").write_text(json.dumps({"filaments": []}))
    assert requete(serveur.port, "/api/presence", corps={"nom": "Raphaël|absent"})[0] == 200
    assert serveur.source() == ["arrivee:Raphaëlabsent"]       # le nom ne peut pas forger un autre evenement
    statut, corps = requete(serveur.port, "/api/sauvegarde")
    sauvegarde = json.loads(corps)
    assert statut == 200 and set(sauvegarde["fichiers"]) == {"memoire.json", "design.json"}
    assert "ha.toml" not in corps.decode() and "token" not in corps.decode()
    assert requete(serveur.port, "/api/restauration", corps={"format": "autre", "fichiers": {}})[0] == 400
    assert requete(serveur.port, "/api/restauration",
                   corps={**sauvegarde, "fichiers": {"../../etc/passwd": {}}})[0] == 400
    sauvegarde["fichiers"]["memoire.json"]["etres"]["Chat"] = {"rencontres": 1}
    r = json.loads(requete(serveur.port, "/api/restauration", corps=sauvegarde)[1])
    assert r["redemarrer"] and json.loads((tmp_path / "memoire.json").read_text())["etres"].keys() == {"Raphael"}
    appli.appliquer_restaurations([tmp_path / "memoire.json", tmp_path / "design.json"], log=lambda m: None)
    assert "Chat" in json.loads((tmp_path / "memoire.json").read_text())["etres"]
    assert not (tmp_path / "memoire.json.restaurer").exists()
    time.sleep(1.1)


def test_design_garde_mes_couleurs():
    d = appli.valider_design({"couleurs": [{"nom": "Vert sapin", "couleur": "#33AA77"}, {"couleur": "#123456"},
                                           {"nom": "faux", "couleur": "vert"}], "schemas": [], "filaments": []})
    assert d["couleurs"] == [{"nom": "Vert sapin", "couleur": "#33aa77"}, {"nom": "#123456", "couleur": "#123456"}]
    assert appli.valider_design({})["couleurs"] == []
