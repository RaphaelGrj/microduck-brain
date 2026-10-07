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
  - "silence_conversation" : un silence d'au moins 1,2 s juste apres plusieurs secondes de voix -> "dernier mot" ;
  - "enonce:<duree>|<sens>" : fin d'une phrase de 0,3 a 3,5 s (tour de parole : le cerveau peut y « repondre ») ;
  - "intonation:monte|descend" : un enonce de 0,4 a 3 s dont la hauteur (autocorrelation) monte ou descend d'au moins
    3 demi-tons -> le canard mime le ton (taquinerie) ;
  - "alarme_fumee:son" : bips aigus (2,5-4,5 kHz) reguliers, au moins 9 en 15 s (motif T3 des detecteurs de fumee :
    3 bips, pause, 3 bips...) -> l'alarme du canard, PRIORITAIRE, meme sans Home Assistant ;
  - "toc_porte"        : 2 a 5 chocs brefs et GRAVES (centroide spectral < 1,5 kHz), espaces de 0,1 a 0,45 s -> on
    frappe a la porte (un claquement de mains est aigu : il reste un "appel") ;
  - "telephone" / "telephone_fin" : quelqu'un parle AU TELEPHONE dans la piece : une seule voix (hauteur mediane des
    enonces stable, a 3 demi-tons pres), coupee de blancs reguliers (l'autre parle dans le combine) -> le canard se
    fait discret. Deux personnes de voix proches donnent le meme motif : consequence benigne (il se tait un moment) ;
  - "baillement_entendu" : un son voise et CONTINU de 1,6 a 3,5 s (une phrase qui descend dure rarement autant), qui descend d'au moins 5 demi-tons, apres un
    silence (pas au milieu d'une phrase) -> baillement contagieux ;
  - "petarades"        : au moins 6 chocs forts en 4 s, a intervalles IRREGULIERS (petards, feux d'artifice) - ni le
    tonnerre (un choc isole ou deux), ni des applaudissements forts (reguliers) -> prudence marquee et plus longue ;
  - "bips_appareil"    : 1 a 6 bips aigus groupes puis le silence (four, micro-ondes, lave-linge en fin de cycle) -
    pas l'alarme incendie, dont les bips continuent (motif T3) ;
  - "vacarme" / "vacarme_fin" : niveau sonore moyen tres eleve pendant une minute (fete, dispute, travaux) -> il se
    retire dans son coin ; fin quand c'est retombe depuis 30 s. Seuil absolu (dBFS) a etalonner sur le vrai micro ;
  - "eternuement"      : bruit large bande (platitude spectrale), attaque nette, 0,12 a 0,6 s, tres au-dessus du fond.
    Heuristique a etalonner : une chute d'objet peut y ressembler (consequence benigne : il "compte" au lieu de sursauter).
Methode : niveau par bloc (dB), bruit de fond suivi par le bas (monte lentement, descend tout de suite), transitoires =
saut de niveau au-dessus du fond qui retombe vite ; tempo = autocorrelation de la "force d'attaque" sur 6 s.
Seuils a etalonner sur le vrai micro (reglables a la construction).

`MicroAlsa` : source optionnelle qui lit le micro par `arecord` (ALSA). NON TESTEE, et probablement INUTILISABLE telle
quelle sur le robot : d'apres le code officiel (pollen-robotics/microduck, pet-detect/src/worker.rs, lu le 2026-10-05),
le micro de la tete n'accepte qu'UN client et c'est `robotd` qui l'occupe (detection de caresse PAR LE SON du grattage,
roucoulement natif, et une "sentinelle" qui classe deja Noise / Voice par enveloppe RMS - sans les exposer aux clients :
"no consumer until the autonomous brain arrives"). Voies : faire remonter ces evenements par robot.subscribe (contribution
amont), ou un partage ALSA (dsnoop) ; quacksat utilise aussi le micro (QUACKSAT_QUACKNAV.md). Vie privee : le son est
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


def platitude(x):
    """Platitude spectrale (0 = son tonal, 1 = bruit blanc) entre 300 Hz et 6 kHz."""
    p = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2 + 1e-12
    f = np.fft.rfftfreq(len(x), 1.0 / TAUX)
    p = p[(f >= 300) & (f <= 6000)]
    return float(np.exp(np.mean(np.log(p))) / np.mean(p))


def centroide(x):
    """Centroide spectral (Hz) : grave (coup sur une porte) ou aigu (claquement de mains)."""
    p = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / TAUX)
    return float(np.sum(f * p) / (np.sum(p) + 1e-12))


def bip_aigu(x):
    """Le bloc est-il un bip d'alarme ? Son quasi pur (>= 50 % de l'energie dans +-60 Hz autour du pic) entre 2,5 et
    4,5 kHz."""
    p = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / TAUX)
    k = int(np.argmax(p))
    if not 2500.0 <= f[k] <= 4500.0:
        return False
    autour = p[(f >= f[k] - 60.0) & (f <= f[k] + 60.0)].sum()
    return autour >= 0.5 * p.sum()


def hauteurs(son, trame=640, pas=320):
    """Hauteur (Hz) des trames voisees (autocorrelation normalisee >= 0,5, 80-400 Hz) : liste de (instant s, f0)."""
    out = []
    for i in range(0, len(son) - trame, pas):
        w = son[i:i + trame] - np.mean(son[i:i + trame])
        e = float(np.dot(w, w))
        if e < 1e-8:
            continue
        lags = np.arange(TAUX // 400, TAUX // 80 + 1)
        r = np.array([float(np.dot(w[:-k], w[k:])) for k in lags]) / e
        k = int(np.argmax(r))
        if r[k] >= 0.5:
            out.append(((i + trame / 2) / TAUX, TAUX / lags[k]))
    return out


def intonation(son, h=None):
    """"monte" / "descend" si la hauteur du dernier tiers de l'enonce differe d'au moins 3 demi-tons de celle du premier
    tiers ; None sinon (enonce trop court, trop peu voise, ou plat). `h` : hauteurs(son) deja calculees."""
    if not 0.4 * TAUX <= len(son) <= 3.5 * TAUX:
        return None
    h = hauteurs(son) if h is None else h
    if len(h) < 6:
        return None
    n = len(h) // 3
    debut = np.mean([np.log2(f) for _, f in h[:n]])
    fin = np.mean([np.log2(f) for _, f in h[-n:]])
    dt = 12.0 * (fin - debut)
    return "monte" if dt >= 3.0 else "descend" if dt <= -3.0 else None


def baillement(son, h):
    """Un baillement : 1,6 a 3,5 s (heuristique a etalonner), voise sur au moins 60 % des trames (pas de pause au milieu), et une hauteur qui
    descend d'au moins 5 demi-tons du premier au dernier quart."""
    duree = len(son) / TAUX
    if not 1.6 <= duree <= 3.5 or len(h) < 0.6 * (len(son) - 640) / 320:
        return False
    n = max(2, len(h) // 4)
    debut = np.mean([np.log2(f) for _, f in h[:n]])
    fin = np.mean([np.log2(f) for _, f in h[-n:]])
    return 12.0 * (debut - fin) >= 5.0


TEL_FENETRE_S = 60.0            # telephone : on juge sur la derniere minute
TEL_ENONCES_MIN = 6
TEL_DEMI_TONS = 3.0             # une seule voix : hauteurs medianes des enonces a +-3 demi-tons
TEL_FIN_S = 25.0                # plus aucune voix depuis 25 s : l'appel est fini


def une_seule_voix(f0s):
    m = float(np.median(np.log2(f0s)))
    return all(abs(12.0 * (np.log2(f) - m)) <= TEL_DEMI_TONS for f in f0s)


class AnalyseurSon:
    def __init__(self, seuil_fort_dbfs=-12.0, saut_transitoire_db=15.0, delai_bruit_s=5.0, delai_appel_s=20.0,
                 seuil_vacarme_dbfs=-28.0):
        self.seuil_vacarme = seuil_vacarme_dbfs
        self.secondes = []                       # niveau moyen (dB) de chaque seconde, sur 60 s (vacarme)
        self._seconde = []
        self.vacarme = False
        self.groupe_bips = []                    # debuts des bips du groupe en cours (bips d'appareil)
        self.chocs = []                          # instants des chocs forts recents (petarades)
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
        self.enonce = []                         # echantillons de l'enonce (voix) en cours, 3 s au plus
        self.calme_enonce = 0                    # blocs silencieux depuis la derniere voix de l'enonce
        self.platitudes = []                     # platitude spectrale des blocs du transitoire en cours
        self.bip_debut = None                    # debut du bip aigu en cours
        self.bips = []                           # instants des bips d'alarme reconnus (15 s)
        self.enonces = []                        # (fin, duree, hauteur mediane) des enonces voises (telephone)
        self.telephone = False
        self.silence_avant_enonce = 0.0          # silence (s) juste avant l'enonce en cours (baillement)

    def _peut(self, nom, delai):
        if self.t - self.dernier.get(nom, -1e9) < delai:
            return False
        self.dernier[nom] = self.t
        return True

    def bloc_muet(self, n):
        """Le canard parle pendant ce bloc (VoixPropre) : le temps avance, mais rien n'est analyse ni appris (ni le
        fond, ni un transitoire, un claquement, un enonce ou un bip en cours)."""
        self.t += n / TAUX
        self.transitoire, self.bip_debut = None, None
        self.claps, self.enonce, self.calme_enonce = [], [], 0

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

        # 1. transitoires : saut au-dessus du fond, qui doit retomber vite (claquement, choc, eternuement)
        if self.transitoire is None and niveau - self.fond >= self.saut and niveau - prec >= self.saut * 0.6:
            self.transitoire = [self.t, niveau, self.fond]
            self.platitudes = [platitude(x)]
            self.centroide_transitoire = centroide(x)
        elif self.transitoire is not None:
            self.transitoire[1] = max(self.transitoire[1], niveau)
            self.platitudes.append(platitude(x))
            duree = self.t - self.transitoire[0]
            if niveau - self.fond < self.saut * 0.5:          # retombe : c'etait bref
                debut, pic, fond = self.transitoire
                self.transitoire = None
                montee = self._montee(debut)
                if (0.12 < duree <= 0.6 and pic - fond >= 25.0 and montee <= 0.03
                        and float(np.mean(self.platitudes)) >= 0.35):
                    if self._peut("eternuement", 1.5):
                        out.append("eternuement")
                elif pic >= self.seuil_fort:
                    self.chocs = [c for c in self.chocs if self.t - c <= 4.0] + [self.t]
                    ecarts = np.diff(self.chocs)
                    # des applaudissements forts sont quasi PERIODIQUES ; des petards, irreguliers
                    irregulier = len(ecarts) >= 5 and float(np.std(ecarts)) >= 0.35 * float(np.mean(ecarts))
                    if len(self.chocs) >= 6 and irregulier and self._peut("petarades", 120.0):
                        self.chocs = []
                        out.append("petarades")
                    elif self._peut("bruit", self.delai_bruit_s):
                        out.append("bruit")
                elif duree <= 0.15 and self.musique is None and montee <= MONTEE_CLAP_S:
                    self.claps.append((debut, self.centroide_transitoire))
            elif duree > 0.6:                                  # son tenu : ni claquement, ni choc, ni eternuement
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

        # 2 quater. bips d'alarme (detecteur de fumee) : bips purs et aigus, 0,08 a 0,8 s, nombreux et reguliers
        if niveau - self.fond >= 15.0 and bip_aigu(x):
            if self.bip_debut is None:
                self.bip_debut = self.t
        elif self.bip_debut is not None:
            if 0.08 <= self.t - self.bip_debut <= 0.8:
                self.bips = [b for b in self.bips if self.t - b <= 15.0] + [self.bip_debut]
                self.groupe_bips.append(self.bip_debut)
                if len(self.bips) >= 9 and self._peut("alarme_fumee", 60.0):
                    out.append("alarme_fumee:son")
            self.bip_debut = None

        # bips d'appareil : le groupe est juge apres 3 s sans bip ; une alarme incendie, elle, ne s'arrete pas
        if self.groupe_bips and self.bip_debut is None and self.t - self.groupe_bips[-1] > 3.0:
            groupe, self.groupe_bips = self.groupe_bips, []
            if (len(groupe) <= 6 and self.t - self.dernier.get("alarme_fumee", -1e9) > 60.0
                    and self._peut("bips_appareil", 60.0)):
                out.append("bips_appareil")

        # vacarme : niveau moyen de chaque seconde, juge sur la derniere minute
        self._seconde.append(niveau)
        if len(self._seconde) >= 50:
            self.secondes = (self.secondes + [10.0 * np.log10(np.mean(10.0 ** (np.array(self._seconde) / 10.0)))])[-60:]
            self._seconde = []
            fort = [db >= self.seuil_vacarme for db in self.secondes]
            if not self.vacarme and len(fort) == 60 and sum(fort) >= 45 and self._peut("vacarme", 600.0):
                self.vacarme = True
                out.append("vacarme")
            elif self.vacarme and not any(fort[-30:]):
                self.vacarme = False
                out.append("vacarme_fin")

        # 2 ter. enonces : on garde le son tant que la voix continue (pauses < 0,3 s), on juge l'intonation a la fin
        if actif:
            if not self.enonce:                  # debut d'enonce : combien de silence juste avant (1,5 s au plus) ?
                self.blocs_enonce = 0
                n = 0
                for v in reversed(self.voix[-76:-1]):
                    if v:
                        break
                    n += 1
                self.silence_avant_enonce = n * BLOC / TAUX
            self.enonce = (self.enonce + [x])[-175:]
            self.blocs_enonce += 1               # duree REELLE (le son garde est tronque a 3,5 s)
            self.calme_enonce = 0
        elif self.enonce:
            self.calme_enonce += 1
            if self.calme_enonce < 15:
                self.enonce.append(x)
                self.blocs_enonce += 1
            else:
                son, self.enonce = np.concatenate(self.enonce[:-14]), []      # sans le silence de fin
                duree = (self.blocs_enonce - 14) * BLOC / TAUX
                tronque = duree > 3.5 + 1e-6     # une longue tirade : ni baillement ni intonation (debut jete)
                h = hauteurs(son) if not tronque else []
                sens = intonation(son, h)
                if (self.silence_avant_enonce >= 1.0 and baillement(son, h)
                        and self._peut("baillement_entendu", 60.0)):
                    out.append("baillement_entendu")
                elif sens and self._peut("intonation", 8.0):
                    out.append(f"intonation:{sens}")
                if not tronque and duree >= 0.3 and len(h) >= 4:        # une voix (hauteur suivie), pas un choc
                    out.append(f"enonce:{duree:.1f}|{sens or ''}")      # tour de parole (vivant : il repond)
                if tronque:
                    self.enonces.append((self.t, duree, None))   # compte dans la parole, sans hauteur
                elif len(h) >= 4:
                    self.enonces.append((self.t, duree, float(np.median([f for _, f in h]))))
                self.enonces = [e for e in self.enonces if self.t - e[0] <= TEL_FENETRE_S]
                out += self._juge_telephone()
        if self.telephone and self.silence_depuis is not None and self.t - self.silence_depuis >= TEL_FIN_S:
            self.telephone = False
            out.append("telephone_fin")

        # 2. groupe de claquements : on juge quand il n'en vient plus depuis 0,8 s
        if self.claps and self.t - self.claps[-1][0] > 0.8:
            out += self._juge_claps()

        # 3. battement regulier (toutes les 0,5 s, sur 6 s de son)
        if len(self.attaques) >= 300 and int(self.t / 0.02) % 25 == 0:
            out += self._juge_rythme()
        return out

    def _juge_telephone(self):
        """Une seule voix sur la derniere minute, des enonces nombreux mais une parole qui n'occupe pas tout le temps
        (les blancs = l'autre au bout du fil). Dans une discussion a deux dans la piece, les hauteurs se melangent."""
        e = [x for x in self.enonces if self.t - x[0] <= TEL_FENETRE_S]
        if self.telephone or len(e) < TEL_ENONCES_MIN:
            return []
        parole = sum(d for _, d, _ in e)
        f0s = [f for _, _, f in e if f is not None]
        if (not 0.15 * TEL_FENETRE_S <= parole <= 0.7 * TEL_FENETRE_S or len(f0s) < TEL_ENONCES_MIN
                or not une_seule_voix(f0s)):
            return []
        if self.t - e[0][0] < 0.6 * TEL_FENETRE_S:
            return []                             # pas encore une minute d'observation
        self.telephone = True
        return ["telephone"]

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
        groupe, self.claps = self.claps, []
        c = [t for t, _ in groupe]
        ecarts = np.diff(c)
        if 2 <= len(c) <= 5 and np.mean([z for _, z in groupe]) < 1500.0 and all(0.1 <= e <= 0.45 for e in ecarts):
            return ["toc_porte"] if self._peut("toc_porte", 20.0) else []     # chocs graves : on frappe a la porte
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


class VoixPropre:
    """Le canard ne doit pas s'entendre lui-meme : sa propre alarme ressemble a une alarme incendie, son "wheee" a un
    bruit fort. Le cerveau signale chaque son qu'il joue (Ctx.sound -> parle) ; pendant sa duree (+ une marge d'echo),
    le micro n'est pas analyse."""
    DUREES_S = {"alarm": 1.2, "greet": 1.0, "inquire": 1.0, "peck": 0.6, "chirp": 0.8, "coo": 1.5, "wheee": 2.5}
    MARGE_S = 0.4

    def __init__(self, horloge=time.monotonic):
        self.horloge = horloge
        self.jusqua = 0.0

    def parle(self, tag):
        self.jusqua = max(self.jusqua, self.horloge() + self.DUREES_S.get(tag, 1.5) + self.MARGE_S)

    def muet(self):
        return self.horloge() < self.jusqua


class MicroAlsa(threading.Thread):
    """Lit le micro (arecord, 16 kHz mono 16 bits) et passe chaque bloc a l'analyseur et, si elles sont configurees, aux
    commandes vocales locales (commandes.py) : une seule lecture du micro pour les deux. `peripherique` : nom ALSA
    (MICRODUCK_MICRO ; sur le robot, le PCM dsnoop partage avec robotd, deploy/robot/asound.conf). NON TESTE sur le robot."""

    def __init__(self, analyseur=None, peripherique=None, commandes=None, voix=None):
        super().__init__(daemon=True)
        self.analyseur = analyseur or AnalyseurSon()
        self.commandes = commandes
        self.voix = voix                               # VoixPropre : rien n'est analyse pendant que le canard parle
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
                        if self.voix is not None and self.voix.muet():
                            self.analyseur.bloc_muet(len(brut) // 2)
                            continue
                        evts = self.analyseur.bloc(np.frombuffer(brut, dtype="<i2") / 32768.0)
                        if self.commandes is not None:
                            evts = evts + self.commandes.bloc_brut(brut)
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
