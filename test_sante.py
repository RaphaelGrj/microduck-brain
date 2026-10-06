#!/usr/bin/env python3
"""Auto-preservation thermique (Brain._verifie_sante) : robot.health -> repos assis sans marche quand les servos
chauffent, halètement, retour a la normale avec hysteresis ; carte chaude -> veille camera en pause."""
from brain import Brain, Humeur
from test_brain import simule


class ClientSante:
    def __init__(self):
        self.moteurs, self.cpu, self.appels = 40.0, 55.0, []

    def notify(self, m, p=None):
        self.appels.append((m, p))

    def request(self, m, p=None, **kw):
        self.appels.append((m, p))
        if m == "robot.health":
            return {"result": {"healthy": True, "motors": {"hottest": "left_knee", "max_c": self.moteurs, "mean_c": 40},
                               "cpu_temp_c": self.cpu}}
        return {"result": {"accepted": True}}


class VeilleBalle:
    pause = False

    def position(self, age_max=1.5):
        return None


def test_servos_chauds_repos_assis_puis_reprise():
    c = ClientSante()
    b = Brain(c, Humeur(energie=0.95), seed=500, extras={"balle": VeilleBalle()})
    simule(b, 40)
    assert not b.surchauffe
    c.moteurs = 63.0
    simule(b, 40)
    noms = [e[1] for e in b.journal]
    assert b.surchauffe and "chaud" in noms and b.ctx.sitting
    n = len(b.journal)
    toggles = sum(1 for m, p in c.appels if m == "robot.do")
    simule(b, 200)
    assert {e[1] for e in b.journal[n:]} <= {"nap"}, "en surchauffe : seulement le repos"
    assert sum(1 for m, p in c.appels if m == "robot.do") == toggles, "il reste assis, sans se relever entre deux siestes"
    assert any(m == "robot.mouth" and p["open"] > 0.2 for m, p in c.appels), "il halete"
    c.moteurs = 55.0
    simule(b, 40)
    assert b.surchauffe, "hysteresis : 55 degres, pas encore refroidi"
    c.moteurs = 48.0
    simule(b, 80)
    assert not b.surchauffe and not b.ctx.sitting, "refroidi : il se releve et reprend sa vie"


def test_carte_chaude_met_la_camera_en_pause():
    c = ClientSante()
    veille = VeilleBalle()
    b = Brain(c, Humeur(energie=0.9), seed=501, extras={"balle": veille})
    c.cpu = 88.0
    simule(b, 35)
    assert veille.pause
    c.cpu = 70.0
    simule(b, 35)
    assert not veille.pause
