#!/usr/bin/env python3
"""Habitudes sonores de la maison (ROADMAP "Silence inhabituel a une heure ou la maison est d'ordinaire bruyante" et
"Rythme different semaine/week-end").

Logique pure : on lui signale chaque voix entendue (audio.py / robotd), elle tient par heure de la journee, separement
pour la semaine et le week-end, une moyenne glissante du nombre de voix par heure (sur les jours passes). Elle dit
ensuite si l'heure courante est d'habitude animee, et si le silence actuel est donc INHABITUEL. Tout reste sur le
canard (dictionnaire sauvegarde dans la memoire locale, memoire.py) ; seuls des compteurs, jamais de son.
"""
import time

POIDS_NOUVEAU_JOUR = 0.25          # moyenne glissante : un jour compte pour un quart
JOURS_MIN = 3                      # pas d'habitude avant 3 jours observes pour cette heure
ANIMEE_PAR_HEURE = 20.0            # au-dessus : heure "d'habitude animee"
SILENCE_S = 1800.0                 # 30 min sans une voix a une heure animee = silence inhabituel


class Habitudes:
    def __init__(self, donnees=None, horloge=time.localtime, sauver=None):
        """`donnees` : dict persistant (ex. memoire.donnees.setdefault("ambiance", {})), modifie sur place ; `sauver()` :
        appele a chaque heure cloturee (memoire.Memoire.sauver)."""
        self.d = donnees if donnees is not None else {}
        self.sauver = sauver
        self.d.setdefault("moyenne", {})            # "semaine:14" -> [moyenne voix/heure, jours observes]
        self.horloge = horloge
        self.heure_en_cours = None                  # (cle, jour de l'annee) de l'heure qu'on compte
        self.compte = 0
        self.derniere_voix = None                   # t_global de la derniere voix entendue

    def _cle(self, h=None):
        h = h or self.horloge()
        return ("weekend" if getattr(h, "tm_wday", 0) >= 5 else "semaine") + f":{h.tm_hour}"

    def _cloture(self):
        if self.heure_en_cours is None:
            return
        cle = self.heure_en_cours[0]
        m, n = self.d["moyenne"].get(cle, [0.0, 0])
        m = self.compte if n == 0 else (1 - POIDS_NOUVEAU_JOUR) * m + POIDS_NOUVEAU_JOUR * self.compte
        self.d["moyenne"][cle] = [m, n + 1]
        if self.sauver is not None:
            self.sauver()

    def avance(self):
        """A appeler regulierement : change d'heure si besoin (et cloture l'heure precedente)."""
        h = self.horloge()
        courante = (self._cle(h), getattr(h, "tm_yday", 0))
        if courante != self.heure_en_cours:
            self._cloture()
            self.heure_en_cours, self.compte = courante, 0

    def voix(self, t_global):
        self.avance()
        self.compte += 1
        self.derniere_voix = t_global

    def animee(self):
        """L'heure courante est-elle d'habitude animee (assez de jours observes) ?"""
        m, n = self.d["moyenne"].get(self._cle(), [0.0, 0])
        return n >= JOURS_MIN and m >= ANIMEE_PAR_HEURE

    def silence_inhabituel(self, t_global, t_debut_ecoute):
        """Silence de SILENCE_S a une heure d'habitude animee. `t_debut_ecoute` : depuis quand on ecoute (au demarrage,
        on n'a encore rien entendu : ce n'est pas un silence)."""
        depuis = self.derniere_voix if self.derniere_voix is not None else t_debut_ecoute
        return self.animee() and t_global - depuis >= SILENCE_S
