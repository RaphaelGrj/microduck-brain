#!/usr/bin/env python3
"""Lot « sans Home Assistant » : installation depuis le telephone, configuration dans l'appli (secrets jamais relus),
profil enfant, imprimantes suivies en direct (PrusaLink, SDCP par WebSocket)."""
import base64
import hashlib
import json
import socket
import struct
import threading
import time

import pytest

import appli
import configuration
import imprimantes
from test_appli import requete


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setattr(configuration, "CHEMIN_DEFAUT", tmp_path / "configuration.json")
    return tmp_path / "configuration.json"


def test_configuration_valide_et_secrets(config):
    assert configuration.ecrire("home_assistant", {"url": "http://ha.local:8123", "token": "JETON-SECRET"})
    assert configuration.ecrire("home_assistant", {"url": "ftp://x"}) is None
    configuration.ecrire("home_assistant", {"url": "http://ha.local:8123", "token": configuration.SECRET})
    assert configuration.lire()["home_assistant"]["token"] == "JETON-SECRET"      # « •••• » ne l'efface pas
    configuration.ecrire("habitant", [{"nom": "Raphaël", "entite": "person.raphael"}, {"nom": "raphaël"}, {"nom": ""},
                                      {"nom": "Clémence", "entite": "rm -rf /"}])
    assert configuration.lire()["habitant"] == [{"nom": "Raphaël", "entite": "person.raphael"}, {"nom": "Clémence"}]
    configuration.ecrire("imprimante_directe", [{"nom": "MK4S", "type": "prusalink", "adresse": "192.168.1.30", "cle_api": "K"},
                                                {"nom": "Cloud", "type": "prusalink", "adresse": "connect.prusa3d.com"},
                                                {"nom": "Saturn", "type": "sdcp", "adresse": "192.168.1.31"}])
    assert [i["nom"] for i in configuration.lire()["imprimante_directe"]] == ["MK4S", "Saturn"]
    vue = json.dumps(configuration.pour_appli(configuration.fusion({}, configuration.lire())), ensure_ascii=False)
    assert "JETON-SECRET" not in vue and '"K"' not in vue and configuration.SECRET in vue
    assert oct(config.stat().st_mode)[-3:] == "600"                         # le jeton est dans ce fichier


def test_fusion_avec_ha_toml():
    toml = {"home_assistant": {"url": "http://ancien:8123", "token": "T"}, "cerveau": {"nom": "Coin", "repas": ["12:30"]},
            "habitant": [{"nom": "X", "entite": "person.x"}]}
    brut = configuration.fusion(toml, {"cerveau": {"nom": "Riri", "garde": True}, "home_assistant":
                                       {"actif": False, "url": "http://ha:8123", "token": "T2"}})
    assert brut["cerveau"] == {"nom": "Riri", "repas": ["12:30"], "garde": True}      # cle par cle
    assert brut["habitant"] == toml["habitant"] and brut["home_assistant"]["url"] is None   # HA desactive


def test_installation_puis_profil_enfant(config):
    a = appli.Appli(None, port=0, log=lambda m: None)
    a.demarrer()
    try:
        assert json.loads(requete(a.port, "/api/sante", code=None)[1])["installation"] is True
        assert requete(a.port, "/api/etat", code="nimporte")[0] == 401
        assert requete(a.port, "/api/installation", code=None, corps={"code": "123"})[0] == 400
        assert requete(a.port, "/api/installation", code=None,
                       corps={"code": "canard-42", "nom": "Riri", "habitants": ["Raphaël", "Clémence"]})[0] == 200
        assert requete(a.port, "/api/installation", code=None, corps={"code": "pirate-99"})[0] == 403   # une fois
        assert configuration.lire()["cerveau"]["nom"] == "Riri" and a.code == "canard-42"
        time.sleep(1.1)
        statut, corps = requete(a.port, "/api/configuration", code="canard-42")
        assert statut == 200 and [h["nom"] for h in json.loads(corps)["habitant"]] == ["Raphaël", "Clémence"]
        r = json.loads(requete(a.port, "/api/configuration", code="canard-42",
                               corps={"section": "appli", "valeur": {"code": "canard-42", "code_enfant": "petit-canard"}})[1])
        assert r["ok"] and a.code_enfant == "petit-canard"
        assert requete(a.port, "/api/commande", code="petit-canard", corps={"commande": "jouer_balle"})[0] == 200
        assert requete(a.port, "/api/commande", code="petit-canard", corps={"commande": "avance"})[0] == 403
        assert requete(a.port, "/api/reglages", code="petit-canard")[0] == 403
        assert requete(a.port, "/api/sauvegarde", code="petit-canard")[0] == 403
        assert json.loads(requete(a.port, "/api/role", code="petit-canard")[1])["role"] == "enfant"
        assert requete(a.port, "/api/redemarrer", code="canard-42", corps={})[0] == 200 and a.redemarrage_demande
    finally:
        a.arreter()


def test_imprimantes_transitions():
    suite = iter(["inactive", "en_cours", "en_cours", "finie", "en_cours", "echec"])
    i = imprimantes.Imprimantes([{"nom": "MK4S", "type": "prusalink", "adresse": "192.168.1.30"}], log=lambda m: None,
                                lecteurs={"prusalink": lambda _: {"etat": next(suite), "progression": 50}})
    for _ in range(6):
        i.releve()
    assert i.source() == ["impression_finie:MK4S", "impression_echec:MK4S"]
    assert i.etat()[0]["etat"] == "echec" and i.etat()[0]["joignable"]

    def panne(_):
        raise OSError("eteinte")
    i.lecteurs["prusalink"] = panne
    i.releve()
    assert i.etat()[0]["joignable"] is False and i.source() == []


def test_sdcp_par_websocket(monkeypatch):
    """Une fausse Saturn (serveur WebSocket local) : le client minimal lit le statut pousse."""
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)
    port = serveur.getsockname()[1]

    def imprimante():
        c, _ = serveur.accept()
        req = c.recv(4096).decode()
        cle = [l.split(": ")[1] for l in req.split("\r\n") if l.lower().startswith("sec-websocket-key")][0]
        accepte = base64.b64encode(hashlib.sha1((cle + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        c.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Accept: {accepte}\r\n\r\n".encode())
        c.recv(4096)                                                  # la requete de statut (masquee)
        msg = json.dumps({"Status": {"PrintInfo": {"Status": 9, "CurrentLayer": 100, "TotalLayer": 100}}}).encode()
        c.sendall(struct.pack("!BBH", 0x81, 126, len(msg)) + msg)
        time.sleep(0.3)
        c.close()

    threading.Thread(target=imprimante, daemon=True).start()
    vrai = imprimantes._ws_ouvrir
    monkeypatch.setattr(imprimantes, "_ws_ouvrir", lambda hote, p, chemin, delai: vrai("127.0.0.1", port, chemin, delai))
    lu = imprimantes.lire_sdcp("192.168.1.31", delai=1.0)
    assert lu["etat"] == "finie" and lu["progression"] == 100
    serveur.close()


def test_tester_home_assistant_refuse_une_adresse_fausse():
    import pont_ha
    assert pont_ha.tester("pas-une-url", "x")[0] is False
    ok, message = pont_ha.tester("http://127.0.0.1:9", "x", delai=1.0)
    assert ok is False and "injoignable" in message


def test_rapport_sans_donnees_personnelles_et_mise_a_jour(tmp_path):
    from test_vie_maison import cerveau, vivre
    a = appli.Appli("canard-42", port=0, log=lambda m: None, version="abc1234 2026-10-06")
    a.brut = {"habitant": [{"nom": "Raphaël"}], "home_assistant": {"url": "http://ha:8123", "token": "SECRET-T"},
              "imprimante_directe": [{"nom": "MK4S du salon", "type": "prusalink", "adresse": "192.168.1.30"}]}
    a.fichier_mise_a_jour = tmp_path / "mise_a_jour"
    b, _, _ = cerveau()
    vivre(b, 1)
    b.presents = {"Raphaël"}
    a.photographier(b, {"battery": {"percent": 70.0}})
    a.sur_evenement("impression_finie:MK4S du salon")
    a.demarrer()
    try:
        statut, corps = requete(a.port, "/api/rapport", code="canard-42")
        texte = corps.decode()
        r = json.loads(texte)
        assert statut == 200 and r["cerveau"] == "abc1234 2026-10-06" and r["configuration"]["habitants"] == 1
        for prive in ("Raphaël", "Raphael", "MK4S", "salon", "192.168", "SECRET-T", "ha:8123"):
            assert prive not in texte, prive
        assert r["alertes"] == [{"t": r["alertes"][0]["t"], "type": "impression_finie"}]
        assert requete(a.port, "/api/mise-a-jour", code="canard-42", corps={"action": "installer", "branche": "x;rm -rf"})[0] == 400
        time.sleep(1.1)
        assert requete(a.port, "/api/mise-a-jour", code="canard-42", corps={"action": "installer", "branche": "main"})[0] == 200
        assert (tmp_path / "mise_a_jour").read_text() == "installer main\n" and a.redemarrage_demande
    finally:
        a.arreter()
