#!/usr/bin/env python3
"""Rythme visible (ROADMAP) : quelqu'un qui bouge en rythme avec la musique devant le canard -> il danse avec lui."""
import numpy as np

from brain import Brain, Humeur
from mouvement import rythme_correspond
from test_brain import FauxClient, simule

RNG = np.random.default_rng(0)


def mouvement(bpm_vrai, amplitude=0.02, duree=4.0, hz=10):
    """Fraction d'image qui change pour quelqu'un qui hoche/balance a `bpm_vrai` (vitesse sans signe : |sin|)."""
    t = np.arange(0, duree, 1 / hz) + RNG.normal(0, 0.01, int(duree * hz))
    f = amplitude * np.abs(np.sin(np.pi * t * bpm_vrai / 60)) + RNG.normal(0, 0.002, len(t))
    return list(zip(t, np.clip(f, 0, None)))


def test_rythme_reconnu_seulement_au_bon_tempo():
    for bpm in (90, 110, 128, 160):
        assert rythme_correspond(mouvement(bpm), bpm), bpm
        for k in (0.6, 0.77, 1.3):
            assert not rythme_correspond(mouvement(bpm * k), bpm), (bpm, k)
        assert not rythme_correspond(mouvement(bpm, amplitude=0.0), bpm), "personne ne bouge"
        hasard = list(zip(np.arange(0, 4, 0.1), np.abs(RNG.normal(0.01, 0.01, 40))))
        assert not rythme_correspond(hasard, bpm), "mouvement au hasard"
    assert not rythme_correspond(mouvement(110, duree=1.5), 110), "trop court pour juger"


class FausseVeille:
    def __init__(self, rythme):
        self.rythme, self.armements, self.arme = rythme, [], False

    def armer(self, periode_s=None):
        self.armements.append(periode_s)
        self.arme = True

    def desarmer(self):
        self.arme = False

    def a_bouge(self):
        return False

    def en_rythme(self, bpm):
        assert self.arme, "on juge le rythme sur ce qui a ete vu pendant l'armement"
        return self.rythme


def danse(rythme):
    c, veille = FauxClient(), FausseVeille(rythme)
    b = Brain(c, Humeur(energie=0.9), seed=21, extras={"mouvement": veille, "exploration": False})
    b.evenement("musique:110")
    simule(b, 3.5)
    assert b.courant.nom == "danse"
    tetes = [p for m, p in c.appels if m == "robot.head"]
    assert veille.arme and veille.armements == [0.1], "camera armee a 10 images/s, tete immobile"
    assert all(abs(p["head_pitch"]) < 1e-9 and abs(p["head_roll"]) < 1e-9 for p in tetes[-50:]), "il regarde sans bouger"
    simule(b, 6)
    assert not veille.arme, "detection desarmee une fois le rythme juge"
    return b, c


def sons(c):
    return [p["tag"] for m, p in c.appels if m == "robot.sound"]


def test_danse_avec_quelqu_un_en_rythme():
    b, c = danse(True)
    assert b.etats["danse"].ensemble and "wheee" in sons(c)
    assert max(p["head_pitch"] for m, p in c.appels if m == "robot.head") > 0.25, "hochements plus amples"


def test_danse_seul_sinon():
    b, c = danse(False)
    assert not b.etats["danse"].ensemble and "wheee" not in sons(c)
    assert 0.1 < max(p["head_pitch"] for m, p in c.appels if m == "robot.head") <= 0.2 + 1e-9


def test_sans_camera_il_danse_tout_de_suite():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=21, extras={"exploration": False})
    b.evenement("musique:110")
    simule(b, 2.5)
    assert b.courant.nom == "danse"
    assert max(p["head_pitch"] for m, p in c.appels if m == "robot.head") > 0.1


def test_musique_coupee_pendant_l_observation_desarme():
    c, veille = FauxClient(), FausseVeille(True)
    b = Brain(c, Humeur(energie=0.9), seed=21, extras={"mouvement": veille, "exploration": False})
    b.evenement("musique:110")
    simule(b, 2)
    b.evenement("musique_fin")
    simule(b, 3)
    assert b.courant.nom != "danse" and not veille.arme


def test_veille_mouvement_cadence_rapide_le_temps_d_un_armement():
    from mouvement import VeilleMouvement
    v = VeilleMouvement(lambda: None)
    v.historique.append((0.0, 0.1))
    v.armer(periode_s=0.1)
    assert v.periode_s == 0.1 and not v.historique
    v.desarmer()
    assert v.periode_s == 0.2
    v.armer()
    assert v.periode_s == 0.2
