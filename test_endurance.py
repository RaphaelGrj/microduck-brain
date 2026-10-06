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
              "alarme_fumee:Salon", "orage", "info", "toc_porte", "alarme_fumee:son", "commande:assis",
              "commande:debout", "commande:stop", "commande:bravo", "commande:danse", "commande:ecoute",
              "commande:pas_compris", "commande:reveil", "son_bref", "voix", "jeu_cache", "commande:trouve"]


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
        if method == "robot.move" and (params["vx"] or params["vyaw"]) and b.porte:
            self.violations.append((round(b.t_global, 1), b.courant.nom, "commande de marche dans les bras"))

    def request(self, method, params=None, **kw):
        b = self.b[0]
        # en mode calme, seule l'alarme incendie parle (etat alarme, ou dans les bras) : les autres "alarm" sont coupes
        if method == "robot.sound" and b.mode_calme and params["tag"] != "alarm":
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
    tombe_jusqua = porte_jusqua = -1.0
    while t < secondes:
        if t >= prochain:
            b.evenement(rng.choice(EVENEMENTS))
            prochain = t + rng.expovariate(1 / 40.0)
        if rng.random() < 1 / (20 * 60 / dt) and t > tombe_jusqua:
            tombe_jusqua = t + 3.0                  # une chute toutes les ~20 min
        if rng.random() < 1 / (15 * 60 / dt) and t > porte_jusqua and t > tombe_jusqua:
            porte_jusqua = t + rng.uniform(3.0, 30.0)  # pris dans les bras toutes les ~15 min
        fallen = t < tombe_jusqua
        b.tick({"t": t, "safety": {"fallen": fallen, "picked_up": t < porte_jusqua},
                "policy": None if fallen else "stand",
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
        assert getattr(b.ctx, "sons_refuses", 0) == 0, "un etat a voulu jouer un son qui n'est pas un son de canard"
        assert len({e[1] for e in b.journal}) >= 15, "trop peu d'etats visites : flux d'evenements mal branche ?"
        assert "porte" in {e[1] for e in b.journal}


def test_demarrage_sur_un_canard_assis():
    from test_brain import FauxClient
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=5)
    b.tick({"t": 0.0, "safety": {"fallen": False}, "policy": "sit"}, 0.02)
    assert b.ctx.sitting, "le cerveau doit savoir que le canard est deja assis"
    b.arret()
    assert not b.ctx.sitting and ("robot.do", {"skill": "sit_toggle"}) in c.appels


class TofAleatoire:
    """ToF factice dont la scene change toutes les quelques secondes : mur proche, bord de vide, main, rien."""
    def __init__(self, rng):
        self.rng, self.t, self.scene = rng, 0.0, None
        self.change()

    def change(self):
        self.scene = self.rng.choice(("rien", "mur", "vide", "main", "couloir"))

    def noter_etat(self, s):
        if self.rng.random() < 0.005:
            self.change()

    def points(self, s):
        return {"main": [(0.12, 0.0, 0.1)], "mur": [(0.35, 0.0, 0.1)]}.get(self.scene, [])

    def libre(self, s):
        return {"rien": {"devant": 3.0, "gauche": 3.0, "droite": 3.0, "vide": float("inf")},
                "mur": {"devant": 0.35, "gauche": 1.0, "droite": 0.6, "vide": float("inf")},
                "vide": {"devant": 0.25, "gauche": 2.0, "droite": 2.0, "vide": 0.25},
                "main": {"devant": 0.12, "gauche": 2.0, "droite": 2.0, "vide": float("inf")},
                "couloir": {"devant": 2.0, "gauche": 0.3, "droite": 0.3, "vide": float("inf")}}[self.scene] | {"n": 3}


class Leurre:
    """Veilles camera factices (balle, mouvement, chat) aux reponses aleatoires."""
    def __init__(self, rng):
        self.rng = rng
        self.suivi = type("S", (), {"visible": False})()
        self.estimation = None

    def position(self, age_max=1.5):
        return (0.12, 0.0) if self.rng.random() < 0.3 else None

    def armer(self):
        pass

    def desarmer(self):
        pass

    def a_bouge(self):
        return self.rng.random() < 0.01

    def cible_regard(self, h):
        return None


def test_endurance_tous_capteurs_jamais_vers_un_vide():
    for seed in (11, 12):
        rng = random.Random(seed)
        tof = TofAleatoire(rng)
        leurre = Leurre(rng)
        violations, marches = [], []
        ref = [None]

        class C(Client):
            def notify(self, method, params=None):
                b = self.b[0]
                if method == "robot.move" and params["vx"] > 0.25:
                    marches.append(b.courant.nom)
                    lib = tof.libre(None)
                    if lib["vide"] < 0.3:
                        violations.append((round(b.t_global, 1), b.courant.nom, "pas vers un vide"))

        c = C(ref)
        b = Brain(c, Humeur(energie=0.8), seed=seed, horloge=FauxHorloge(14),
                  extras={"tof": tof, "balle": leurre, "mouvement": leurre, "chat": leurre, "exploration": False})
        ref[0] = b
        b.presents.add("Raphael")
        t, prochain = 0.0, 5.0
        while t < 3600.0:
            if t >= prochain:
                b.evenement(rng.choice(EVENEMENTS))
                prochain = t + rng.expovariate(1 / 30.0)
            leurre.suivi.visible = rng.random() < 0.002 or (leurre.suivi.visible and rng.random() < 0.995)
            b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand", "battery": {"percent": 70.0},
                    "odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0}, "joints": [0.0] * 15}, 0.02)
            t += 0.02
        b.arret()
        assert not violations, violations[:5]
        assert len(marches) > 500, f"le test doit faire marcher le canard ({len(marches)} commandes)"
        assert not c.sons_en_calme, c.sons_en_calme[:5]
        assert not b.ctx.sitting
