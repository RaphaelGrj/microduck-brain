#!/usr/bin/env python3
"""Messages laisses au canard dans l'application : « dis a Clemence qu'il y a des crepes ».

Le canard ne dit pas de mots (regle d'identite) : quand la personne est la (retour a la maison, ou deja presente), il
le lui SIGNALE en sons de canard (« il y a du nouveau ») et l'application lui montre le texte. L'expediteur est prevenu
(alerte « Message transmis »). Gardes dans messages.json (sur le canard), 30 jours au plus.
"""
import json
import os
import time
import uuid
from pathlib import Path

CHEMIN_DEFAUT = None                    # (None : ~/.local/share/microduck/messages.json, lu a chaque appel)
MAX = 30
GARDE_S = 30 * 86400


def chemin_defaut():
    return Path(os.environ.get("MICRODUCK_MESSAGES", Path.home() / ".local/share/microduck/messages.json"))


def propre(v, n):
    return "".join(c for c in v if c.isprintable() and c not in "|:").strip()[:n] if isinstance(v, str) else ""


class Messages:
    def __init__(self, chemin=None, mur=time.time):
        self.chemin = Path(chemin) if chemin else (CHEMIN_DEFAUT or chemin_defaut())
        self.mur = mur
        try:
            self.liste = [m for m in json.loads(self.chemin.read_text()) if isinstance(m, dict) and m.get("id")]
        except (OSError, ValueError):
            self.liste = []

    def _sauver(self):
        limite = self.mur() - GARDE_S
        self.liste = [m for m in self.liste if m.get("t", 0) >= limite][-MAX:]
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.chemin.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.liste, ensure_ascii=False))
            os.replace(tmp, self.chemin)
        except OSError:
            pass

    def ajouter(self, pour, texte, de=""):
        """-> le message, ou None si incomplet."""
        pour, texte, de = propre(pour, 40), propre(texte, 280), propre(de, 40)
        if not pour or not texte:
            return None
        m = {"id": uuid.uuid4().hex[:12], "pour": pour, "texte": texte, "de": de or None, "t": round(self.mur()),
             "transmis": None}
        self.liste.append(m)
        self._sauver()
        return m

    def annuler(self, ident):
        avant = len(self.liste)
        self.liste = [m for m in self.liste if m["id"] != ident]
        self._sauver()
        return len(self.liste) != avant

    def transmis(self, ident):
        """-> le message transmis (pour l'alerte), ou None."""
        for m in self.liste:
            if m["id"] == ident and not m.get("transmis"):
                m["transmis"] = round(self.mur())
                self._sauver()
                return m
        return None

    def en_attente(self):
        return [m for m in self.liste if not m.get("transmis")]
