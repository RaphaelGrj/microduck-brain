#!/usr/bin/env python3
"""Memoire persistante du canard (premiere brique de la memoire relationnelle, Phase 3).

Un fichier JSON local (hors depot : `~/.local/share/microduck/memoire.json`, ou MICRODUCK_MEMOIRE) qui retient, par
"etre" de la maison (chat, personne...) : nombre de rencontres, premiere et derniere rencontre, repartition par heure
(les habitudes), et une familiarite 0..1 qui monte a chaque rencontre et redescend lentement avec l'absence.
Ecriture atomique (fichier temporaire + rename) : une coupure ne corrompt pas la memoire.
"""
import json
import math
import os
import threading
import time
from pathlib import Path

CHEMIN_DEFAUT = Path(os.environ.get("MICRODUCK_MEMOIRE", Path.home() / ".local/share/microduck/memoire.json"))
DEMI_VIE_FAMILIARITE_J = 14.0      # sans rencontre, la familiarite est divisee par 2 en deux semaines
GAIN_RENCONTRE = 0.15              # chaque rencontre rapproche la familiarite de 1 de 15 %


class Memoire:
    def __init__(self, chemin=CHEMIN_DEFAUT, horloge=time.time):
        self.chemin = Path(chemin)
        self.horloge = horloge
        self.verrou = threading.Lock()
        try:
            self.donnees = json.loads(self.chemin.read_text())
        except (FileNotFoundError, ValueError):
            self.donnees = {"etres": {}}

    def _etre(self, nom):
        return self.donnees["etres"].setdefault(nom, {
            "rencontres": 0, "premiere": None, "derniere": None, "par_heure": [0] * 24, "familiarite": 0.0})

    def familiarite(self, nom):
        """Familiarite actuelle (avec l'oubli depuis la derniere rencontre)."""
        with self.verrou:
            e = self.donnees["etres"].get(nom)
            if not e or e["derniere"] is None:
                return 0.0
            jours = (self.horloge() - e["derniere"]) / 86400
            return e["familiarite"] * math.pow(0.5, jours / DEMI_VIE_FAMILIARITE_J)

    def rencontre(self, nom):
        """Note une rencontre (appele a chaque NOUVELLE apparition) et sauvegarde."""
        f = self.familiarite(nom)
        with self.verrou:
            now = self.horloge()
            e = self._etre(nom)
            e["rencontres"] += 1
            e["premiere"] = e["premiere"] or now
            e["derniere"] = now
            e["par_heure"][time.localtime(now).tm_hour] += 1
            e["familiarite"] = f + GAIN_RENCONTRE * (1.0 - f)
            self._sauver()
            return dict(e)

    def depart(self, nom):
        """Note qu'un habitant vient de partir (presence Home Assistant), pour mesurer son absence a son retour."""
        with self.verrou:
            self._etre(nom)["parti"] = self.horloge()
            self._sauver()

    def absence_s(self, nom):
        """Duree depuis son depart note (None si on ne l'a jamais vu partir, ou s'il est revenu depuis)."""
        e = self.donnees["etres"].get(nom)
        if not e or not e.get("parti") or (e["derniere"] or 0) > e["parti"]:
            return None
        return self.horloge() - e["parti"]

    def blague(self, nom):
        """Une taquinerie de plus (taquineries.py : running gag, trophee de malice) ; sauvegarde."""
        with self.verrou:
            b = self.donnees.setdefault("blagues", {})
            b[nom] = b.get(nom, 0) + 1
            self._sauver()

    def blagues(self):
        return dict(self.donnees.get("blagues", {}))

    def heure_habituelle(self, nom):
        """L'heure de la journee ou on le rencontre le plus souvent (None si jamais)."""
        e = self.donnees["etres"].get(nom)
        if not e or not e["rencontres"]:
            return None
        return max(range(24), key=lambda h: e["par_heure"][h])

    def _sauver(self):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.donnees, indent=1))
        os.replace(tmp, self.chemin)
