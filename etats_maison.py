#!/usr/bin/env python3
"""La maison : alarme fumee / CO (prioritaire sur tout), tours sur demande (boutons Home Assistant).
"""
import math

import gestures
from etats_base import Etat, V_ROTATION


class AlarmeFumee(Etat):
    """Detecteur de fumee / CO (Home Assistant) : le canard donne l'alarme - son "alarm" toutes les 2 s pendant 20 s,
    tete dressee qui balaie. PRIORITAIRE sur tout : reveille la sieste, passe outre le silence du mode calme et une
    conversation vocale en cours (la securite des habitants avant la tranquillite)."""
    nom = "alarme"
    DUREE = 20.0

    def entre(self, brain):
        brain.ctx.silence = False
        self.n = 0

    def duree(self, brain):
        return self.DUREE

    def pas(self, brain, t):
        if t >= 2.0 * self.n:
            self.n += 1
            brain.ctx.sound("alarm")
        brain.ctx.head((0.0, -0.3, 0.5 * math.sin(2 * math.pi * t / 2.0), 0.0))
        brain.ctx.move()

    def sort(self, brain):
        brain.ctx.silence = brain.mode_calme
        brain.ctx.calme()

class Toupie(Etat):
    """Tour sur demande (bouton HA) : un tour complet sur lui-meme, a l'odometrie, puis un petit salut."""
    nom = "toupie"
    DUREE_MAX = 10.0

    def entre(self, brain):
        brain.ctx.sound("wheee")
        self.cumul, self.yaw_prec, self.fini = 0.0, None, None

    def duree(self, brain):
        return self.DUREE_MAX

    def pas(self, brain, t):
        o = (brain.ctx.state or {}).get("odom")
        if o is not None:
            if self.yaw_prec is not None:
                self.cumul += abs(math.remainder(o["yaw"] - self.yaw_prec, 2 * math.pi))
            self.yaw_prec = o["yaw"]
        if self.fini is None and (self.cumul >= 2 * math.pi - 0.3 or t >= self.DUREE_MAX - 2.0):
            self.fini = t
            brain.ctx.sound("chirp")
        brain.ctx.head((0.0, 0.0, 0.0, 0.0) if self.fini is None else gestures.oui(min(t - self.fini, 1.2)))
        brain.ctx.move(vyaw=V_ROTATION if self.fini is None else 0.0)
        if self.fini is not None and t - self.fini >= 1.4:
            brain.fin_etat = t

class AssisDemande(Etat):
    """Tour sur demande : "assis !" - il s'assoit (sit_toggle) et reste assis 20 s, ou jusqu'au bouton suivant."""
    nom = "assis_demande"

    def entre(self, brain):
        brain.ctx.sound("chirp")
        if not brain.ctx.sitting:
            brain.ctx.toggle_sit()

    def duree(self, brain):
        return 20.0

    def sur_evenement(self, brain, base):
        if base == "tour_assis":
            brain.fin_etat = brain.t_etat         # "debout !" : on se releve
            return True
        return False

    def pas(self, brain, t):
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))

    def sort(self, brain):
        if brain.ctx.sitting and not brain.reste_assis():
            brain.ctx.toggle_sit()
        brain.ctx.calme()
