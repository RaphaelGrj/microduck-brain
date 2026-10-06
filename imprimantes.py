#!/usr/bin/env python3
"""Imprimantes 3D suivies EN DIRECT par le canard, sans Home Assistant (configuration.py, section
imprimante_directe ; page Connexions de l'application) :

- Prusa (MK3S, MK4S... avec PrusaLink) : GET http://<adresse>/api/v1/status, cle API dans X-Api-Key ;
- Elegoo (Saturn 4 Ultra... protocole SDCP) : WebSocket ws://<adresse>:3030/websocket, statut pousse par l'imprimante.

Fin d'impression -> evenement « impression_finie:<nom> », echec -> « impression_echec:<nom> » : les memes que par
Home Assistant, le cerveau reagit pareil. Reseau LOCAL seulement (configuration.adresse_locale), un fil a part, jamais
dans la boucle a 50 Hz. A VALIDER sur les vraies imprimantes : codes d'etat SDCP (v3) et cle PrusaLink selon le firmware.
"""
import base64
import json
import os
import queue
import socket
import struct
import threading
import time
import urllib.error
import urllib.request

import configuration

PERIODE_S = 20.0
# PrusaLink : printer.state
PRUSA_EN_COURS = {"PRINTING", "PAUSED", "BUSY"}
PRUSA_FINIE = {"FINISHED"}
PRUSA_ECHEC = {"ERROR", "ATTENTION"}
# SDCP v3 : Status.PrintInfo.Status (0 inactif, 1 mise a zero, 2 descente, 3 exposition, 4 remontee, 5 pause en cours,
# 6 en pause, 7 arret en cours, 8 arretee, 9 terminee, 10 verification du fichier)
SDCP_EN_COURS = {1, 2, 3, 4, 5, 6, 10}
SDCP_FINIE = {9}
SDCP_ARRETEE = {8}


def lire_prusalink(adresse, cle, delai=5.0):
    """-> {"etat": "en_cours"|"finie"|"echec"|"inactive", "progression": 0..100|None, "reste_s": int|None}"""
    hote = adresse.split("://")[-1].rstrip("/")
    req = urllib.request.Request(f"http://{hote}/api/v1/status", headers={"X-Api-Key": cle or ""})
    with urllib.request.urlopen(req, timeout=delai) as r:
        d = json.loads(r.read(65536))
    etat = str((d.get("printer") or {}).get("state", "")).upper()
    job = d.get("job") or {}
    return {"etat": "en_cours" if etat in PRUSA_EN_COURS else "finie" if etat in PRUSA_FINIE
            else "echec" if etat in PRUSA_ECHEC else "inactive",
            "progression": job.get("progress"), "reste_s": job.get("time_remaining"), "brut": etat}


FICHIER_MAX = 64 * 1024 * 1024
EXTENSIONS_PRUSA = (".bgcode", ".gcode")


def nom_de_fichier(nom):
    """Nom sur la cle USB de l'imprimante : lettres, chiffres, - _ . seulement (8.3 inutile sur MK4S)."""
    base = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(nom or ""))[:60].strip("._")
    return base if base.lower().endswith(EXTENSIONS_PRUSA) else None


def envoyer_prusalink(adresse, cle, nom, octets, imprimer=False, delai=60.0):
    """Envoie un G-code (deja tranche pour CETTE imprimante) sur la cle USB d'une Prusa, et lance l'impression si on le
    demande. PrusaLink : PUT /api/v1/files/usb/<nom> (A VALIDER sur la MK4S : nom du stockage « usb »). -> code HTTP."""
    nom = nom_de_fichier(nom)
    if nom is None or not octets or len(octets) > FICHIER_MAX:
        raise ValueError("fichier .bgcode ou .gcode attendu")
    hote = adresse.split("://")[-1].rstrip("/")
    req = urllib.request.Request(f"http://{hote}/api/v1/files/usb/{nom}", data=octets, method="PUT", headers={
        "X-Api-Key": cle or "", "Content-Type": "application/octet-stream", "Overwrite": "?1",
        "Print-After-Upload": "?1" if imprimer else "?0"})
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            return r.status
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise OSError("clé API refusée par l'imprimante") from e
        if e.code == 409:
            raise OSError("l'imprimante est occupée (impression en cours ?)") from e
        raise OSError(f"l'imprimante a répondu {e.code}") from e


# -- WebSocket minimal (client, texte seulement) : la bibliotheque standard n'en a pas ---------------------------------
def _ws_ouvrir(hote, port, chemin, delai):
    s = socket.create_connection((hote, port), timeout=delai)
    cle = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {chemin} HTTP/1.1\r\nHost: {hote}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {cle}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    entete = b""
    while b"\r\n\r\n" not in entete:
        morceau = s.recv(1024)
        if not morceau:
            raise OSError("poignee de main WebSocket refusee")
        entete += morceau
    if b" 101 " not in entete.split(b"\r\n", 1)[0]:
        raise OSError("pas de WebSocket ici")
    return s, entete.split(b"\r\n\r\n", 1)[1]


def _ws_envoyer(s, texte):
    donnees = texte.encode()
    masque = os.urandom(4)
    n = len(donnees)
    tete = struct.pack("!BB", 0x81, 0x80 | n) if n < 126 else struct.pack("!BBH", 0x81, 0x80 | 126, n)
    s.sendall(tete + masque + bytes(b ^ masque[i % 4] for i, b in enumerate(donnees)))


def _ws_messages(s, reste, delai):
    """Les messages texte recus pendant `delai` secondes."""
    fin, tampon = time.monotonic() + delai, reste
    while time.monotonic() < fin:
        while len(tampon) >= 2:
            b1, b2 = tampon[0], tampon[1]
            n, pos = b2 & 0x7F, 2
            if n == 126:
                if len(tampon) < 4:
                    break
                n, pos = struct.unpack("!H", tampon[2:4])[0], 4
            elif n == 127:
                if len(tampon) < 10:
                    break
                n, pos = struct.unpack("!Q", tampon[2:10])[0], 10
            if len(tampon) < pos + n:
                break
            charge, tampon = tampon[pos:pos + n], tampon[pos + n:]
            if b1 & 0x0F == 1:
                yield charge.decode("utf-8", "replace")
        s.settimeout(max(0.05, fin - time.monotonic()))
        try:
            morceau = s.recv(65536)
        except socket.timeout:
            return
        if not morceau:
            return
        tampon += morceau


def lire_sdcp(adresse, delai=4.0):
    hote = adresse.split("://")[-1].split("/")[0].split(":")[0]
    s, reste = _ws_ouvrir(hote, 3030, "/websocket", delai)
    try:
        _ws_envoyer(s, json.dumps({"Id": "", "Data": {"Cmd": 0, "Data": {}, "RequestID": os.urandom(8).hex(),
                                                       "MainboardID": "", "TimeStamp": int(time.time()), "From": 0}}))
        statut = None
        for m in _ws_messages(s, reste, delai):
            try:
                d = json.loads(m)
            except ValueError:
                continue
            st = d.get("Status") or (d.get("Data") or {}).get("Status")
            if isinstance(st, dict) and isinstance(st.get("PrintInfo"), dict):
                statut = st["PrintInfo"]
        if statut is None:
            raise OSError("pas de statut SDCP")
    finally:
        s.close()
    code = statut.get("Status")
    total, fait = statut.get("TotalLayer") or 0, statut.get("CurrentLayer") or 0
    return {"etat": "en_cours" if code in SDCP_EN_COURS else "finie" if code in SDCP_FINIE
            else "echec" if code in SDCP_ARRETEE else "inactive",
            "progression": round(100 * fait / total) if total else None, "reste_s": None, "brut": code}


class Imprimantes:
    def __init__(self, liste, log=print, lecteurs=None):
        self.liste = [i for i in liste if configuration.adresse_locale(i.get("adresse"))]
        self.log = log
        self.lecteurs = lecteurs or {"prusalink": lambda i: lire_prusalink(i["adresse"], i.get("cle_api")),
                                     "sdcp": lambda i: lire_sdcp(i["adresse"])}
        self.evenements = queue.Queue()
        self.etats = {}                          # nom -> dernier etat lu (pour l'appli)
        self._verrou = threading.Lock()

    def releve(self):
        """Un tour de toutes les imprimantes : transitions -> evenements du cerveau."""
        for i in self.liste:
            nom = i["nom"]
            try:
                e = self.lecteurs[i["type"]](i)
                e["joignable"] = True
            except Exception as x:                # eteinte, cle refusee... : on reessaie au prochain tour
                e = {"etat": None, "joignable": False, "erreur": str(x)[:80]}
            with self._verrou:
                avant = (self.etats.get(nom) or {}).get("etat")
                self.etats[nom] = {**e, "nom": nom, "type": i["type"], "t": time.time()}
            if avant == "en_cours" and e.get("etat") == "finie":
                self.evenements.put(f"impression_finie:{nom}")
            elif avant == "en_cours" and e.get("etat") == "echec":
                self.evenements.put(f"impression_echec:{nom}")

    def etat(self):
        with self._verrou:
            return [{k: v for k, v in e.items() if k != "brut"} for e in self.etats.values()]

    def source(self):
        out = []
        while True:
            try:
                out.append(self.evenements.get_nowait())
            except queue.Empty:
                return out

    def demarrer(self, periode=PERIODE_S):
        arret = threading.Event()

        def veille():
            while not arret.is_set():
                self.releve()
                arret.wait(periode)

        threading.Thread(target=veille, daemon=True, name="imprimantes").start()
        return arret
