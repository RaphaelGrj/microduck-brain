#!/usr/bin/env python3
"""Caresse (ROADMAP, table Humains : "Caresse | pet-detect | roucoulement, etat Petted, geste content").

Le detecteur officiel `pet-detect` n'est pas encore documente cote API (a verifier a la livraison) : le cerveau accepte
donc un evenement "caresse" venu de l'exterieur, ET propose ce detecteur maison, sans capteur en plus : une main posee
sur la tete la DEPLACE. Les servos XL330 sont souples (gains bas) ; quand la consigne de tete est immobile depuis un
moment, leur position mesuree (`robot.state.joints`, tete = indices 5..8) est stable a quelques milliemes de radian
pres. Un ecart net et durable par rapport a cette position de repos = quelque chose appuie sur la tete.

Logique pure (testable sans robot). Hypotheses a valider sur le vrai canard : amplitude reelle de l'ecart sous une
caresse (les XL330 de la tete cedent-ils de > 3 degres ?), bruit des joints en position debout, et ce que fait
`pet-detect` (peut-etre la meme chose, en mieux).
"""

ETABLISSEMENT_S = 1.0      # apres un changement de consigne : la tete rejoint sa consigne (lissage robotd)
MESURE_S = 0.5             # puis on mesure sa position de repos pendant 0,5 s
SEUIL_RAD = 0.06           # ~3,4 degres d'ecart sur un joint de tete
TENU_S = 0.3               # ecart tenu au moins 0,3 s (un choc ou un a-coup de la marche n'est pas une caresse)
ADAPTATION_S = 10.0        # derive lente de la position de repos (temperature, gravite) suivie en dehors des contacts


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
        self.contact_depuis = None
        self.en_contact = False

    def ecart(self, joints):
        return max(abs(j - r) for j, r in zip(joints, self.repos)) if self.repos is not None else 0.0

    def mise_a_jour(self, t, consigne, joints_tete, immobile=True):
        """`consigne` : derniere consigne robot.head (tuple), `joints_tete` : 4 positions mesurees, `immobile` : le
        corps ne marche pas. Renvoie ["caresse"] au debut d'un contact, [] sinon."""
        if not immobile or consigne != self.consigne or joints_tete is None:
            self.reinitialiser(consigne if immobile else None, t)
            return []
        age = t - self.t_consigne
        if age < ETABLISSEMENT_S:
            return []
        if self.repos is None:
            self.echantillons.append(tuple(joints_tete))
            if age >= ETABLISSEMENT_S + MESURE_S:
                n = len(self.echantillons)
                self.repos = [sum(e[i] for e in self.echantillons) / n for i in range(4)]
            return []
        e = self.ecart(joints_tete)
        if e < SEUIL_RAD / 2:
            self.contact_depuis, self.en_contact = None, False
            k = min(1.0, 0.02 / ADAPTATION_S)          # ~ une trame de 20 ms sur ADAPTATION_S
            self.repos = [r + k * (j - r) for r, j in zip(self.repos, joints_tete)]
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
