#!/usr/bin/env python3
"""Endurance : 2 h simulees avec un flux aleatoire de TOUS les evenements que le cerveau connait, et les invariants de
securite verifies a chaque trame. Attrape les interactions entre fonctions que les tests unitaires ne voient pas."""
import random

from brain import Brain, Humeur
from test_brain import FauxHorloge

EVENEMENTS = ["bruit", "chat", "personne", "main", "caresse", "appel", "applaudissements", "musique:110", "musique_fin",
              "retour:Raphael|20000", "depart:Raphael", "impression_finie:MK4S", "impression_echec:MK4S",
              "sonnette:Entree", "machine_finie:Lave-linge", "jeu_soleil", "fin_jeu", "stop_taquinerie",
              "intonation:monte", "intonation:descend", "eternuement", "discussion_longue", "silence_conversation",
              "aspirateur_on", "aspirateur_off", "objet_approche", "meteo:rainy", "meteo:lightning", "meteo:sunny",
              "tour_salut", "tour_toupie", "tour_assis", "ecoute_on", "ecoute_off", "calme_on", "calme_off",
              "alarme_fumee:Salon", "orage", "info"]


class Client:
    """Faux robotd qui surveille les invariants a chaque commande."""
    def __init__(self, brain_ref):
        self.b = brain_ref
        self.violations = []
        self.sons_en_calme = []

    def notify(self, method, params=None):
        b = self.b[0]
        if method == "robot.move" and params["vx"] > 0.25 and b.ctx.extras.get("tof") is None:
            self.violations.append((round(b.t_global, 1), b.courant.nom, "marche sans capteur de distance"))

    def request(self, method, params=None, **kw):
        b = self.b[0]
        if method == "robot.sound" and b.mode_calme and b.courant.nom != "alarme":
            self.sons_en_calme.append((round(b.t_global, 1), b.courant.nom, params))
        return {"result": {"accepted": True}}


def _endurance(seed, secondes=7200.0):
    rng = random.Random(seed)
    ref = [None]
    c = Client(ref)
    b = Brain(c, Humeur(energie=0.6), seed=seed, horloge=FauxHorloge(14), extras={"exploration": False})
    ref[0] = b
    b.detecteur_main.main = (0.0, 0.12, 0.0, 0.1)
    t, dt = 0.0, 0.02
    prochain = rng.expovariate(1 / 40.0)
    tombe_jusqua = -1.0
    while t < secondes:
        if t >= prochain:
            b.evenement(rng.choice(EVENEMENTS))
            prochain = t + rng.expovariate(1 / 40.0)
        if rng.random() < 1 / (20 * 60 / dt) and t > tombe_jusqua:
            tombe_jusqua = t + 3.0                  # une chute toutes les ~20 min
        fallen = t < tombe_jusqua
        b.tick({"t": t, "safety": {"fallen": fallen}, "policy": None if fallen else "stand",
                "battery": {"percent": max(5.0, 90.0 - t / 100.0)},
                "odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0},
                "joints": [0.0] * 15}, dt)
        t += dt
    b.arret()
    return b, c


def test_endurance_deux_heures_invariants():
    for seed in (1, 2, 3):
        b, c = _endurance(seed)
        assert not c.violations, c.violations[:5]
        assert not c.sons_en_calme, c.sons_en_calme[:5]
        assert not b.ctx.sitting, f"seed {seed} : reste assis apres l'arret"
        assert len({e[1] for e in b.journal}) >= 15, "trop peu d'etats visites : flux d'evenements mal branche ?"


def test_demarrage_sur_un_canard_assis():
    from test_brain import FauxClient
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=5)
    b.tick({"t": 0.0, "safety": {"fallen": False}, "policy": "sit"}, 0.02)
    assert b.ctx.sitting, "le cerveau doit savoir que le canard est deja assis"
    b.arret()
    assert not b.ctx.sitting and ("robot.do", {"skill": "sit_toggle"}) in c.appels
