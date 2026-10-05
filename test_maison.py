#!/usr/bin/env python3
"""Tests du lot "maison" : alarme fumee, meteo, tours sur demande, toilette apres l'atelier (brain.py + pont_ha.py)."""
import math
import tempfile
from pathlib import Path

import pont_ha
from brain import Brain, Humeur
from test_brain import FauxClient, simule


def sons(c):
    return [p["tag"] for m, p in c.appels if m == "robot.sound"]


def test_pont_fumee_et_meteo():
    toml = """
[home_assistant]
url = "http://ha.local:8123"
[[appareil]]
nom = "Fumee"
type = "fumee"
entite = "binary_sensor.fumee_salon"
[[appareil]]
nom = "Meteo"
type = "meteo"
entite = "weather.maison"
"""
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "ha.toml"
        chemin.write_text(toml)
        cfg = pont_ha.lire_config(chemin)
    pont = pont_ha.PontHA(cfg, "J", log=lambda m: None)
    pont._sur_changement("binary_sensor.fumee_salon", "off", "on")
    pont._sur_changement("weather.maison", "sunny", "rainy")
    pont._sur_changement("weather.maison", "rainy", "unavailable")
    assert pont.source() == ["alarme_fumee:Fumee", "meteo:rainy"]
    assert {b[3] for b in pont_ha.PublieurMQTT.BOUTONS} >= {"tour_salut", "tour_toupie", "tour_assis"}


def test_alarme_prioritaire_meme_en_calme_et_en_sieste():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=200)
    simule(b, 5, evenements=[(0.5, "calme_on")])
    assert b.courant.nom == "nap" and b.ctx.silence
    simule(b, 25, evenements=[(0.5, "alarme_fumee:Salon")])
    assert sons(c).count("alarm") >= 8, "l'alarme doit sonner, meme en mode calme"
    assert b.ctx.silence, "apres l'alarme, le mode calme retrouve son silence"
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=201)
    simule(b, 3, evenements=[(0.5, "ecoute_on")])
    simule(b, 3, evenements=[(0.5, "alarme_fumee:Salon")])
    assert b.courant.nom == "alarme", "meme pendant une conversation vocale"


def test_meteo_reagit_au_changement_seulement():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=202)
    simule(b, 20, evenements=[(0.5, "meteo:rainy"), (5.0, "meteo:pouring"), (10.0, "meteo:rainy")])
    assert [e[1] for e in b.journal].count("meteo_curieux") == 1, "le debut de la pluie, pas chaque instant"
    simule(b, 30, evenements=[(0.5, "meteo:lightning-rainy")])
    noms = [e[1] for e in b.journal]
    assert "meteo_orage" in noms and noms[noms.index("meteo_orage") + 1] == "nap", noms
    assert b.MARCHE_PAR_METEO[b.meteo] < 1.0, "par orage, moins envie de se promener"


def test_tours_sur_demande():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=203)
    simule(b, 6, evenements=[(0.5, "tour_salut")])
    assert "salut" in [e[1] for e in b.journal]
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=204)
    monde = {"yaw": 0.0}
    b.evenement("tour_toupie")
    for i in range(int(12 / 0.02)):
        moves = [p for m, p in c.appels[-6:] if m == "robot.move"]
        if moves:
            monde["yaw"] += 0.65 * moves[-1]["vyaw"] * 0.02
        b.tick({"t": i * 0.02, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [0.0, 0.0, 0.11], "yaw": monde["yaw"]}}, 0.02)
    assert 2 * math.pi - 0.4 <= monde["yaw"] <= 2 * math.pi + 0.3, math.degrees(monde["yaw"])
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=205)
    simule(b, 5, evenements=[(0.5, "tour_assis")])
    assert b.ctx.sitting and b.courant.nom == "assis_demande"
    simule(b, 3, evenements=[(0.5, "tour_assis")])
    assert not b.ctx.sitting, "deuxieme appui : debout"
    b.evenement("calme_on")
    simule(b, 2, evenements=[(0.5, "tour_salut")])
    assert [e[1] for e in b.journal].count("salut") == 0, "rien en mode calme"


def test_toilette_apres_une_impression():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=206)
    b.P_TOILETTE = 1.0
    simule(b, 10, evenements=[(0.5, "impression_finie:MK4S")])
    noms = [e[1] for e in b.journal]
    assert noms[noms.index("celebre") + 1] == "lissage", noms


def test_alarme_et_porte_entendues_sans_home_assistant():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=210)
    simule(b, 25, evenements=[(0.5, "alarme_fumee:son")])
    assert "alarme" in [e[1] for e in b.journal] and sons(c).count("alarm") >= 8
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=211)
    simule(b, 6, evenements=[(0.5, "toc_porte")])
    assert "sonnette" in [e[1] for e in b.journal]
