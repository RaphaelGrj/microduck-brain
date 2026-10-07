#!/usr/bin/env python3
"""Minuteurs et rappels de l'application, gardes SUR le canard (planning.json) : ils survivent a un redemarrage.

- Minuteur : « 12 min, les pates ». A la fin, le canard le signale en sons de canard (etat Signal) et le telephone
  recoit une notification importante.
- Rappel : « a 18 h, rappelle a Clemence d'arroser les plantes ». Pour quelqu'un : il devient un message (messages.py),
  signale a la personne si elle est la, sinon a son retour. Pour tout le monde : il le signale tout de suite. Un rappel
  peut revenir chaque jour.
Le reveil doux, lui, est une routine (reglages.py, action « reveil »).
"""
import json
import os
import time
import uuid
from pathlib import Path

MINUTEUR_MAX_S = 24 * 3600
MAX = 40


def chemin_defaut():
    return Path(os.environ.get("MICRODUCK_PLANNING", Path.home() / ".local/share/microduck/planning.json"))


def _texte(v, n):
    return "".join(c for c in v if c.isprintable() and c not in "|:").strip()[:n] if isinstance(v, str) else ""


def prochaine(heure, minute, maintenant, horloge=time.localtime):
    """Instant (epoch) du prochain HH:MM local, aujourd'hui ou demain."""
    h = horloge(maintenant)
    cible = time.mktime((h.tm_year, h.tm_mon, h.tm_mday, heure, minute, 0, 0, 0, -1))
    return cible if cible > maintenant + 1 else time.mktime((h.tm_year, h.tm_mon, h.tm_mday + 1, heure, minute, 0, 0, 0, -1))


class Planning:
    def __init__(self, chemin=None, mur=time.time):
        self.chemin = Path(chemin) if chemin else chemin_defaut()
        self.mur = mur
        try:
            d = json.loads(self.chemin.read_text())
        except (OSError, ValueError):
            d = {}
        self.minuteurs = [m for m in d.get("minuteurs", []) if isinstance(m, dict) and m.get("id")]
        self.rappels = [r for r in d.get("rappels", []) if isinstance(r, dict) and r.get("id")]

    def _sauver(self):
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.chemin.with_suffix(".tmp")
            tmp.write_text(json.dumps({"minuteurs": self.minuteurs, "rappels": self.rappels}, ensure_ascii=False))
            os.replace(tmp, self.chemin)
        except OSError:
            pass

    def minuteur(self, secondes, nom=""):
        try:
            s = int(secondes)
        except (TypeError, ValueError):
            return None
        if not 5 <= s <= MINUTEUR_MAX_S or len(self.minuteurs) >= MAX:
            return None
        m = {"id": uuid.uuid4().hex[:10], "nom": _texte(nom, 40) or "Minuteur", "duree": s, "fin": round(self.mur() + s, 1)}
        self.minuteurs.append(m)
        self._sauver()
        return m

    def rappel(self, texte, heure, pour="", quotidien=False):
        """heure : "HH:MM" (prochaine occurrence). -> le rappel, ou None."""
        texte, pour = _texte(texte, 200), _texte(pour, 40)
        try:
            hh, mm = (int(x) for x in str(heure).split(":"))
            assert 0 <= hh < 24 and 0 <= mm < 60
        except (ValueError, AssertionError):
            return None
        if not texte or len(self.rappels) >= MAX:
            return None
        r = {"id": uuid.uuid4().hex[:10], "texte": texte, "pour": pour or None, "heure": f"{hh:02d}:{mm:02d}",
             "quand": round(prochaine(hh, mm, self.mur())), "quotidien": bool(quotidien)}
        self.rappels.append(r)
        self._sauver()
        return r

    def annuler(self, ident):
        avant = len(self.minuteurs) + len(self.rappels)
        self.minuteurs = [m for m in self.minuteurs if m["id"] != ident]
        self.rappels = [r for r in self.rappels if r["id"] != ident]
        if len(self.minuteurs) + len(self.rappels) == avant:
            return False
        self._sauver()
        return True

    def echus(self):
        """-> ([minuteurs finis], [rappels arrives]) ; retires (ou reprogrammes au lendemain s'ils sont quotidiens)."""
        t = self.mur()
        finis = [m for m in self.minuteurs if m["fin"] <= t]
        arrives = [r for r in self.rappels if r["quand"] <= t]
        if not finis and not arrives:
            return [], []
        self.minuteurs = [m for m in self.minuteurs if m["fin"] > t]
        garde = [r for r in self.rappels if r["quand"] > t]
        for r in arrives:
            if r.get("quotidien"):
                hh, mm = (int(x) for x in r["heure"].split(":"))
                garde.append({**r, "quand": round(prochaine(hh, mm, t))})
        self.rappels = garde
        self._sauver()
        return finis, arrives

    def etat(self):
        return {"maintenant": self.mur(), "minuteurs": sorted(self.minuteurs, key=lambda m: m["fin"]),
                "rappels": sorted(self.rappels, key=lambda r: r["quand"])}
