#!/usr/bin/env python3
"""Test du pont Home Assistant contre le FAUX HA local (mock_ha.py) : aucun simulateur necessaire.

Verifie : transitions d'etat -> evenements du cerveau (et seulement elles), etats ignores, jeton refuse,
publication des entites du canard, reconnexion apres coupure. Usage : bash ~/run-brain.sh test_ha.py
"""
import time

import brain
import mock_ha
import pont_ha

JETON = "JETON_DE_TEST"
CFG = {"surveillance": [
    {"entite": "sensor.prusa_mk4s", "nom": "MK4S",
     "reactions": {"finished": "impression_finie", "stopped": "impression_echec", "error": "impression_echec",
                   "printing": "impression_commencee"}},
    {"entite": "sensor.elegoo_saturn", "nom": "Saturn",
     "reactions": {"Complete": "impression_finie", "Failed": "impression_echec"}},
], "publier_toutes_les_s": 1}


def attendre(cond, secs=3.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        if cond():
            return True
        time.sleep(0.05)
    return False


def faux_etat():
    return {"policy": "stand", "safety": {"fallen": False}, "odom": {"position": [1.0, 2.0, 0.1], "yaw": 0.5},
            "battery": {"percent": 87.4, "volts": 7.9}}


class FauxBrain:
    def __init__(self):
        self.courant = type("E", (), {"nom": "chill"})()
        self.humeur = brain.Humeur(0.64, 0.2)


def test_evenements():
    ha = mock_ha.MockHA(JETON)
    log = []
    pont = pont_ha.PontHA({**CFG, "url": ha.url, "url_ws": ha.url_ws}, JETON, log=log.append)
    pont.demarrer()
    try:
        assert attendre(lambda: ha.abonnes), "le pont ne s'est pas abonne : " + str(log)
        ha.set_state("sensor.prusa_mk4s", "printing")                 # 1re apparition : ancien etat None
        assert attendre(lambda: pont.source() == ["impression_commencee:MK4S"])
        ha.set_state("sensor.prusa_mk4s", "printing")                 # meme etat : rien
        ha.set_state("sensor.prusa_mk4s", "unavailable")              # ignore
        ha.set_state("sensor.prusa_mk4s", "finished")
        assert attendre(lambda: pont.source() == ["impression_finie:MK4S"]), log
        ha.set_state("sensor.prusa_mk4s", "ERROR")                    # insensible a la casse
        assert attendre(lambda: pont.source() == ["impression_echec:MK4S"]), log
        ha.set_state("sensor.elegoo_saturn", "Complete")              # 2e imprimante, etat a majuscule
        assert attendre(lambda: pont.source() == ["impression_finie:Saturn"]), log
        ha.set_state("sensor.autre_chose", "finished")                # entite non surveillee
        ha.set_state("sensor.prusa_mk4s", "idle")                     # etat sans reaction
        time.sleep(0.5)
        assert pont.source() == [], "evenement parasite"
    finally:
        pont.stop()
        ha.arreter()
    print("evenements : OK (transitions seulement, casse ignoree, etats parasites ignores)")


def test_publication():
    ha = mock_ha.MockHA(JETON)
    pont = pont_ha.PontHA({**CFG, "url": ha.url, "url_ws": ha.url_ws}, JETON, log=print)
    pont.photographier(FauxBrain(), faux_etat())
    pont.demarrer()
    try:
        assert attendre(lambda: "sensor.microduck_batterie" in ha.etats), ha.etats.keys()
        assert ha.etats["sensor.microduck_batterie"]["state"] == "87"
        assert ha.etats["sensor.microduck_batterie"]["attributes"]["device_class"] == "battery"
        assert ha.etats["binary_sensor.microduck_tombe"]["state"] == "off"
        assert ha.etats["sensor.microduck_etat"]["state"] == "chill"
        assert ha.etats["sensor.microduck_position"]["state"] == "1.00,2.00"
        etat = faux_etat()
        etat["safety"]["fallen"] = True                               # une chute doit remonter vite
        pont.photographier(FauxBrain(), etat)
        assert attendre(lambda: ha.etats["binary_sensor.microduck_tombe"]["state"] == "on"), "chute non publiee"
        r = pont.client.appeler_service("scene", "turn_on", {"entity_id": "scene.salon"})
        assert r == 200 and ha.appels == [("scene", "turn_on", {"entity_id": "scene.salon"})], ha.appels
    finally:
        pont.stop()
        ha.arreter()
    print("publication : OK (entites sensor.microduck_*, chute remontee, appel de service)")


def test_jeton_refuse():
    ha = mock_ha.MockHA(JETON)
    log = []
    pont = pont_ha.PontHA({**CFG, "url": ha.url, "url_ws": ha.url_ws}, "MAUVAIS", log=log.append)
    pont.demarrer()
    try:
        assert attendre(lambda: any("jeton refuse" in m for m in log)), log
        assert not ha.abonnes
        assert "MAUVAIS" not in "".join(log), "le jeton ne doit jamais etre ecrit dans les logs"
    finally:
        pont.stop()
        ha.arreter()
    print("jeton refuse : OK (message clair, aucune fuite du jeton, pas d'abonnement)")


def test_reconnexion():
    ha = mock_ha.MockHA(JETON)
    log = []
    pont = pont_ha.PontHA({**CFG, "url": ha.url, "url_ws": ha.url_ws}, JETON, log=log.append)
    pont.demarrer()
    try:
        assert attendre(lambda: ha.abonnes)
        anciens = list(ha.abonnes)
        for ws in anciens:                                            # coupure cote HA
            ws.close()
        assert attendre(lambda: any("connexion perdue" in m for m in log))
        # une NOUVELLE connexion abonnee (l'ancienne peut rester un instant dans l'ensemble)
        assert attendre(lambda: any(ws not in anciens for ws in list(ha.abonnes)), 8.0), "pas de reconnexion : " + str(log)
        ha.set_state("sensor.prusa_mk4s", "finished")
        assert attendre(lambda: pont.source() == ["impression_finie:MK4S"]), log
    finally:
        pont.stop()
        ha.arreter()
    print("reconnexion : OK")


def test_cerveau():
    """Les evenements maison declenchent bien les etats de reaction du cerveau (sans robot)."""
    class Client:
        def __init__(self):
            self.appels = []
        def notify(self, *a):
            self.appels.append(("notify",) + a)
        def request(self, methode, params=None, *a, **k):
            self.appels.append((methode, params))
            return {}
    c = Client()
    b = brain.Brain(c, seed=1)
    b.evenement("impression_finie:MK4S")
    b._traite_evenements()
    assert b.courant.nom == "celebre" and ("robot.sound", {"tag": "greet"}) in c.appels, (b.courant.nom, c.appels)
    b.evenement("impression_echec:Saturn")
    b._traite_evenements()
    assert b.courant.nom == "alerte" and ("robot.sound", {"tag": "alarm"}) in c.appels
    b._bascule("nap")                                                 # une alerte interrompt la sieste
    b.ctx.sitting = False
    b.evenement("impression_echec:MK4S")
    b._traite_evenements()
    assert b.courant.nom == "alerte"
    print("cerveau : OK (finie -> celebre + greet, echec -> alerte + alarm, l'alerte reveille)")


def test_config_et_verifier():
    """Format a sections : champs non remplis ignores, reactions par defaut, jeton jamais affiche ; --verifier."""
    import tempfile
    from pathlib import Path
    ha = mock_ha.MockHA(JETON)
    toml = f'''
[home_assistant]
url = "{ha.url}"
url_ws = "{ha.url_ws}"
token = "{JETON}"
[mqtt]
actif = true
hote = "127.0.0.1"
port = {ha.rest.server_address[1]}
[[imprimante]]
nom = "Prusa 1"
type = "prusalink"
entite = "sensor.prusa_1_etat"
[[imprimante]]
nom = "Prusa 2"
type = "prusalink"
entite = "A_REMPLIR"
[[imprimante]]
nom = "Saturn"
type = "elegoo"
entite = "sensor.saturn_etat"
reactions = {{ complete = "impression_finie" }}
'''
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "ha.toml"
        chemin.write_text(toml)
        cfg = pont_ha.lire_config(chemin)
    assert cfg["url"] == ha.url and [s["nom"] for s in cfg["surveillance"]] == ["Prusa 1", "Saturn"], cfg["surveillance"]
    assert cfg["ignorees"] == ["Prusa 2"]
    assert cfg["surveillance"][0]["reactions"]["finished"] == "impression_finie"      # defauts prusalink
    assert cfg["surveillance"][1]["reactions"] == {"complete": "impression_finie"}
    assert pont_ha.lire_jeton(cfg) == JETON
    assert pont_ha.lire_config(Path(__file__).parent / "ha.exemple.toml")["url"] is None   # le modele vide est refuse proprement
    ha.set_state("sensor.prusa_1_etat", "idle", {"friendly_name": "Prusa 1 etat"})
    ha.set_state("sensor.salon_temperature", "21", {"friendly_name": "Salon"})
    sortie = []
    res = pont_ha.verifier(cfg, JETON, log=sortie.append)
    assert res["rest"] and res["ws"] and res["mqtt"] is True and res["version"].endswith("mock"), res
    assert [e[0] for e in res["entites"]] == ["sensor.prusa_1_etat"], res["entites"]       # le capteur du salon n'est pas liste
    assert JETON not in "\n".join(sortie), "le jeton ne doit jamais apparaitre"
    mauvais = pont_ha.verifier(cfg, "MAUVAIS", log=sortie.append)
    assert not mauvais["rest"] and any("jeton refuse" in m for m in sortie)
    ha.arreter()
    print("config + verifier : OK (champs A_REMPLIR ignores, imprimantes listees, jeton jamais affiche, mauvais jeton explique)")


def test_calme():
    """Interrupteur calme : etat initial lu au demarrage, on/off -> evenements ; cerveau : sieste, silence, pas de promenade."""
    ha = mock_ha.MockHA(JETON)
    ha.set_state("input_boolean.microduck_calme", "on")             # deja actif au demarrage du pont
    pont = pont_ha.PontHA({**CFG, "url": ha.url, "url_ws": ha.url_ws, "interrupteur_calme": "input_boolean.microduck_calme"},
                          JETON, log=lambda m: None)

    pont.client._get = lambda chemin: ha.etats[chemin.rsplit("/", 1)[1]]
    pont.demarrer()
    try:
        assert attendre(lambda: ha.abonnes)
        assert pont.source() == ["calme_on"], "etat initial non applique"
        ha.set_state("input_boolean.microduck_calme", "off")
        assert attendre(lambda: pont.source() == ["calme_off"])
    finally:
        pont.stop()
        ha.arreter()

    class Client:
        def __init__(self):
            self.appels = []

        def notify(self, *a):
            self.appels.append(a)

        def request(self, methode, params=None, *a, **k):
            self.appels.append((methode, params))
            return {}
    c = Client()
    b = brain.Brain(c, seed=1)
    etat = {"safety": {"fallen": False}}
    b.evenement("calme_on")
    for _ in range(int(120 / 0.02)):                               # 2 minutes de mode calme
        b.tick(etat, 0.02)
    noms = {n for _, n, _, _ in b.journal}
    assert noms <= {"nap"}, noms
    b.evenement("impression_finie:MK4S")                            # une notification reste visible, mais muette
    b.tick(etat, 0.02)
    assert b.courant.nom == "celebre"
    assert not any(a[0] == "robot.sound" for a in c.appels), "aucun son en mode calme"
    b.evenement("calme_off")
    b.tick(etat, 0.02)
    assert not b.mode_calme
    print("mode calme : OK (etat initial lu, on/off, sieste prolongee, aucun son, notifications muettes)")


def test_accueil_familiarite():
    import tempfile
    from pathlib import Path
    from memoire import Memoire

    class Client:
        def __init__(self):
            self.sons = []

        def notify(self, *a):
            pass

        def request(self, methode, params=None, *a, **k):
            if methode == "robot.sound":
                self.sons.append(params["tag"])
            return {}
    with tempfile.TemporaryDirectory() as d:
        m = Memoire(Path(d) / "m.json")
        sons = []
        for _ in range(8):
            m.rencontre("chat")
            c = Client()
            b = brain.Brain(c, seed=1, extras={"chat": object(), "memoire": m})
            b.etats["regarde_chat"].entre(b)
            sons.append(c.sons[-1])
    assert sons[0] == "inquire" and sons[-1] == "coo" and "greet" in sons, sons
    print(f"accueil selon la familiarite : OK ({' -> '.join(dict.fromkeys(sons))} au fil des rencontres)")


if __name__ == "__main__":
    test_calme()
    test_accueil_familiarite()
    test_config_et_verifier()
    test_evenements()
    test_publication()
    test_jeton_refuse()
    test_reconnexion()
    test_cerveau()
    print("TOUS LES TESTS OK")
