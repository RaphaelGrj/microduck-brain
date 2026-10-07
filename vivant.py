#!/usr/bin/env python3
"""Ce qui le rend vivant au quotidien (ROADMAP « Vivant », 2026-10-07) - le canard, pas l'application :

  - vie_au_repos : il n'est jamais fige - respiration (le cou monte et descend doucement), petites saccades du regard ;
    plus lent quand il est fatigue, plus vif quand il est eveille ;
  - Habituation : un stimulus nouveau le fait sursauter fort, de moins en moins s'il revient, puis il l'ignore ; apres une
    longue absence, il redevient interessant ;
  - Retours : il apprend l'heure habituelle de retour de chacun (semaine / week-end) pour l'attendre a la porte ;
  - age : jours vecus depuis sa premiere mise en route. Jeune, il est timide (visiteurs, demandes d'attention) et peu sur
    de ses blagues ; il gagne en assurance avec les semaines. Il reste jeune et maladroit : l'age ne touche ni la
    marche ni ses gestes ;
  - etats : Boude (bouderie, reconcilie par une caresse), AttendPorte, SuisMoi (il suit une jambe au capteur de
    distance), JeTeSuis (il part devant et se retourne pour verifier qu'on le suit).

Toutes les sorties sont des sons de canard et des mouvements ; rien ne quitte le canard.
"""
import math
import statistics
import time

import gestures
from etats_base import TETE_PROMENADE, V_PROMENADE, V_ROTATION, Etat, fatigue

# -- respiration et micro-saccades ---------------------------------------------------------------------------------
RESPIRATION_RAD = 0.015          # amplitude du cou (~0,9 degre) : vu, pas remarque ; sous les seuils des detecteurs
RESPIRATION_S = 4.0              # une respiration (plus lente quand il est fatigue)
SACCADE_RAD = 0.035              # petit deplacement du regard (lacet) ; garde la tete dans 0,05 rad du repos
SACCADE_ATTENTE_S = (1.5, 4.5)
SACCADE_MONTEE_S = 0.25


def vie_au_repos(brain, t, base=(0.0, 0.0, 0.0, 0.0)):
    """Consigne de tete au repos : `base` + respiration + saccades. Lente et petite : les detecteurs de caresse et de
    main tendue la tolerent (ils suivent une consigne qui bouge doucement)."""
    v = brain.__dict__.setdefault("_vie", {"cible": 0.0, "depart": 0.0, "t_saccade": 0.0, "prochaine": 2.0})
    rng = getattr(brain, "_rng_vie", brain.rng)          # (hasard a part : ne change pas les autres tirages)
    f = fatigue(brain)
    periode = RESPIRATION_S * (1.0 + 0.6 * (1.0 - f)) * (1.15 - 0.3 * brain.humeur.eveil)
    souffle = RESPIRATION_RAD * math.sin(2 * math.pi * t / periode)
    if t < v["t_saccade"]:                                # nouvel etat : on repart d'un regard centre
        v.update(cible=0.0, depart=0.0, t_saccade=t, prochaine=t + 1.5)
    if t >= v["prochaine"]:
        regard = v["cible"] if t - v["t_saccade"] >= SACCADE_MONTEE_S else v["depart"]
        v["depart"], v["t_saccade"] = regard, t
        v["cible"] = 0.0 if abs(regard) > 0.0 and rng.random() < 0.5 else rng.uniform(-SACCADE_RAD, SACCADE_RAD)
        attente = rng.uniform(*SACCADE_ATTENTE_S) * (1.4 - 0.6 * brain.humeur.eveil)
        v["prochaine"] = t + attente
    k = min(1.0, (t - v["t_saccade"]) / SACCADE_MONTEE_S)
    k = k * k * (3 - 2 * k)                               # depart et arrivee doux
    lacet = v["depart"] + (v["cible"] - v["depart"]) * k
    return (base[0] + souffle, base[1] + 0.4 * souffle, base[2] + lacet, base[3])


# -- habituation -------------------------------------------------------------------------------------------------------
class Habituation:
    """Par stimulus : un compteur qui decroit (demi-vie DEMI_VIE_S). Intensite de la reaction = 1 / (1 + 0,8 n) :
    1 la premiere fois, ~0,55 la deuxieme, ~0,3 a la quatrieme... ; apres quelques heures sans lui, il redevient neuf."""
    DEMI_VIE_S = 30 * 60

    def __init__(self):
        self.n = {}                                       # cle -> (compte, instant)

    def _compte(self, cle, t):
        c, t0 = self.n.get(cle, (0.0, t))
        return c * math.pow(0.5, (t - t0) / self.DEMI_VIE_S)

    def intensite(self, cle, t):
        return 1.0 / (1.0 + 0.8 * self._compte(cle, t))

    def noter(self, cle, t):
        """Note le stimulus et renvoie l'intensite de la reaction (avant ce stimulus)."""
        i = self.intensite(cle, t)
        self.n[cle] = (self._compte(cle, t) + 1.0, t)
        return i


# -- age : timidite de jeunesse, assurance des blagues ----------------------------------------------------------------
JEUNESSE_JOURS = 21              # timide les trois premieres semaines (de moins en moins)
ASSURANCE_JOURS = 60             # ses blagues gagnent en assurance pendant deux mois


def age_jours(perso, mur):
    """Jours depuis sa premiere mise en route (garde dans la personnalite, donc dans la memoire et la sauvegarde)."""
    if perso is None or getattr(perso, "sauver", None) is None:
        return math.inf                                   # sans memoire (essais) : adulte, aucun effet
    naissance = perso.d.setdefault("naissance", round(mur))
    return max(0.0, (mur - naissance) / 86400.0)


def timidite_jeunesse(age):
    """1 a la naissance, 0 apres JEUNESSE_JOURS."""
    return max(0.0, 1.0 - age / JEUNESSE_JOURS)


def assurance_blagues(age):
    """0,5 au debut (blagues rares et prudentes) -> 1,0 apres ASSURANCE_JOURS (tel que reglé)."""
    return 0.5 + 0.5 * min(1.0, age / ASSURANCE_JOURS)


# -- heures de retour apprises -----------------------------------------------------------------------------------------
RETOURS_GARDES = 40
RETOURS_MIN = 4                  # au moins 4 retours du meme genre de jour pour oser une prediction
DISPERSION_MAX_MIN = 45          # des retours trop eparpilles : pas d'habitude, pas d'attente


def noter_retour(donnees, qui, h):
    """`h` : time.struct_time du retour. Garde [semaine_ou_weekend, minute du jour]."""
    if not qui or not hasattr(h, "tm_hour"):
        return
    l = donnees.setdefault("retours", {}).setdefault(qui, [])
    l.append([1 if getattr(h, "tm_wday", 0) >= 5 else 0, h.tm_hour * 60 + h.tm_min])
    del l[:-RETOURS_GARDES]


def retour_prevu(donnees, qui, weekend):
    """Minute du jour habituelle de retour (mediane) pour ce genre de jour, ou None si pas d'habitude nette."""
    l = [m for w, m in (donnees.get("retours") or {}).get(qui, []) if w == (1 if weekend else 0)]
    if len(l) < RETOURS_MIN:
        return None
    med = statistics.median(l)
    if statistics.median(abs(m - med) for m in l) > DISPERSION_MAX_MIN:
        return None
    return int(med)


# -- etats --------------------------------------------------------------------------------------------------------------
class Boude(Etat):
    """Il boude : tete tournee de cote et un peu basse, il ne repond plus aux appels (un coup d'oeil, puis il se
    detourne). Une caresse (ou une main) le reconcilie. Jamais longtemps : DUREE_S au plus."""
    nom = "boude"
    DUREE_S = (60.0, 150.0)

    def entre(self, brain):
        self.cote = brain.rng.choice((-1.0, 1.0))
        self.duree_s = brain.rng.uniform(*self.DUREE_S)
        self.coup_oeil = None                             # instant d'un coup d'oeil (on l'a appele)
        brain.ctx.sound("peck")                           # « hmpf »

    def duree(self, brain):
        return self.duree_s

    def regarde(self, brain):
        self.coup_oeil = brain.t_etat

    def pas(self, brain, t):
        brain.ctx.move()
        detourne = (0.0, 0.15, 0.55 * self.cote, -0.1 * self.cote)
        if self.coup_oeil is not None and t - self.coup_oeil < 1.6:
            k = math.sin(math.pi * (t - self.coup_oeil) / 1.6)       # un regard en coin, puis il se detourne
            brain.ctx.head((0.0, 0.15, 0.55 * self.cote * (1.0 - 0.7 * k), -0.1 * self.cote))
            return
        brain.ctx.head(vie_au_repos(brain, t, detourne))


class AttendPorte(Etat):
    """Il attend quelqu'un a l'heure habituelle de son retour : tete un peu haute vers l'avant, immobile, un petit
    « inquire » de temps en temps. Fini au retour (l'accueil prend la main) ou au bout de DUREE_S."""
    nom = "attend_porte"
    DUREE_S = 15 * 60.0
    APPEL_S = 90.0

    def entre(self, brain):
        self.qui = getattr(self, "qui", None)
        self.t_appel = 20.0

    def duree(self, brain):
        return self.DUREE_S

    def pas(self, brain, t):
        brain.ctx.move()
        brain.ctx.head(vie_au_repos(brain, t, (0.0, -0.12, 0.0, 0.0)))
        if t >= self.t_appel:
            self.t_appel = t + self.APPEL_S * brain.rng.uniform(0.8, 1.4)
            if brain.rng.random() < 0.6 * brain.perso.bavardage():
                brain.ctx.sound("inquire")


class SuisMoi(Etat):
    """« Suis-moi » : il suit la jambe (ou l'objet) la plus proche devant lui au capteur de distance, a ~50 cm. Il
    pivote vers elle, avance si elle s'eloigne, s'arrete si elle s'arrete. Perdue plus de PERDU_S : un « inquire », fin.
    Securite : jamais sans capteur, jamais vers un vide ; vitesses au-dessus de la zone morte (marche par rafales)."""
    nom = "suis_moi"
    DUREE_S = 120.0
    CONE_RAD = math.radians(45)
    PORTEE = (0.2, 1.6)
    DISTANCE = 0.5
    PERDU_S = 3.0

    def entre(self, brain):
        self.vu = 0.0
        brain.ctx.sound("chirp")

    def duree(self, brain):
        return self.DUREE_S

    @classmethod
    def cible(cls, points):
        """(distance, angle) du plus proche point devant, dans le cone et la portee, ou None."""
        best = None
        for x, y, *_ in points or []:
            d, a = math.hypot(x, y), math.atan2(y, x)
            if x > 0 and abs(a) <= cls.CONE_RAD and cls.PORTEE[0] <= d <= cls.PORTEE[1] and (best is None or d < best[0]):
                best = (d, a)
        return best

    def pas(self, brain, t):
        s = brain.ctx.state or {}
        tof = brain.ctx.extras.get("tof")
        brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
        pts = tof.points(s) if tof is not None else None
        lib = tof.libre(s) if tof is not None else None
        c = self.cible(pts)
        if c is None or lib is None:
            brain.ctx.move()
            if t - self.vu >= self.PERDU_S:
                brain.ctx.sound("inquire")                # « ou es-tu passe ? »
                brain.fin_etat = t
            return
        self.vu = t
        d, a = c
        if abs(a) > math.radians(20):
            brain.ctx.move(vyaw=math.copysign(V_ROTATION, a))
        elif d > self.DISTANCE + 0.2 and lib["vide"] > 0.6:
            brain.ctx.move(vx=V_PROMENADE)
        else:
            brain.ctx.move()


class JeTeSuis(Etat):
    """« Je te suis » a l'envers : il part devant, s'arrete, se retourne et verifie au capteur de distance qu'on le
    suit (quelqu'un a moins de 1,5 m) : content, il repart ; personne : un « inquire » et il attend un peu. 3 tours."""
    nom = "mene"
    TOURS = 3
    MARCHE_S, DEMI_TOUR_S, REGARDE_S = 2.5, math.pi / V_ROTATION, 2.0

    def entre(self, brain):
        self.tour, self.phase, self.t0, self.suivi = 0, "marche", 0.0, 0
        brain.ctx.sound("chirp")

    def duree(self, brain):
        return self.TOURS * (self.MARCHE_S + 2 * self.DEMI_TOUR_S + self.REGARDE_S) + 6.0

    def pas(self, brain, t):
        s = brain.ctx.state or {}
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(s) if tof is not None else None
        dt = t - self.t0
        if self.phase == "marche":
            brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
            if lib is None or lib["devant"] < 0.45 or dt >= self.MARCHE_S:
                self.phase, self.t0 = "demi_tour", t
                brain.ctx.move()
            else:
                brain.ctx.move(vx=V_PROMENADE)
        elif self.phase == "demi_tour":
            brain.ctx.move(vyaw=V_ROTATION)
            if dt >= self.DEMI_TOUR_S:
                self.phase, self.t0 = "regarde", t
                brain.ctx.move()
        elif self.phase == "regarde":
            brain.ctx.move()
            brain.ctx.head((0.0, -0.05, 0.0, 0.0))
            if dt >= self.REGARDE_S:
                pts = tof.points(s) if tof is not None else None
                quelqu_un = SuisMoi.cible(pts) is not None and SuisMoi.cible(pts)[0] <= 1.5
                self.suivi += 1 if quelqu_un else 0
                brain.ctx.sound("wheee" if quelqu_un else "inquire")
                self.tour += 1
                self.phase, self.t0 = ("retour", t) if self.tour < self.TOURS else ("fin", t)
        elif self.phase == "retour":
            brain.ctx.move(vyaw=V_ROTATION)               # il se remet dans le sens de la marche
            if dt >= self.DEMI_TOUR_S:
                self.phase, self.t0 = "marche", t
        else:
            brain.ctx.move()
            brain.fin_etat = t


class Reponse(Etat):
    """Tour de parole : il « repond » a ce qu'on vient de lui dire, en un son et un geste choisis d'apres l'enonce."""
    nom = "repond"

    def __init__(self):
        self.son, self.geste = "chirp", "oui"

    @staticmethod
    def choisir(duree, sens):
        if sens == "monte":
            return "inquire", "curieux"                   # une question : « hein ? »
        if sens == "descend":
            return "coo", "oui"                           # une phrase posee : un roucoulement d'accord
        if duree < 0.8:
            return "chirp", "oui"                         # un mot : un petit « oui »
        return ("greet" if duree > 2.0 else "chirp"), "curieux"

    def entre(self, brain):
        self.d, self.fn = gestures.GESTES[self.geste]
        self.joue = False

    def duree(self, brain):
        return self.d + 0.3

    def pas(self, brain, t):
        brain.ctx.move()
        if not self.joue and t >= 0.15:
            self.joue = True
            brain.ctx.sound(self.son)
        brain.ctx.head(self.fn(min(t, self.d)))
