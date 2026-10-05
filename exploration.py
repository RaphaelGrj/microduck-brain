#!/usr/bin/env python3
"""Memoire d'exploration ("novelty grid" de la machine M9 officielle) : une grille de cases de 25 cm, dans le repere de
l'odometrie, qui retient ou le canard est deja passe (avec oubli progressif). Quand il part se promener, il choisit le
cap qui mene vers les cases les moins visitees : il explore la maison au lieu de tourner en rond.

Pure logique (testable sans robot) ; brain.py l'alimente avec state["odom"] et lui demande un cap.
"""
import math

CASE = 0.25                 # m
DEMI_VIE_S = 600.0          # une case visitee redevient "nouvelle" de moitie en 10 min
PORTEE = 1.0                # on juge un cap sur le premier metre devant
DEMI_VIE_OBSTACLE_S = 1800.0  # un meuble ne bouge pas souvent : on s'en souvient ~30 min
DEMI_VIE_CHUTE_S = 30 * 86400.0  # une "zone noire" (deja tombe ici) s'oublie tres lentement (~1 mois)


class Exploration:
    def __init__(self):
        self.visites = {}       # (i, j) -> (poids, instant de la derniere mise a jour)
        self.obstacles = {}     # (i, j) -> instant ou le ToF y a vu un obstacle
        self.chutes = {}        # (i, j) -> instant ou le canard est deja tombe ici ("zone noire" apprise,
                                 # ROADMAP "Occupation autonome..." : distincte de l'evitement ToF generique)

    def _poids(self, cle, t):
        v = self.visites.get(cle)
        if v is None:
            return 0.0
        return v[0] * math.pow(0.5, (t - v[1]) / DEMI_VIE_S)

    def noter(self, x, y, t):
        """Le canard est en (x, y) (odometrie) a l'instant t (s) : la case compte une visite de plus."""
        cle = (math.floor(x / CASE), math.floor(y / CASE))
        self.visites[cle] = (self._poids(cle, t) + 1.0, t)

    def obstacle(self, x, y, t):
        """Le capteur de distance voit un obstacle en (x, y) (odometrie)."""
        self.obstacles[(math.floor(x / CASE), math.floor(y / CASE))] = t

    def chute(self, x, y, t):
        """Le canard vient de tomber en (x, y) (derniere position connue avant la chute) : "zone noire" apprise,
        a eviter specifiquement, pas juste un obstacle detecte a chaque fois (ex. carrelage glissant, bord de
        tapis, marche) - voir ROADMAP "Occupation autonome et recherche d'attention"."""
        self.chutes[(math.floor(x / CASE), math.floor(y / CASE))] = t

    def _bloque(self, cle, t):
        v = self.obstacles.get(cle)
        if v is not None and math.pow(0.5, (t - v) / DEMI_VIE_OBSTACLE_S) > 0.5:
            return True
        v = self.chutes.get(cle)
        return v is not None and math.pow(0.5, (t - v) / DEMI_VIE_CHUTE_S) > 0.5

    def nouveaute(self, x, y, cap, t, portee=PORTEE):
        """Nouveaute moyenne (0..1) des cases traversees en partant de (x, y) vers `cap` (rad, repere odometrie).
        Un obstacle connu sur le chemin arrete le rayon : les cases derriere ne comptent pas, et le cap est penalise
        d'autant plus que l'obstacle est proche."""
        n, total = 0, 0.0
        vues = set()
        nb_pas = int(portee / (CASE / 2))
        for k in range(1, nb_pas + 1):
            d = k * CASE / 2
            cle = (math.floor((x + d * math.cos(cap)) / CASE), math.floor((y + d * math.sin(cap)) / CASE))
            if cle in vues:
                continue
            vues.add(cle)
            if self._bloque(cle, t):
                return (total / n if n else 0.0) * (k / nb_pas) * 0.5
            total += 1.0 / (1.0 + self._poids(cle, t))
            n += 1
        return total / n if n else 1.0

    def meilleur_ecart(self, x, y, cap, t, ecarts_deg=(-90, -60, -30, 0, 30, 60, 90)):
        """Ecart de cap (rad, relatif au cap actuel) vers la zone la plus nouvelle ; a nouveaute egale, le plus petit."""
        notes = [(self.nouveaute(x, y, cap + math.radians(e), t), -abs(e), e) for e in ecarts_deg]
        return math.radians(max(notes)[2])
