#!/usr/bin/env python3
"""Tests du jeu "1-2-3 soleil" (etat soleil de brain.py + mouvement.py), sans robot : odometrie qui integre les
consignes de rotation, veille mouvement et ToF factices, images synthetiques pour le detecteur."""
import math

import cv2
import numpy as np

from brain import Brain, Humeur
from mouvement import DetecteurMouvement
from test_brain import FauxClient


class FausseVeille:
    def __init__(self):
        self.arme, self.bouge, self.armements = False, False, 0

    def armer(self):
        self.arme, self.armements = True, self.armements + 1

    def desarmer(self):
        self.arme = False

    def a_bouge(self):
        return self.arme and self.bouge


class FauxTofDevant:
    def __init__(self):
        self.devant = 3.0

    def noter_etat(self, s):
        pass

    def libre(self, s):
        return {"devant": self.devant, "gauche": 3.0, "droite": 3.0, "vide": math.inf, "n": 5}


def simule(b, c, secondes, monde, t0=0.0, sur_trame=None):
    """monde = {"yaw": ...} : le canard tourne a 65 % de la consigne vyaw (ZONE_MORTE.md)."""
    for i in range(int(secondes / 0.02)):
        t = t0 + i * 0.02
        if sur_trame:
            sur_trame(b, t)
        moves = [p for m, p in c.appels[-6:] if m == "robot.move"]
        if moves:
            monde["yaw"] += 0.65 * moves[-1]["vyaw"] * 0.02
        b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [0.0, 0.0, 0.11], "yaw": monde["yaw"]}}, 0.02)


def nouveau(seed=60):
    c, veille, tof = FauxClient(), FausseVeille(), FauxTofDevant()
    b = Brain(c, Humeur(energie=0.9), seed=seed, extras={"mouvement": veille, "tof": tof, "exploration": False})
    b.fin_etat = 1e9
    return b, c, veille, tof


def sons(c):
    return [p["tag"] for m, p in c.appels if m == "robot.sound"]


def test_demi_tours_sans_derive_et_compte():
    # a chaque "regarde", le canard fait face au joueur (cap du debut, a ~20 deg pres) ; a chaque "compte", il lui
    # tourne le dos - et ca ne derive pas d'une manche a l'autre.
    b, c, veille, tof = nouveau()
    monde = {"yaw": 0.0}
    b.evenement("jeu_soleil")
    jeu, caps = b.etats["soleil"], {"compte": [], "regarde": []}
    for k in range(250):
        simule(b, c, 0.2, monde, t0=k * 0.2)
        if jeu.phase in caps and b.courant.nom == "soleil":
            caps[jeu.phase].append(abs(math.remainder(monde["yaw"], 2 * math.pi)))
    assert jeu.manche >= 3
    assert caps["regarde"] and max(caps["regarde"]) < math.radians(25), [math.degrees(x) for x in caps["regarde"]]
    assert caps["compte"] and min(caps["compte"]) > math.radians(150), [math.degrees(x) for x in caps["compte"]]
    assert veille.armements >= 3, "la detection doit s'armer a chaque fois qu'il regarde"
    assert sons(c)[0] == "greet" and sons(c).count("chirp") >= 2 and "inquire" in sons(c)


def test_vu_quand_ca_bouge():
    b, c, veille, tof = nouveau(61)
    monde = {"yaw": 0.0}
    veille.bouge = True
    b.evenement("jeu_soleil")
    simule(b, c, 20.0, monde)
    jeu = b.etats["soleil"]
    assert jeu.vus >= 1 and "alarm" in sons(c), sons(c)


def test_gagne_quand_le_joueur_arrive():
    b, c, veille, tof = nouveau(62)
    monde = {"yaw": 0.0}
    b.evenement("jeu_soleil")

    def arrive(b, t):
        tof.devant = 0.2 if t > 8.0 else 3.0     # pendant qu'il compte, le joueur s'approche
    simule(b, c, 40.0, monde, sur_trame=arrive)
    jeu = b.etats["soleil"]
    assert jeu.resultat == "gagne", (jeu.resultat, jeu.manche)
    assert "wheee" in sons(c) and b.courant.nom != "soleil"


def test_caresse_fait_gagner_et_fin_jeu_arrete():
    b, c, veille, tof = nouveau(63)
    monde = {"yaw": 0.0}
    b.evenement("jeu_soleil")
    simule(b, c, 5.0, monde)
    b.evenement("caresse")
    simule(b, c, 5.0, monde, t0=5.0)
    assert b.etats["soleil"].resultat == "gagne"
    assert "caresse" not in {e[1] for e in b.journal}, "la caresse est prise par le jeu"
    b2, c2, _, _ = nouveau(64)
    b2.evenement("jeu_soleil")
    simule(b2, c2, 3.0, {"yaw": 0.0})
    b2.evenement("fin_jeu")
    simule(b2, c2, 3.0, {"yaw": 0.0}, t0=3.0)
    assert b2.etats["soleil"].resultat == "arrete" and b2.courant.nom != "soleil"


def test_fin_apres_les_manches_et_jamais_sans_camera_ni_en_calme():
    b, c, veille, tof = nouveau(65)
    b.etats["soleil"].MANCHES_MAX = 2
    b.evenement("jeu_soleil")
    simule(b, c, 60.0, {"yaw": 0.0})
    assert b.etats["soleil"].resultat == "fini" and b.courant.nom != "soleil"
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=66)            # pas de camera
    b.evenement("jeu_soleil")
    simule(b, c, 2.0, {"yaw": 0.0})
    assert "soleil" not in {e[1] for e in b.journal}
    b, c, veille, tof = nouveau(67)
    b.evenement("calme_on")
    b.evenement("jeu_soleil")
    simule(b, c, 2.0, {"yaw": 0.0})
    assert "soleil" not in {e[1] for e in b.journal}


def _scene(rng):
    img = cv2.GaussianBlur((rng.random((640, 360, 3)) * 60 + 80).astype(np.uint8), (21, 21), 0)
    return img


def test_detecteur_mouvement_images_synthetiques():
    rng = np.random.default_rng(0)
    fond = _scene(rng)

    def bruit(img):
        return np.clip(img.astype(int) + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)

    def personne(x):
        img = fond.copy()
        cv2.rectangle(img, (x, 200), (x + 40, 330), (20, 20, 20), -1)
        return bruit(img)
    d = DetecteurMouvement()
    assert d.mise_a_jour(personne(150))[0] is False, "la premiere image est la reference"
    assert not any(d.mise_a_jour(personne(150))[0] for _ in range(10)), "une personne immobile ne bouge pas"
    bouge, fraction, centre = d.mise_a_jour(personne(165))
    assert bouge and 0.4 < centre[0] < 0.6, (bouge, fraction, centre)
    d.mise_a_jour(personne(165))
    eclaire = np.clip(personne(165).astype(int) + 15, 0, 255).astype(np.uint8)
    assert not d.mise_a_jour(eclaire)[0], "un changement de lumiere global n'est pas un mouvement"


# --- cache-cache lance par le canard ------------------------------------------------------------------------------
def _cache(seed=70):
    tof = FauxTofDevant()
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=seed, extras={"tof": tof, "exploration": False})
    b.fin_etat = 1e9
    return b, c, tof


def test_cache_cache_trouve_par_la_voix_ou_la_main():
    for trouve in ("commande:trouve", "caresse"):
        b, c, tof = _cache()
        b.evenement("jeu_cache")
        simule(b, c, 60, {"yaw": 0.0})
        jeu = b.etats["cache_cache"]
        assert b.courant.nom == "cache_cache" and jeu.phase == "cache" and b.ctx.sitting
        assert "peck" in sons(c), "des indices sonores pour le trouver a l'oreille"
        b.evenement(trouve)
        simule(b, c, 10, {"yaw": 0.0}, t0=60)
        assert jeu.resultat == "trouve" and "wheee" in sons(c) and not b.ctx.sitting, trouve
        assert b.courant.nom != "cache_cache"


def test_cache_cache_trouve_de_pres_ou_abandon():
    b, c, tof = _cache(71)
    b.evenement("jeu_cache")
    simule(b, c, 20, {"yaw": 0.0})
    tof.devant = 0.2                                   # quelqu'un s'est approche tout pres
    simule(b, c, 10, {"yaw": 0.0}, t0=20)
    assert b.etats["cache_cache"].resultat == "trouve"
    b, c, tof = _cache(72)
    b.evenement("jeu_cache")
    simule(b, c, 330, {"yaw": 0.0})
    assert b.etats["cache_cache"].resultat == "abandon" and not b.ctx.sitting


def test_cache_cache_jamais_sans_capteur_ni_en_calme():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=73)
    b.evenement("jeu_cache")
    simule(b, c, 5, {"yaw": 0.0})
    assert "cache_cache" not in {e[1] for e in b.journal}
    b, c, tof = _cache(74)
    b.evenement("calme_on")
    b.evenement("jeu_cache")
    simule(b, c, 5, {"yaw": 0.0})
    assert "cache_cache" not in {e[1] for e in b.journal}
