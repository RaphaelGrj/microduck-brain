#!/usr/bin/env python3
"""Squelette du cerveau comportemental (Phase 3) : etats + modele energie/eveil.

Inspire des etats M9 de Pollen (Chill, LookAround, Wander, TurnInPlace, Startle, Nap...),
sans RL : chaque etat ne fait qu'envoyer des intents a robotd (robot.head, robot.move,
robot.do) et le vocabulaire de gestes vient de gestures.py.

Principes (ROADMAP "regles de vie") :
  - initiative rare : longs temps de repos (Chill) entre deux actions ;
  - ne jamais insister : un evenement ignore (Nap, chute) n'est pas rejoue ;
  - securite : si le canard est tombe, le cerveau s'arrete et ne commande plus rien ;
  - a la sortie, tete neutre, arret du mouvement, et on se releve si on dormait.

Usage : python3 brain.py [duree_s] [--energy 0.2] [--events bruit@20,chat@40]
"""
import math
import random
import sys
import time

import gestures
from exploration import Exploration
from caresse import DetecteurCaresse
from main_tendue import DetecteurMain
from navigation import AllerVers

DT_DEFAUT = 0.02  # une trame robot.state = 20 ms


class Humeur:
    """Energie 0..1 (baisse en activite, remonte au repos/sieste) et eveil 0..1
    (monte sur evenement, retombe seul)."""

    def __init__(self, energie=0.8, eveil=0.2):
        self.energie = energie
        self.eveil = eveil

    def avance(self, dt, etat):
        taux = {"chill": +0.004, "nap": +0.03, "wander": -0.02,
                "turn": -0.01, "look": -0.004, "startle": -0.01, "curious": -0.003}
        self.energie += taux.get(etat, 0.0) * dt
        self.eveil -= 0.05 * dt
        self.energie = min(1.0, max(0.0, self.energie))
        self.eveil = min(1.0, max(0.0, self.eveil))


# Fatigue progressive VISIBLE a basse energie (ROADMAP "chantier actif", 2026-10-05) : amplitude et cadence des
# mouvements de tete seulement. Jamais vx/vyaw - ils doivent rester au-dessus de la zone morte de la politique de
# marche (ZONE_MORTE.md : vx >= 0.3, |vyaw| >= 1.2), sous peine de jambes figees malgre la commande envoyee.
FATIGUE_PLEIN = 0.6   # energie au-dessus de laquelle : aucun ralentissement visible
FATIGUE_BAS = 0.25    # = Brain.SEUIL_SIESTE (juste avant la sieste) : lenteur la plus marquee prevue ici
FATIGUE_MIN = 0.6     # jamais moins de 60% : il continue de bouger, pas un arret visuel


def fatigue(brain):
    """Multiplicateur (FATIGUE_MIN..1.0) applique a l'amplitude ET a la frequence d'un mouvement de tete : plus
    l'energie est basse, plus les gestes sont lents et discrets, sans jamais s'arreter net."""
    e = brain.humeur.energie
    if e >= FATIGUE_PLEIN:
        return 1.0
    k = max(0.0, (e - FATIGUE_BAS) / (FATIGUE_PLEIN - FATIGUE_BAS))
    return FATIGUE_MIN + (1.0 - FATIGUE_MIN) * k


class Ctx:
    """Ce que voit un etat : client robotd, derniere trame, aide pour commander."""

    def __init__(self, client):
        self.client = client
        self.state = None
        self.sitting = False

    def head(self, vals):
        self.tete_cmd = tuple(vals)             # derniere consigne de tete (detecteurs : main tendue, caresse)
        self.client.notify("robot.head", {"neck_pitch": vals[0], "head_pitch": vals[1],
                                          "head_yaw": vals[2], "head_roll": vals[3]})

    def move(self, vx=0.0, vy=0.0, vyaw=0.0):
        self.client.notify("robot.move", {"vx": vx, "vy": vy, "vyaw": vyaw})

    def pose(self, p=None):
        """Pose du corps debout (robot.pose : z m, roulis rad, tangage rad), lissee par robotd. None = retour au neutre
        (active=false, une seule fois) : un client qui laisse une pose active la laisse au robot."""
        if p is None:
            if getattr(self, "pose_active", False):
                self.client.notify("robot.pose", {"z": 0.0, "roll": 0.0, "pitch": 0.0, "active": False})
                self.pose_active = False
            return
        self.client.notify("robot.pose", {"z": p[0], "roll": p[1], "pitch": p[2], "active": True})
        self.pose_active = True

    def toggle_sit(self):
        self.client.request("robot.do", {"skill": "sit_toggle"})
        self.sitting = not self.sitting

    # duree d'ouverture du bec par son (s) : le bec bouge avec la voix (robot.mouth, que seul le cerveau pilote)
    BEC_S = {"chirp": 0.25, "peck": 0.15, "greet": 0.5, "coo": 0.6, "inquire": 0.45, "alarm": 0.8, "wheee": 1.2}

    def sound(self, tag):
        """La voix du canard (robot.sound) : alarm, greet, inquire, peck, chirp, coo, wheee. Muette en mode calme."""
        if getattr(self, "silence", False):
            return
        try:
            r = self.client.request("robot.sound", {"tag": tag})
            if isinstance(r, dict) and "error" in r:     # un robot sans voix refuse (JSON-RPC error, pas d'exception)
                print(f"  (son {tag} refuse : {r['error']})", flush=True)
                return
        except Exception as e:      # on ne bloque jamais un geste pour un son
            print(f"  (son {tag} impossible : {e})", flush=True)
            return
        self.bec_t0, self.bec_fin = time.monotonic(), time.monotonic() + self.BEC_S.get(tag, 0.4)

    def bec(self):
        """A chaque trame : bec qui bat pendant le son (~8 Hz), puis refermé une fois. robot.mouth est une consigne
        continue (la derniere valeur reste) : on ne l'envoie que pendant le son et a la fermeture."""
        fin = getattr(self, "bec_fin", None)
        if fin is None:
            return
        now = time.monotonic()
        if now >= fin:
            self.client.notify("robot.mouth", {"open": 0.0})
            self.bec_fin = None
            return
        self.client.notify("robot.mouth", {"open": 0.45 + 0.35 * math.cos(2 * math.pi * 8.0 * (now - self.bec_t0))})

    def calme(self):
        self.head((0.0, 0.0, 0.0, 0.0))
        self.move()
        self.pose(None)


class Etat:
    nom = "?"

    def duree(self, brain):
        return 4.0

    def entre(self, brain):
        pass

    def pas(self, brain, t):
        """Appele a chaque trame avec t = secondes depuis l'entree dans l'etat."""
        brain.ctx.calme()

    def sort(self, brain):
        brain.ctx.calme()


class Chill(Etat):
    nom = "chill"

    def duree(self, brain):
        # initiative rare : plus l'eveil est haut, moins on reste longtemps au calme
        base = brain.rng.uniform(6.0, 12.0)
        return base * (1.0 - 0.5 * brain.humeur.eveil)


class LookAround(Etat):
    nom = "look"

    def duree(self, brain):
        return 6.0

    def pas(self, brain, t):
        f = fatigue(brain)                                        # fatigue progressive : plus lent, plus discret
        yaw = 0.6 * f * math.sin(2 * math.pi * t / (6.0 / f))
        brain.ctx.head((0.0, 0.1 * f * math.sin(2 * math.pi * t / (3.0 / f)), yaw, 0.0))


# Vitesses AU-DESSUS de la zone morte de la politique de marche (ZONE_MORTE.md) : en dessous, les jambes restent figees.
V_PROMENADE, V_ROTATION = 0.4, 1.5
LIBRE_MIN = 0.45                 # on n'avance pas si le ToF voit un obstacle (ou un vide) a moins de 45 cm devant
TETE_PROMENADE = 0.3             # inclinaison de tete en marchant (rad) : voir le sol, donc les marches, assez tot


class TurnInPlace(Etat):
    """Tourne sur place ; du cote le plus degage si le ToF le dit (ou si Wander vient de buter), sinon au hasard."""
    nom = "turn"

    def entre(self, brain):
        virage = getattr(brain, "virage_cible", None)        # demande par l'exploration : un angle precis
        prefere = getattr(brain, "cote_degage", None)
        if virage:
            self.signe = math.copysign(1.0, virage)
            self.duree_s = min(2.0, max(0.6, abs(math.degrees(virage)) / 50.0))   # ~50 deg/s a vyaw = 1,5
            brain.virage_cible = None
            brain.suivant_force = "wander"                   # puis on part dans la direction choisie
            brain.cap_choisi = True
        else:
            self.signe = prefere if prefere else brain.rng.choice((-1.0, 1.0))
            self.duree_s = brain.rng.uniform(1.0, 1.8)      # ~50 a 90 deg
        brain.cote_degage = None

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))                 # tete neutre : tete baissee, la rotation est morte
        brain.ctx.move(vyaw=V_ROTATION * self.signe)


class Wander(Etat):
    """Promenade en ligne droite, SEULEMENT si le capteur de distance voit de la place devant. Sans ToF frais : on ne
    bouge pas (prudence). Obstacle a moins de LIBRE_MIN : on s'arrete, on note le cote le plus degage, et on passe a
    `turn`."""
    nom = "wander"

    SEUIL_PASSAGE_ETROIT = 0.5   # m, de chaque cote : en dessous des deux, pause avant de s'y engager

    def entre(self, brain):
        self.duree_s = brain.rng.uniform(2.5, 6.0)
        self.arrets = 0
        self.virage = None
        self.pause_faite = False     # une seule pause par traversee, pas a chaque trame dans le passage
        self.pause_jusqua = None
        # Exploration : avant de partir, regarder si une direction mene vers des zones moins visitees (sauf si on vient
        # justement de tourner pour ca).
        o = brain.ctx.state.get("odom") if brain.ctx.state is not None else None
        if brain.explo_actif and o is not None and not getattr(brain, "cap_choisi", False):
            ecart = brain.exploration.meilleur_ecart(o["position"][0], o["position"][1], o["yaw"], brain.t_global)
            if abs(ecart) >= math.radians(30):
                self.virage = ecart
        brain.cap_choisi = False

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
        # Tete un peu baissee : le canard regarde ou il met les pattes. Tete au neutre, les rayons du ToF touchent le sol
        # trop loin et le bord d'une estrade n'est vu qu'une fois passe (essai_vide.py : 0/3 au neutre, 3/3 a 0,3 rad).
        brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
        if t < 0.4:
            brain.ctx.move()                                 # on laisse la tete se placer avant de juger le sol
            return
        if self.virage is not None:                          # d'abord tourner vers la zone la plus nouvelle
            brain.virage_cible, self.virage = self.virage, None
            brain.fin_etat = brain.t_etat
            brain.suivant_force = "turn"
            brain.ctx.move()
            return
        if self.pause_jusqua is not None:
            brain.ctx.move()                                 # immobile : on "jauge" le passage avant de s'y engager
            if t >= self.pause_jusqua:
                self.pause_jusqua = None
            return
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(brain.ctx.state) if tof is not None and brain.ctx.state is not None else None
        if lib is None:
            brain.ctx.move()                                 # aveugle : on reste sur place
            return
        if lib["devant"] < 9.0 and brain.ctx.state.get("odom"):    # obstacle vu devant : on le note dans la grille
            o = brain.ctx.state["odom"]
            brain.exploration.obstacle(o["position"][0] + lib["devant"] * math.cos(o["yaw"]),
                                       o["position"][1] + lib["devant"] * math.sin(o["yaw"]), brain.t_global)
        # Passage etroit (ROADMAP "chantier actif") : une pause VISIBLE avant de s'y engager, comme un animal qui
        # jauge un couloir serre - pas un evitement (on continue ensuite), distinct de l'arret sur obstacle ci-dessous.
        if (not self.pause_faite and lib["devant"] >= LIBRE_MIN
                and lib["gauche"] < self.SEUIL_PASSAGE_ETROIT and lib["droite"] < self.SEUIL_PASSAGE_ETROIT):
            self.pause_faite = True
            self.pause_jusqua = t + 0.6
            brain.ctx.move()
            return
        if lib["devant"] < LIBRE_MIN:
            brain.ctx.move()
            brain.cote_degage = 1.0 if lib["gauche"] >= lib["droite"] else -1.0
            brain.obstacle_vu = brain.obstacle_vu + 1 if hasattr(brain, "obstacle_vu") else 1
            brain.fin_etat = brain.t_etat                    # fin de la promenade : on va tourner
            brain.suivant_force = "turn"
            return
        brain.ctx.move(vx=V_PROMENADE)


class Geste(Etat):
    """Etat qui joue un geste de gestures.py (tete) avec recul optionnel."""

    def __init__(self, nom_etat, geste, recul=False, son=None):
        self.nom = nom_etat
        self.geste = geste
        self.recul = recul
        self.son = son              # etiquette de robot.sound jouee a l'entree (la voix du canard)
        self._duree, self._fn = gestures.GESTES[geste]

    def entre(self, brain):
        if self.son:
            brain.ctx.sound(self.son)

    def duree(self, brain):
        return self._duree + 0.5

    def pas(self, brain, t):
        brain.ctx.head(self._fn(min(t, self._duree)) if t < self._duree else (0, 0, 0, 0))
        corps = gestures.GESTES_CORPS.get(self.geste)
        if corps is not None:
            brain.ctx.pose(corps(t) if t < self._duree else None)
        if self.recul and t <= 0.5:
            brain.ctx.move(vx=-0.1)


class Nap(Etat):
    """Affaissement de tete, assis, repos qui recharge l'energie, puis on se leve."""
    nom = "nap"

    def entre(self, brain):
        self.assis = brain.ctx.sitting           # deja assis (sieste prolongee en mode calme) : on ne se rassoit pas
        self.leve = False
        self.total = 2.0 + 4.0 + brain.rng.uniform(8.0, 14.0) + 4.0
        # "Reves" pendant le sommeil profond (ROADMAP "chantier actif", 2026-10-05) : 0 a 2 petits tressaillements
        # de tete, jamais pendant l'endormissement (< 2s) ni le reveil (derniers 4s) - juste de quoi distinguer une
        # sieste "vivante" d'une simple pause, sans RL ni capteur supplementaire.
        profond = self.total - 2.0 - 4.0
        self.reves = []
        if profond >= 3.0:
            for _ in range(brain.rng.randint(0, 2)):
                t0 = 2.0 + brain.rng.uniform(0.5, profond - 1.5)
                self.reves.append([t0, brain.rng.uniform(0.6, 1.2), brain.rng.choice((-1, 1)), False])

    def duree(self, brain):
        return self.total

    def pas(self, brain, t):
        ctx = brain.ctx
        if t < 2.0 and not self.assis:
            ctx.head(gestures.fatigue(t))
        elif not self.assis:
            ctx.toggle_sit()
            self.assis = True
        elif t >= self.total - 4.0 and not self.leve and not brain.reste_assis():
            ctx.toggle_sit()
            self.leve = True
            ctx.head((0, 0, 0, 0))
        elif self.assis and not self.leve:
            for reve in self.reves:
                t0, duree, signe, joue = reve
                if t0 <= t < t0 + duree:
                    if not joue:
                        ctx.sound("chirp")        # murmure sonore occasionnel (ROADMAP) ; silencieux en mode calme
                        reve[3] = True
                    k = math.sin(math.pi * (t - t0) / duree)      # monte puis redescend a 0 : jamais de saut brusque
                    ctx.head((0.0, 0.7 + 0.05 * signe * k, 0.08 * signe * k, 0.0))
                    break

    def sort(self, brain):
        if brain.ctx.sitting and not brain.reste_assis():
            brain.ctx.toggle_sit()
        brain.ctx.calme()


class RegardeChat(Etat):
    """Le chat vient d'apparaitre : petit son interrogatif, puis on le suit des yeux quelques secondes. La position du
    chat vient de la veille (chat.py) ; c'est robotd qui calcule l'orientation de la tete (`robot.look`), on renvoie
    ensuite ces angles a chaque trame pour tenir le regard.

    Garde-fou "reculer s'il approche vite" (ROADMAP, table chat) : si le chat se rapproche tres vite en dessous d'un
    seuil de proximite, petit pas en arriere (vx negatif) le temps qu'il passe le seuil - jamais une poursuite dans
    l'autre sens, jamais si le chat est deja loin ou s'approche lentement (une visite normale ne doit pas le faire
    fuir). vx reste dans la plage marche arriere documentee pour le chat (ZONE_MORTE.md : |vx| >= 0.3)."""
    nom = "regarde_chat"

    # familiarite (memoire.py) -> (son, duree du regard) : mefiant au debut, chaleureux avec le temps
    ACCUEIL = ((0.3, "inquire", 8.0), (0.6, "greet", 7.0), (1.01, "coo", 6.0))

    SEUIL_PROXIMITE_M = 0.35       # distance chat-robot en dessous de laquelle une approche rapide inquiete
    SEUIL_VITESSE_APPROCHE = 0.3   # m/s de fermeture pour declencher le recul (bruit normal du suivi sinon)
    VX_RECUL = -0.35               # au-dessus de la zone morte en valeur absolue (vx >= 0.3)
    DUREE_RECUL_S = 1.0            # un seul petit pas, pas une fuite continue

    def entre(self, brain):
        mem = brain.ctx.extras.get("memoire")
        self.familiarite = mem.familiarite("chat") if mem is not None else 0.0
        _, son, self.duree_s = next(a for a in self.ACCUEIL if self.familiarite < a[0])
        brain.ctx.sound(son)
        self.son = son
        self.tete = (0.0, 0.0, 0.0, 0.0)
        self.t_vise = None
        self.n_look = 0
        self._dist_prec = None
        self._t_dist_prec = None
        self._recule_jusqua = -1.0

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
        veille, s = brain.ctx.extras.get("chat"), brain.ctx.state
        recul = t < self._recule_jusqua
        if veille is not None and s is not None:
            e = veille.estimation
            if e is not None and e[0] != self.t_vise:
                self.t_vise = e[0]
                cible = veille.cible_regard(s["odom"]["position"][2])
                if cible:
                    r = brain.ctx.client.request("robot.look", {"x": float(cible[0]), "y": float(cible[1]), "z": float(cible[2])})
                    h = (r.get("result") or {}).get("head") if isinstance(r, dict) else None
                    if h:
                        self.tete = (h["neck_pitch"], h["head_pitch"], h["head_yaw"], h["head_roll"])
                        self.n_look += 1
                distance = math.hypot(e[1], e[2])
                if self._dist_prec is not None and e[0] > self._t_dist_prec:
                    vitesse_approche = (self._dist_prec - distance) / (e[0] - self._t_dist_prec)
                    if distance < self.SEUIL_PROXIMITE_M and vitesse_approche > self.SEUIL_VITESSE_APPROCHE:
                        self._recule_jusqua = t + self.DUREE_RECUL_S
                        recul = True
                self._dist_prec, self._t_dist_prec = distance, e[0]
        brain.ctx.head(self.tete)
        brain.ctx.move(vx=self.VX_RECUL if recul else 0.0)


class Ecoute(Etat):
    """Une conversation vocale est en cours (quacksat, satellite Assist de HA) : le cerveau se tait et ne commande PLUS
    RIEN (robotd : le dernier ecrit gagne ; quacksat balance la tete en reflechissant et peut faire marcher le canard a la
    demande). Une seule consigne a l'entree : arreter la promenade en cours. Sortie sur ecoute_off, ou au bout de
    DUREE_MAX si le signal de fin se perd (satellite devenu indisponible)."""
    nom = "ecoute"
    DUREE_MAX = 90.0

    def entre(self, brain):
        brain.ctx.move()
        brain.ctx.pose(None)

    def duree(self, brain):
        return self.DUREE_MAX

    def pas(self, brain, t):
        pass

    def sort(self, brain):
        pass                                    # pas de consigne de tete au milieu d'une reponse de quacksat


class MainTendue(Etat):
    """Une main vient d'etre tendue devant le canard (main_tendue.py, ToF) : petit son interrogatif, il la regarde
    (`robot.look`, comme le chat), puis la "picore" doucement - de petits coups de tete vers elle. Le corps ne bouge
    pas : approcher de quelques centimetres est impossible a la marche (ZONE_MORTE.md : pas de pas plus fin que
    ~2-3 cm, et le pied pourrait cogner la main). La main retiree, un petit chirp et c'est fini."""
    nom = "main_tendue"
    DUREE_MAX = 10.0
    PERIODE_PICORE = 1.2         # s entre deux coups de bec
    COUP = 0.3                   # s, duree d'un coup de bec
    AMPLITUDE = 0.25             # rad de head_pitch en plus du regard

    def entre(self, brain):
        brain.ctx.sound("inquire")
        self.tete = (0.0, 0.25, 0.0, 0.0)       # en attendant robot.look : la tete se baisse un peu vers l'avant
        self.t_vise = None
        self.n_coups = 0
        self.parti = False

    def duree(self, brain):
        return self.DUREE_MAX

    def pas(self, brain, t):
        det, s = brain.detecteur_main, brain.ctx.state
        if not det.presente(brain.t_global):
            if t > 0.5 and not self.parti:
                self.parti = True
                brain.ctx.sound("chirp")
                brain.fin_etat = min(brain.fin_etat, t + 0.6)     # on laisse le chirp sonner, puis on se remet
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            brain.ctx.move()
            return
        m = det.main
        if m[0] != self.t_vise and s is not None and s.get("odom"):
            self.t_vise = m[0]
            r = brain.ctx.client.request("robot.look", {"x": float(m[1]), "y": float(m[2]),
                                                        "z": float(m[3] - s["odom"]["position"][2])})
            h = (r.get("result") or {}).get("head") if isinstance(r, dict) else None
            if h:
                self.tete = (h["neck_pitch"], h["head_pitch"], h["head_yaw"], h["head_roll"])
        tete = list(self.tete)
        if t >= 1.0:                             # une seconde a la regarder, puis les coups de bec
            phase = (t - 1.0) % self.PERIODE_PICORE
            if phase < self.COUP:
                if phase < 0.03 and int((t - 1.0) / self.PERIODE_PICORE) >= self.n_coups:
                    self.n_coups += 1
                    if self.n_coups <= 3:
                        brain.ctx.sound("peck")
                tete[1] += self.AMPLITUDE * math.sin(math.pi * phase / self.COUP)
        brain.ctx.head(tuple(tete))
        brain.ctx.move()


class Caresse(Etat):
    """On le caresse (caresse.py, ou `pet-detect` officiel plus tard) - etat "Petted" du M9 : roucoulement, la tete
    s'appuie doucement contre la main et frotte un peu, puis un petit tremoussement de contentement. Calme l'eveil."""
    nom = "caresse"
    APPUI_S = 3.0

    def entre(self, brain):
        brain.ctx.sound("coo")
        brain.humeur.eveil = max(0.0, brain.humeur.eveil - 0.15)
        self.d_content, self.f_content = gestures.GESTES["content"]

    def duree(self, brain):
        return self.APPUI_S + self.d_content + 0.3

    def pas(self, brain, t):
        if t < self.APPUI_S:
            k = gestures._smooth(t, 0.0, 0.6) * (1.0 - gestures._smooth(t, self.APPUI_S - 0.5, self.APPUI_S))
            brain.ctx.head((0.0, 0.1 * k, 0.08 * k * math.sin(2 * math.pi * 0.7 * t), 0.15 * k))
            brain.ctx.pose(None)
        elif t < self.APPUI_S + self.d_content:
            u = t - self.APPUI_S
            brain.ctx.head(self.f_content(u))
            brain.ctx.pose(gestures.content_corps(u))
        else:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            brain.ctx.pose(None)
        brain.ctx.move()


class Soleil(Etat):
    """Jeu "1-2-3 soleil" (ROADMAP, table Humains "Jeux" et prochaine etape n°4) : le canard se retourne, compte en
    chirps (rythme variable : c'est tout le jeu), se retourne d'un coup et regarde ; s'il voit quelque chose bouger
    (mouvement.py, difference d'images, camera immobile), "vu !" (alarme + non de la tete). Le joueur gagne s'il
    arrive tout pres (ToF devant < 30 cm au moment ou le canard regarde) ou s'il le caresse : tremoussement + wheee.
    Fin apres MANCHES_MAX manches, sur "fin_jeu", ou si le joueur ne se fait jamais voir ni n'arrive (parti ?).

    Les demi-tours se font a l'odometrie, vers des caps absolus (le joueur, puis le dos au joueur) (vyaw 1,5 au-dessus de la zone morte, ~50 deg/s : ~3,5 s par demi-tour) ; la
    detection de mouvement n'est armee qu'une fois le canard stabilise (STABILISATION_S apres l'arret)."""
    nom = "soleil"
    MANCHES_MAX = 10
    REGARD_S = 3.5
    STABILISATION_S = 0.8
    DEMI_TOUR_MAX_S = 5.0
    ARRIVEE_M = 0.30
    ABANDON_MANCHES = 6          # manches d'affilee sans mouvement vu ni arrivee : le joueur est sans doute parti

    def entre(self, brain):
        self.veille = brain.ctx.extras.get("mouvement")
        self.manche, self.vus, self.calmes = 0, 0, 0
        self.resultat = None
        o = (brain.ctx.state or {}).get("odom")
        self.cap_joueur = o["yaw"] if o else None          # le joueur est en face au moment ou il lance le jeu
        brain.ctx.sound("greet")
        self._phase(brain, "annonce", 0.0)

    def duree(self, brain):
        return 600.0                             # le jeu decide lui-meme de sa fin (brain.fin_etat)

    def _phase(self, brain, nom, t):
        self.phase, self.t_phase = nom, t
        if self.veille is not None:
            self.veille.desarmer()
        if nom == "compte":
            self.duree_compte = brain.rng.uniform(1.5, 4.0)
            self.bips = sorted(brain.rng.uniform(0.2, self.duree_compte - 0.3) for _ in range(2)) + [self.duree_compte - 0.2]
            self.n_bips = 0
        elif nom == "regarde":
            self.arme = False

    def _tourne(self, brain, t, cap):
        """Rotation sur place vers le cap ABSOLU `cap` (odometrie), par le plus court : le cap du joueur est memorise
        au debut du jeu, sinon les petites erreurs de chaque demi-tour s'additionnent et le canard finit par ne plus
        lui faire face. True quand c'est fait (a ~20 deg pres, l'inertie finit le virage), ou au bout de
        DEMI_TOUR_MAX_S."""
        o = (brain.ctx.state or {}).get("odom")
        fait, signe = t - self.t_phase >= self.DEMI_TOUR_MAX_S, 1.0
        if o and cap is not None:
            ecart = math.remainder(cap - o["yaw"], 2 * math.pi)
            fait = fait or abs(ecart) <= 0.35
            signe = 1.0 if ecart > 0 else -1.0
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))
        brain.ctx.move(vyaw=0.0 if fait else V_ROTATION * signe)
        return fait

    def _fin(self, brain, t, resultat):
        self.resultat = resultat
        print(f"[{brain.t_global:6.1f}s] 1-2-3 soleil : {resultat} (manche {self.manche}, vu {self.vus} fois)", flush=True)
        if self.veille is not None:
            self.veille.desarmer()
        if resultat == "gagne":
            brain.ctx.sound("wheee")
            self._phase(brain, "fete", t)
        else:
            brain.ctx.sound("coo")
            self._phase(brain, "salut", t)

    def sur_evenement(self, brain, base):
        """Evenements pendant le jeu : une caresse = le joueur l'a touche, il a gagne ; fin_jeu = on arrete."""
        if self.resultat is not None:
            return base in ("caresse", "fin_jeu")
        if base == "caresse":
            self._fin(brain, brain.t_etat, "gagne")
            return True
        if base == "fin_jeu":
            self._fin(brain, brain.t_etat, "arrete")
            return True
        return False

    def pas(self, brain, t):
        ctx, dt = brain.ctx, t - self.t_phase
        if self.phase == "annonce":
            ctx.head(gestures.oui(min(dt, 1.2)) if dt < 1.2 else (0, 0, 0, 0))
            ctx.move()
            if dt >= 1.5:
                self.manche += 1
                self._phase(brain, "demi_tour", t)
        elif self.phase == "demi_tour":
            dos = None if self.cap_joueur is None else self.cap_joueur + math.pi
            if self._tourne(brain, t, dos):
                self._phase(brain, "compte", t)
        elif self.phase == "compte":
            ctx.head((0.0, 0.3, 0.0, 0.0))       # tete baissee : "les yeux fermes"
            ctx.move()
            if self.n_bips < len(self.bips) and dt >= self.bips[self.n_bips]:
                ctx.sound("chirp" if self.n_bips < 2 else "inquire")
                self.n_bips += 1
            if dt >= self.duree_compte:
                self._phase(brain, "retour", t)
        elif self.phase == "retour":
            if self._tourne(brain, t, self.cap_joueur):
                self._phase(brain, "regarde", t)
        elif self.phase == "regarde":
            ctx.head((0.0, -0.15, 0.0, 0.0))     # le regard un peu leve, vers le joueur debout
            ctx.move()
            if not self.arme and dt >= self.STABILISATION_S and self.veille is not None:
                self.veille.armer()
                self.arme = True
            tof = ctx.extras.get("tof")
            lib = tof.libre(ctx.state) if tof is not None and ctx.state is not None and dt >= self.STABILISATION_S else None
            if lib is not None and lib["devant"] < self.ARRIVEE_M:
                self._fin(brain, t, "gagne")
            elif self.arme and self.veille.a_bouge():
                self.vus += 1
                self.calmes = 0
                ctx.sound("alarm")
                self._phase(brain, "vu", t)
            elif dt >= self.REGARD_S:
                self.calmes += 1
                if self.manche >= self.MANCHES_MAX:
                    self._fin(brain, t, "fini")
                elif self.calmes >= self.ABANDON_MANCHES:
                    self._fin(brain, t, "abandon")
                else:
                    self.manche += 1
                    ctx.sound("chirp")
                    self._phase(brain, "demi_tour", t)
        elif self.phase == "vu":
            d, fn = gestures.GESTES["non"]
            ctx.head(fn(dt) if dt < d else (0, 0, 0, 0))
            ctx.move()
            if dt >= d + 0.3:
                if self.manche >= self.MANCHES_MAX:
                    self._fin(brain, t, "fini")
                else:
                    self.manche += 1
                    self._phase(brain, "demi_tour", t)
        elif self.phase == "fete":
            d, fn = gestures.GESTES["content"]
            ctx.head(fn(dt) if dt < d else (0, 0, 0, 0))
            ctx.pose(gestures.content_corps(dt) if dt < d else None)
            ctx.move()
            if dt >= d + 0.3:
                brain.fin_etat = t
        else:                                    # salut : un petit "oui" et on rend la main
            ctx.head(gestures.oui(dt) if dt < 1.2 else (0, 0, 0, 0))
            ctx.move()
            if dt >= 1.5:
                brain.fin_etat = t

    def sort(self, brain):
        if self.veille is not None:
            self.veille.desarmer()
        brain.ctx.calme()


class VaAuCoin(Etat):
    """Fatigue : avant la sieste, il rejoint son coin de sieste prefere (Exploration.coin_favori("nap")) - pivote,
    marche droit, tete un peu baissee comme en promenade. Arrive, bloque (obstacle, capteur muet plus d'1 s) ou trop
    long : il fait la sieste la ou il est. Jamais un detour : c'est une envie, pas une mission."""
    nom = "va_au_coin"
    DUREE_MAX = 25.0
    BLOQUE_MAX_S = 1.0

    def __init__(self):
        self.cible = None

    def entre(self, brain):
        self.nav = AllerVers(self.cible)
        self.bloque_depuis = None
        print(f"[{brain.t_global:6.1f}s] va faire la sieste dans son coin ({self.cible[0]:.2f}, {self.cible[1]:.2f})",
              flush=True)

    def duree(self, brain):
        return self.DUREE_MAX

    def _fin(self, brain, t, pourquoi):
        brain.ctx.move()
        brain.suivant_force = "nap"
        brain.fin_etat = t
        self.issue = pourquoi

    def pas(self, brain, t):
        s = brain.ctx.state or {}
        o = s.get("odom")
        brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
        if t < 0.4 or o is None:
            brain.ctx.move()
            return
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(s) if tof is not None else None
        statut, vx, vyaw = self.nav.commande(o["position"][0], o["position"][1], o["yaw"], lib)
        if statut == "arrive":
            return self._fin(brain, t, "arrive")
        if statut == "bloque":
            self.bloque_depuis = self.bloque_depuis if self.bloque_depuis is not None else t
            if t - self.bloque_depuis >= self.BLOQUE_MAX_S:
                return self._fin(brain, t, "bloque")
        else:
            self.bloque_depuis = None
        if statut == "pivote":
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))     # tete baissee, la rotation est morte (ZONE_MORTE.md)
        brain.ctx.move(vx=vx, vyaw=vyaw)



class Danse(Etat):
    """De la musique (audio.py : battement regulier) : il hoche la tete en rythme et se dandine un peu, s'arrete avec
    la musique (musique_fin) ou au bout de DUREE_MAX - pas un juke-box : DELAI_DANSE_S avant de recommencer."""
    nom = "danse"
    DUREE_MAX = 30.0

    def __init__(self):
        self.bpm = 100

    def entre(self, brain):
        self.periode = 60.0 / (self.bpm / 2 if self.bpm > 130 else self.bpm)    # a 180 BPM, un hochement sur deux
        brain.ctx.sound("chirp")

    def duree(self, brain):
        return self.DUREE_MAX

    def sur_evenement(self, brain, base):
        if base == "musique_fin":
            brain.fin_etat = brain.t_etat + 0.5
            return True
        return base.startswith("musique")

    def pas(self, brain, t):
        k = gestures._smooth(t, 0.0, 1.0) * (1.0 - gestures._smooth(t, brain.fin_etat - 1.0, brain.fin_etat))
        phase = 2 * math.pi * t / self.periode
        brain.ctx.head((0.0, 0.2 * k * max(0.0, math.sin(phase)), 0.0, 0.12 * k * math.sin(phase / 2)))
        brain.ctx.pose((0.0, 0.12 * k * math.sin(phase / 2), 0.0) if k > 0.05 else None)
        brain.ctx.move()


class Accueil(Etat):
    """Un habitant rentre a la maison (presence Home Assistant, voir pont_ha.py). L'accueil depend de la familiarite
    (memoire.py : reservee au debut, chaleureuse avec le temps) et de la duree de l'absence (simple signe s'il est sorti
    cinq minutes, joie apres une longue journee). Pas encore de marche vers l'entree : il faudrait une position fiable
    (odometrie qui derive ; balises UWB plus tard)."""
    nom = "accueil"
    ABSENCE_COURTE_S = 15 * 60
    ABSENCE_LONGUE_S = 4 * 3600

    def __init__(self):
        self.qui, self.absence_s = None, None

    @classmethod
    def sequence(cls, familiarite, absence_s):
        """-> [(geste de gestures.py, son robot.sound)] joues l'un apres l'autre."""
        if absence_s is not None and absence_s < cls.ABSENCE_COURTE_S:
            return [("oui", "chirp")]                         # il vient de sortir : un petit signe, pas une fete
        if familiarite < 0.3:
            return [("curieux", "inquire")]                   # encore un peu reserve
        seq = [("oui", "greet")]
        if familiarite >= 0.6:
            seq.append(("curieux", "coo"))
        if absence_s is not None and absence_s >= cls.ABSENCE_LONGUE_S:
            seq.append(("content", "wheee"))                  # tremoussement de joie apres une longue absence
        return seq

    def entre(self, brain):
        mem = brain.ctx.extras.get("memoire")
        familiarite = mem.familiarite(self.qui) if mem is not None and self.qui else 0.0
        if self.absence_s is None and mem is not None and self.qui:
            self.absence_s = mem.absence_s(self.qui)
        if mem is not None and self.qui:
            mem.rencontre(self.qui)
        self.etapes = []
        t = 0.0
        seq = self.sequence(familiarite, self.absence_s)
        self.messages, brain.messages = brain.messages, []
        if self.messages:
            seq = seq + [("curieux", "inquire"), ("oui", "chirp")]   # "pendant ton absence, il s'est passe quelque chose"
        for geste, son in seq:
            d, fn = gestures.GESTES[geste]
            self.etapes.append((t, d, fn, son, gestures.GESTES_CORPS.get(geste)))
            t += d + 0.3
        self.total = t
        self.joues = set()
        print(f"[{brain.t_global:6.1f}s] accueil de {self.qui} (familiarite {familiarite:.2f}, absence "
              f"{'?' if self.absence_s is None else f'{self.absence_s / 60:.0f} min'}) : "
              f"{' + '.join(e[3] for e in self.etapes)}"
              + (f" ; messages transmis : {', '.join(self.messages)}" if self.messages else ""), flush=True)

    def duree(self, brain):
        return self.total + 0.3

    def pas(self, brain, t):
        tete, corps = (0, 0, 0, 0), None
        for i, (t0, d, fn, son, fn_corps) in enumerate(self.etapes):
            if t0 <= t < t0 + d:
                if i not in self.joues:
                    self.joues.add(i)
                    brain.ctx.sound(son)
                tete = fn(t - t0)
                corps = fn_corps(t - t0) if fn_corps else None
        brain.ctx.head(tete)
        brain.ctx.pose(corps)


class JeuSolitaire(Etat):
    """Occupation autonome (ROADMAP "Occupation autonome et recherche d'attention") : personne n'est disponible pour
    s'en occuper, le canard s'amuse seul plutot que de rester simplement passif. Petit mouvement ludique sur place
    (avance/recule comme s'il poussait un objet, tete qui suit), pas une vraie recherche de balle (ca demande la
    vision, Phase 2) : juste de quoi distinguer visuellement ce moment d'un `Chill` au repos."""
    nom = "jeu_solitaire"

    def duree(self, brain):
        return brain.rng.uniform(5.0, 9.0)

    def entre(self, brain):
        brain.ctx.sound("chirp")

    def pas(self, brain, t):
        brain.ctx.head((0.0, 0.0, 0.5 * math.sin(2 * math.pi * t / 2.0), 0.0))
        brain.ctx.move(vx=0.2 * math.sin(2 * math.pi * t / 2.0))


class RechercheAttention(Etat):
    """Occupation autonome, variante "aller chercher l'attention" : un habitant (presence HA) ou le chat (veille
    camera) est disponible, le canard va vers lui plutot que de jouer seul. Une seule tentative, jamais insistee
    (regle de vie) : `brain.derniere_fois["ennui"]` sert de temporisation, pas de boucle ici.

    Vers le chat : on reutilise `cible_regard` comme `RegardeChat`, on a sa position. Vers un humain : pas de
    position fiable sans balises UWB (meme limite que `Accueil`, voir sa docstring) -> juste un appel sonore et un
    regard qui balaie, sans deplacement vers une direction qu'on ne connait pas."""
    nom = "cherche_attention"

    def __init__(self):
        self.cible = None   # "humain" ou "chat", pose par Brain._choisit_suivant avant la bascule

    def duree(self, brain):
        return 5.0

    def entre(self, brain):
        brain.ctx.sound("inquire" if self.cible == "humain" else "chirp")
        self.t_vise = None

    def pas(self, brain, t):
        if self.cible == "chat":
            veille, s = brain.ctx.extras.get("chat"), brain.ctx.state
            if veille is not None and s is not None:
                e = veille.estimation
                if e is not None and e[0] != self.t_vise:
                    self.t_vise = e[0]
                    cible = veille.cible_regard(s["odom"]["position"][2])
                    if cible:
                        r = brain.ctx.client.request("robot.look", {"x": float(cible[0]), "y": float(cible[1]), "z": float(cible[2])})
                        h = (r.get("result") or {}).get("head") if isinstance(r, dict) else None
                        if h:
                            brain.ctx.head((h["neck_pitch"], h["head_pitch"], h["head_yaw"], h["head_roll"]))
                            return
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            return
        yaw = 0.5 * math.sin(2 * math.pi * t / 4.0)       # pas de position connue : un regard qui balaie, pas une marche
        brain.ctx.head((0.0, 0.0, yaw, 0.0))


class Sequence(Etat):
    """Suite de gestes de gestures.py, chacun avec son son (robot.sound), joues l'un apres l'autre - la meme mecanique
    que `Accueil`, pour les routines qui n'ont pas besoin de sa logique de familiarite."""

    def __init__(self, nom_etat, etapes):
        self.nom = nom_etat
        self.etapes_def = list(etapes)          # [(geste, son ou None)]

    def etapes_pour(self, brain):
        return self.etapes_def

    def entre(self, brain):
        self.etapes, t = [], 0.0
        for geste, son in self.etapes_pour(brain):
            d, fn = gestures.GESTES[geste]
            self.etapes.append((t, d, fn, son, gestures.GESTES_CORPS.get(geste)))
            t += d + 0.3
        self.total = t
        self.joues = set()

    def duree(self, brain):
        return self.total + 0.3

    def pas(self, brain, t):
        tete, corps = (0, 0, 0, 0), None
        for i, (t0, d, fn, son, fn_corps) in enumerate(self.etapes):
            if t0 <= t < t0 + d:
                if i not in self.joues:
                    self.joues.add(i)
                    if son:
                        brain.ctx.sound(son)
                tete = fn(t - t0)
                corps = fn_corps(t - t0) if fn_corps else None
        brain.ctx.head(tete)
        brain.ctx.pose(corps)


class Bonjour(Sequence):
    """Routine du matin (ROADMAP, table Humains : "etirement du matin", prochaine etape n°6) : une fois par jour, a
    l'heure reelle configuree, un grand etirement puis un bonjour - plus chaleureux si quelqu'un est a la maison
    (presence HA), un simple roucoulement sinon. Independant du reveil de sieste (qui s'etire deja)."""

    def __init__(self):
        super().__init__("bonjour", [])

    def etapes_pour(self, brain):
        if brain.presents:
            return [("etirement", "coo"), ("oui", "greet")]
        return [("etirement", "coo")]


class Brain:
    SEUIL_SIESTE = 0.25
    # "Va se recharger de sa propre initiative avant d'etre a court" (ROADMAP "chantier actif") : la VRAIE batterie
    # (state["battery"]["percent"], distincte du modele comportemental `Humeur.energie`) force le repos en dessous
    # de ce seuil - anticipation (consommer moins en se posant) plutot qu'attendre l'arret force. Pas encore de
    # retour physique au chargeur : aucune position de chargeur connue dans brain.py (meme limite que `Accueil`).
    BATTERIE_BASSE_PCT = 25.0
    RARES = {"lissage": 0.015, "ebouriffe": 0.01, "etirement": 0.008, "eternuement": 0.005}   # poids face a ~1 pour le reste
    DELAI_RARE = 300.0
    # Occupation autonome / recherche d'attention (ROADMAP "chantier actif", 2026-10-05) : si rien ne s'est passe
    # depuis SEUIL_ENNUI_S, le canard ne reste pas simplement passif en Chill -> jeu solitaire ou recherche
    # d'attention (humain present, sinon chat visible). Jamais plus souvent que DELAI_ENNUI_S (ne jamais insister).
    SEUIL_ENNUI_S = 600.0
    DELAI_ENNUI_S = 300.0
    # "S'ebroue apres une longue immobilite REELLE" (ROADMAP "chantier actif") : reutilise le geste `ebouriffe`
    # existant, mais declenche par l'etat constate (odom qui ne bouge quasi pas) plutot que par l'horloge/le hasard
    # des RARES ci-dessus - les deux partagent le meme garde-fou (`derniere_fois["ebouriffe"]`, DELAI_RARE) pour ne
    # jamais se declencher plus souvent que le geste "rare" habituel, quelle que soit la cause.
    SEUIL_IMMOBILE_S = 1200.0    # 20 min sans bouger de plus de SEUIL_DEPLACEMENT
    SEUIL_DEPLACEMENT = 0.1      # m : en dessous, on considere que le canard n'a pas vraiment bouge
    # Garde-fou "chat agace" (ROADMAP, garde-fous du chat, non negociable) : renverse plusieurs fois de suite -> il
    # s'assoit et passe en veille plutot que de recommencer. Valable quelle que soit la cause (chat, enfant, sol
    # glissant) : tomber en serie n'est jamais une raison de repartir aussitot.
    CHUTES_AGACE = 3
    FENETRE_CHUTES_S = 600.0
    VEILLE_AGACE_S = 900.0
    DELAI_DANSE_S = 300.0       # une danse au plus toutes les 5 min (initiative rare, pas un juke-box)
    TAQUIN_PROBA = 0.2          # "non" theatral avant d'accepter de jouer (registre du jeu seulement, jamais la securite)
    # evenement de la maison -> (etat de reaction, hausse d'eveil)
    REACTIONS_MAISON = {
        "impression_finie": ("celebre", 0.4),
        "impression_echec": ("alerte", 0.7),
        "impression_commencee": ("info", 0.1),
        "alerte": ("alerte", 0.7),
        "info": ("info", 0.2),
        # messager de la maison (pont_ha.py, sections [[appareil]])
        "sonnette": ("sonnette", 0.6),
        "machine_finie": ("messager", 0.2),
        "machine_echec": ("alerte", 0.7),
    }
    # Notifications qui meritent d'etre REDITES a un habitant absent a ce moment-la (ROADMAP "Messager physique") : le
    # canard les garde et les rappelle a l'accueil du prochain retour (sans navigation : il ne va pas chercher
    # quelqu'un, il transmet quand on rentre). Une sonnette n'a pas de sens apres coup : pas gardee.
    MESSAGES_A_GARDER = ("impression_finie", "impression_echec", "machine_finie", "machine_echec")
    MESSAGES_MAX = 5

    BONJOUR_FENETRE_H = 4       # le bonjour du matin n'est dit que dans les 4 h qui suivent l'heure prevue

    def __init__(self, client, humeur=None, seed=None, extras=None, heures_calmes=None, horloge=time.localtime,
                 bonjour=None):
        self.ctx = Ctx(client)
        self.ctx.extras = extras or {}          # perceptions externes partagees (ex. {"chat": VeilleChat})
        # "Heures calmes" (ROADMAP, table Humains : routine "Heure, HA" -> Nap) : optionnel (None = desactive, le
        # comportement par defaut ne change pas) - un tuple (heure_debut, heure_fin) en heure LOCALE, ex. (23, 7)
        # pour 23h-7h (franchit minuit). Reutilise exactement le chemin "calme_on"/"calme_off" de l'interrupteur
        # HA (meme effet : assis, silencieux, prioritaire) plutot que dupliquer sa logique - un vrai toggle HA
        # pendant la nuit reste respecte jusqu'au prochain changement d'heure (evenement non renvoye si deja a
        # l'etat demande). `horloge` injectable pour les tests (sinon l'heure reelle de la machine).
        self.heures_calmes = heures_calmes
        self.horloge = horloge
        self._nuit_actuelle = None
        # Routine du matin : `bonjour` = heure locale (8 ou (7, 30)) a partir de laquelle le canard dit bonjour, une
        # seule fois par jour, des qu'il est au repos (chill/look) et hors mode calme ; rien apres la fenetre de
        # BONJOUR_FENETRE_H (un "bonjour" a 17h n'a pas de sens). None = desactive (opt-in, comme heures_calmes).
        self.bonjour = (bonjour, 0) if isinstance(bonjour, int) else (tuple(bonjour) if bonjour else None)
        self._jour_bonjour = None
        self.humeur = humeur or Humeur()
        self.rng = random.Random(seed)
        self.etats = {
            "chill": Chill(), "look": LookAround(), "turn": TurnInPlace(),
            "wander": Wander(), "nap": Nap(),
            "startle": Geste("startle", "surpris", recul=True),
            "curious": Geste("curious", "curieux"),
            # reactions aux notifications de la maison (Home Assistant, voir pont_ha.py)
            "celebre": Geste("celebre", "content", son="greet"),   # impression terminee : tremoussement de joie
            "alerte": Geste("alerte", "surpris", son="alarm"),     # impression ratee, alarme
            "info": Geste("info", "curieux", son="inquire"),       # information a signaler
            "regarde_chat": RegardeChat(),                         # le chat vient d'apparaitre
            "accueil": Accueil(),                                  # un habitant rentre (presence HA)
            "rituel_depart": Geste("rituel_depart", "oui", son="chirp"),  # signe discret au depart, symetrique
            "ecoute": Ecoute(),                                    # conversation vocale en cours (quacksat)
            # vocabulaire M9 (gestes de tete scriptes) : initiatives RARES, voir RARES / _choisit_suivant
            "etirement": Geste("etirement", "etirement", son="coo"),
            "ebouriffe": Geste("ebouriffe", "ebouriffe"),
            "lissage": Geste("lissage", "lissage"),
            "eternuement": Geste("eternuement", "eternuement", son="peck"),
            "jeu_solitaire": JeuSolitaire(),                       # occupation autonome, personne de disponible
            "cherche_attention": RechercheAttention(),             # occupation autonome, humain/chat disponible
            "bonjour": Bonjour(),                                  # routine du matin, une fois par jour
            # messager : "on sonne !" (tete qui se redresse + alarme, puis interrogatif) ; "c'est fini" (signe)
            "sonnette": Sequence("sonnette", [("surpris", "alarm"), ("curieux", "inquire")]),
            "messager": Sequence("messager", [("curieux", "inquire"), ("oui", "chirp")]),
            "main_tendue": MainTendue(),                           # une main tendue devant lui (ToF) : il picore
            "caresse": Caresse(),                                  # on le caresse : roucoulement, tete contre la main
            "soleil": Soleil(),                                    # jeu "1-2-3 soleil" (camera + ToF)
            "va_au_coin": VaAuCoin(),                              # fatigue : rejoindre son coin de sieste
            "taquin": Sequence("taquin", [("non", "inquire")]),    # "non..." puis il joue quand meme
            # reflexes sonores (audio.py)
            "appel": Sequence("appel", [("curieux", "inquire"), ("oui", "greet")]),   # deux claquements : "oui ?"
            "bravo": Sequence("bravo", [("content", "wheee")]),                       # applaudissements
            "danse": Danse(),                                                        # musique : hochements en rythme
        }
        self.chutes = []                        # t_global des dernieres chutes (garde-fou "chat agace")
        self.veille_jusqua = -1.0               # repos force apres une serie de chutes
        self.detecteur_caresse = DetecteurCaresse()
        self.detecteur_main = DetecteurMain()
        self._tete_prec, self._t_tete_change = None, 0.0     # derniere consigne de tete vue, et quand elle a change
        self.messages = []                      # notifications a redire au prochain habitant qui rentre
        self.suivant_force = None               # etat impose pour la prochaine bascule (un etat qui enchaine)
        self.derniere_fois = {}                 # etat rare -> t_global de la derniere fois
        self.mode_calme = False                 # interrupteur "calme" de Home Assistant (regle de vie)
        self.exploration = Exploration()        # memoire des zones visitees (novelty grid du M9)
        self.explo_actif = self.ctx.extras.get("exploration", True)
        self._t_explo = -1.0
        self._derniere_position = None          # derniere position odom connue, pour noter une "zone noire" a la chute
        self._pos_ref_immobile = None           # (x, y) de reference pour detecter l'immobilite reelle
        self._t_ref_immobile = 0.0
        self._batterie_pct = None               # vraie batterie (state["battery"]["percent"]), si connue
        self.courant = self.etats["chill"]
        self.t_etat = 0.0
        self.fin_etat = self.courant.duree(self)
        self.evenements = []
        self.differes = []                      # notifications arrivees pendant une conversation : rejouees apres
        self.journal = []  # (t_global, nom_etat, energie, eveil)
        self.t_global = 0.0
        self.tombe = False
        self.presents = set()                   # habitants actuellement a la maison (presence HA, retour/depart)
        self.derniere_interaction = 0.0         # dernier evenement externe notable (hors bascule calme/ecoute)

    # -- evenements externes (plus tard : micro, camera, HA...) --
    def evenement(self, nom):
        self.evenements.append(nom)

    def _traite_evenements(self):
        while self.evenements:
            nom = self.evenements.pop(0)
            base, _, detail = nom.partition(":")     # "impression_echec:MK4S" -> ("impression_echec", "MK4S")
            if base in ("calme_on", "calme_off"):
                # Regle de vie : interrupteur "calme" (veille, silence, sieste forcee). Prioritaire sur tout.
                actif = base == "calme_on"
                if actif != self.mode_calme:
                    self.mode_calme = actif
                    self.ctx.silence = actif
                    print(f"[{self.t_global:6.1f}s] mode calme {'ACTIVE' if actif else 'desactive'}", flush=True)
                    self._bascule("nap" if actif else ("etirement" if self.courant.nom == "nap" else "chill"))
                continue
            # Occupation autonome : tout evenement reel (hors bascule "calme") remet le compteur d'ennui a zero,
            # qu'il soit ou non traite immediatement (differe pendant une conversation, ignore pendant la sieste...).
            self.derniere_interaction = self.t_global
            if base in ("ecoute_on", "ecoute_off"):
                # conversation vocale (satellite Assist) : on se tait ; a la fin, on reprend et on rejoue ce qui attendait
                if base == "ecoute_on" and self.courant.nom != "ecoute":
                    print(f"[{self.t_global:6.1f}s] conversation vocale : le cerveau se tait", flush=True)
                    self._bascule("ecoute")
                elif base == "ecoute_off" and self.courant.nom == "ecoute":
                    print(f"[{self.t_global:6.1f}s] fin de conversation ({len(self.differes)} evenement(s) en attente)", flush=True)
                    self._bascule("nap" if self.mode_calme else "chill")
                continue
            if self.courant.nom == "ecoute" and base != "depart":
                self.differes.append(nom)       # ni son ni geste pendant que quelqu'un parle au canard
                continue
            if base in ("retour", "depart"):
                # presence d'un habitant (person.* dans HA) : "retour:Nom|absence_s", "depart:Nom"
                qui, _, absence = detail.partition("|")
                mem = self.ctx.extras.get("memoire")
                if base == "depart":
                    self.presents.discard(qui)
                    if mem is not None:
                        mem.depart(qui)
                    # Petit rituel de presence, symetrique de l'accueil au retour (ROADMAP "chantier actif") : un
                    # signe discret et reconnaissable, jamais une "fete" - et jamais pendant la sieste, le calme ou
                    # une conversation en cours (ne jamais interrompre pour un simple depart).
                    if not self.mode_calme and self.courant.nom not in ("nap", "ecoute"):
                        self._bascule("rituel_depart")
                    continue
                self.presents.add(qui)
                absence = float(absence) if absence else (mem.absence_s(qui) if mem is not None else None)
                longue = absence is not None and absence >= Accueil.ABSENCE_LONGUE_S
                if self.mode_calme or (self.courant.nom == "nap" and not longue):
                    # calme : jamais de reaction ; sieste : seul un retour apres une longue absence le reveille
                    if mem is not None:
                        mem.rencontre(qui)
                    print(f"[{self.t_global:6.1f}s] {qui} rentre (pas de reaction : "
                          f"{'mode calme' if self.mode_calme else 'sieste'})", flush=True)
                    continue
                self.etats["accueil"].qui, self.etats["accueil"].absence_s = qui, absence
                self.humeur.eveil = min(1.0, self.humeur.eveil + (0.6 if longue else 0.3))
                self._bascule("accueil")
                continue
            if base in self.REACTIONS_MAISON:
                # une notification que l'habitant a demandee n'est pas un caprice : elle interrompt la sieste
                etat, eveil = self.REACTIONS_MAISON[base]
                self.humeur.eveil = min(1.0, self.humeur.eveil + eveil)
                if base in self.MESSAGES_A_GARDER and not self.presents:
                    self.messages = (self.messages + [nom])[-self.MESSAGES_MAX:]
                print(f"[{self.t_global:6.1f}s] notification maison : {nom}", flush=True)
                self._bascule(etat)
                continue
            sur_evt = getattr(self.courant, "sur_evenement", None)
            if sur_evt is not None and sur_evt(self, base):
                continue                        # l'etat en cours (un jeu) a pris l'evenement pour lui
            if base == "jeu_soleil":
                if self.mode_calme or self.courant.nom in ("soleil", "nap"):
                    continue                    # pas de jeu en mode calme ; pas pendant la sieste (ne pas reveiller)
                if self.ctx.extras.get("mouvement") is None:
                    print(f"[{self.t_global:6.1f}s] 1-2-3 soleil impossible : pas de camera (veille mouvement)", flush=True)
                    continue
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.4)
                if self.rng.random() < self.TAQUIN_PROBA:
                    self.suivant_force = "soleil"    # taquinerie : "non..." de la tete, puis il joue quand meme
                    self._bascule("taquin")
                else:
                    self._bascule("soleil")
                continue
            if base == "caresse":
                if self.courant.nom == "nap" or self.mode_calme:
                    self.ctx.sound("coo")       # caresse pendant le sommeil : un roucoulement, sans se reveiller
                elif self.courant.nom != "caresse":
                    self._bascule("caresse")
                continue
            if self.courant.nom == "nap":
                continue  # ne jamais insister : on dort, l'evenement est perdu
            if nom == "bruit":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.5)
                self._bascule("startle")
            elif nom == "chat":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("regarde_chat" if "chat" in self.ctx.extras else "curious")
            elif base == "appel":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("appel")
            elif base == "applaudissements":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("bravo")
            elif base == "musique" and self.t_global - self.derniere_fois.get("danse", -1e9) >= self.DELAI_DANSE_S:
                self.derniere_fois["danse"] = self.t_global
                self.etats["danse"].bpm = int(detail) if detail.isdigit() else 100
                self._bascule("danse")
            elif nom == "main":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.2)
                self._bascule("main_tendue")
            elif nom == "personne":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("curious")

    def reste_assis(self):
        """Pendant le mode calme ou la veille apres des chutes, on ne se releve pas entre deux siestes."""
        return self.mode_calme or self.t_global < self.veille_jusqua

    COIN_DISTANCE = (0.5, 4.0)               # m : plus pres, inutile de bouger ; plus loin, l'odometrie a trop derive

    def _coin_atteignable(self):
        """Coin de sieste appris (exploration.py), s'il est a une distance raisonnable et que le capteur de distance
        est la (on ne marche jamais a l'aveugle)."""
        if self.ctx.extras.get("tof") is None or not (self.ctx.state or {}).get("odom"):
            return None
        coin = self.exploration.coin_favori("nap", self.t_global)
        if coin is None:
            return None
        p = self.ctx.state["odom"]["position"]
        d = math.hypot(coin[0] - p[0], coin[1] - p[1])
        return coin if self.COIN_DISTANCE[0] <= d <= self.COIN_DISTANCE[1] else None

    def _choisit_suivant(self):
        force = getattr(self, "suivant_force", None)
        if force:
            self.suivant_force = None
            return force
        if self.mode_calme or self.t_global < self.veille_jusqua:
            return "nap"                        # sieste prolongee, assis : interrupteur calme, ou veille apres des chutes
        h = self.humeur
        batterie_basse = self._batterie_pct is not None and self._batterie_pct < self.BATTERIE_BASSE_PCT
        if h.energie < self.SEUIL_SIESTE or batterie_basse:
            # fatigue "jouee" OU vraie batterie basse : meme reponse (repos) - dans son coin favori s'il est connu et
            # pas trop loin (sauf batterie basse : on ne gaspille pas les derniers pourcents a marcher)
            if not batterie_basse and self.courant.nom not in ("nap", "va_au_coin"):
                coin = self._coin_atteignable()
                if coin is not None:
                    self.etats["va_au_coin"].cible = coin
                    return "va_au_coin"
            return "nap"
        if self.courant.nom == "nap":
            self.derniere_fois["etirement"] = self.t_global
            return "etirement"                  # on s'etire en se reveillant
        if self.courant.nom != "chill":
            return "chill"
        # Occupation autonome / recherche d'attention : rien ne s'est passe depuis longtemps -> le canard ne reste
        # pas simplement passif. Priorite sur les initiatives habituelles (look/turn/wander/RARES), mais seulement
        # si le delai minimal est passe (ne jamais insister).
        sans_interaction = self.t_global - self.derniere_interaction
        depuis_ennui = self.t_global - self.derniere_fois.get("ennui", -1e9)
        if sans_interaction >= self.SEUIL_ENNUI_S and depuis_ennui >= self.DELAI_ENNUI_S:
            self.derniere_fois["ennui"] = self.t_global
            chat = self.ctx.extras.get("chat")
            chat_visible = chat is not None and getattr(chat.suivi, "visible", False)
            if self.presents or chat_visible:
                self.etats["cherche_attention"].cible = "humain" if self.presents else "chat"
                return "cherche_attention"
            return "jeu_solitaire"
        poids = {"look": 0.4, "turn": 0.2 + 0.3 * h.energie,
                 "wander": 0.15 + 0.4 * h.energie * (0.5 + h.eveil)}
        # Initiative rare et surprenante (principe Pollen : un duo surprise est un plaisir, un juke-box non) :
        # faible probabilite, et jamais deux fois le meme geste en moins de DELAI_RARE secondes.
        for nom, p in self.RARES.items():
            if self.t_global - self.derniere_fois.get(nom, -1e9) >= self.DELAI_RARE:
                poids[nom] = p
        noms = list(poids)
        return self.rng.choices(noms, weights=[poids[n] for n in noms])[0]

    def _bascule(self, nom):
        if self.courant.nom == "ecoute" and nom != "ecoute" and self.differes:
            self.evenements.extend(self.differes)      # fin de conversation (ou delai depasse) : on rejoue ce qui attendait
            self.differes = []
        if nom in self.RARES:
            self.derniere_fois[nom] = self.t_global
        self.courant.sort(self)
        self.courant = self.etats[nom]
        self.courant.entre(self)
        self.t_etat = 0.0
        self.fin_etat = self.courant.duree(self)
        self.journal.append((round(self.t_global, 1), nom,
                             round(self.humeur.energie, 2), round(self.humeur.eveil, 2)))
        print(f"[{self.t_global:6.1f}s] -> {nom:8s} energie={self.humeur.energie:.2f} "
              f"eveil={self.humeur.eveil:.2f}", flush=True)

    REPOS_MAIN = ("chill", "main_tendue")    # canard immobile, tete au repos : une main peut lui etre tendue
    TETE_STABLE_S = 1.0                      # la tete doit etre immobile depuis 1 s (sinon un meuble "apparait")

    def _surveille_main(self, state):
        """Main tendue (main_tendue.py) : seulement quand le canard est immobile - en marchant, tout ce dont il
        s'approche "apparait" devant lui. Jamais si le chat est la (une patte n'est pas une main, et pas de geste vif
        pres du chat : garde-fou de la ROADMAP)."""
        tof = self.ctx.extras.get("tof")
        if tof is None or not hasattr(tof, "points"):
            return
        tete = getattr(self.ctx, "tete_cmd", None)
        if tete != getattr(self, "_tete_prec", None):
            self._tete_prec, self._t_tete_change = tete, self.t_global
        en_suivi = self.courant.nom == "main_tendue"     # la tete suit la main : on continue de la localiser
        if (self.courant.nom not in self.REPOS_MAIN or self.mode_calme
                or (not en_suivi and self.t_global - self._t_tete_change < self.TETE_STABLE_S)):
            self.detecteur_main.reinitialiser()
            return
        evts = self.detecteur_main.mise_a_jour(tof.points(state), self.t_global)
        chat = self.ctx.extras.get("chat")
        if chat is not None and getattr(getattr(chat, "suivi", None), "visible", False):
            return
        if self.courant.nom != "main_tendue":
            for e in evts:
                self.evenement(e)

    def _surveille_caresse(self, state):
        joints = state.get("joints")
        if not joints or len(joints) < 9:
            return
        immobile = self.courant.nom == "chill" or (     # sieste : pas pendant qu'il s'assoit ni qu'il se releve
            self.courant.nom == "nap" and 6.0 <= self.t_etat < self.fin_etat - 4.0)
        for e in self.detecteur_caresse.mise_a_jour(self.t_global, getattr(self.ctx, "tete_cmd", None),
                                                    joints[5:9], immobile):
            self.evenement(e)

    def _verifie_bonjour(self):
        h = self.horloge()
        jour = getattr(h, "tm_yday", None)
        if jour == self._jour_bonjour:
            return
        minutes = h.tm_hour * 60 + getattr(h, "tm_min", 0)
        debut = self.bonjour[0] * 60 + self.bonjour[1]
        if not (0 <= minutes - debut < self.BONJOUR_FENETRE_H * 60):
            return
        if self.mode_calme or self.tombe or self.courant.nom not in ("chill", "look"):
            return                              # on attend un moment de repos (ne jamais interrompre une activite)
        self._jour_bonjour = jour
        print(f"[{self.t_global:6.1f}s] routine du matin : bonjour", flush=True)
        self._bascule("bonjour")

    def tick(self, state, dt):
        """Un pas du cerveau, a appeler une fois par trame robot.state."""
        self.ctx.state = state
        self.ctx.bec()
        if self.ctx.extras.get("tof") is not None:
            self.ctx.extras["tof"].noter_etat(state)     # pose de tete datee, pour placer chaque trame ToF a son instant
        self.t_global += dt
        if self.heures_calmes is not None:
            debut, fin = self.heures_calmes
            h = self.horloge().tm_hour
            nuit = (h >= debut or h < fin) if debut > fin else (debut <= h < fin)
            if nuit != self._nuit_actuelle:
                self._nuit_actuelle = nuit
                self.evenement("calme_on" if nuit else "calme_off")
        if state.get("odom"):
            self._derniere_position = (state["odom"]["position"][0], state["odom"]["position"][1])
        pct = state.get("battery", {}).get("percent")
        if pct is not None:
            self._batterie_pct = pct
        if state.get("safety", {}).get("fallen"):
            if not self.tombe:
                print(f"[{self.t_global:6.1f}s] CHUTE : cerveau en pause (robotd se charge du relevement)", flush=True)
                if self._derniere_position is not None:
                    self.exploration.chute(*self._derniere_position, self.t_global)   # "zone noire" apprise
                self.chutes = [t for t in self.chutes if self.t_global - t <= self.FENETRE_CHUTES_S] + [self.t_global]
                if len(self.chutes) >= self.CHUTES_AGACE:
                    self.veille_jusqua = self.t_global + self.VEILLE_AGACE_S
                    chat = self.ctx.extras.get("chat")
                    qui = "le chat" if chat is not None and getattr(chat.suivi, "visible", False) else "quelque chose"
                    print(f"[{self.t_global:6.1f}s] {len(self.chutes)} chutes en {self.FENETRE_CHUTES_S / 60:.0f} min "
                          f"({qui}) : veille {self.VEILLE_AGACE_S / 60:.0f} min, assis", flush=True)
            self.tombe = True
            self.ctx.calme()
            return
        if self.tombe and state.get("policy") == "stand":
            # De nouveau debout (la sequence limp_fall de robotd l'a releve) : il s'ebroue, comme un canard qui se
            # remet d'une glissade, puis reprend sa vie. Pas en mode calme (silence et immobilite d'abord).
            self.tombe = False
            print(f"[{self.t_global:6.1f}s] releve apres la chute", flush=True)
            if self.t_global < self.veille_jusqua:
                self._bascule("nap")             # serie de chutes : il s'assoit et ne recommence pas
            elif not self.mode_calme:
                self._bascule("ebouriffe")
        if self.tombe:
            return                              # pas encore la politique 'stand' : on attend sans rien commander
        if state.get("odom") and self.t_global - self._t_explo >= 0.5:
            self._t_explo = self.t_global
            self.exploration.noter(state["odom"]["position"][0], state["odom"]["position"][1], self.t_global)
        if state.get("odom") and self.courant.nom in ("chill", "nap"):
            # "Deux coins favoris distincts selon l'activite" (ROADMAP "chantier actif") : on accumule le temps
            # passe par activite, par case - a chaque trame (pas throttle comme `noter` ci-dessus : c'est une duree
            # cumulee, pas un compteur de passages). La navigation vers le coin appris n'est pas encore cablee (pas
            # de position fiable connue d'avance, meme limite que Accueil).
            o = state["odom"]
            self.exploration.preference(o["position"][0], o["position"][1], self.courant.nom, dt, self.t_global)
        if state.get("odom"):
            # "S'ebroue apres une longue immobilite REELLE" (ROADMAP "chantier actif") : l'odom ne bouge quasi pas
            # depuis SEUIL_IMMOBILE_S -> `ebouriffe`, uniquement depuis un etat de repos (chill/look), pas en
            # interrompant autre chose (wander, accueil, ecoute...). Meme garde-fou que le tirage RARES habituel.
            pos = (state["odom"]["position"][0], state["odom"]["position"][1])
            if self._pos_ref_immobile is None or math.hypot(pos[0] - self._pos_ref_immobile[0],
                                                              pos[1] - self._pos_ref_immobile[1]) > self.SEUIL_DEPLACEMENT:
                self._pos_ref_immobile, self._t_ref_immobile = pos, self.t_global
            elif (self.t_global - self._t_ref_immobile >= self.SEUIL_IMMOBILE_S
                  and self.t_global - self.derniere_fois.get("ebouriffe", -1e9) >= self.DELAI_RARE
                  and not self.mode_calme and self.courant.nom in ("chill", "look")):
                self.derniere_fois["ebouriffe"] = self.t_global
                self._t_ref_immobile = self.t_global     # redemarre la fenetre : pas de declenchement en boucle
                self._bascule("ebouriffe")

        self._surveille_main(state)
        self._surveille_caresse(state)
        self._traite_evenements()
        if self.bonjour is not None:
            self._verifie_bonjour()                 # apres les evenements : un "calme_on" en attente passe d'abord
        self.humeur.avance(dt, self.courant.nom)
        self.t_etat += dt
        self.courant.pas(self, self.t_etat)
        if self.t_etat >= self.fin_etat:
            self._bascule(self._choisit_suivant())

    def arret(self):
        """Sortie propre : on se leve si on dormait, tete neutre, mouvement arrete."""
        self.courant.sort(self)
        self.ctx.calme()


def run(client, duree, humeur=None, evenements=None, seed=None, source=None, a_chaque_tick=None, extras=None,
        **options):
    """`source()` : appelee a chaque trame, renvoie les noms d'evenements arrives depuis l'exterieur (pont
    Home Assistant...). `a_chaque_tick(brain, state)` : crochet facultatif (publication d'etat...). `options` :
    reglages optionnels de Brain (heures_calmes, bonjour...)."""
    brain = Brain(client, humeur=humeur, seed=seed, extras=extras, **options)
    evenements = sorted(evenements or [])
    last_t = None
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < duree:
            state = client.read_state_frame()
            t = state.get("t")
            dt = (t - last_t) if (t is not None and last_t is not None and 0 < t - last_t < 0.5) else DT_DEFAUT
            last_t = t
            while evenements and evenements[0][0] <= time.monotonic() - t0:
                brain.evenement(evenements.pop(0)[1])
            if source:
                for nom in source():
                    brain.evenement(nom)
            brain.tick(state, dt)
            if a_chaque_tick:
                a_chaque_tick(brain, state)
    finally:
        brain.arret()
    return brain


def _parse_args(argv):
    duree, energie, events = 60.0, 0.8, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--energy":
            energie = float(argv[i + 1]); i += 2
        elif a == "--events":
            for item in argv[i + 1].split(","):
                nom, _, t = item.partition("@")
                events.append((float(t), nom))
            i += 2
        else:
            duree = float(a); i += 1
    return duree, energie, events


if __name__ == "__main__":
    from poc_robotd_client import RobotdClient, SOCK_PATH
    duree, energie, events = _parse_args(sys.argv[1:])
    c = RobotdClient(SOCK_PATH)
    c.request("robot.subscribe", {})
    print(f"Cerveau actif {duree:.0f}s, energie initiale {energie}", flush=True)
    b = run(c, duree, Humeur(energie=energie), events)
    print(f"Fin. {len(b.journal)} transitions.", flush=True)
