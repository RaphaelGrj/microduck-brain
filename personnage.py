#!/usr/bin/env python3
"""Son personnage au quotidien (ROADMAP « Vivant II », 2026-10-07) - le canard, pas l'application :

  - Hoquet : une crise de « hic » (un peck et la tete qui sursaute), qui passe toute seule, ou d'un coup avec une
    caresse ou une surprise ;
  - Gaffe : il bute sur un obstacle en promenade -> il secoue la tete, regarde l'objet d'un air vexe, et le contourne
    en faisant un detour exagere (la maladresse fait partie du personnage ; jamais un vrai danger) ;
  - Nid : avant la sieste, il tourne deux fois sur lui-meme, comme un chien qui fait son nid ;
  - Succes (cabotinage) : ce qui a fait rire ou applaudir revient plus souvent, ce qui tombe a plat se fait rare ;
  - Rituels : une habitude propre a chaque habitant (une caresse le soir...) : il vient la reclamer a l'heure ;
  - Inspecte : un objet nouveau dans le decor -> il s'en approche et le picore du bec (puis s'y habitue) ;
  - Doudou : sa balle, une fois qu'il y a beaucoup joue : il va la retrouver et se pose a cote ;
  - Rythme : on tape un rythme -> il le rejoue en coups de bec sonores ;
  - nom_sonore : une petite suite de sons a lui pour chaque habitant (sa facon de dire un nom, sans mot) ;
  - Petit : des voix fortes et tendues -> il se fait tout petit et silencieux ; des rires -> il s'anime ;
  - BainSoleil : une tache de soleil au sol (camera) -> il va s'y poser, et s'etire.

Toutes les sorties sont des sons de canard et des mouvements ; rien ne quitte le canard.
"""
import math
import zlib

import gestures
from etats_base import LIBRE_MIN, TETE_PROMENADE, V_PROMENADE, V_ROTATION, Etat, Sequence
from vivant import vie_au_repos


# -- hoquet --------------------------------------------------------------------------------------------------------
class Hoquet(Etat):
    """Crise de hoquet : un « hic » (peck + petit sursaut de la tete) toutes les 2 a 3,5 s, 20 a 45 s. Une caresse ou
    une surprise la fait passer (le cerveau enchaine alors « gueri »)."""
    nom = "hoquet"
    DUREE_S = (20.0, 45.0)
    ECART_S = (2.0, 3.5)
    HIC_S = 0.35

    def entre(self, brain):
        rng = getattr(brain, "_rng_vie", brain.rng)
        self.duree_s = rng.uniform(*self.DUREE_S)
        self.prochain, self.t_hic, self.hics = 0.8, None, 0
        self.rng = rng

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
        brain.ctx.move()
        if t >= self.prochain:
            self.t_hic, self.hics = t, self.hics + 1
            self.prochain = t + self.rng.uniform(*self.ECART_S)
            brain.ctx.sound("peck")                       # « hic ! »
        base = vie_au_repos(brain, t)
        if self.t_hic is not None and t - self.t_hic < self.HIC_S:
            k = math.sin(math.pi * (t - self.t_hic) / self.HIC_S)
            brain.ctx.head((base[0] - 0.08 * k, base[1] - 0.12 * k, base[2], base[3]))   # la tete sursaute
            return
        brain.ctx.head(base)


# -- gaffe : il bute, vexe, et contourne en exagerant -----------------------------------------------------------------
class Gaffe(Etat):
    """Il vient de buter (obstacle tout pres en promenade) : sursaut, « non » de la tete, regard vexe vers l'objet,
    puis un detour exagere (un grand pivot du cote degage). Jamais de marche ici : pivots sur place seulement."""
    nom = "gaffe"
    SURPRIS_S, NON_S, REGARD_S = 0.8, 2.4, 1.6

    def entre(self, brain):
        self.cote = getattr(brain, "cote_degage", 1.0) or 1.0
        self.pivot_s = (math.pi / 2 * 1.4) / V_ROTATION   # un quart de tour... et un peu plus (exagere)
        brain.ctx.sound("peck")

    def duree(self, brain):
        return self.SURPRIS_S + self.NON_S + self.REGARD_S + self.pivot_s + 0.5

    def pas(self, brain, t):
        a, b, c = self.SURPRIS_S, self.SURPRIS_S + self.NON_S, self.SURPRIS_S + self.NON_S + self.REGARD_S
        if t < a:
            brain.ctx.move()
            brain.ctx.head(gestures.surpris(t))
        elif t < b:
            brain.ctx.move()
            brain.ctx.head(gestures.non(t - a))
        elif t < c:
            brain.ctx.move()
            if t - b < 0.05:
                brain.ctx.sound("inquire")                # « qui a mis ca la ? »
            k = gestures._smooth(t - b, 0.0, 0.4)
            brain.ctx.head((0.0, 0.25 * k, 0.0, 0.15 * k))   # il fixe l'objet, tete penchee
        elif t < c + self.pivot_s:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))          # tete haute : la rotation est morte tete baissee
            brain.ctx.move(vyaw=self.cote * V_ROTATION)
        else:
            brain.ctx.move()
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))


# -- nid : deux tours sur lui-meme avant la sieste --------------------------------------------------------------------
class Nid(Etat):
    """Rituel du coucher : il tourne deux fois sur lui-meme (pivot sur place, tete haute), un « coo », puis la sieste."""
    nom = "nid"
    TOURS = 2

    def entre(self, brain):
        self.tour_s = 2 * math.pi / V_ROTATION
        self.sens = getattr(brain, "_rng_vie", brain.rng).choice((-1.0, 1.0))
        self.coo = False
        brain.suivant_force = "nap"

    def duree(self, brain):
        return self.TOURS * self.tour_s + 1.2

    def pas(self, brain, t):
        if t < self.TOURS * self.tour_s:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            brain.ctx.move(vyaw=self.sens * V_ROTATION)
            return
        brain.ctx.move()
        if not self.coo:
            self.coo = True
            brain.ctx.sound("coo")                        # il s'installe
        brain.ctx.head(gestures.fatigue(min(t - self.TOURS * self.tour_s, 1.0)))


# -- cabotinage -----------------------------------------------------------------------------------------------------------
class Succes:
    """Ce qui fait rire : un score par geste (garde dans la memoire). +1 quand on rit ou applaudit juste apres, -0,3
    quand quelqu'un est la et que rien ne vient. poids() : 0,4 (tombe a plat) .. 2,5 (son numero favori)."""
    FENETRE_S = 20.0

    def __init__(self, donnees=None):
        self.scores = donnees.setdefault("succes", {}) if donnees is not None else {}
        self.en_cours = None                              # (nom, t_global) du dernier numero

    def poids(self, nom):
        return max(0.4, min(2.5, 1.0 + 0.25 * self.scores.get(nom, 0.0)))

    def joue(self, nom, t):
        self.en_cours = (nom, t)

    def reaction(self, t):
        """Rires ou applaudissements a t : -> le nom du numero qui les a provoques, ou None."""
        if self.en_cours is None or t - self.en_cours[1] > self.FENETRE_S:
            return None
        nom = self.en_cours[0]
        self.scores[nom] = min(6.0, self.scores.get(nom, 0.0) + 1.0)
        self.en_cours = None
        return nom

    def juge(self, t, public):
        """A appeler regulierement : un numero sans reaction devant quelqu'un -> il a fait un flop."""
        if self.en_cours is not None and t - self.en_cours[1] > self.FENETRE_S:
            nom = self.en_cours[0]
            self.en_cours = None
            if public:
                self.scores[nom] = max(-2.4, self.scores.get(nom, 0.0) - 0.3)
                return nom
        return None


# -- rituels propres a chaque habitant ------------------------------------------------------------------------------------
RITUEL_JOURS = 14                # on regarde les deux dernieres semaines
RITUEL_MIN = 4                   # au moins 4 jours differents a la meme heure


def noter_rituel(donnees, qui, heure, jour):
    """Une caresse de `qui` a `heure` (0-23) le `jour` (numero de jour) : garde les jours distincts, par heure."""
    if not qui:
        return
    jours = donnees.setdefault("rituels", {}).setdefault(qui, {}).setdefault(str(heure), [])
    if jour not in jours:
        jours.append(jour)
    jours[:] = [j for j in jours if jour - j < RITUEL_JOURS]


def rituel_maintenant(donnees, qui, heure, jour):
    """Vrai si `qui` a l'habitude d'un calin a cette heure-ci et qu'il n'a pas encore eu lieu aujourd'hui."""
    jours = ((donnees.get("rituels") or {}).get(qui) or {}).get(str(heure), [])
    recents = [j for j in jours if 0 < jour - j < RITUEL_JOURS]
    return len(recents) >= RITUEL_MIN and jour not in jours


# -- un objet nouveau : il va le picorer --------------------------------------------------------------------------------
class Inspecte(Etat):
    """Il s'approche de l'objet nouveau (jusqu'a ~20 cm, 3 s au plus, a l'arret au moindre vide), le picore du bec
    (peck + « oui »), un « inquire », et reprend sa vie."""
    nom = "inspecte"
    PRES = 0.2
    MARCHE_MAX_S = 3.0

    def entre(self, brain):
        self.arrive = None

    def duree(self, brain):
        return self.MARCHE_MAX_S + 4.0

    def pas(self, brain, t):
        s = brain.ctx.state or {}
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(s) if tof is not None and s else None
        if self.arrive is None:
            brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
            if (lib is None or lib.get("vide", math.inf) < 0.6 or lib["devant"] <= self.PRES
                    or t >= self.MARCHE_MAX_S):
                self.arrive = t
                brain.ctx.move()
                if lib is None or lib.get("vide", math.inf) < 0.6:
                    brain.fin_etat = t                    # aveugle ou un vide : on n'y va pas
                    return
                brain.ctx.sound("peck")
            else:
                brain.ctx.move(vx=V_PROMENADE)
            return
        dt = t - self.arrive
        brain.ctx.move()
        if dt < 1.2:
            brain.ctx.head(gestures.oui(dt))              # il le picore
        elif dt < 3.7:
            if dt - 1.2 < 0.03:
                brain.ctx.sound("inquire")
            brain.ctx.head(gestures.curieux(dt - 1.2))
        else:
            brain.fin_etat = t


# -- doudou -------------------------------------------------------------------------------------------------------------
DOUDOU_PARTIES = 3               # sa balle devient son doudou apres quelques parties


class Doudou(Etat):
    """Pres de son doudou (la balle) : il le picore (skill officiel `ground_pick` : un mime tant qu'on ne sait pas s'il
    attrape vraiment), un « coo » tendre, puis il reste pose a cote, tete vers lui, un moment."""
    nom = "doudou"
    RESTE_S = (20.0, 45.0)

    def entre(self, brain):
        r = brain.ctx.client.request("robot.do", {"skill": "ground_pick"}) if brain.ctx.client else None
        self.pick = not (isinstance(r, dict) and "error" in r) and r is not None
        self.reste = getattr(brain, "_rng_vie", brain.rng).uniform(*self.RESTE_S)
        self.t_coo = None

    def duree(self, brain):
        return (6.0 if self.pick else 0.0) + 1.0 + self.reste

    def pas(self, brain, t):
        pol = (brain.ctx.state or {}).get("policy")
        if self.pick and self.t_coo is None and not ((t >= 1.0 and pol != "ground_pick") or t >= 6.0):
            return                                        # le robot pilote le geste
        if self.t_coo is None:
            self.t_coo = t
            brain.ctx.sound("coo")
        brain.ctx.move()
        brain.ctx.head(vie_au_repos(brain, t, (0.0, 0.3, 0.0, 0.1)))   # tete penchee vers son doudou


# -- rythme --------------------------------------------------------------------------------------------------------------
class Rythme(Etat):
    """On a tape un rythme (audio : « motif:<ecarts en ms> ») : il le rejoue en coups de bec sonores, la tete qui
    pique a chaque coup. Espiegle, il ajoute parfois un coup de trop... et prend un air fier."""
    nom = "rythme"
    PIQUE_S = 0.14
    MAX_COUPS = 8

    def __init__(self):
        self.ecarts = []

    def entre(self, brain):
        rng = getattr(brain, "_rng_vie", brain.rng)
        coups, t = [0.6], 0.6                             # un temps de silence : il a ecoute
        for e in self.ecarts[: self.MAX_COUPS - 1]:
            t += min(1.0, max(0.1, e))
            coups.append(t)
        self.bonus = rng.random() < 0.2 + 0.3 * brain.perso.trait("espieglerie")
        if self.bonus and len(coups) >= 2:
            t += coups[-1] - coups[-2]
            coups.append(t)                               # un de plus, pour voir
        self.coups, self.joues = coups, set()
        self.fin_coups = coups[-1] + self.PIQUE_S

    def duree(self, brain):
        return self.fin_coups + (1.8 if self.bonus else 0.6)

    def pas(self, brain, t):
        brain.ctx.move()
        for i, c in enumerate(self.coups):
            if c <= t < c + self.PIQUE_S:
                if i not in self.joues:
                    self.joues.add(i)
                    brain.ctx.sound("peck")
                k = math.sin(math.pi * (t - c) / self.PIQUE_S)
                brain.ctx.head((0.0, 0.18 * k, 0.0, 0.0))
                return
        if self.bonus and t >= self.fin_coups:
            brain.ctx.head(gestures.fier(min(t - self.fin_coups, 1.8)))
            return
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))


# -- son nom a lui pour chaque habitant ------------------------------------------------------------------------------------
SONS_NOM = ("chirp", "coo", "inquire", "peck", "greet")


def nom_sonore(qui):
    """2 ou 3 sons de canard, toujours les memes pour un habitant (stables d'un redemarrage a l'autre, sans rien
    stocker) : sa facon de dire un prenom, sans mot."""
    h = zlib.crc32(("nom:" + qui).encode())
    n = 2 + h % 2
    sons = []
    for _ in range(n):
        h //= 5
        sons.append(SONS_NOM[h % len(SONS_NOM)])
    if len(set(sons)) == 1:
        sons[-1] = SONS_NOM[(SONS_NOM.index(sons[-1]) + 1) % len(SONS_NOM)]
    return tuple(sons)


class Nomme(Sequence):
    """Il « dit le nom » de quelqu'un : sa suite de sons pour lui, chaque son avec un petit hochement."""

    def __init__(self):
        super().__init__("nomme", [])
        self.qui, self.ensuite = None, None

    def etapes_pour(self, brain):
        return [("oui", son) for son in (nom_sonore(self.qui) if self.qui else ("chirp",))]

    def entre(self, brain):
        super().entre(brain)
        if self.ensuite:
            brain.suivant_force, self.ensuite = self.ensuite, None


# -- l'ambiance de la maison ------------------------------------------------------------------------------------------------
class Petit(Etat):
    """Des voix fortes et tendues : il se fait tout petit - cou rentre, tete basse, immobile et muet, un moment."""
    nom = "petit"
    DUREE_S = (60.0, 120.0)

    def entre(self, brain):
        self.duree_s = getattr(brain, "_rng_vie", brain.rng).uniform(*self.DUREE_S)

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
        brain.ctx.move()
        k = gestures._smooth(t, 0.0, 1.5)
        brain.ctx.head(vie_au_repos(brain, t, (-0.15 * k, 0.35 * k, 0.0, 0.0)))


# -- bain de soleil ---------------------------------------------------------------------------------------------------------
def tache_soleil(img, seuil=0.9, ecart=0.3, fraction_min=0.03):
    """Tache de soleil au sol : dans la moitie basse de l'image (le sol), une zone tres lumineuse (luminance >= seuil,
    et bien au-dessus de la mediane) qui couvre au moins `fraction_min`. `img` : tableau HxWx3 (0-255).
    -> (x relatif 0..1 du centre de la tache, fraction couverte), ou None."""
    import numpy as np
    a = np.asarray(img, dtype=np.float32)
    if a.ndim != 3 or a.shape[0] < 4:
        return None
    sol = a[a.shape[0] // 2:, :, :3] / 255.0
    lum = sol.max(axis=2)
    masque = (lum >= seuil) & (lum >= float(np.median(lum)) + ecart)
    f = float(masque.mean())
    if f < fraction_min:
        return None
    xs = np.nonzero(masque)[1]
    return float(xs.mean() + 0.5) / sol.shape[1], f


class BainSoleil(Etat):
    """Il a vu une tache de soleil au sol : il pivote vers elle, avance (2,5 s au plus, a l'arret devant un obstacle
    ou un vide), s'etire, s'assoit au chaud tete levee, un « coo » de bien-etre, puis se releve."""
    nom = "bain_soleil"
    CHAMP_RAD = math.radians(45)
    MARCHE_MAX_S = 2.5

    def __init__(self):
        self.x_rel = 0.5

    def entre(self, brain):
        self.angle = -(self.x_rel - 0.5) * self.CHAMP_RAD     # image : droite = lacet negatif
        self.pivot_s = abs(self.angle) / V_ROTATION if abs(self.angle) > math.radians(8) else 0.0
        self.phase, self.t0 = "pivote", 0.0
        self.reste = getattr(brain, "_rng_vie", brain.rng).uniform(40.0, 90.0)
        brain.ctx.sound("chirp")

    def duree(self, brain):
        return self.pivot_s + self.MARCHE_MAX_S + 3.5 + self.reste + 3.0

    def pas(self, brain, t):
        dt = t - self.t0
        s = brain.ctx.state or {}
        if self.phase == "pivote":
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            if dt >= self.pivot_s:
                self.phase, self.t0 = "avance", t
                brain.ctx.move()
            else:
                brain.ctx.move(vyaw=math.copysign(V_ROTATION, self.angle))
        elif self.phase == "avance":
            brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
            tof = brain.ctx.extras.get("tof")
            lib = tof.libre(s) if tof is not None and s else None
            if (lib is None or lib["devant"] < LIBRE_MIN or lib.get("vide", math.inf) < 0.6
                    or dt >= self.MARCHE_MAX_S):
                self.phase, self.t0 = "etire", t
                brain.ctx.move()
            else:
                brain.ctx.move(vx=V_PROMENADE)
        elif self.phase == "etire":
            brain.ctx.move()
            brain.ctx.head(gestures.etirement(min(dt, 3.0)))
            if dt >= 3.2:
                self.phase, self.t0 = "chauffe", t
                if not brain.ctx.sitting:
                    brain.ctx.toggle_sit()
                brain.ctx.sound("coo")
        elif self.phase == "chauffe":
            brain.ctx.head(vie_au_repos(brain, t, (0.0, -0.2, 0.0, 0.0)))   # tete levee vers la lumiere
            if dt >= self.reste:
                self.phase, self.t0 = "leve", t
                if brain.ctx.sitting and not brain.reste_assis():
                    brain.ctx.toggle_sit()
        else:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            brain.ctx.move()

    def sort(self, brain):
        if brain.ctx.sitting and not brain.reste_assis():
            brain.ctx.toggle_sit()
        brain.ctx.calme()
