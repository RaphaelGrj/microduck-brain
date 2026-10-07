#!/usr/bin/env python3
"""Etats lances depuis l'application (lot « jeux depuis le telephone ») : parcours d'obstacles et balle guidee
(Parcours), pose pour une photo (PosePhoto).

Memes garde-fous que la navigation vers un coin (navigation.py) : marche droite vers chaque point, capteur de distance
obligatoire, arret des qu'il n'y a plus de place devant. Pas de contournement : un point bloque met fin au parcours.
"""
import math

import gestures
from etats_base import TETE_PROMENADE, Etat
from etats_vie import VaAuCoin
from navigation import AllerVers


class Parcours(VaAuCoin):
    """Rejoindre une suite de points (repere de l'odometrie, poses sur la carte de l'appli), chronometre. Fini (ou
    abandonne) : il le dit a l'appli (« parcours_fini:<issue>|<duree>|<atteints>/<total> ») et enchaine sur `apres`
    (fierte si tout est atteint ; pour la balle guidee : le jeu de balle, qui la cherche a la camera)."""
    nom = "parcours"
    PAR_POINT_S = 25.0
    POINTS_MAX = 6
    ETAPE_MAX_M = 4.0           # au-dela, l'odometrie a trop derive pour viser juste

    def __init__(self):
        super().__init__("parcours", "fier", "faire son parcours")
        self.points, self.apres, self.genre = [], None, "parcours"

    def charger(self, points, genre="parcours"):
        self.points = list(points)[:self.POINTS_MAX]
        self.genre = genre
        self.apres = "balle" if genre == "balle" else None

    @classmethod
    def lire_points(cls, texte, depart):
        """"x,y;x,y" -> [(x, y)] ; None si illisible ou si une etape est trop longue (a partir de `depart`)."""
        points, prec = [], depart
        for morceau in (texte or "").split(";")[:cls.POINTS_MAX]:
            try:
                x, y = (float(v) for v in morceau.split(","))
            except ValueError:
                return None
            if not (math.isfinite(x) and math.isfinite(y)):
                return None
            if prec is not None and math.hypot(x - prec[0], y - prec[1]) > cls.ETAPE_MAX_M:
                return None
            points.append((round(x, 2), round(y, 2)))
            prec = (x, y)
        return points or None

    def entre(self, brain):
        self.i = 0
        self.cible = self.points[0]
        self.nav = AllerVers(self.cible)
        self.bloque_depuis = None
        self.issue = None
        brain.ctx.sound("chirp")                # « c'est parti ! »
        print(f"[{brain.t_global:6.1f}s] {self.genre} : {len(self.points)} point(s)", flush=True)

    def duree(self, brain):
        return self.PAR_POINT_S * len(self.points)

    def _fin(self, brain, t, pourquoi):
        brain.ctx.move()
        atteints = self.i + (1 if pourquoi == "arrive" else 0)
        self.issue = pourquoi
        reussi = atteints == len(self.points)
        if self.apres == "balle" and (brain.ctx.extras.get("balle") is None or brain.surchauffe):
            brain.suivant_force = "curious"     # sans camera, il ne peut pas la chercher : il regarde autour
        else:
            brain.suivant_force = self.apres or ("compliment" if reussi else "hesite")
        brain.fin_etat = t
        brain._previent(f"parcours_fini:{self.genre}|{'reussi' if reussi else pourquoi}|{t:.1f}|{atteints}/{len(self.points)}")

    def pas(self, brain, t):
        s = brain.ctx.state or {}
        o = s.get("odom")
        brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
        if t < 0.4 or o is None:
            brain.ctx.move()
            return
        if t >= brain.fin_etat - 0.05 and self.issue is None:
            return self._fin(brain, t, "trop_long")
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(s) if tof is not None else None
        statut, vx, vyaw = self.nav.commande(o["position"][0], o["position"][1], o["yaw"], lib)
        if statut == "arrive":
            if self.i + 1 >= len(self.points):
                return self._fin(brain, t, "arrive")
            self.i += 1                         # point suivant
            self.cible = self.points[self.i]
            self.nav = AllerVers(self.cible)
            brain.ctx.sound("peck")             # un point de passe
            brain.ctx.move()
            return
        if statut == "bloque":
            self.bloque_depuis = self.bloque_depuis if self.bloque_depuis is not None else t
            if t - self.bloque_depuis >= self.BLOQUE_MAX_S:
                return self._fin(brain, t, "bloque")
        else:
            self.bloque_depuis = None
        if statut == "pivote":
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
        brain.ctx.move(vx=vx, vyaw=vyaw)

    def sort(self, brain):
        if self.issue is None and self.points:  # interrompu (stop, alarme, chute...) : l'appli le saura
            self.issue = "interrompu"
            brain._previent(f"parcours_fini:{self.genre}|interrompu|{brain.t_etat:.1f}|{self.i}/{len(self.points)}")
        super().sort(brain)


class PosePhoto(Etat):
    """Mode photo : il prend la pose (le sommet d'un geste de gestures.py) et la TIENT immobile le temps de la photo,
    sans un son."""
    nom = "pose_photo"
    TENUE_S = 3.5
    POSES = ("content", "fier", "curieux", "oui", "surpris", "etirement", "ebouriffe", "gene")

    def __init__(self):
        self.geste = "fier"

    def entre(self, brain):
        self.d, self.fn = gestures.GESTES[self.geste]
        self.sommet = self.d / 2

    def duree(self, brain):
        return self.sommet + self.TENUE_S

    def pas(self, brain, t):
        brain.ctx.move()
        brain.ctx.head(self.fn(min(t, self.sommet)))


class Signal(Etat):
    """Minuteur fini, rappel, reveil doux (application) : il le signale en sons de canard, par cycles, jusqu'a ce qu'on
    l'arrete (bouton de l'appli, caresse, main tendue) ou au bout de CYCLES. Demande expres de l'habitant : il joue meme
    en mode calme ou pendant la sieste (comme une notification), jamais a terre, dans les bras ou pendant l'alarme.
    Le reveil monte doucement : roucoulements d'abord, puis pepiements, puis bonjour."""
    nom = "signal"
    PAUSE_S = 20.0
    SEQUENCES = {
        "minuteur": [[("surpris", "chirp"), ("oui", "chirp"), ("curieux", "inquire")]] * 3,
        "rappel": [[("curieux", "inquire"), ("oui", "chirp")]] * 2,
        "reveil": [[("fatigue", "coo"), ("etirement", "coo")], [("curieux", "chirp"), ("oui", "chirp")],
                   [("content", "greet"), ("oui", "wheee")]],
    }

    def __init__(self):
        self.genre, self.ident = "minuteur", ""

    def entre(self, brain):
        self.cycles = self.SEQUENCES.get(self.genre, self.SEQUENCES["rappel"])
        self.etapes, t = [], 0.0
        for k, cycle in enumerate(self.cycles):
            for geste, son in cycle:
                d, fn = gestures.GESTES[geste]
                self.etapes.append((t, d, fn, son))
                t += d + 0.3
            if k < len(self.cycles) - 1:
                t += self.PAUSE_S
        self.total, self.joues, self.arrete = t, set(), False

    def duree(self, brain):
        return self.total + 0.3

    def arreter(self, brain, comment):
        if not self.arrete:
            self.arrete = True
            brain._previent(f"signal_fin:{self.genre}|{self.ident}|{comment}")
            brain.fin_etat = brain.t_etat

    def au_repos(self, t):
        """Entre deux cycles, tete immobile depuis 1 s : une caresse peut y etre reconnue (elle l'arrete)."""
        return all(not (t0 - 0.2 <= t < t0 + d + 1.0) for t0, d, _, _ in self.etapes)

    def pas(self, brain, t):
        brain.ctx.move()
        tete = (0.0, 0.0, 0.0, 0.0)
        for i, (t0, d, fn, son) in enumerate(self.etapes):
            if t0 <= t < t0 + d:
                if i not in self.joues:
                    self.joues.add(i)
                    brain.ctx.sound(son, meme_en_silence=not brain.discret)   # (pas si quelqu'un telephone)
                tete = fn(t - t0)
        brain.ctx.head(tete)

    def sort(self, brain):
        self.arreter(brain, "fini")
        super().sort(brain)
