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


class Ctx:
    """Ce que voit un etat : client robotd, derniere trame, aide pour commander."""

    def __init__(self, client):
        self.client = client
        self.state = None
        self.sitting = False

    def head(self, vals):
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
        yaw = 0.6 * math.sin(2 * math.pi * t / 6.0)
        brain.ctx.head((0.0, 0.1 * math.sin(2 * math.pi * t / 3.0), yaw, 0.0))


# Vitesses AU-DESSUS de la zone morte de la politique de marche (ZONE_MORTE.md) : en dessous, les jambes restent figees.
V_PROMENADE, V_ROTATION = 0.4, 1.5
LIBRE_MIN = 0.45                 # on n'avance pas si le ToF voit un obstacle a moins de 45 cm devant


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

    def entre(self, brain):
        self.duree_s = brain.rng.uniform(2.5, 6.0)
        self.arrets = 0
        self.virage = None
        # Exploration : avant de partir, regarder si une direction mene vers des zones moins visitees (sauf si on vient
        # justement de tourner pour ca).
        if brain.explo_actif and brain.ctx.state is not None and not getattr(brain, "cap_choisi", False):
            o = brain.ctx.state["odom"]
            ecart = brain.exploration.meilleur_ecart(o["position"][0], o["position"][1], o["yaw"], brain.t_global)
            if abs(ecart) >= math.radians(30):
                self.virage = ecart
        brain.cap_choisi = False

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))
        if self.virage is not None:                          # d'abord tourner vers la zone la plus nouvelle
            brain.virage_cible, self.virage = self.virage, None
            brain.fin_etat = brain.t_etat
            brain.suivant_force = "turn"
            brain.ctx.move()
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

    def duree(self, brain):
        return self.total

    def pas(self, brain, t):
        ctx = brain.ctx
        if t < 2.0 and not self.assis:
            ctx.head(gestures.fatigue(t))
        elif not self.assis:
            ctx.toggle_sit()
            self.assis = True
        elif t >= self.total - 4.0 and not self.leve and not brain.mode_calme:
            ctx.toggle_sit()
            self.leve = True
            ctx.head((0, 0, 0, 0))

    def sort(self, brain):
        if brain.ctx.sitting and not brain.mode_calme:
            brain.ctx.toggle_sit()
        brain.ctx.calme()


class RegardeChat(Etat):
    """Le chat vient d'apparaitre : petit son interrogatif, puis on le suit des yeux quelques secondes. La position du
    chat vient de la veille (chat.py) ; c'est robotd qui calcule l'orientation de la tete (`robot.look`), on renvoie
    ensuite ces angles a chaque trame pour tenir le regard."""
    nom = "regarde_chat"

    # familiarite (memoire.py) -> (son, duree du regard) : mefiant au debut, chaleureux avec le temps
    ACCUEIL = ((0.3, "inquire", 8.0), (0.6, "greet", 7.0), (1.01, "coo", 6.0))

    def entre(self, brain):
        mem = brain.ctx.extras.get("memoire")
        self.familiarite = mem.familiarite("chat") if mem is not None else 0.0
        _, son, self.duree_s = next(a for a in self.ACCUEIL if self.familiarite < a[0])
        brain.ctx.sound(son)
        self.son = son
        self.tete = (0.0, 0.0, 0.0, 0.0)
        self.t_vise = None
        self.n_look = 0

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
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
                        self.tete = (h["neck_pitch"], h["head_pitch"], h["head_yaw"], h["head_roll"])
                        self.n_look += 1
        brain.ctx.head(self.tete)


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
        for geste, son in self.sequence(familiarite, self.absence_s):
            d, fn = gestures.GESTES[geste]
            self.etapes.append((t, d, fn, son, gestures.GESTES_CORPS.get(geste)))
            t += d + 0.3
        self.total = t
        self.joues = set()
        print(f"[{brain.t_global:6.1f}s] accueil de {self.qui} (familiarite {familiarite:.2f}, absence "
              f"{'?' if self.absence_s is None else f'{self.absence_s / 60:.0f} min'}) : "
              f"{' + '.join(e[3] for e in self.etapes)}", flush=True)

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


class Brain:
    SEUIL_SIESTE = 0.25
    RARES = {"lissage": 0.015, "ebouriffe": 0.01, "etirement": 0.008, "eternuement": 0.005}   # poids face a ~1 pour le reste
    DELAI_RARE = 300.0
    # evenement de la maison -> (etat de reaction, hausse d'eveil)
    REACTIONS_MAISON = {
        "impression_finie": ("celebre", 0.4),
        "impression_echec": ("alerte", 0.7),
        "impression_commencee": ("info", 0.1),
        "alerte": ("alerte", 0.7),
        "info": ("info", 0.2),
    }

    def __init__(self, client, humeur=None, seed=None, extras=None):
        self.ctx = Ctx(client)
        self.ctx.extras = extras or {}          # perceptions externes partagees (ex. {"chat": VeilleChat})
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
            "ecoute": Ecoute(),                                    # conversation vocale en cours (quacksat)
            # vocabulaire M9 (gestes de tete scriptes) : initiatives RARES, voir RARES / _choisit_suivant
            "etirement": Geste("etirement", "etirement", son="coo"),
            "ebouriffe": Geste("ebouriffe", "ebouriffe"),
            "lissage": Geste("lissage", "lissage"),
            "eternuement": Geste("eternuement", "eternuement", son="peck"),
        }
        self.derniere_fois = {}                 # etat rare -> t_global de la derniere fois
        self.mode_calme = False                 # interrupteur "calme" de Home Assistant (regle de vie)
        self.exploration = Exploration()        # memoire des zones visitees (novelty grid du M9)
        self.explo_actif = self.ctx.extras.get("exploration", True)
        self._t_explo = -1.0
        self.courant = self.etats["chill"]
        self.t_etat = 0.0
        self.fin_etat = self.courant.duree(self)
        self.evenements = []
        self.differes = []                      # notifications arrivees pendant une conversation : rejouees apres
        self.journal = []  # (t_global, nom_etat, energie, eveil)
        self.t_global = 0.0
        self.tombe = False

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
                    if mem is not None:
                        mem.depart(qui)
                    continue
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
                print(f"[{self.t_global:6.1f}s] notification maison : {nom}", flush=True)
                self._bascule(etat)
                continue
            if self.courant.nom == "nap":
                continue  # ne jamais insister : on dort, l'evenement est perdu
            if nom == "bruit":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.5)
                self._bascule("startle")
            elif nom == "chat":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("regarde_chat" if "chat" in self.ctx.extras else "curious")
            elif nom == "personne":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("curious")

    def _choisit_suivant(self):
        force = getattr(self, "suivant_force", None)
        if force:
            self.suivant_force = None
            return force
        if self.mode_calme:
            return "nap"                        # sieste prolongee, assis, sans bruit, tant que l'interrupteur est actif
        h = self.humeur
        if h.energie < self.SEUIL_SIESTE:
            return "nap"
        if self.courant.nom == "nap":
            self.derniere_fois["etirement"] = self.t_global
            return "etirement"                  # on s'etire en se reveillant
        if self.courant.nom != "chill":
            return "chill"
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

    def tick(self, state, dt):
        """Un pas du cerveau, a appeler une fois par trame robot.state."""
        self.ctx.state = state
        self.ctx.bec()
        self.t_global += dt
        if state.get("safety", {}).get("fallen"):
            if not self.tombe:
                print(f"[{self.t_global:6.1f}s] CHUTE : cerveau en pause (robotd se charge du relevement)", flush=True)
            self.tombe = True
            self.ctx.calme()
            return
        if self.tombe and state.get("policy") == "stand":
            # De nouveau debout (la sequence limp_fall de robotd l'a releve) : il s'ebroue, comme un canard qui se
            # remet d'une glissade, puis reprend sa vie. Pas en mode calme (silence et immobilite d'abord).
            self.tombe = False
            print(f"[{self.t_global:6.1f}s] releve apres la chute", flush=True)
            if not self.mode_calme:
                self._bascule("ebouriffe")
        if self.tombe:
            return                              # pas encore la politique 'stand' : on attend sans rien commander
        if state.get("odom") and self.t_global - self._t_explo >= 0.5:
            self._t_explo = self.t_global
            self.exploration.noter(state["odom"]["position"][0], state["odom"]["position"][1], self.t_global)

        self._traite_evenements()
        self.humeur.avance(dt, self.courant.nom)
        self.t_etat += dt
        self.courant.pas(self, self.t_etat)
        if self.t_etat >= self.fin_etat:
            self._bascule(self._choisit_suivant())

    def arret(self):
        """Sortie propre : on se leve si on dormait, tete neutre, mouvement arrete."""
        self.courant.sort(self)
        self.ctx.calme()


def run(client, duree, humeur=None, evenements=None, seed=None, source=None, a_chaque_tick=None, extras=None):
    """`source()` : appelee a chaque trame, renvoie les noms d'evenements arrives depuis l'exterieur (pont
    Home Assistant...). `a_chaque_tick(brain, state)` : crochet facultatif (publication d'etat...)."""
    brain = Brain(client, humeur=humeur, seed=seed, extras=extras)
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
