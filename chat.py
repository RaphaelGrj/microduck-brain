#!/usr/bin/env python3
"""Veille du chat : detection YOLO a faible cadence sur la camera, transformee en EVENEMENTS pour le cerveau.

`SuiviChat` est la logique pure (testable sans camera ni reseau) ; `VeilleChat` est le fil qui lui donne les images.
Regles de vie (ROADMAP) : ne pas reagir a une detection isolee (confirmation sur plusieurs images), ne pas
insister (delai de grace entre deux reactions), ne reagir qu'a une NOUVELLE apparition (le chat doit avoir ete
absent un moment), et garder la derniere vue (position, instant) pour le regard et la memoire.

Branchement : brain.run(..., source=veille.source) ; l'evenement "chat" declenche deja l'etat `curious` du cerveau.
"""
import threading
import time


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
        self.nb_apparitions = 0                 # mémoire elementaire : combien de fois le chat est apparu

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
        if self.dernier_evenement is not None and now - self.dernier_evenement < self.delai_grace_s:
            return []                            # ne jamais insister
        self.dernier_evenement = now
        return ["chat"]


class VeilleChat(threading.Thread):
    def __init__(self, detecteur, grab_frame, periode_s=0.5, seuil=0.5, **suivi):
        super().__init__(daemon=True)
        self.detecteur, self.grab, self.periode_s, self.seuil = detecteur, grab_frame, periode_s, seuil
        self.suivi = SuiviChat(**suivi)
        self.evenements = []
        self.verrou = threading.Lock()
        self.actif = True

    def run(self):
        while self.actif:
            t0 = time.monotonic()
            try:
                objets = self.detecteur.detect(self.grab(), classes=("cat",), seuil=self.seuil)
                evts = self.suivi.mise_a_jour(objets)
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
