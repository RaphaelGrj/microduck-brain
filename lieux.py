#!/usr/bin/env python3
"""Les lieux du canard : la maison, chez les parents, en vacances... Chacun a son nom, ses reseaux Wi-Fi et la derniere
carte qu'il y a dessinee. Quand le reseau Wi-Fi change, le canard bascule seul vers le lieu qui le connait, ou en cree
un nouveau ; on peut aussi choisir, renommer, archiver, restaurer ou supprimer un lieu depuis l'application.

- Le reseau est lu SUR le canard (iwgetid, wpa_cli ou nmcli), dans un fil a part : jamais dans la boucle a 50 Hz.
- Un lieu ARCHIVE est range : il n'encombre plus la liste, mais il garde sa carte et reste reconnu par son reseau
  (s'il y retourne, il ressort des archives). SUPPRIMER oublie tout.
- « Bascule automatique » se coupe lieu par lieu : il propose alors le lieu dans l'appli au lieu d'y basculer.
- La carte d'un lieu est gardee pour etre REGARDEE dans l'appli. Elle ne sert pas encore a se deplacer : l'odometrie
  repart de zero a chaque demarrage, il faudra un recalage (balises UWB, chargeur) pour la reutiliser.

Fichier local : lieux.json a cote de la memoire (MICRODUCK_LIEUX pour un autre chemin). Rien ne sort du canard,
sauf vers le telephone appaire (nom des lieux et des reseaux).
"""
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

import memoire

CHEMIN_DEFAUT = Path(os.environ.get("MICRODUCK_LIEUX", memoire.CHEMIN_DEFAUT.parent / "lieux.json"))
CONFIRMATIONS = 2           # meme reseau vu 2 fois de suite avant de basculer (un point d'acces qui flanche ne suffit pas)
PERIODE_S = 30.0
NOM_MAX = 40


def lire_reseau(executer=subprocess.run):
    """Le Wi-Fi auquel le canard est connecte : {"ssid", "bssid"} ou None. Outils essayes dans l'ordre ; tous locaux."""
    def sortie(*cmd):
        if shutil.which(cmd[0]) is None:
            return None
        try:
            r = executer(list(cmd), capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 else None

    ssid = (sortie("iwgetid", "-r") or "").strip()
    if ssid:
        return {"ssid": ssid, "bssid": ((sortie("iwgetid", "-a", "-r") or "").strip().lower() or None)}
    st = sortie("wpa_cli", "status")
    if st:
        champs = dict(l.split("=", 1) for l in st.splitlines() if "=" in l)
        if champs.get("wpa_state") == "COMPLETED" and champs.get("ssid"):
            return {"ssid": champs["ssid"], "bssid": (champs.get("bssid") or "").lower() or None}
    nm = sortie("nmcli", "-t", "-f", "ACTIVE,SSID,BSSID", "dev", "wifi")
    for ligne in (nm or "").splitlines():
        morceaux = ligne.replace("\\:", "\x00").split(":")
        if len(morceaux) >= 3 and morceaux[0] == "yes" and morceaux[1]:
            return {"ssid": morceaux[1].replace("\x00", ":"), "bssid": morceaux[2].replace("\x00", ":").lower() or None}
    return None


def nom_propre(nom):
    nom = "".join(c for c in str(nom or "") if c.isprintable()).strip()[:NOM_MAX]
    return nom or None


class Lieux:
    def __init__(self, chemin=CHEMIN_DEFAUT, horloge=time.time, log=print):
        self.chemin, self.horloge, self.log = Path(chemin), horloge, log
        self.verrou = threading.RLock()
        self.evenements = queue.Queue()
        self.carte_actuelle = lambda: {}        # branchee par canard.py sur la carte de l'application
        self.reseau = None                      # dernier reseau lu
        self.suggestion = None                  # lieu reconnu mais a bascule manuelle : propose dans l'appli
        self._candidat, self._vu = None, 0      # reseau inconnu ou autre lieu, en attente de confirmation
        self._reseau_choix = None               # reseau au moment d'un choix dans l'appli : pas de bascule auto dessus
        self.d = {"actuel": None, "lieux": {}, "suivant": 1}
        try:
            self.d.update(json.loads(self.chemin.read_text()))
        except (OSError, ValueError):
            pass
        if self.d["actuel"] not in self.d["lieux"]:
            self.d["actuel"] = self._creer("Maison")

    # -- outils ------------------------------------------------------------------------------------------------------
    def _creer(self, nom, reseau=None):
        lid = f"l{self.d['suivant']}"
        self.d["suivant"] += 1
        self.d["lieux"][lid] = {"nom": nom, "reseaux": [reseau] if reseau else [], "cree": round(self.horloge()),
                                "vu": round(self.horloge()), "archive": False, "auto": True, "carte": {}}
        return lid

    def _sauver(self):
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.chemin.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.d, ensure_ascii=False, separators=(",", ":")))
            os.replace(tmp, self.chemin)
        except OSError as e:
            self.log(f"lieux : sauvegarde impossible ({e})")

    def _lieu_du_reseau(self, reseau):
        """Le lieu qui connait ce reseau : meme point d'acces d'abord, sinon meme nom de reseau."""
        for cle in ("bssid", "ssid"):
            if not reseau.get(cle):
                continue
            for lid, l in self.d["lieux"].items():
                if any(r.get(cle) == reseau[cle] for r in l["reseaux"]):
                    return lid
        return None

    def _basculer(self, lid, genre):
        avant = self.d["actuel"]
        if avant == lid:
            return
        carte = self.carte_actuelle() or {}
        if carte.get("cases") and avant in self.d["lieux"]:
            self.d["lieux"][avant]["carte"] = carte          # la derniere carte du lieu quitte, pour la regarder
        self.d["actuel"] = lid
        l = self.d["lieux"][lid]
        l["archive"] = False                                  # il y est : il ressort des archives
        l["vu"] = round(self.horloge())
        self.suggestion = None
        self._sauver()
        self.evenements.put(f"lieu:{genre}|{l['nom']}")
        self.log(f"lieu : {l['nom']} ({genre})")

    # -- le reseau observe (fil de veille) ---------------------------------------------------------------------------
    def observer(self, reseau):
        """Un nouveau releve du Wi-Fi. Bascule apres CONFIRMATIONS releves identiques ; pas de reseau = on ne sait pas."""
        with self.verrou:
            self.reseau = reseau
            if not reseau or not reseau.get("ssid"):
                self._candidat, self._vu = None, 0
                return
            actuel = self.d["lieux"][self.d["actuel"]]
            lid = self._lieu_du_reseau(reseau)
            if lid == self.d["actuel"]:
                self._candidat, self._vu, self.suggestion = None, 0, None
                actuel["vu"] = round(self.horloge())
                if reseau.get("bssid") and not any(r.get("bssid") == reseau["bssid"] for r in actuel["reseaux"]):
                    actuel["reseaux"].append(dict(reseau))   # un autre point d'acces de la meme maison (repeteur)
                    self._sauver()
                return
            if lid is None and not actuel["reseaux"]:
                actuel["reseaux"].append(dict(reseau))       # premier reseau connu : c'est celui du lieu actuel
                self._sauver()
                return
            if self._reseau_choix and reseau.get("ssid") == self._reseau_choix:
                return                                       # lieu choisi a la main sur ce reseau : on le respecte
            cle = lid or ("?", reseau["ssid"])
            self._vu = self._vu + 1 if cle == self._candidat else 1
            self._candidat = cle
            if self._vu < CONFIRMATIONS:
                return
            self._candidat, self._vu, self._reseau_choix = None, 0, None
            if lid is None:
                self._basculer(self._creer("Nouveau lieu", dict(reseau)), "nouveau")
            elif self.d["lieux"][lid]["auto"]:
                self._basculer(lid, "retour")
            else:
                self.suggestion = lid

    # -- l'application -----------------------------------------------------------------------------------------------
    def action(self, quoi, lid=None, nom=None):
        """Une action de l'appli. -> (True, None) ou (False, raison)."""
        with self.verrou:
            if quoi == "nouveau":
                nouveau = self._creer(nom_propre(nom) or "Nouveau lieu")
                self._reseau_choix = (self.reseau or {}).get("ssid")
                self._basculer(nouveau, "nouveau")
                return True, None
            l = self.d["lieux"].get(lid)
            if l is None:
                return False, "lieu inconnu"
            actuel = lid == self.d["actuel"]
            if quoi == "basculer":
                self._reseau_choix = (self.reseau or {}).get("ssid")
                self._basculer(lid, "manuel")
            elif quoi == "renommer":
                if not nom_propre(nom):
                    return False, "nom vide"
                l["nom"] = nom_propre(nom)
                if actuel:
                    self.evenements.put(f"lieu:renomme|{l['nom']}")
            elif quoi in ("archiver", "supprimer") and actuel:
                return False, "c'est le lieu actuel : basculer d'abord sur un autre"
            elif quoi == "archiver":
                l["archive"] = True
            elif quoi == "restaurer":
                l["archive"] = False
            elif quoi == "supprimer":
                del self.d["lieux"][lid]
                if self.suggestion == lid:
                    self.suggestion = None
            elif quoi == "lier":
                if not (self.reseau or {}).get("ssid"):
                    return False, "le canard n'est connecte a aucun Wi-Fi"
                for autre in self.d["lieux"].values():   # un reseau n'appartient qu'a un lieu
                    autre["reseaux"] = [r for r in autre["reseaux"] if r.get("ssid") != self.reseau["ssid"]]
                l["reseaux"].append(dict(self.reseau))
            elif quoi == "delier":
                l["reseaux"] = [r for r in l["reseaux"] if r.get("ssid") != nom]
            elif quoi in ("auto_on", "auto_off"):
                l["auto"] = quoi == "auto_on"
            else:
                return False, "action inconnue"
            self._sauver()
            return True, None

    def resume(self):
        """Pour l'appli : les lieux sans leurs cartes (GET /api/lieux)."""
        with self.verrou:
            return {
                "actuel": self.d["actuel"], "reseau": (self.reseau or {}).get("ssid"), "suggestion": self.suggestion,
                "lieux": [{"id": lid, "nom": l["nom"], "reseaux": sorted({r["ssid"] for r in l["reseaux"] if r.get("ssid")}),
                           "archive": l["archive"], "auto": l["auto"], "vu": l["vu"], "carte": bool(l["carte"])}
                          for lid, l in sorted(self.d["lieux"].items(), key=lambda kv: -kv[1]["vu"])],
            }

    def carte(self, lid):
        """La derniere carte gardee d'un lieu ; pour le lieu actuel, la carte en cours."""
        with self.verrou:
            if lid == self.d["actuel"]:
                return self.carte_actuelle() or {}
            return (self.d["lieux"].get(lid) or {}).get("carte") or {}

    def nom_actuel(self):
        with self.verrou:
            return self.d["lieux"][self.d["actuel"]]["nom"]

    # -- cerveau et fil de veille ------------------------------------------------------------------------------------
    def source(self):
        out = []
        while True:
            try:
                out.append(self.evenements.get_nowait())
            except queue.Empty:
                return out

    def demarrer(self, lire=lire_reseau, periode=PERIODE_S):
        arret = threading.Event()

        def veille():
            while not arret.is_set():
                try:
                    self.observer(lire())
                except Exception as e:                       # jamais d'arret du canard pour un releve rate
                    self.log(f"lieux : releve du Wi-Fi impossible ({e})")
                arret.wait(periode)

        threading.Thread(target=veille, daemon=True, name="lieux").start()
        return arret
