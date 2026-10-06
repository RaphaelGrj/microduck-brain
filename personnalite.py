#!/usr/bin/env python3
"""Personnalite du canard : quatre traits lents, faconnes par sa vie (CLAUDE.md "systeme de personnalite / etat
d'emotion transverse" ; ROADMAP "Preferences et apprentissage non programme").

  curiosite    : monte quand il decouvre (objet nouveau, exploration) -> plus de promenades ;
  sociabilite  : monte avec les caresses et les accueils, baisse quand on l'ignore -> cherche la compagnie plus tot ;
  espieglerie  : monte avec les taquineries jouees, baisse a chaque "stop" -> taquine plus ou moins ;
  prudence     : monte apres une chute ou un sursaut -> se promene moins.

Chaque canard a un TEMPERAMENT DE BASE tire une fois pour toutes a sa premiere mise en route (deux canards ne sont pas
pareils) ; les traits s'en ecartent avec les experiences et y reviennent lentement (moitie du chemin en ~3 jours sans
nouvelle experience). Tout est sauvegarde sur le canard (memoire.py), rien n'est envoye ailleurs que des nombres a
Home Assistant. Les effets sont des multiplicateurs autour de 1 : un trait a 0,5 ne change rien au comportement.
"""
import math
import random

TRAITS = ("curiosite", "sociabilite", "espieglerie", "prudence")
DEMI_VIE_RETOUR_S = 3 * 86400.0      # retour vers le temperament de base
# experience -> {trait: variation}
EXPERIENCES = {
    "caresse": {"sociabilite": +0.02},
    "accueil": {"sociabilite": +0.01},
    "ignore": {"sociabilite": -0.02},
    "remarque": {"curiosite": +0.015},
    "promenade": {"curiosite": +0.002},
    "taquinerie": {"espieglerie": +0.006},
    "stop": {"espieglerie": -0.05},
    "chute": {"prudence": +0.03},
    "sursaut": {"prudence": +0.004},
    "jeu": {"espieglerie": +0.01, "sociabilite": +0.01},
    "gronde": {"espieglerie": -0.03, "sociabilite": -0.005},     # son nom dit sur un ton fache
    "calin": {"sociabilite": +0.01},                              # son nom dit sur un ton doux / chantonne
}


class Personnalite:
    def __init__(self, donnees=None, rng=None, sauver=None):
        """`donnees` : dict persistant (memoire.donnees.setdefault("personnalite", {})), modifie sur place. Sans `donnees`
        (pas de memoire : tests, essais), le temperament est NEUTRE (0,5 partout) : aucun effet sur le comportement."""
        persistant = donnees is not None
        self.d = donnees if persistant else {}
        self.sauver = sauver
        if "base" not in self.d:
            r = rng or random.Random()
            self.d["base"] = ({t: round(min(0.7, max(0.3, r.gauss(0.5, 0.08))), 3) for t in TRAITS} if persistant
                              else {t: 0.5 for t in TRAITS})
            self.d["traits"] = dict(self.d["base"])
        self.d.setdefault("traits", dict(self.d["base"]))
        self._t_retour = None

    def trait(self, nom):
        return self.d["traits"][nom]

    def vit(self, experience):
        for t, dv in EXPERIENCES.get(experience, {}).items():
            self.d["traits"][t] = min(1.0, max(0.0, self.d["traits"][t] + dv))

    def avance(self, t_global, periode_s=3600.0):
        """Une fois par heure environ : retour lent vers le temperament de base, puis sauvegarde."""
        if self._t_retour is None:
            self._t_retour = t_global
            return
        dt = t_global - self._t_retour
        if dt < periode_s:
            return
        self._t_retour = t_global
        k = 1.0 - math.pow(0.5, dt / DEMI_VIE_RETOUR_S)
        for t in TRAITS:
            v = self.d["traits"][t]
            self.d["traits"][t] = v + k * (self.d["base"][t] - v)
        if self.sauver is not None:
            self.sauver()

    # -- effets (multiplicateurs ~ 1 autour de 0,5) --------------------------------------------------------------------
    def envie_promenade(self):
        return (0.5 + self.trait("curiosite")) * (1.5 - self.trait("prudence"))

    def envie_taquiner(self):
        return 0.5 + self.trait("espieglerie")

    def patience_seul(self):
        """Multiplie le temps avant de s'ennuyer et d'aller chercher de la compagnie : un canard sociable y va plus tot."""
        return 1.5 - self.trait("sociabilite")
