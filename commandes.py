#!/usr/bin/env python3
"""Commandes vocales reconnues SUR le canard (ROADMAP, table Humains : "Commandes vocales -> reponse en sons de canard").

Remplace quacksat, abandonne le 2026-10-05 : dans tous ses modes, quacksat envoie le son du micro HORS du canard
(Home Assistant, LLM, API) et repond par synthese vocale - deux regles du projet violees. Ici :
  - reconnaissance HORS LIGNE (Vosk, petit modele francais ~40 Mo telecharge une fois a l'installation), avec une
    GRAMMAIRE restreinte a quelques mots : plus fiable et bien moins gourmand qu'une dictee libre ;
  - le NOM du canard d'abord ("<nom> assis") : la tele et les conversations ne le commandent pas ;
  - aucune reponse en mots : le cerveau repond avec ses sons de canard et ses gestes ; s'il n'a pas compris, une
    hesitation ("inquire" + tete penchee).

`Commandes` est la logique pure (testable avec un faux reconnaisseur) ; le son vient de audio.MicroAlsa (meme flux que
les reflexes sonores), qui suppose le micro partage avec robotd (contrib/robotd-audio-capture.patch + dsnoop, voir
deploy/robot/asound.conf).
"""
import json
import time

import numpy as np

TAUX = 16000
TAMPON_S = 6.0                  # son garde pour mesurer le ton du nom (Vosk donne l'instant de chaque mot)
GRONDE_DB = 6.0                 # nom dit 6 dB plus fort que d'habitude, sans monter : on le gronde
CALIN_DEMI_TONS = 3.0           # nom qui monte (chantonne) ou dit plus doucement que d'habitude : on le cajole
CALIN_DB = -4.0


def ton_du_nom(son, niveau_habituel):
    """Ton sur lequel on a dit son nom, SANS comprendre les mots (ROADMAP "Distingue le ton en entendant son prenom") :
    "gronde" (plus fort que d'habitude, hauteur qui ne monte pas), "calin" (hauteur qui monte, ou plus doux que
    d'habitude), None sinon. -> (ton, niveau dB du nom)."""
    from audio import hauteurs
    x = np.asarray(son, dtype=np.float64)
    if len(x) < int(0.15 * TAUX):
        return None, None
    niveau = 10.0 * np.log10(float(np.mean(x * x)) + 1e-12)
    h = hauteurs(x)
    monte = None
    if len(h) >= 4:
        n = max(1, len(h) // 3)
        monte = 12.0 * (np.mean([np.log2(f) for _, f in h[-n:]]) - np.mean([np.log2(f) for _, f in h[:n]]))
    if niveau_habituel is None:
        return ("calin" if monte is not None and monte >= CALIN_DEMI_TONS else None), niveau
    if niveau - niveau_habituel >= GRONDE_DB and (monte is None or monte < 1.0):
        return "gronde", niveau
    if (monte is not None and monte >= CALIN_DEMI_TONS) or niveau - niveau_habituel <= CALIN_DB:
        return "calin", niveau
    return None, niveau

# phrase reconnue -> evenement du cerveau (brain.py). Plusieurs formulations pour la meme commande.
VOCABULAIRE = {
    "viens": "appel", "viens ici": "appel", "ici": "appel",
    "assis": "commande:assis", "couche": "commande:assis",
    "debout": "commande:debout", "leve toi": "commande:debout",
    "tourne": "tour_toupie", "fais un tour": "tour_toupie",
    "salut": "tour_salut", "coucou": "tour_salut", "bonjour": "tour_salut",
    "on joue": "jeu_soleil", "joue": "jeu_soleil", "un deux trois soleil": "jeu_soleil",
    "stop": "commande:stop", "arrete": "commande:stop", "non": "commande:stop",
    "chut": "calme_on", "silence": "calme_on", "dodo": "calme_on",
    "reveille toi": "commande:reveil",
    "bravo": "commande:bravo", "gentil": "commande:bravo", "c'est bien": "commande:bravo",
    "danse": "commande:danse",
    "la balle": "jeu_balle", "joue a la balle": "jeu_balle", "va chercher": "jeu_balle",
    "cache toi": "jeu_cache", "cache cache": "jeu_cache",
    "trouve": "commande:trouve", "je t'ai trouve": "commande:trouve",
}
CONFIANCE_MIN = 0.6             # confiance moyenne des mots (Vosk) en dessous de laquelle on "n'a pas compris"


class Commandes:
    def __init__(self, fabrique_reconnaisseur, nom="canard", horloge=time.monotonic, maison=None):
        """`fabrique_reconnaisseur(grammaire_json)` -> objet facon vosk.KaldiRecognizer (AcceptWaveform, Result).
        `maison` : phrases domotiques de ha.toml ([[action]] voix = ...) -> evenement "maison:<id>" (pont_ha appelle
        le service HA ; seule la COMMANDE reconnue sort du canard, jamais le son)."""
        self.nom = nom.lower()
        self.horloge = horloge
        self.vocabulaire = dict(VOCABULAIRE)
        for phrase, evt in (maison or {}).items():
            self.vocabulaire.setdefault(phrase, evt)    # les commandes du canard gardent la priorite
        # le nom seul, nom + commande, et la commande seule (dite juste apres le nom, apres une pause)
        phrases = sorted({f"{self.nom} {p}" for p in self.vocabulaire} | set(self.vocabulaire) | {self.nom})
        self.reco = fabrique_reconnaisseur(json.dumps(phrases + ["[unk]"], ensure_ascii=False))
        self.attente_nom = None            # instant ou le nom seul a ete dit : la commande peut suivre (3 s)
        self.tampon = np.zeros(0, dtype=np.int16)     # dernier son recu (TAMPON_S), pour le ton du nom
        self.lus = 0                       # echantillons recus depuis le debut (horloge des mots de Vosk)
        self.niveaux_nom = []              # niveau (dB) des derniers noms "neutres" : la reference du ton

    def bloc_brut(self, octets):
        """Son brut (S16_LE mono 16 kHz) -> evenements (liste, souvent vide)."""
        x = np.frombuffer(octets, dtype=np.int16)
        self.tampon = np.concatenate([self.tampon, x])[-int(TAMPON_S * TAUX):]
        self.lus += len(x)
        if not self.reco.AcceptWaveform(octets):
            return []
        return self.comprendre(json.loads(self.reco.Result()))

    def _ton(self, mots):
        """Ton du nom (premier mot), mesure sur le son du tampon aux instants donnes par Vosk (start/end, en s depuis le
        debut du flux). Le son n'est garde que TAMPON_S en memoire : rien n'est enregistre."""
        m = mots[0]
        if "start" not in m or "end" not in m:
            return None
        debut = int(m["start"] * TAUX) - (self.lus - len(self.tampon))
        fin = int(m["end"] * TAUX) - (self.lus - len(self.tampon))
        if debut < 0 or fin > len(self.tampon) or fin <= debut:
            return None
        habituel = float(np.median(self.niveaux_nom)) if len(self.niveaux_nom) >= 3 else None
        ton, niveau = ton_du_nom(self.tampon[debut:fin] / 32768.0, habituel)
        if niveau is not None:
            # la reference suit TOUTES les mesures (mediane des 20 derniers noms) : le niveau au micro depend de la
            # distance et de la piece ; une reference figee sur les seuls noms "neutres" le croirait grondé pour toujours
            self.niveaux_nom = (self.niveaux_nom + [niveau])[-20:]
        return ton

    def comprendre(self, resultat):
        texte = (resultat.get("text") or "").strip().lower()
        mots = resultat.get("result") or []
        if not texte or texte == "[unk]":
            return []
        confiance = sum(m.get("conf", 1.0) for m in mots) / len(mots) if mots else 1.0
        now = self.horloge()
        ton = self._ton(mots) if mots and mots[0].get("word") == self.nom else None
        if texte == self.nom:
            self.attente_nom = now          # "canard ?" ... il ecoute la suite
            return ["commande:ecoute"] + ([f"ton:{ton}"] if ton else [])
        if texte.startswith(self.nom + " "):
            reste = texte[len(self.nom) + 1:]
        elif self.attente_nom is not None and now - self.attente_nom <= 3.0:
            reste = texte                   # "canard..." (pause) "assis"
        else:
            return []                       # sans son nom : ce n'est pas a lui qu'on parle
        self.attente_nom = None
        # pas de "ton:" avec une commande : le geste du ton (penaud, cajole) ecraserait la commande qu'il accompagne
        if confiance < CONFIANCE_MIN or reste not in self.vocabulaire:
            return ["commande:pas_compris"]
        return [self.vocabulaire[reste]]


def fabrique_vosk(chemin_modele):
    """Fabrique de reconnaisseur Vosk (hors ligne). Importe vosk seulement ici : le reste tourne sans."""
    import vosk
    vosk.SetLogLevel(-1)
    modele = vosk.Model(str(chemin_modele))

    def fabrique(grammaire):
        r = vosk.KaldiRecognizer(modele, 16000, grammaire)
        r.SetWords(True)
        return r
    return fabrique
