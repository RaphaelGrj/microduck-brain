#!/usr/bin/env python3
"""Jeu de balle autonome (etats_jeux.JeuBalle) avec un faux controleur d'approche : fete si la balle part, depit puis
regain de motivation si elle reste la, arret net devant un vide, jamais sans capteur de distance."""
import math
import time

from brain import Brain, Humeur
from test_brain import FauxClient, simule


class FausseApproche:
    crees = 0

    def __init__(self, client, tir_apres=40):
        FausseApproche.crees += 1
        self.c, self.n, self.tir_apres, self.etat = client, 0, tir_apres, "CHERCHER"
        self.vis = type("V", (), {"run_flag": True})()

    def pas(self, s):
        self.c.notify("robot.move", {"vx": 0.4, "vy": 0.0, "vyaw": 0.0})

    def etape(self, s):
        self.n += 1
        if self.n >= self.tir_apres:
            self.c.request("robot.do", {"skill": "kick_left"})
            self.etat = "FINI"


class Tof:
    def __init__(self):
        self.vide = math.inf

    def noter_etat(self, s):
        pass

    def libre(self, s):
        return {"devant": 1.0, "gauche": 2.0, "droite": 2.0, "vide": self.vide, "n": 1}


class VeilleBalle:
    def __init__(self, pos):
        self.pos = pos

    def position(self, age_max=1.5):
        return self.pos

    @property
    def estimation(self):
        """(t, x, y) comme balle.VeilleBalle : toujours une image plus recente que le tir."""
        return None if self.pos is None else (time.monotonic() + 1e6, self.pos[0], self.pos[1])


def cerveau(pos_apres_tir, seed=900):
    FausseApproche.crees = 0
    c, tof, veille = FauxClient(), Tof(), VeilleBalle(pos_apres_tir)
    b = Brain(c, Humeur(energie=0.9), seed=seed,
              extras={"tof": tof, "balle": veille, "exploration": False, "fabrique_approche": FausseApproche})
    b.fin_etat = 1e9
    return b, c, tof


def sons(c):
    return [p["tag"] for m, p in c.appels if m == "robot.sound"]


def test_balle_partie_fete():
    b, c, _ = cerveau(None)                            # apres le tir, plus de balle devant lui : partie au loin
    simule(b, 18, evenements=[(0.2, "jeu_balle")])  # (fete + tour de victoire eventuel)
    jeu = b.etats["balle"]
    assert jeu.resultat == "reussi" and "wheee" in sons(c) and ("robot.do", {"skill": "kick_left"}) in c.appels
    assert jeu.ap.vis.run_flag is False, "la camera du controleur est arretee a la fin"


def test_tir_rate_depit_puis_regain():
    b, c, _ = cerveau((0.12, 0.0), seed=901)           # la balle est toujours a ses pieds
    simule(b, 40, evenements=[(0.2, "jeu_balle")])
    jeu = b.etats["balle"]
    assert "coo" in sons(c), "soupir de depit"
    assert FausseApproche.crees >= 2, "regain de motivation : un nouvel essai"
    assert FausseApproche.crees <= jeu.MANCHES_MAX and jeu.resultat == "rate"


def test_vide_devant_arret_net():
    b, c, tof = cerveau(None, seed=902)
    simule(b, 0.4, evenements=[(0.1, "jeu_balle")])
    tof.vide = 0.2
    simule(b, 1.0)
    assert b.etats["balle"].resultat == "securite"
    dernier = [p for m, p in c.appels if m == "robot.move"][-1]
    assert dernier["vx"] == 0.0, "la commande du controleur est annulee"


def test_jamais_sans_capteur_ni_en_calme():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=903, extras={"fabrique_approche": FausseApproche})
    simule(b, 3, evenements=[(0.2, "jeu_balle")])
    assert "balle" not in {e[1] for e in b.journal}
    b, c, _ = cerveau(None, seed=904)
    b.evenement("calme_on")
    simule(b, 3, evenements=[(0.5, "jeu_balle")])
    assert "balle" not in {e[1] for e in b.journal}


def test_il_va_jouer_tout_seul_quand_il_voit_sa_balle():
    b, c, _ = cerveau((0.8, 0.1), seed=905)
    b.P_BALLE = 1.0
    b.fin_etat = 0.0
    simule(b, 30)
    assert "balle" in {e[1] for e in b.journal}


# --- M9 : Zoomies, GroundPick spontane --------------------------------------------------------------------------
def test_zoomies_en_pleine_forme_et_sans_danger():
    c, tof = FauxClient(), Tof()
    b = Brain(c, Humeur(energie=0.95, eveil=0.9), seed=910, horloge=__import__("test_brain").FauxHorloge(15),
              extras={"tof": tof, "exploration": False})
    b.P_ZOOMIES = 1.0
    b.fin_etat = 0.0
    simule(b, 12)
    assert "zoomies" in {e[1] for e in b.journal}
    sprints = [p["vx"] for m, p in c.appels if m == "robot.move" and p["vx"] > 0.45]
    assert sprints, "des sprints"
    c, tof = FauxClient(), Tof()
    tof.vide = 0.2
    b = Brain(c, Humeur(energie=0.95, eveil=0.9), seed=911, horloge=__import__("test_brain").FauxHorloge(15),
              extras={"tof": tof, "exploration": False})
    b._bascule("zoomies")
    simule(b, 3)
    assert not any(m == "robot.move" and p["vx"] > 0 for m, p in c.appels), "un vide devant : aucun sprint"


def test_picore_le_sol():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=912)
    b._bascule("picore")
    simule(b, 9)
    assert ("robot.do", {"skill": "ground_pick"}) in c.appels and "peck" in sons(c)
