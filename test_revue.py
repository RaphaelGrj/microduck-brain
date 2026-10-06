#!/usr/bin/env python3
"""Non-regression des defauts trouves par la revue de code du 2026-10-06 (un test par defaut corrige)."""
import numpy as np
import pytest

from audio import AnalyseurSon, BLOC, TAUX, VoixPropre
from brain import Brain, Humeur
from test_brain import FauxClient, simule
from test_jeu_balle import cerveau as cerveau_balle


def sons(c):
    return [p["tag"] for m, p in c.appels if m == "robot.sound"]


def _tick(b, t, dt):
    b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand"}, dt)


@pytest.mark.parametrize("hz", [10, 50])
def test_son_une_fois_quelle_que_soit_la_cadence(hz):
    # avant : fenetre de temps -> 2-3 fois a 50 Hz, jamais a 10 Hz
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=1)
    b.fin_etat = 1e9
    n0 = len(sons(c))
    for k in range(hz * 2):
        b.son_une_fois("cle", "chirp")
        _tick(b, k / hz, 1.0 / hz)
    assert sons(c)[n0:].count("chirp") == 1
    b._bascule("chill")                         # nouvelle entree dans un etat : le son peut rejouer
    b.son_une_fois("cle", "chirp")
    assert sons(c)[n0:].count("chirp") == 2


def test_fin_jeu_arrete_le_jeu_de_balle():
    b, c, _ = cerveau_balle(None)
    b._bascule("balle")
    simule(b, 1)
    b.evenement("fin_jeu")
    simule(b, 0.1)
    assert b.etats["balle"].resultat == "arrete" or b.courant.nom != "balle"
    simule(b, 10)
    assert b.courant.nom != "balle", "fin_jeu doit sortir du jeu de balle"


def test_fin_jeu_arrete_le_cache_cache():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=3, extras={"exploration": False})
    b._bascule("cache_cache")
    simule(b, 2)
    b.evenement("fin_jeu")
    simule(b, 15)
    assert b.courant.nom != "cache_cache"


def test_chute_en_mode_calme_puis_releve_se_recale_debout_puis_se_rassoit():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=4)
    b.evenement("calme_on")
    simule(b, 20)
    assert b.ctx.sitting
    simule(b, 10, tombe_entre=(1.0, 4.0))       # renverse ; robotd le releve DEBOUT (policy stand)
    assert b.courant.nom == "nap"
    assert b.ctx.sitting, "remis debout par robotd, il doit se rasseoir pour sa sieste (etat assis resynchronise)"
    n = sum(1 for m, p in c.appels if m == "robot.do" and p == {"skill": "sit_toggle"})
    assert n >= 2, "un sit_toggle pour s'asseoir, un autre apres le relevement"


def test_camera_distante_refusee():
    from vision import grab_frame
    with pytest.raises(RuntimeError, match="distante"):
        grab_frame("http://192.168.1.20:8080/frame")


def test_voix_propre_rend_le_micro_sourd_pendant_le_son():
    t = [0.0]
    v = VoixPropre(horloge=lambda: t[0])
    assert not v.muet()
    v.parle("alarm")
    t[0] = 1.0
    assert v.muet()
    t[0] = 1.2 + VoixPropre.MARGE_S + 0.01
    assert not v.muet()


def test_bloc_muet_ne_declenche_rien():
    # le "wheee" ou l'alarm du canard lui-meme ne doivent ni declencher un sursaut, ni passer pour une alarme incendie
    a = AnalyseurSon()
    rng = np.random.default_rng(0)
    for _ in range(int(3 * TAUX / BLOC)):
        assert a.bloc(rng.normal(0, 0.003, BLOC)) == []
    t0 = a.t
    for _ in range(int(2 * TAUX / BLOC)):
        a.bloc_muet(BLOC)                       # le canard joue un son tres fort : rien n'est analyse
    assert a.t > t0
    evts = []
    for _ in range(int(2 * TAUX / BLOC)):
        evts += a.bloc(rng.normal(0, 0.003, BLOC))
    assert evts == [], evts
