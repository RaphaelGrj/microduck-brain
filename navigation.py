#!/usr/bin/env python3
"""Aller vers un point connu (repere de l'odometrie) : la brique qui manquait pour le coin favori (ROADMAP, "pas de
navigation vers un point dans brain.py").

Pas de planification : le canard pivote vers le point, puis marche droit dessus, en re-pivotant quand le cap derive.
Contraintes de la politique de marche (ZONE_MORTE.md) : rotation seulement a |vyaw| >= 1,2, marche a vx >= 0,3, pas
de correction fine par le corps -> un "pivote puis marche" avec hysteresis (sinon il oscille entre les deux), et une
arrivee a 25 cm pres (resolution reelle ~2-3 cm, mais la derive de l'odometrie est bien plus grande). Securite : le
capteur de distance doit voir de la place devant (comme la promenade), sinon on s'arrete et l'appelant abandonne -
pas de contournement d'obstacle ici.

Limite assumee : l'odometrie derive (glissements, tapis) et repart de zero quand robotd redemarre ; un point appris
plus tot dans la meme session reste approximatif. Des balises UWB (ROADMAP Phase 4) donneraient un vrai repere.
"""
import math

ARRIVEE_M = 0.25
CAP_PIVOT = math.radians(25)      # au-dela, on s'arrete pour pivoter
CAP_REPRISE = math.radians(35)    # en marchant, on tolere jusque-la avant de re-pivoter (hysteresis)
CAP_ALIGNE = math.radians(10)     # un pivot commence va jusque-la (sinon il repart au bord et re-pivote aussitot)
V_MARCHE, V_PIVOT = 0.4, 1.5
LIBRE_MIN = 0.45


class AllerVers:
    def __init__(self, cible):
        self.cible = cible
        self.marche = False
        self.pivot = False

    def commande(self, x, y, yaw, libre):
        """-> (statut, vx, vyaw) ; statut : "arrive", "bloque" (obstacle ou capteur muet), "pivote", "avance".
        `libre` : resultat de tof.Tof.libre (ou None si pas de trame)."""
        dx, dy = self.cible[0] - x, self.cible[1] - y
        if math.hypot(dx, dy) <= ARRIVEE_M:
            self.marche = False
            return "arrive", 0.0, 0.0
        ecart = math.remainder(math.atan2(dy, dx) - yaw, 2 * math.pi)
        seuil = CAP_ALIGNE if self.pivot else (CAP_REPRISE if self.marche else CAP_PIVOT)
        if abs(ecart) > seuil:
            self.marche, self.pivot = False, True
            return "pivote", 0.0, math.copysign(V_PIVOT, ecart)
        self.pivot = False
        if libre is None or libre["devant"] < LIBRE_MIN:
            self.marche = False
            return "bloque", 0.0, 0.0
        self.marche = True
        return "avance", V_MARCHE, 0.0
