#!/usr/bin/env python3
"""Journal en photos et mode photo de l'application (desactive par defaut : reglage « photos »).

Le canard garde quelques images de sa journee (le chat croise, une partie de balle, un retour a la maison, une
impression finie...) SUR LUI, dans ~/.local/share/microduck/photos/. Le telephone les affiche par l'application
(reseau local, code parent) ; elles ne partent nulle part ailleurs, jamais vers Home Assistant, et s'effacent toutes
seules apres JOURS_GARDES jours. Aucune analyse : ce sont des souvenirs, pas des donnees.

La camera est lue en local seulement (meme regle que vision.py), dans un fil a part : jamais dans la boucle du cerveau.
"""
import os
import re
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

FRAME_URL = os.environ.get("MICRODUCK_FRAME_URL", "http://127.0.0.1:8080/frame")
JOURS_GARDES = 7
MAX_PHOTOS = 80
MAX_OCTETS = 4 * 1024 * 1024
ECART_MEME_MOTIF_S = 10 * 60            # au plus une photo automatique par motif toutes les 10 min
# etat du cerveau (ou evenement) -> motif de la photo automatique
MOTIFS = {"etat:regarde_chat": "chat", "etat:accueil": "retour", "etat:jour_special": "jour_special",
          "etat:danse": "danse", "etat:fier": "fier", "etat:balle": "balle", "etat:remarque": "objet",
          "etat:regarde_impression": "impression",
          "impression_finie": "impression", "impression_echec": "impression"}
NOM = re.compile(r"^\d{10}-\d{3}-[a-z_]{1,20}\.(png|jpg)$")


def lire_camera(url=FRAME_URL, delai=3.0):
    """Une image de la camera, telle quelle (PNG/JPEG). Camera du canard SEULEMENT (boucle locale)."""
    if urlparse(url).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError(f"camera distante refusee ({url}) : seule la camera du canard est lue")
    with urllib.request.urlopen(url, timeout=delai) as r:
        donnees = r.read(MAX_OCTETS + 1)
    if len(donnees) > MAX_OCTETS:
        raise RuntimeError("image trop grosse")
    return donnees


def extension(donnees):
    if donnees[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if donnees[:3] == b"\xff\xd8\xff":
        return "jpg"
    return None


def dossier_defaut():
    return Path(os.environ.get("MICRODUCK_PHOTOS", Path.home() / ".local/share/microduck/photos"))


class Photos:
    def __init__(self, dossier=None, lire=lire_camera, log=print, mur=time.time):
        self.dossier = Path(dossier) if dossier else dossier_defaut()
        self.lire, self.log, self.mur = lire, log, mur
        self.actif = False                      # reglage « photos » (journal automatique) ; le mode photo marche toujours
        self._derniere = {}                     # motif -> instant de la derniere photo automatique
        self._verrou = threading.Lock()
        self.en_cours = False

    # -- prise -------------------------------------------------------------------------------------------------------
    def sur_evenement(self, quoi):
        """Ecouteur du cerveau : rien de lent ici (la prise se fait dans un fil)."""
        motif = MOTIFS.get(str(quoi).partition("|")[0]) or MOTIFS.get(str(quoi).partition(":")[0])
        if not self.actif or motif is None:
            return
        maintenant = self.mur()
        if maintenant - self._derniere.get(motif, -1e12) < ECART_MEME_MOTIF_S:
            return
        self._derniere[motif] = maintenant
        self.prendre(motif)

    def prendre(self, motif="photo", attendre=False):
        """Une photo, dans un fil (attendre=True : tout de suite, pour les tests et le mode photo). -> id ou None."""
        motif = re.sub(r"[^a-z_]", "", str(motif).lower())[:20] or "photo"
        if attendre:
            return self._prendre(motif)
        threading.Thread(target=self._prendre, args=(motif,), daemon=True).start()
        return None

    def _prendre(self, motif):
        with self._verrou:
            if self.en_cours:
                return None
            self.en_cours = True
        try:
            donnees = self.lire()
            ext = extension(donnees or b"")
            if ext is None:
                raise RuntimeError("ce n'est pas une image")
            t = self.mur()
            ident = f"{int(t):010d}-{int((t % 1) * 1000):03d}-{motif}.{ext}"
            self.dossier.mkdir(parents=True, exist_ok=True)
            os.chmod(self.dossier, 0o700)
            tmp = self.dossier / (ident + ".tmp")
            tmp.write_bytes(donnees)
            os.replace(tmp, self.dossier / ident)
            self.nettoyer()
            return ident
        except Exception as e:
            self.log(f"photo impossible ({motif}) : {e}")
            return None
        finally:
            self.en_cours = False

    # -- lecture, effacement -----------------------------------------------------------------------------------------
    def _fichiers(self):
        try:
            return sorted((f for f in self.dossier.iterdir() if NOM.match(f.name)), key=lambda f: f.name)
        except OSError:
            return []

    def nettoyer(self):
        limite = self.mur() - JOURS_GARDES * 86400
        fichiers = self._fichiers()
        for i, f in enumerate(fichiers):
            if int(f.name[:10]) < limite or i < len(fichiers) - MAX_PHOTOS:
                try:
                    f.unlink()
                except OSError:
                    pass

    def liste(self):
        """[{"id", "t", "motif"}], la plus recente d'abord."""
        self.nettoyer()
        return [{"id": f.name, "t": int(f.name[:10]), "motif": f.name[15:].rsplit(".", 1)[0]}
                for f in reversed(self._fichiers())]

    def lire_photo(self, ident):
        """-> (octets, type) ou None. Le nom est verifie : rien d'autre que les photos du dossier."""
        if not isinstance(ident, str) or not NOM.match(ident):
            return None
        try:
            return (self.dossier / ident).read_bytes(), ("image/png" if ident.endswith(".png") else "image/jpeg")
        except OSError:
            return None

    def supprimer(self, ident=None):
        """Une photo, ou toutes (ident None)."""
        for f in self._fichiers():
            if ident is None or f.name == ident:
                try:
                    f.unlink()
                except OSError:
                    pass
        return True
