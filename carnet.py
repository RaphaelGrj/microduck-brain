#!/usr/bin/env python3
"""Carnet d'entretien du canard (application) : pieces changees, coques imprimees (liees au catalogue), servos et
batteries remplaces, nettoyages... Garde SUR le canard (carnet.json), compris dans la sauvegarde.

Un servo ou une batterie notes « remplaces » repartent d'une mesure neuve dans le diagnostic (diagnostic.py) : la piece
neuve n'est pas comparee a l'ancienne.
"""
import json
import os
import time
import uuid
from pathlib import Path

from diagnostic import SERVOS

TYPES = ("piece", "impression", "servo", "batterie", "nettoyage", "autre")
MAX = 300


def chemin_defaut():
    return Path(os.environ.get("MICRODUCK_CARNET", Path.home() / ".local/share/microduck/carnet.json"))


def _texte(v, n):
    return "".join(c for c in v if c.isprintable()).strip()[:n] if isinstance(v, str) else ""


def valider(e):
    """Entree envoyee par l'appli -> forme propre, ou None."""
    if not isinstance(e, dict) or e.get("type") not in TYPES:
        return None
    propre = {"type": e["type"], "texte": _texte(e.get("texte"), 200)}
    date = _texte(e.get("date"), 10)
    propre["date"] = date if len(date) == 10 and date[4] == "-" and date[7] == "-" and date.replace("-", "").isdigit() \
        else time.strftime("%Y-%m-%d")
    if e["type"] == "servo":
        if e.get("servo") not in SERVOS or e.get("servo") == "mouth":
            return None
        propre["servo"] = e["servo"]
    if e["type"] == "batterie":
        if str(e.get("batterie")) not in ("1", "2", "3"):
            return None
        propre["batterie"] = str(e["batterie"])
    piece = _texte(e.get("piece"), 60)              # id d'une piece du catalogue (microduck-catalogue)
    if piece:
        propre["piece"] = piece
    if not propre["texte"] and e["type"] in ("piece", "impression", "nettoyage", "autre") and not piece:
        return None
    return propre


class Carnet:
    def __init__(self, chemin=None):
        self.chemin = Path(chemin) if chemin else chemin_defaut()

    def lire(self):
        try:
            d = json.loads(self.chemin.read_text())
            return d if isinstance(d, list) else []
        except (OSError, ValueError):
            return []

    def _ecrire(self, liste):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps(liste[-MAX:], ensure_ascii=False))
        os.replace(tmp, self.chemin)

    def ajouter(self, e):
        propre = valider(e)
        if propre is None:
            return None
        propre["id"] = uuid.uuid4().hex[:10]
        liste = self.lire() + [propre]
        liste.sort(key=lambda x: x.get("date", ""))
        self._ecrire(liste)
        return propre

    def supprimer(self, ident):
        liste = self.lire()
        reste = [x for x in liste if x.get("id") != ident]
        if len(reste) == len(liste):
            return False
        self._ecrire(reste)
        return True
