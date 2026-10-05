#!/usr/bin/env python3
"""Commandes vocales locales (commandes.py + brain.py) avec un faux reconnaisseur facon Vosk : grammaire, nom du canard
obligatoire, confiance, et reponses UNIQUEMENT en sons de canard."""
import json

from brain import SONS_CANARD, Brain, Humeur
from commandes import VOCABULAIRE, Commandes
from test_brain import FauxClient, simule


class FauxVosk:
    """Rend, a chaque AcceptWaveform, le prochain resultat de la file (ou rien)."""
    def __init__(self, grammaire):
        self.grammaire = json.loads(grammaire)
        self.file = []

    def AcceptWaveform(self, octets):
        return bool(self.file)

    def Result(self):
        texte, conf = self.file.pop(0)
        return json.dumps({"text": texte, "result": [{"word": m, "conf": conf} for m in texte.split()]})


def commandes(nom="daffy", t=None):
    t = t if t is not None else [0.0]
    c = Commandes(lambda g: FauxVosk(g), nom=nom, horloge=lambda: t[0])
    return c, t


def dit(c, texte, conf=0.95):
    c.reco.file.append((texte, conf))
    return c.bloc_brut(b"\0" * 640)


def test_grammaire_restreinte():
    c, _ = commandes()
    g = c.reco.grammaire
    assert "daffy assis" in g and "assis" in g and "daffy" in g and "[unk]" in g
    assert len(g) == 2 * len(VOCABULAIRE) + 2


def test_nom_obligatoire_et_traduction():
    c, t = commandes()
    assert dit(c, "daffy assis") == ["commande:assis"]
    assert dit(c, "assis") == [], "sans son nom : ce n'est pas a lui qu'on parle"
    assert dit(c, "daffy viens") == ["appel"]
    assert dit(c, "daffy on joue") == ["jeu_soleil"]
    assert dit(c, "daffy") == ["commande:ecoute"]
    t[0] = 1.5
    assert dit(c, "tourne") == ["tour_toupie"], "nom, pause, commande"
    t[0] = 10.0
    assert dit(c, "tourne") == [], "trop longtemps apres le nom"


def test_pas_compris():
    c, _ = commandes()
    assert dit(c, "daffy assis", conf=0.3) == ["commande:pas_compris"]
    assert dit(c, "[unk]") == [] and dit(c, "") == []


def test_le_cerveau_repond_en_sons_de_canard():
    for phrase in VOCABULAIRE:
        c, _ = commandes()
        evts = dit(c, f"daffy {phrase}")
        client = FauxClient()
        b = Brain(client, Humeur(energie=0.9), seed=7)
        simule(b, 8, evenements=[(0.5, e) for e in evts])
        sons = {p["tag"] for m, p in client.appels if m == "robot.sound"}
        assert sons <= SONS_CANARD, (phrase, sons)
        assert getattr(b.ctx, "sons_refuses", 0) == 0


def test_commandes_dans_le_cerveau():
    client = FauxClient()
    b = Brain(client, Humeur(energie=0.9), seed=8)
    simule(b, 6, evenements=[(0.5, "commande:assis")])
    assert b.ctx.sitting and b.courant.nom == "assis_demande"
    simule(b, 3, evenements=[(0.5, "commande:debout")])
    assert not b.ctx.sitting
    simule(b, 5, evenements=[(0.5, "commande:bravo"), (3.0, "commande:pas_compris")])
    noms = [e[1] for e in b.journal]
    assert "compliment" in noms and "hesite" in noms
    b.evenement("calme_on")
    simule(b, 3)
    simule(b, 3, evenements=[(0.5, "commande:assis")])
    assert b.courant.nom == "nap", "en mode calme, seul 'reveille-toi' compte"
    simule(b, 3, evenements=[(0.5, "commande:reveil")])
    assert not b.mode_calme
