#!/usr/bin/env python3
"""Commandes vocales locales (commandes.py + brain.py) avec un faux reconnaisseur facon Vosk : grammaire, nom du canard
obligatoire, confiance, et reponses UNIQUEMENT en sons de canard."""
import json

import numpy as np

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


def voix_nom(f0_debut, f0_fin, amplitude, duree=0.5):
    t = np.arange(int(duree * 16000)) / 16000
    f0 = f0_debut + (f0_fin - f0_debut) * t / duree
    ph = 2 * np.pi * np.cumsum(f0) / 16000
    env = np.minimum(1.0, np.minimum(t, duree - t) / 0.03)
    return (amplitude * env * (np.sin(ph) + 0.5 * np.sin(2 * ph)) * 32767).astype(np.int16)


def appelle(c, son, t0):
    """Le nom dit pendant `son`, dans un flux de silence ; Vosk le reconnait a la fin avec ses instants."""
    silence = np.zeros(1600, dtype=np.int16)
    debut = c.lus / 16000 + 0.1
    flux = np.concatenate([silence, son, silence])
    c.reco.file.append(("daffy", 0.95))
    c.reco.mots = [{"word": "daffy", "conf": 0.95, "start": debut, "end": debut + len(son) / 16000}]
    return c.bloc_brut(flux.tobytes())


class FauxVoskInstants(FauxVosk):
    def Result(self):
        texte, conf = self.file.pop(0)
        return json.dumps({"text": texte, "result": self.mots})


def test_ton_du_nom_gronde_ou_calin():
    c = Commandes(lambda g: FauxVoskInstants(g), nom="daffy")
    for k in range(4):                                    # sa facon habituelle de l'appeler
        assert appelle(c, voix_nom(200, 190, 0.05), k) == ["commande:ecoute"]
    assert appelle(c, voix_nom(210, 180, 0.2), 5) == ["commande:ecoute", "ton:gronde"]     # fort, qui descend
    assert appelle(c, voix_nom(190, 260, 0.05), 6) == ["commande:ecoute", "ton:calin"]     # chantonne, qui monte
    assert appelle(c, voix_nom(200, 190, 0.05), 7) == ["commande:ecoute"]


def test_penaud_quand_on_le_gronde_cajole_quand_on_le_cajole():
    cl = FauxClient()
    b = Brain(cl, Humeur(energie=0.9), seed=5)
    simule(b, 1.05, evenements=[(1.0, "commande:ecoute")])
    n = len(cl.appels)
    simule(b, 4, evenements=[(0.05, "ton:gronde")])
    assert b.journal[-1][1] == "penaud" or "penaud" in [e[1] for e in b.journal]
    assert not any(m == "robot.sound" for m, _ in cl.appels[n:]), "penaud : pas un son"
    assert b.malice.stop_jusqua > b.t_global, "plus de blague apres une gronderie"
    assert b.perso.trait("espieglerie") < 0.5
    simule(b, 5, evenements=[(1.0, "ton:calin")])
    assert "cajole" in [e[1] for e in b.journal] and ("robot.sound", {"tag": "coo"}) in cl.appels


def test_pas_de_ton_avec_une_commande_et_reference_qui_s_adapte():
    c = Commandes(lambda g: FauxVoskInstants(g), nom="daffy")
    for k in range(4):
        appelle(c, voix_nom(200, 190, 0.05), k)
    # "daffy assis" dit fort : la commande seule, sans "ton:gronde" qui l'ecraserait
    son = voix_nom(210, 180, 0.2)
    silence = np.zeros(1600, dtype=np.int16)
    debut = c.lus / 16000 + 0.1
    c.reco.file.append(("daffy assis", 0.95))
    c.reco.mots = [{"word": "daffy", "conf": 0.95, "start": debut, "end": debut + len(son) / 16000},
                   {"word": "assis", "conf": 0.95, "start": debut + 0.5, "end": debut + 0.8}]
    assert c.bloc_brut(np.concatenate([silence, son, silence]).tobytes()) == ["commande:assis"]
    # le canard est maintenant plus pres : on l'appelle pareil, mais 6 dB plus fort au micro, durablement
    tons = [appelle(c, voix_nom(200, 190, 0.1), k) for k in range(12)]
    assert tons[-1] == ["commande:ecoute"], "la reference s'est adaptee : plus grondé a chaque appel"
