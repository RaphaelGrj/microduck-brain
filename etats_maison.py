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
        brain.ctx.silence = brain.mode_calme or getattr(brain, "discret", False)
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


class AutoTestReveil(Etat):
    """Auto-test au premier reveil de la journee (ROADMAP "Diagnostic / auto-surveillance") : sans bouger les jambes,
    il verifie ce que robotd dit de lui (boucle, bus, IMU), une trame ToF, une image camera (dans un fil : la requete
    HTTP ne doit pas bloquer la boucle), et que la tete SUIT ses consignes (lacet puis tangage : le joint doit avoir
    bouge d'au moins 60 % de la consigne). Verdict dans diagnostic.AutoTest -> Home Assistant ; un "chirp" si tout va
    bien, un "inquire" sinon (jamais d'alarme : ce n'est pas une urgence)."""
    nom = "autotest"
    AMPLITUDE = 0.3
    SUIVI_MIN = 0.6

    def entre(self, brain):
        import threading
        import diagnostic
        sante = brain.lit_sante()
        self.res = dict(diagnostic.verdict_sante(sante))
        self.res.update(diagnostic.verdict_batterie(sante, brain.diagnostic.batterie))
        tof = brain.ctx.extras.get("tof")
        if tof is None:
            self.res["tof"] = (False, "absent")
        self.camera = None
        test = brain.ctx.extras.get("camera_test")
        if test is not None:
            def essai():
                try:
                    self.camera = (bool(test()), "image recue")
                except Exception as e:
                    self.camera = (False, type(e).__name__)
            threading.Thread(target=essai, daemon=True).start()
        self.ref = {}
        self.fini = False

    def duree(self, brain):
        return 4.0

    def _joint(self, brain, i):
        j = (brain.ctx.state or {}).get("joints")
        return j[i] if j and len(j) > i else None

    def _suivi(self, brain, cle, i):
        avant, apres = self.ref.get(cle), self._joint(brain, i)
        if avant is None or apres is None:
            self.res[cle] = (False, "joint non lu")
        else:
            d = abs(apres - avant)
            self.res[cle] = (d >= self.SUIVI_MIN * self.AMPLITUDE, f"{d:.2f}/{self.AMPLITUDE} rad")

    def pas(self, brain, t):
        brain.ctx.move()
        a = self.AMPLITUDE
        if t < 0.6:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            self.ref["tete_lacet"], self.ref["tete_tangage"] = self._joint(brain, 7), self._joint(brain, 6)
            tof = brain.ctx.extras.get("tof")
            if tof is not None and brain.ctx.state is not None and t >= 0.3:
                lib = tof.libre(brain.ctx.state)
                self.res["tof"] = (lib is not None, f"{lib.get('n', 0)} obstacle(s)" if lib else "pas de trame")
        elif t < 1.6:
            brain.ctx.head((0.0, 0.0, a, 0.0))
        elif "tete_lacet" not in self.res:
            self._suivi(brain, "tete_lacet", 7)  # premiere trame apres 1,6 s, quelle que soit la cadence (10-50 Hz)
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
        elif t < 2.4:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            self.ref["tete_tangage"] = self._joint(brain, 6)
        elif t < 3.4:
            brain.ctx.head((0.0, a, 0.0, 0.0))
        else:
            if not self.fini:
                self.fini = True
                self._suivi(brain, "tete_tangage", 6)
                if brain.ctx.extras.get("camera_test") is not None:
                    self.res["camera"] = self.camera or (False, "pas de reponse")
                brain.diagnostic.autotest.termine(brain.diagnostic.mur(), self.res)
                ko = [k for k, v in self.res.items() if not v[0]]
                print(f"[{brain.t_global:6.1f}s] auto-test : {'OK' if not ko else 'ECHEC ' + ', '.join(ko)}", flush=True)
                brain.ctx.sound("inquire" if ko else "chirp")
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
