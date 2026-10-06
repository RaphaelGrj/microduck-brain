#!/usr/bin/env python3
"""Memoire persistante du canard (premiere brique de la memoire relationnelle, Phase 3).

Un fichier JSON local (hors depot : `~/.local/share/microduck/memoire.json`, ou MICRODUCK_MEMOIRE) qui retient, par
"etre" de la maison (chat, personne...) : nombre de rencontres, premiere et derniere rencontre, repartition par heure
(les habitudes), et une familiarite 0..1 qui monte a chaque rencontre et redescend lentement avec l'absence.
Ecriture atomique (fichier temporaire + rename) : une coupure ne corrompt pas la memoire.

Cout (mesure 2026-10-06, memoire de plusieurs mois ~60 Ko) : la mise en JSON COMPACTE prend ~1 ms sur PC (l'indentation
fait passer json.dumps sur l'encodeur Python pur : x4). Elle se fait dans le fil de l'appelant, sous le verrou, pour
une copie coherente ; avec `ecriture_differee` (canard.py), l'ecriture disque part dans un fil a part : la boucle a
50 Hz du cerveau ne l'attend jamais. Derniere ecriture a l'arret (atexit).
"""
import atexit
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
    def __init__(self, chemin=CHEMIN_DEFAUT, horloge=time.time, ecriture_differee=False):
        self.chemin = Path(chemin)
        self.horloge = horloge
        self.verrou = threading.Lock()
        self._a_ecrire = None                   # dernier texte JSON en attente d'ecriture (le plus recent gagne)
        self._cond = threading.Condition()
        self._verrou_ecriture = threading.Lock()   # une seule ecriture a la fois (fil ecrivain / vider a l'arret)
        self._differee = ecriture_differee
        if ecriture_differee:
            threading.Thread(target=self._ecrivain, daemon=True).start()
            atexit.register(self.fermer)
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

    def sauver(self):
        """Sauvegarde explicite (ex. habitudes.py a chaque heure cloturee)."""
        with self.verrou:
            self._sauver()

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
        for essai in range(3):
            try:
                texte = json.dumps(self.donnees, separators=(",", ":"))   # copie coherente, prise sous le verrou
                break
            except RuntimeError:                # le cerveau modifiait un dictionnaire pendant la copie (autre fil)
                if essai == 2:
                    return                      # la prochaine sauvegarde reussira
        if not self._differee:
            self._ecrire(texte)
            return
        with self._cond:
            self._a_ecrire = texte
            self._cond.notify()

    def _ecrire(self, texte):
        with self._verrou_ecriture:
            self._ecrire_fichier(texte)

    def _ecrire_fichier(self, texte):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.chemin.with_suffix(".tmp")
        tmp.write_text(texte)
        os.replace(tmp, self.chemin)

    def _prendre(self):
        with self._cond:
            texte, self._a_ecrire = self._a_ecrire, None
            return texte

    def _ecrivain(self):
        while True:
            with self._cond:
                while self._a_ecrire is None:
                    self._cond.wait()
            with self._verrou_ecriture:         # qui tient le verrou prend le texte : jamais deux ecritures a la fois
                texte = self._prendre()
                if texte is None:
                    continue                    # vider() l'a deja ecrit
                try:
                    self._ecrire_fichier(texte)
                except OSError:
                    pass                        # disque plein, carte retiree... la prochaine sauvegarde reessaiera

    def fermer(self):
        """Arret du cerveau : sauvegarde de l'etat ACTUEL (pas seulement ce qui attendait), ecrite tout de suite."""
        try:
            self.sauver()
        finally:
            self.vider()

    def vider(self):
        """Ecrit tout de suite ce qui attend, apres une ecriture deja en cours (arret du cerveau)."""
        with self._verrou_ecriture:
            texte = self._prendre()
            if texte is not None:
                self._ecrire_fichier(texte)
