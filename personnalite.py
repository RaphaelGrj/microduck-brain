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

    # -- voix personnelle (ROADMAP "Motif sonore personnel qui derive legerement avec le temps") ------------------------
    # Les petits sons gratuits (coo, chirp, peck) ont chacun un poids : un son suivi d'une reaction humaine dans les
    # 30 s se renforce (il apprend ce qui attire l'attention de SA maison), et tous derivent un peu au hasard chaque
    # jour : deux canards finissent par ne pas "parler" pareil, et le meme canard change doucement avec les mois.
    SONS_PERSO = ("coo", "chirp", "peck")
    RENFORCE = 0.15
    DERIVE_JOUR = 0.05
    POIDS_MIN, POIDS_MAX = 0.3, 3.0

    def _poids_sons(self):
        return self.d.setdefault("sons", {s: 1.0 for s in self.SONS_PERSO})

    def choisit_son(self, rng):
        p = self._poids_sons()
        return rng.choices(self.SONS_PERSO, weights=[p[s] for s in self.SONS_PERSO])[0]

    def renforce_son(self, tag):
        p = self._poids_sons()
        if tag in p:
            p[tag] = min(self.POIDS_MAX, p[tag] + self.RENFORCE)

    def derive_sons(self, rng):
        """Une fois par jour : petite marche au hasard des poids."""
        p = self._poids_sons()
        for s in self.SONS_PERSO:
            p[s] = min(self.POIDS_MAX, max(self.POIDS_MIN, p[s] * (1.0 + rng.uniform(-self.DERIVE_JOUR, self.DERIVE_JOUR))))

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

    # -- curseurs de l'application (reglages.py « caractere ») : 0,5 = tel qu'il est ; 0 = au minimum, 1 = au maximum --
    reglage = {}

    def curseur(self, nom):
        v = self.reglage.get(nom, 0.5)
        return 0.2 + 1.6 * v                     # 0,2 .. 1,8 (1 au milieu)

    def bavardage(self):
        return 2.0 * self.reglage.get("bavard", 0.5)        # 0 : plus aucun petit son gratuit

    # -- effets (multiplicateurs ~ 1 autour de 0,5) --------------------------------------------------------------------
    def envie_promenade(self):
        return (0.5 + self.trait("curiosite")) * (1.5 - self.trait("prudence")) * self.curseur("joueur")

    def envie_taquiner(self):
        return (0.5 + self.trait("espieglerie")) * self.curseur("taquin")

    def patience_seul(self):
        """Multiplie le temps avant de s'ennuyer et d'aller chercher de la compagnie : un canard sociable y va plus tot."""
        return 1.5 - self.trait("sociabilite")
