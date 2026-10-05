#!/usr/bin/env python3
"""Tests des reflexes sonores (audio.py) sur des sons SYNTHETIQUES : silence bruite, claquements de mains (bruit bref a
decroissance rapide), choc tres fort, battement regulier sur fond musical, parole simulee (bouffees irregulieres)."""
import numpy as np

from audio import AnalyseurSon, BLOC, TAUX

RNG = np.random.default_rng(0)


def fond(secondes, niveau=0.003):
    return RNG.normal(0, niveau, int(secondes * TAUX))


def clap(sig, t, amplitude=0.12, decroissance=0.012):
    n = int(0.08 * TAUX)
    i = int(t * TAUX)
    env = amplitude * np.exp(-np.arange(n) / (decroissance * TAUX))
    sig[i:i + n] += RNG.normal(0, 1, n) * env


def analyse(sig, a=None):
    a = a or AnalyseurSon()
    out = []
    for k in range(0, len(sig) - BLOC + 1, BLOC):
        for e in a.bloc(sig[k:k + BLOC]):
            out.append((round(a.t, 2), e))
    return out


def noms(evts):
    return [e for _, e in evts]


def test_silence_rien():
    assert analyse(fond(20)) == []


def test_double_claquement_appel():
    s = fond(5)
    clap(s, 2.0)
    clap(s, 2.35)
    assert noms(analyse(s)) == ["appel"]


def test_un_seul_claquement_ignore():
    s = fond(5)
    clap(s, 2.0)
    assert analyse(s) == []


def test_applaudissements():
    s = fond(6)
    for k in range(8):
        clap(s, 1.0 + k * 0.22 + RNG.uniform(-0.03, 0.03))
    assert noms(analyse(s)) == ["applaudissements"]


def test_choc_fort_sursaut_une_seule_fois():
    s = fond(6)
    clap(s, 2.0, amplitude=0.9, decroissance=0.03)            # porte qui claque, objet qui tombe
    clap(s, 2.6, amplitude=0.9, decroissance=0.03)            # le rebond : pas un deuxieme sursaut
    assert noms(analyse(s)) == ["bruit"]


def test_musique_tempo_puis_fin():
    s = fond(16)
    t = np.arange(len(s)) / TAUX
    s[: int(12 * TAUX)] += 0.02 * np.sin(2 * np.pi * 220 * t[: int(12 * TAUX)])     # nappe musicale
    for k in range(int(12 / 0.5)):                                                     # grosse caisse a 120 BPM
        clap(s, 0.1 + k * 0.5, amplitude=0.25, decroissance=0.02)
    evts = analyse(s)
    musique = [e for e in noms(evts) if e.startswith("musique:")]
    assert len(musique) == 1 and abs(int(musique[0].split(":")[1]) - 120) <= 6, evts
    assert noms(evts)[-1] == "musique_fin", evts
    assert "appel" not in noms(evts) and "applaudissements" not in noms(evts), "les battements ne sont pas des claps"


def test_parole_irreguliere_ni_musique_ni_appel():
    s = fond(14)
    t = 0.5
    while t < 13:                                               # syllabes : bouffees de 80-250 ms, espacements irreguliers
        d = RNG.uniform(0.08, 0.25)
        n = int(d * TAUX)
        i = int(t * TAUX)
        s[i:i + n] += RNG.normal(0, 0.03, n) * np.hanning(n)
        t += d + RNG.uniform(0.05, 0.6)
    evts = noms(analyse(s))
    assert not any(e.startswith("musique") for e in evts) and "appel" not in evts, evts


# --- cerveau -------------------------------------------------------------------------------------------------------
from brain import Brain, Humeur  # noqa: E402
from test_brain import FauxClient, simule  # noqa: E402


def test_cerveau_reflexes_sonores():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=90)
    simule(b, 40, evenements=[(1.0, "appel"), (10.0, "applaudissements"), (20.0, "musique:120"), (30.0, "musique_fin")])
    j = [e for e in b.journal]
    noms_ = [e[1] for e in j]
    assert "appel" in noms_ and "bravo" in noms_ and "danse" in noms_, noms_
    debut = next(e[0] for e in j if e[1] == "danse")
    fin = next(e[0] for e in j if e[0] > debut)
    assert 29.5 <= fin <= 31.5, f"la danse doit s'arreter avec la musique ({debut} -> {fin})"
    hoche = [p["head_pitch"] for m, p in c.appels if m == "robot.head"]
    assert max(hoche) > 0.15


def test_danse_pas_un_juke_box():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=91)
    simule(b, 120, evenements=[(1.0, "musique:100"), (40.0, "musique_fin"), (60.0, "musique:100")])
    assert [e[1] for e in b.journal].count("danse") == 1, "deux danses en moins de 5 min"
