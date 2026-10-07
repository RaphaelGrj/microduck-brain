#!/usr/bin/env python3
"""Tests du lot "social" de brain.py : salut propre a chaque habitant, decouragement progressif, geste signature
quotidien, gene apres une chute devant quelqu'un, attente inquiete, refuge apres des detonations."""
import tempfile
import time
from pathlib import Path

import memoire
from brain import Accueil, Brain, Humeur
from test_brain import FauxClient, FauxHorloge, simule


def test_salut_propre_a_chaque_habitant_et_stable():
    assert Accueil.signature("Raphael") == Accueil.signature("Raphael")
    sigs = {Accueil.signature(n) for n in ("Raphael", "Camille", "Lea", "Tom", "Ines", "Hugo", "Zoe", "Max")}
    assert len(sigs) >= 3, "les habitants n'ont pas tous le meme salut"
    seq = Accueil.sequence(0.8, 3600, "Raphael")
    assert seq[0] == Accueil.signature("Raphael")
    assert Accueil.sequence(0.4, 3600, "Raphael")[0] == ("oui", "greet"), "signature seulement une fois familier"


def test_decouragement_progressif():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=300, horloge=FauxHorloge(15))
    b.presents.add("Raphael")
    b.P_SIGNATURE = b.P_ATTENTE = b.P_REGARD_MYSTERE = b.P_GAG = 0.0
    simule(b, 2500)                                   # 40 min sans que personne ne reponde
    noms = [e[1] for e in b.journal]
    assert noms.count("cherche_attention") == 2, noms.count("cherche_attention")
    apres = noms[noms.index("cherche_attention"):]
    assert "jeu_solitaire" in apres or "boude" in apres, "ignore deux fois : il s'occupe seul (ou il boude, vivant.py)"
    assert b.ignores >= 2
    b.evenement("caresse")
    simule(b, 1)
    assert b.ignores == 0, "une interaction efface le decouragement"


def test_geste_signature_une_fois_par_jour():
    c = FauxClient()
    horloge = FauxHorloge(15)
    b = Brain(c, Humeur(energie=0.9), seed=301, horloge=horloge)
    b.presents.add("Raphael")
    b.P_SIGNATURE = 1.0
    simule(b, 300)
    assert [e[1] for e in b.journal].count("signature") == 1
    horloge.jour += 1
    simule(b, 300)
    assert [e[1] for e in b.journal].count("signature") == 2


def test_gene_apres_une_chute_devant_quelqu_un():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=302)
    b.presents.add("Raphael")
    simule(b, 30, tombe_entre=(10.0, 13.0))
    noms = [e[1] for e in b.journal]
    assert "gene" in noms and noms[noms.index("gene") + 1] == "ebouriffe", noms
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=302)
    simule(b, 30, tombe_entre=(10.0, 13.0))
    assert "gene" not in [e[1] for e in b.journal], "seul, pas de gene"


def test_attente_inquiete_si_quelqu_un_tarde():
    with tempfile.TemporaryDirectory() as d:
        t = [time.time()]
        mem = memoire.Memoire(Path(d) / "m.json", horloge=lambda: t[0])
        mem.rencontre("Raphael")
        heure = time.localtime(t[0]).tm_hour            # il rentre d'habitude a cette heure-la
        mem.depart("Raphael")
        t[0] += 3 * 3600                                 # parti depuis 3 h
        c = FauxClient()
        b = Brain(c, Humeur(energie=0.9), seed=303, horloge=FauxHorloge((heure + 2) % 24), extras={"memoire": mem})
        b.P_ATTENTE = 1.0
        simule(b, 120)
        assert [e[1] for e in b.journal].count("attente") == 1, "une fois, puis pas avant 30 min"
        b2 = Brain(FauxClient(), Humeur(energie=0.9), seed=303, horloge=FauxHorloge((heure + 6) % 24),
                   extras={"memoire": mem})
        b2.P_ATTENTE = 1.0
        simule(b2, 120)
        assert "attente" not in [e[1] for e in b2.journal], "loin de son heure habituelle : pas d'inquietude"


def test_refuge_apres_des_detonations():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=304)
    simule(b, 30, evenements=[(1.0, "bruit"), (6.0, "bruit"), (12.0, "bruit")])
    noms = [e[1] for e in b.journal]
    assert noms.count("startle") == 3 and noms[noms.index("startle", noms.index("startle") + 1) + 2:].count("nap") >= 1, noms
