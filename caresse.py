#!/usr/bin/env python3
"""Caresse (ROADMAP, table Humains : "Caresse | pet-detect | roucoulement, etat Petted, geste content").

Le `pet-detect` officiel est AUDIO (il entend le grattage, micro dans la tete) et tourne dans robotd sans rien exposer aux
clients (code lu le 2026-10-05). Le cerveau accepte donc un evenement "caresse" venu de l'exterieur, ET propose ce
detecteur maison, sans capteur en plus : une main posee sur la tete la DEPLACE. Les servos XL330 sont souples (gains bas) ; quand la consigne de tete est immobile depuis un
moment, leur position mesuree (`robot.state.joints`, tete = indices 5..8) est stable a quelques milliemes de radian
pres. Un ecart net et durable par rapport a cette position de repos = quelque chose appuie sur la tete.

Deuxieme indice, plus direct (2026-10-05) : `robot.state.currents_ma` (v36) donne le COURANT de chaque servo - "la seule
mesure de force exterieure du robot", y compris "une main qui appuie sur le bec" selon la doc de Pollen. Quand il est
publie, un surcroit de courant durable sur un servo de tete compte aussi comme contact. Et le `pet-detect` officiel
(audio : il entend le grattage) remontera par robot.state.audio si le patch contrib/robotd-audio-state.patch est
accepte - le cerveau le traduit alors en evenement "caresse" sans passer par ce detecteur.

Logique pure (testable sans robot). Hypotheses a valider sur le vrai canard : amplitude reelle de l'ecart sous une
caresse (les XL330 de la tete cedent-ils de > 3 degres ? quel surcroit de courant ?), bruit des joints et des courants
en position debout.
"""

ETABLISSEMENT_S = 1.0      # apres un changement de consigne : la tete rejoint sa consigne (lissage robotd)
MESURE_S = 0.5             # puis on mesure sa position de repos pendant 0,5 s
SEUIL_RAD = 0.06           # ~3,4 degres d'ecart sur un joint de tete
TENU_S = 0.3               # ecart tenu au moins 0,3 s (un choc ou un a-coup de la marche n'est pas une caresse)
SEUIL_MA = 60.0            # surcroit de courant sur un servo de tete (mA) : un appui qui force le servo
ADAPTATION_S = 10.0        # derive lente de la position de repos (temperature, gravite) suivie en dehors des contacts
SAUT_RAD = 0.05            # une consigne qui SAUTE (geste, regard) : on remesure ; une consigne qui glisse lentement
                           # (respiration, petites saccades : vivant.py) est suivie - on mesure l'ecart a la consigne


class DetecteurCaresse:
    def __init__(self, delai_s=15.0):
        self.delai_s = delai_s
        self.dernier_evenement = None
        self.reinitialiser(None, 0.0)

    def reinitialiser(self, consigne, t):
        self.consigne = consigne
        self.t_consigne = t
        self.echantillons = []
        self.repos = None          # position de repos des 4 joints de tete
        self.repos_ma = None       # courant de repos des 4 servos de tete (si publie)
        self.contact_depuis = None
        self.en_contact = False

    def _ecarts(self, joints):
        """Position mesuree moins consigne (la tete suit sa consigne a un petit ecart pres : gravite, souplesse)."""
        c = self.consigne
        return [j - (c[i] if c is not None and i < len(c) else 0.0) for i, j in enumerate(joints)]

    def ecart(self, joints):
        if self.repos is None:
            return 0.0
        return max(abs(e - r) for e, r in zip(self._ecarts(joints), self.repos))

    def mise_a_jour(self, t, consigne, joints_tete, immobile=True, courants=None):
        """`consigne` : derniere consigne robot.head (tuple), `joints_tete` : 4 positions mesurees, `immobile` : le
        corps ne marche pas, `courants` : 4 courants mesures (mA) ou None. Renvoie ["caresse"] au debut d'un contact."""
        if not immobile or joints_tete is None:
            self.reinitialiser(consigne if immobile else None, t)
            return []
        if consigne != self.consigne:
            saut = (consigne is None or self.consigne is None
                    or max(abs(a - b) for a, b in zip(consigne, self.consigne)) > SAUT_RAD * (1 if self.repos is None else 0.5))
            if saut:
                self.reinitialiser(consigne, t)
                return []
            self.consigne = consigne               # elle glisse doucement : on la suit sans remesurer
        age = t - self.t_consigne
        if age < ETABLISSEMENT_S:
            return []
        if self.repos is None:
            self.echantillons.append((tuple(self._ecarts(joints_tete)), tuple(courants) if courants else None))
            if age >= ETABLISSEMENT_S + MESURE_S:
                n = len(self.echantillons)
                self.repos = [sum(e[0][i] for e in self.echantillons) / n for i in range(4)]
                if all(e[1] for e in self.echantillons):
                    self.repos_ma = [sum(e[1][i] for e in self.echantillons) / n for i in range(4)]
            return []
        e = self.ecart(joints_tete)
        if courants and self.repos_ma is not None:
            # ramene l'ecart de courant a l'echelle du seuil de position : un seul critere "contact"
            e = max(e, SEUIL_RAD * max(abs(c - r) for c, r in zip(courants, self.repos_ma)) / SEUIL_MA)
        if e < SEUIL_RAD / 2:
            self.contact_depuis, self.en_contact = None, False
            k = min(1.0, 0.02 / ADAPTATION_S)          # ~ une trame de 20 ms sur ADAPTATION_S
            self.repos = [r + k * (j - r) for r, j in zip(self.repos, self._ecarts(joints_tete))]
            if courants and self.repos_ma is not None:
                self.repos_ma = [r + k * (c - r) for r, c in zip(self.repos_ma, courants)]
            return []
        if e < SEUIL_RAD:
            return []
        if self.contact_depuis is None:
            self.contact_depuis = t
        if (not self.en_contact and t - self.contact_depuis >= TENU_S
                and (self.dernier_evenement is None or t - self.dernier_evenement >= self.delai_s)):
            self.en_contact = True
            self.dernier_evenement = t
            return ["caresse"]
        return []
