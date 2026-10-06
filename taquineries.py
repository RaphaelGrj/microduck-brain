#!/usr/bin/env python3
"""Socle commun des taquineries (ROADMAP "Chantier suivant : taquiner l'humain").

Une taquinerie n'est drole que rare, breve, entre gens qui se connaissent, et elle s'arrete au premier "stop". Ce
module ne joue rien lui-meme : il dit au cerveau si une taquinerie est PERMISE maintenant, la note quand elle a lieu,
et garde la memoire des blagues (compteurs persistants) qui fait le "running gag" et le "trophee de malice".

Regles (toutes testees dans test_taquineries.py) :
  - budget : PAR_HEURE taquineries par heure au plus, ECART_MIN_S entre deux, jamais la meme deux fois de suite ;
    certaines ont leur propre budget (LIMITES : le "dernier mot" peut revenir plus souvent, mais pas en boucle) ;
  - seulement avec quelqu'un de familier (memoire.py, FAMILIARITE_MIN) : la familiarite du plus familier des presents
    (presence HA) ; une taquinerie declenchee par un geste humain (main tendue, appel) ne demande pas la presence HA,
    mais si des presents sont connus, l'un d'eux doit etre familier ;
  - jamais en mode calme, la nuit, pendant une conversation vocale, en veille apres des chutes, ni juste apres un
    accueil (on dit bonjour d'abord) ;
  - signal "stop" (bouton HA, "non" vocal, fin de jeu) : coupe la taquinerie en cours et les interdit STOP_S.
"""
import math

PAR_HEURE = 4
ECART_MIN_S = 300.0
FAMILIARITE_MIN = 0.6
APRES_ACCUEIL_S = 300.0
STOP_S = 1800.0
NUIT = (22, 8)                  # sans heures calmes configurees : pas de taquinerie de 22 h a 8 h
LIMITES = {"dernier_mot": (3, 600.0),     # nom -> (nombre max, fenetre s) ; hors budget general
           "pousse_balle": (2, 600.0),    # "une ou deux fois, pas une boucle sans fin"
           "compte_eternuements": (4, 120.0)}
RUNNING_GAG = 5                 # a partir de 5 fois la meme blague, il en est visiblement fier


class Malice:
    def __init__(self, memoire=None):
        self.memoire = memoire
        self.historique = []    # (t_global, nom)
        self.stop_jusqua = -1.0
        self.compteurs = {}     # si pas de memoire persistante

    # -- droits ----------------------------------------------------------------------------------
    def _nuit(self, brain):
        if brain.heures_calmes is not None:
            return False        # deja gere par le mode calme
        h = brain.horloge().tm_hour
        return h >= NUIT[0] or h < NUIT[1]

    def familiarite_presents(self, brain):
        if not brain.presents:
            return None
        if self.memoire is None:
            return 0.0
        return max(self.memoire.familiarite(qui) for qui in brain.presents)

    def permise(self, brain, nom, humain=False):
        """`humain` : declenchee par un geste humain (quelqu'un est donc la, meme sans presence HA)."""
        t = brain.t_global
        if brain.mode_calme or brain.reste_assis() or brain.tombe or brain.courant.nom in ("ecoute", "nap"):
            return False
        if getattr(brain, "discret", False) or (hasattr(brain, "timidite") and brain.timidite() > 0.0):
            return False        # quelqu'un telephone ; un visiteur inconnu : pas de blague
        if t < self.stop_jusqua or self._nuit(brain):
            return False
        if t - getattr(brain, "t_dernier_accueil", -1e9) < APRES_ACCUEIL_S:
            return False
        fam = self.familiarite_presents(brain)
        if fam is None and not humain:
            return False        # spontanee : il faut savoir que quelqu'un est la
        if fam is not None and fam < FAMILIARITE_MIN:
            return False
        if nom in LIMITES:
            n, fenetre = LIMITES[nom]
            return sum(1 for tt, nn in self.historique if nn == nom and t - tt < fenetre) < n
        generales = [(tt, nn) for tt, nn in self.historique if nn not in LIMITES]
        if generales and (generales[-1][1] == nom or t - generales[-1][0] < ECART_MIN_S):
            return False
        return sum(1 for tt, _ in generales if t - tt < 3600.0) < PAR_HEURE

    # -- memoire des blagues -----------------------------------------------------------------------
    def noter(self, brain, nom):
        self.historique = [(tt, nn) for tt, nn in self.historique if brain.t_global - tt < 3600.0] + [(brain.t_global, nom)]
        if self.memoire is not None and hasattr(self.memoire, "blague"):
            self.memoire.blague(nom)
        else:
            self.compteurs[nom] = self.compteurs.get(nom, 0) + 1

    def compte(self, nom=None):
        c = self.memoire.blagues() if self.memoire is not None and hasattr(self.memoire, "blagues") else self.compteurs
        return sum(c.values()) if nom is None else c.get(nom, 0)

    def fierte(self, nom):
        """0 si la blague n'est pas (encore) un running gag ; sinon 0.4..1, qui grandit avec le total des blagues
        reussies (trophee de malice : une fierte qui se construit sur l'historique, pas identique a chaque fois)."""
        if self.compte(nom) < RUNNING_GAG:
            return 0.0
        return min(1.0, 0.4 + 0.15 * math.log2(1 + self.compte() / RUNNING_GAG))

    # -- stop ----------------------------------------------------------------------------------------
    def stop(self, brain):
        self.stop_jusqua = brain.t_global + STOP_S
