#!/usr/bin/env python3
"""Reflexes sonores sans deep learning (ROADMAP "Reflexes autonomes declenches par l'environnement (son, vue)") :
le pipeline micro qui manquait (journal du 2026-10-05 : "aucun pipeline micro/FFT n'existe encore").

`AnalyseurSon` (logique pure, numpy) recoit le son par blocs de 20 ms (mono, flottants -1..1) et emet des evenements :
  - "bruit"            : un son sec et TRES fort (objet qui tombe, porte qui claque) -> sursaut (etat startle existant) ;
  - "appel"            : 2 ou 3 claquements de mains rapproches et reguliers -> le canard repond, comme appele ;
  - "applaudissements" : 5 claquements ou plus en 2,5 s, serres (>= 3 par seconde) -> joie ;
  - "musique:<bpm>"    : un battement regulier (60 a 180 BPM) tenu plusieurs secondes -> il hoche la tete en rythme ;
  - "musique_fin"      : le battement s'est arrete ;
  - "discussion_longue" : des voix (son actif, hors musique) sur plus de 25 % des blocs de 2 min -> faux baillement ;
  - "silence_conversation" : un silence d'au moins 1,2 s juste apres plusieurs secondes de voix -> "dernier mot".
Methode : niveau par bloc (dB), bruit de fond suivi par le bas (monte lentement, descend tout de suite), transitoires =
saut de niveau au-dessus du fond qui retombe vite ; tempo = autocorrelation de la "force d'attaque" sur 6 s.
Seuils a etalonner sur le vrai micro (reglables a la construction).

`MicroAlsa` : source optionnelle qui lit le micro par `arecord` (ALSA). NON TESTEE : le canard n'est pas livre, et
quacksat utilise deja le micro (partage ALSA via dsnoop a prevoir, voir QUACKSAT_QUACKNAV.md). Vie privee : le son est
analyse en memoire, bloc par bloc, rien n'est enregistre ni envoye.
"""
import subprocess
import threading
import time

import numpy as np

TAUX = 16000
BLOC = 320                      # 20 ms
SOUS_BLOC = 40                  # 2,5 ms : pour mesurer le temps de montee d'un transitoire
MONTEE_CLAP_S = 0.0075          # un claquement atteint son pic en quelques ms ; une syllabe en plusieurs dizaines
DB_MIN = -100.0


class AnalyseurSon:
    def __init__(self, seuil_fort_dbfs=-12.0, saut_transitoire_db=15.0, delai_bruit_s=5.0, delai_appel_s=20.0):
        self.seuil_fort, self.saut = seuil_fort_dbfs, saut_transitoire_db
        self.delai_bruit_s, self.delai_appel_s = delai_bruit_s, delai_appel_s
        self.t = 0.0
        self.fond = None                         # bruit de fond (dB)
        self.niveaux = []                        # derniers niveaux (dB), 6 s
        self.attaques = []                       # force d'attaque par bloc (6 s)
        self.transitoire = None                  # (debut, pic) d'un transitoire en cours
        self.claps = []                          # instants des claquements du groupe en cours
        self.dernier = {}                        # evenement -> instant de la derniere emission
        self.musique = None                      # bpm si un battement est en cours
        self.enveloppe = []                      # (instant, dB) par sous-bloc de 2,5 ms, sur 0,5 s
        self.voix = []                           # 1 si le bloc est "actif" (voix probable), sur 2 min
        self.silence_depuis = None               # debut du silence en cours

    def _peut(self, nom, delai):
        if self.t - self.dernier.get(nom, -1e9) < delai:
            return False
        self.dernier[nom] = self.t
        return True

    def bloc(self, echantillons):
        """Un bloc de BLOC echantillons (np.ndarray float, -1..1). Renvoie la liste des evenements (souvent vide)."""
        x = np.asarray(echantillons, dtype=np.float64)
        niveau = max(DB_MIN, 10.0 * np.log10(float(np.mean(x * x)) + 1e-12))
        sous = x[: len(x) // SOUS_BLOC * SOUS_BLOC].reshape(-1, SOUS_BLOC)
        t0 = self.t
        self.enveloppe = (self.enveloppe + [(t0 + (i + 1) * SOUS_BLOC / TAUX, 10.0 * np.log10(float(e) + 1e-12))
                                            for i, e in enumerate(np.mean(sous * sous, axis=1))])[-200:]
        self.t += len(x) / TAUX
        out = []
        prec = self.niveaux[-1] if self.niveaux else niveau
        self.niveaux = (self.niveaux + [niveau])[-300:]
        self.attaques = (self.attaques + [max(0.0, niveau - prec)])[-300:]
        if self.fond is None:
            self.fond = niveau
        # fond suivi par le bas : descend tout de suite, monte de 0,5 dB/s (la musique ne devient pas "le silence")
        self.fond = niveau if niveau < self.fond else self.fond + 0.01

        # 1. transitoires : saut au-dessus du fond, qui doit retomber en moins de 150 ms (un claquement, un choc)
        if self.transitoire is None and niveau - self.fond >= self.saut and niveau - prec >= self.saut * 0.6:
            self.transitoire = [self.t, niveau]
        elif self.transitoire is not None:
            self.transitoire[1] = max(self.transitoire[1], niveau)
            duree = self.t - self.transitoire[0]
            if niveau - self.fond < self.saut * 0.5:          # retombe : c'etait bref
                debut, pic = self.transitoire
                self.transitoire = None
                if pic >= self.seuil_fort:
                    if self._peut("bruit", self.delai_bruit_s):
                        out.append("bruit")
                elif duree <= 0.15 and self.musique is None and self._montee(debut) <= MONTEE_CLAP_S:
                    self.claps.append(debut)
            elif duree > 0.4:                                  # son tenu : ni claquement ni choc
                self.transitoire = None

        # 2 bis. voix / conversation (son actif ni bref ni rythme : parole probable)
        actif = niveau - self.fond >= 10.0 and self.musique is None
        self.voix = (self.voix + [1 if actif else 0])[-6000:]
        if actif:
            self.silence_depuis = None
        elif self.silence_depuis is None:
            self.silence_depuis = self.t
            parle = sum(self.voix[-400:-1])                 # 8 s avant ce silence
            self._silence_apres_voix = parle >= 150         # >= 3 s de voix
        elif (self.t - self.silence_depuis >= 1.2 and getattr(self, "_silence_apres_voix", False)):
            self._silence_apres_voix = False
            if self._peut("silence_conversation", 20.0):
                out.append("silence_conversation")
        if len(self.voix) >= 6000 and int(self.t / 0.02) % 50 == 0 and sum(self.voix) / len(self.voix) >= 0.25:
            if self._peut("discussion_longue", 900.0):
                out.append("discussion_longue")

        # 2. groupe de claquements : on juge quand il n'en vient plus depuis 0,8 s
        if self.claps and self.t - self.claps[-1] > 0.8:
            out += self._juge_claps()

        # 3. battement regulier (toutes les 0,5 s, sur 6 s de son)
        if len(self.attaques) >= 300 and int(self.t / 0.02) % 25 == 0:
            out += self._juge_rythme()
        return out

    def _montee(self, debut):
        """Temps (s) pour passer de -20 dB sous le pic au pic, sur l'enveloppe fine autour du transitoire."""
        env = [(t, db) for t, db in self.enveloppe if t >= debut - 0.04]
        if not env:
            return 1.0
        i_pic = max(range(len(env)), key=lambda i: env[i][1])
        t_pic, pic = env[i_pic]
        i = i_pic
        while i > 0 and env[i - 1][1] > pic - 20.0:
            i -= 1
        return t_pic - env[i][0]

    def _juge_claps(self):
        c, self.claps = self.claps, []
        ecarts = np.diff(c)
        if len(c) >= 5 and c[-1] - c[0] <= 2.5 and float(np.mean(ecarts)) <= 0.35:   # serres : pas un battement
            return ["applaudissements"] if self._peut("applaudissements", self.delai_appel_s) else []
        if 2 <= len(c) <= 3 and all(0.12 <= e <= 0.7 for e in ecarts) and (len(c) == 2 or np.ptp(ecarts) < 0.15):
            return ["appel"] if self._peut("appel", self.delai_appel_s) else []
        return []

    def _juge_rythme(self):
        a = np.array(self.attaques)
        a = a - a.mean()
        ac0 = float(np.dot(a, a))
        fort = np.mean(np.array(self.niveaux) > self.fond + 6.0) > 0.5
        bpm = None
        if ac0 > 1e-9 and fort:
            # un battement se REPETE : correle a sa periode ET au double (le debit de syllabes d'une discussion
            # donne un pic a une periode, rarement au double) ; puis le meme tempo deux evaluations de suite
            ac = lambda k: float(np.dot(a[:-k], a[k:])) / ac0
            notes = [(min(ac(k), ac(2 * k)), k) for k in range(17, 51)]   # 180 a 60 BPM, blocs de 20 ms
            meilleur, k = max(notes)
            if meilleur >= 0.25:
                bpm = round(60.0 / (k * BLOC / TAUX))
        # le meme tempo (a 6 % pres) sur 4 evaluations de suite (2 s) avant d'y croire
        self._bpms = (getattr(self, "_bpms", []) + [bpm])[-4:]
        if bpm is not None and self.musique is None and not (
                len(self._bpms) == 4 and all(b is not None and abs(b - bpm) <= 0.06 * bpm for b in self._bpms)):
            return []
        if bpm is not None and self.musique is None:
            self.musique = bpm
            return [f"musique:{bpm}"]
        if bpm is None and self.musique is not None:
            self.musique = None
            return ["musique_fin"]
        return []


class MicroAlsa(threading.Thread):
    """Lit le micro (arecord, 16 kHz mono 16 bits) et passe chaque bloc a l'analyseur. `peripherique` : nom ALSA
    (MICRODUCK_MICRO, ex. "dsnoop:0" pour partager le micro avec quacksat). NON TESTE sur le robot."""

    def __init__(self, analyseur=None, peripherique=None):
        super().__init__(daemon=True)
        self.analyseur = analyseur or AnalyseurSon()
        self.peripherique = peripherique
        self.evenements, self.verrou, self.actif = [], threading.Lock(), True

    def run(self):
        cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(TAUX), "-c", "1", "-t", "raw"]
        if self.peripherique:
            cmd += ["-D", self.peripherique]
        while self.actif:
            try:
                with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as p:
                    while self.actif:
                        brut = p.stdout.read(BLOC * 2)
                        if len(brut) < BLOC * 2:
                            break
                        evts = self.analyseur.bloc(np.frombuffer(brut, dtype="<i2") / 32768.0)
                        if evts:
                            with self.verrou:
                                self.evenements += evts
                    p.terminate()
            except OSError:
                pass                                   # pas d'arecord / pas de micro : on reessaie plus tard
            time.sleep(5.0)

    def source(self):
        """A passer a brain.run(source=...)."""
        with self.verrou:
            out, self.evenements = self.evenements, []
        return out
