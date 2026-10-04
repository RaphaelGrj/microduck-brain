#!/usr/bin/env python3
"""Veille du chat : detection YOLO a faible cadence sur la camera, transformee en EVENEMENTS pour le cerveau, en
POSITION estimee (pour le regard) et en souvenirs (memoire.py).

`SuiviChat` est la logique pure (testable sans camera ni reseau) ; `VeilleChat` est le fil qui lui donne les images.
Regles de vie (ROADMAP) : ne pas reagir a une detection isolee (confirmation sur plusieurs images), ne pas
insister (delai de grace entre deux reactions), ne reagir qu'a une NOUVELLE apparition (le chat doit avoir ete
absent un moment), et garder la derniere vue (position, instant) pour le regard et la memoire.

Branchement (voir demo_chat.py) : brain.run(..., source=veille.source, a_chaque_tick=veille.etat_robot_hook,
extras={"chat": veille}) ; l'evenement "chat" fait passer le cerveau dans l'etat `regarde_chat`, qui suit le chat
des yeux par `robot.look` (le robot calcule lui-meme l'orientation de la tete).
"""
import threading
import time

import geometry

HAUTEUR_REGARD = 0.18          # on regarde ~18 cm au-dessus du sol (la tete d'un chat assis), pas ses pattes


class SuiviChat:
    def __init__(self, confirmations=2, absence_s=20.0, delai_grace_s=120.0, horloge=time.monotonic):
        self.confirmations = confirmations      # images consecutives avec un chat avant de le croire
        self.absence_s = absence_s              # absence necessaire pour qu'une revue compte comme une apparition
        self.delai_grace_s = delai_grace_s      # pas deux reactions plus rapprochees que ca
        self.horloge = horloge
        self.serie = 0
        self.visible = False
        self.derniere_vue = None                # (instant, Objet) de la derniere detection confirmee
        self.dernier_evenement = None
        self.nb_apparitions = 0
        self.sur_apparition = None              # rappel(instant) a chaque nouvelle apparition (memoire)

    def mise_a_jour(self, objets):
        """`objets` : detections 'cat' de la derniere image. Renvoie la liste des evenements a emettre (0 ou 1)."""
        now = self.horloge()
        if not objets:
            self.serie = 0
            if self.visible and self.derniere_vue and now - self.derniere_vue[0] > self.absence_s:
                self.visible = False            # le chat est parti
            return []
        self.serie += 1
        meilleur = max(objets, key=lambda o: o.score)
        if self.serie < self.confirmations:
            return []
        absent_avant = (not self.visible) or self.derniere_vue is None or now - self.derniere_vue[0] > self.absence_s
        self.derniere_vue = (now, meilleur)
        self.visible = True
        if not absent_avant:
            return []                            # il est toujours la : pas de nouvel evenement
        self.nb_apparitions += 1
        if self.sur_apparition:
            self.sur_apparition(now)
        if self.dernier_evenement is not None and now - self.dernier_evenement < self.delai_grace_s:
            return []                            # ne jamais insister
        self.dernier_evenement = now
        return ["chat"]


class VeilleChat(threading.Thread):
    def __init__(self, detecteur, grab_frame, periode_s=0.5, seuil=0.5, memoire=None, **suivi):
        super().__init__(daemon=True)
        self.detecteur, self.grab, self.periode_s, self.seuil = detecteur, grab_frame, periode_s, seuil
        self.suivi = SuiviChat(**suivi)
        if memoire is not None:
            self.suivi.sur_apparition = lambda t: memoire.rencontre("chat")
        self.evenements = []
        self.verrou = threading.Lock()
        self.actif = True
        self.etat_robot = None                   # derniere trame robot.state (pose de la camera), ecrite par le cerveau
        self.estimation = None                   # (instant, x, y) du chat au sol, repere du tronc, derniere vue

    def etat_robot_hook(self, brain, state):
        """A passer a brain.run(a_chaque_tick=...) : donne a la veille la pose courante de la camera."""
        self.etat_robot = state

    def run(self):
        while self.actif:
            t0 = time.monotonic()
            try:
                etat = self.etat_robot               # la pose AU MOMENT de la prise de vue (la tete bouge lentement)
                objets = self.detecteur.detect(self.grab(), classes=("cat",), seuil=self.seuil)
                evts = self.suivi.mise_a_jour(objets)
                if objets and etat is not None and self.suivi.visible:
                    o = max(objets, key=lambda q: q.score)
                    p = geometry.point_au_sol(o.pied[0], o.pied[1], etat["frames"]["camera"], etat["odom"]["position"][2])
                    if p is not None:
                        self.estimation = (time.monotonic(), float(p[0]), float(p[1]))
                if evts:
                    with self.verrou:
                        self.evenements += evts
            except Exception:
                pass                             # une image ratee ne doit pas arreter la veille
            time.sleep(max(0.0, self.periode_s - (time.monotonic() - t0)))

    def source(self):
        """A passer a brain.run(source=...)."""
        with self.verrou:
            out, self.evenements = self.evenements, []
        return out

    def cible_regard(self, hauteur_tronc, age_max=1.5):
        """Point a regarder (x, y, z repere du tronc) si le chat a ete localise recemment, sinon None."""
        e = self.estimation
        if e is None or time.monotonic() - e[0] > age_max:
            return None
        return e[1], e[2], HAUTEUR_REGARD - hauteur_tronc
