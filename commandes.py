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
    def __init__(self, fabrique_reconnaisseur, nom="canard", horloge=time.monotonic):
        """`fabrique_reconnaisseur(grammaire_json)` -> objet facon vosk.KaldiRecognizer (AcceptWaveform, Result)."""
        self.nom = nom.lower()
        self.horloge = horloge
        # le nom seul, nom + commande, et la commande seule (dite juste apres le nom, apres une pause)
        phrases = sorted({f"{self.nom} {p}" for p in VOCABULAIRE} | set(VOCABULAIRE) | {self.nom})
        self.reco = fabrique_reconnaisseur(json.dumps(phrases + ["[unk]"], ensure_ascii=False))
        self.attente_nom = None            # instant ou le nom seul a ete dit : la commande peut suivre (3 s)

    def bloc_brut(self, octets):
        """Son brut (S16_LE mono 16 kHz) -> evenements (liste, souvent vide)."""
        if not self.reco.AcceptWaveform(octets):
            return []
        return self.comprendre(json.loads(self.reco.Result()))

    def comprendre(self, resultat):
        texte = (resultat.get("text") or "").strip().lower()
        mots = resultat.get("result") or []
        if not texte or texte == "[unk]":
            return []
        confiance = sum(m.get("conf", 1.0) for m in mots) / len(mots) if mots else 1.0
        now = self.horloge()
        if texte == self.nom:
            self.attente_nom = now          # "canard ?" ... il ecoute la suite
            return ["commande:ecoute"]
        if texte.startswith(self.nom + " "):
            reste = texte[len(self.nom) + 1:]
        elif self.attente_nom is not None and now - self.attente_nom <= 3.0:
            reste = texte                   # "canard..." (pause) "assis"
        else:
            return []                       # sans son nom : ce n'est pas a lui qu'on parle
        self.attente_nom = None
        if confiance < CONFIANCE_MIN or reste not in VOCABULAIRE:
            return ["commande:pas_compris"]
        return [VOCABULAIRE[reste]]


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
