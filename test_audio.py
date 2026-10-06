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


def parole(sig, debut, fin, rng=None):
    rng = rng or RNG
    t = debut
    while t < fin:
        d = rng.uniform(0.08, 0.25)
        n = int(d * TAUX)
        i = int(t * TAUX)
        sig[i:i + n] += rng.normal(0, 0.03, n) * np.hanning(n)
        t += d + rng.uniform(0.03, 0.15)


def test_discussion_longue_et_silences():
    s = fond(150)
    for k in range(15):                          # 10 s de discussion, 2 s de silence, en boucle
        parole(s, 1 + 10 * k, 9 + 10 * k)
    evts = noms(analyse(s))
    assert evts.count("discussion_longue") == 1, evts
    assert 3 <= evts.count("silence_conversation") <= 8, evts      # pas plus d'un toutes les 20 s
    assert "appel" not in evts and not any(e.startswith("musique") for e in evts), evts


def test_silence_sans_discussion_avant():
    s = fond(10)
    parole(s, 2.0, 3.0)                           # une seule seconde de voix
    assert "silence_conversation" not in noms(analyse(s))


def toc(sig, t, amplitude=0.15):
    """Coup sur une porte : bruit filtre grave (< 800 Hz), attaque nette, 25 ms."""
    n = int(0.06 * TAUX)
    i = int(t * TAUX)
    brut = RNG.normal(0, 1, n + 64)
    grave = np.convolve(brut, np.ones(24) / 24, mode="same")[:n]     # passe-bas grossier
    sig[i:i + n] += amplitude * 6 * grave * np.exp(-np.arange(n) / (0.012 * TAUX))


def test_on_frappe_a_la_porte():
    s = fond(5)
    for k in range(3):
        toc(s, 2.0 + 0.25 * k)
    evts = noms(analyse(s))
    assert evts == ["toc_porte"], evts


def bips(sig, debut, cycles, f=3200.0):
    """Motif T3 d'un detecteur de fumee : 3 bips de 0,5 s espaces de 0,5 s, puis 1,5 s de pause."""
    t = debut
    for _ in range(cycles):
        for _ in range(3):
            n = int(0.5 * TAUX)
            i = int(t * TAUX)
            sig[i:i + n] += 0.1 * np.sin(2 * np.pi * f * np.arange(n) / TAUX)
            t += 1.0
        t += 1.0


def test_alarme_incendie_entendue():
    s = fond(20)
    bips(s, 1.0, 4)
    evts = noms(analyse(s))
    assert evts.count("alarme_fumee:son") == 1, evts
    s = fond(10)
    bips(s, 1.0, 1)                                   # 3 bips (micro-ondes) : pas une alarme
    assert "alarme_fumee:son" not in noms(analyse(s))


# --- cerveau -------------------------------------------------------------------------------------------------------
from brain import Brain, Humeur  # noqa: E402
from test_brain import FauxClient, simule  # noqa: E402


def test_cerveau_reflexes_sonores():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=90)
    simule(b, 40, evenements=[(1.0, "appel"), (10.0, "applaudissements"), (20.0, "musique:120"), (30.0, "musique_fin")])
    j = [e for e in b.journal]
    noms_ = [e[1] for e in j]
    assert {"appel", "faux_endormi", "sourde_oreille"} & set(noms_), noms_      # repond, ou taquine (taquineries.py)
    assert "bravo" in noms_ and "danse" in noms_, noms_
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


def voix(sig, debut, duree, f0_debut, f0_fin, amplitude=0.06):
    """Enonce voise synthetique : 3 harmoniques, hauteur qui glisse lineairement."""
    n = int(duree * TAUX)
    t = np.arange(n) / TAUX
    f0 = f0_debut + (f0_fin - f0_debut) * t / duree
    phase = 2 * np.pi * np.cumsum(f0) / TAUX
    env = np.minimum(1.0, np.minimum(t, duree - t) / 0.05)
    i = int(debut * TAUX)
    sig[i:i + n] += amplitude * env * (np.sin(phase) + 0.5 * np.sin(2 * phase) + 0.3 * np.sin(3 * phase))


def test_intonation_monte_descend_plat():
    for f0a, f0b, attendu in ((150, 230, "intonation:monte"), (230, 150, "intonation:descend"), (180, 185, None)):
        s = fond(4)
        voix(s, 1.0, 1.2, f0a, f0b)
        evts = [e for e in noms(analyse(s)) if e.startswith("intonation")]
        assert evts == ([attendu] if attendu else []), (f0a, f0b, evts)


def eternuement(sig, t, amplitude=0.15, duree=0.3):
    n = int(duree * TAUX)
    i = int(t * TAUX)
    env = np.minimum(1.0, np.arange(n) / (0.004 * TAUX)) * np.exp(-np.arange(n) / (0.09 * TAUX))
    sig[i:i + n] += RNG.normal(0, 1, n) * amplitude * env


def test_eternuements_ni_claquement_ni_parole():
    s = fond(8)
    eternuement(s, 2.0)
    eternuement(s, 4.5)
    evts = noms(analyse(s))
    assert evts == ["eternuement", "eternuement"], evts
    s = fond(5)
    clap(s, 2.0)
    clap(s, 2.35)
    assert noms(analyse(s)) == ["appel"], "un claquement n'est pas un eternuement"


def test_baillement_entendu_mais_pas_une_phrase_qui_descend():
    s = fond(6)
    voix(s, 2.0, 2.4, 260, 120, amplitude=0.05)          # long, continu, qui descend d'une octave, apres un silence
    evts = noms(analyse(s))
    assert "baillement_entendu" in evts and not any(e.startswith("intonation") for e in evts), evts
    s = fond(6)
    voix(s, 1.0, 0.8, 200, 210)                          # en pleine conversation (0,5 s apres une phrase) :
    voix(s, 2.3, 2.4, 260, 120)                          # pas un baillement
    assert "baillement_entendu" not in noms(analyse(s))


def appel(voix_f0, duree_s=80.0, enonce_s=1.4, blanc_s=2.6):
    """Une personne au telephone : enonces voises, coupes de blancs (l'autre parle dans le combine)."""
    s = fond(duree_s)
    t, k = 1.0, 0
    while t + enonce_s < duree_s - 30:
        f0 = voix_f0[k % len(voix_f0)]
        voix(s, t, enonce_s, f0, f0 * 1.05)
        t += enonce_s + blanc_s
        k += 1
    return s


def test_telephone_une_seule_voix_avec_des_blancs():
    evts = noms(analyse(appel([180, 190, 175])))
    assert "telephone" in evts and evts.index("telephone_fin") > evts.index("telephone"), evts


def test_pas_telephone_quand_deux_personnes_parlent():
    assert "telephone" not in noms(analyse(appel([120, 230])))           # deux voix bien differentes en alternance


def bip(sig, t, duree=0.2, f=3200.0, amplitude=0.1):
    n = int(duree * TAUX)
    i = int(t * TAUX)
    sig[i:i + n] += amplitude * np.sin(2 * np.pi * f * np.arange(n) / TAUX)


def test_bips_d_appareil_mais_pas_l_alarme_incendie():
    s = fond(8)
    for k in range(3):
        bip(s, 1.0 + 0.5 * k)                              # micro-ondes : 3 bips puis plus rien
    evts = noms(analyse(s))
    assert evts == ["bips_appareil"], evts
    s = fond(20)
    t = 1.0
    while t < 17:
        for k in range(3):
            bip(s, t + 0.8 * k, duree=0.5)                 # T3 : 3 bips, pause, 3 bips...
        t += 3.9
    evts = noms(analyse(s))
    assert "alarme_fumee:son" in evts and "bips_appareil" not in evts, evts


def test_vacarme_prolonge_puis_retombe():
    s = np.concatenate([RNG.normal(0, 0.08, int(70 * TAUX)), fond(40)])     # une minute tres bruyante, puis le calme
    evts = noms(analyse(s))
    assert "vacarme" in evts and evts.index("vacarme_fin") > evts.index("vacarme"), evts
    assert "vacarme" not in noms(analyse(np.concatenate([RNG.normal(0, 0.08, int(20 * TAUX)), fond(60)]))), \
        "un bruit de 20 s n'est pas un vacarme"
