#!/usr/bin/env python3
"""Main tendue (ROADMAP, table Humains : "Main tendue | ToF (suivi de main) | Regard, approche, picore").

Logique pure, sans robot : on lui donne les points d'obstacle du capteur de distance (`tof.Tof.points` : (x, y, hauteur
au-dessus du sol) dans le repere du tronc) et elle dit quand une main vient d'etre tendue, et ou elle est.

Une main tendue n'est pas un mur : c'est quelque chose qui APPARAIT tout pres devant un canard IMMOBILE. Le meuble
devant lequel il se repose est la depuis longtemps (pas d'apparition) ; un mur dont il s'approche en marchant ne compte
pas (l'appelant ne donne des points que pendant les etats de repos et reinitialise l'historique sinon). Il faut aussi
que l'objet reste un moment (une patte de chat qui passe, un rayon bruite ne sont pas une main tendue) et on ne
reagit pas plus souvent que `delai_s` (ne jamais insister).

Pas d'apprentissage ni de vision : 64 rayons, des seuils. A valider sur le vrai robot (le simulateur n'a pas de main) :
portee utile du VL53L5CX a 5-30 cm, reflectivite de la peau, cadence reelle des trames.
"""
import math

ZONE_X = (0.04, 0.30)          # m devant le tronc : a portee de bec (au-dela, ce n'est pas "tendu vers lui")
ZONE_Y = 0.15                  # m de chaque cote
ZONE_H = (0.04, 0.30)          # m au-dessus du sol : une main, pas le sol ni le dessus d'un meuble
CLUSTER = 0.05                 # m : points a moins de 5 cm du plus proche = la meme main
ECART_APPARITION = 0.15        # il y a peu, le plus proche devant etait au moins 15 cm plus loin (ou rien)
FENETRE_APPARITION_S = 1.5
CONFIRMATION_S = 0.25          # presence continue avant d'y croire
PERTE_S = 0.6                  # au-dela sans la voir : la main est partie


class DetecteurMain:
    def __init__(self, delai_s=20.0):
        self.delai_s = delai_s
        self.reinitialiser()
        self.dernier_evenement = None

    def reinitialiser(self):
        """A appeler quand le canard bouge (marche, rotation) : l'historique "avant" ne veut plus rien dire."""
        self.historique = []    # (t, distance du plus proche devant ou inf)
        self.depuis = None      # instant de la premiere trame ou la main est vue (presence continue)
        self.apparue = False    # la presence en cours a commence par une apparition
        self.notifie = False    # l'evenement de cette presence a deja ete emis
        self.main = None        # (t, x, y, hauteur) derniere position vue

    def presente(self, t):
        return self.main is not None and t - self.main[0] <= PERTE_S

    def mise_a_jour(self, points, t):
        """`points` : liste de (x, y, h) ou None (pas de trame fraiche). Renvoie ["main"] a la confirmation d'une main
        nouvellement tendue, [] sinon."""
        if points is None:
            return []
        devant = [(x, y, h) for x, y, h in points if x > 0 and abs(y) <= ZONE_Y and ZONE_H[0] <= h <= ZONE_H[1]]
        proche = min((p for p in devant if ZONE_X[0] <= p[0] <= ZONE_X[1]), key=lambda p: p[0], default=None)
        d_min = min((p[0] for p in devant), default=math.inf)
        avant = [d for tt, d in self.historique if t - tt <= FENETRE_APPARITION_S]
        self.historique = [(tt, d) for tt, d in self.historique if t - tt <= FENETRE_APPARITION_S] + [(t, d_min)]
        if proche is None:
            if self.depuis is not None and (self.main is None or t - self.main[0] > PERTE_S):
                self.depuis, self.apparue = None, False
            return []
        groupe = [p for p in devant if math.dist(p, proche) <= CLUSTER]
        self.main = (t, *(sum(c) / len(groupe) for c in zip(*groupe)))
        if self.depuis is None:
            self.depuis = t
            self.apparue = any(d >= proche[0] + ECART_APPARITION for d in avant)
            self.notifie = False
        if (self.apparue and not self.notifie and t - self.depuis >= CONFIRMATION_S
                and (self.dernier_evenement is None or t - self.dernier_evenement >= self.delai_s)):
            self.notifie = True
            self.dernier_evenement = t
            return ["main"]
        return []
