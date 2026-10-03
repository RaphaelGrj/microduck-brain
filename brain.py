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

    def toggle_sit(self):
        self.client.request("robot.do", {"skill": "sit_toggle"})
        self.sitting = not self.sitting

    def sound(self, tag):
        """La voix du canard (robot.sound) : alarm, greet, inquire, peck, chirp, coo, wheee."""
        try:
            self.client.request("robot.sound", {"tag": tag})
        except Exception as e:      # un robot sans voix refuse : on ne bloque jamais un geste pour un son
            print(f"  (son {tag} refuse : {e})", flush=True)

    def calme(self):
        self.head((0.0, 0.0, 0.0, 0.0))
        self.move()


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


class TurnInPlace(Etat):
    nom = "turn"

    def entre(self, brain):
        self.signe = brain.rng.choice((-1.0, 1.0))

    def duree(self, brain):
        return 1.5

    def pas(self, brain, t):
        brain.ctx.move(vyaw=0.4 * self.signe)


class Wander(Etat):
    nom = "wander"

    def duree(self, brain):
        return 2.5

    def pas(self, brain, t):
        brain.ctx.move(vx=0.1)


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
        if self.recul and t <= 0.5:
            brain.ctx.move(vx=-0.1)


class Nap(Etat):
    """Affaissement de tete, assis, repos qui recharge l'energie, puis on se leve."""
    nom = "nap"

    def entre(self, brain):
        self.assis = False
        self.leve = False
        self.total = 2.0 + 4.0 + brain.rng.uniform(8.0, 14.0) + 4.0

    def duree(self, brain):
        return self.total

    def pas(self, brain, t):
        ctx = brain.ctx
        if t < 2.0:
            ctx.head(gestures.fatigue(t))
        elif not self.assis:
            ctx.toggle_sit()
            self.assis = True
        elif t >= self.total - 4.0 and not self.leve:
            ctx.toggle_sit()
            self.leve = True
            ctx.head((0, 0, 0, 0))

    def sort(self, brain):
        if brain.ctx.sitting:
            brain.ctx.toggle_sit()
        brain.ctx.calme()


class Brain:
    SEUIL_SIESTE = 0.25
    # evenement de la maison -> (etat de reaction, hausse d'eveil)
    REACTIONS_MAISON = {
        "impression_finie": ("celebre", 0.4),
        "impression_echec": ("alerte", 0.7),
        "impression_commencee": ("info", 0.1),
        "alerte": ("alerte", 0.7),
        "info": ("info", 0.2),
    }

    def __init__(self, client, humeur=None, seed=None):
        self.ctx = Ctx(client)
        self.humeur = humeur or Humeur()
        self.rng = random.Random(seed)
        self.etats = {
            "chill": Chill(), "look": LookAround(), "turn": TurnInPlace(),
            "wander": Wander(), "nap": Nap(),
            "startle": Geste("startle", "surpris", recul=True),
            "curious": Geste("curious", "curieux"),
            # reactions aux notifications de la maison (Home Assistant, voir pont_ha.py)
            "celebre": Geste("celebre", "oui", son="greet"),       # impression terminee
            "alerte": Geste("alerte", "surpris", son="alarm"),     # impression ratee, alarme
            "info": Geste("info", "curieux", son="inquire"),       # information a signaler
        }
        self.courant = self.etats["chill"]
        self.t_etat = 0.0
        self.fin_etat = self.courant.duree(self)
        self.evenements = []
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
            elif nom in ("chat", "personne"):
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("curious")

    def _choisit_suivant(self):
        h = self.humeur
        if h.energie < self.SEUIL_SIESTE:
            return "nap"
        if self.courant.nom != "chill":
            return "chill"
        poids = {"look": 0.4, "turn": 0.2 + 0.3 * h.energie,
                 "wander": 0.15 + 0.4 * h.energie * (0.5 + h.eveil)}
        noms = list(poids)
        return self.rng.choices(noms, weights=[poids[n] for n in noms])[0]

    def _bascule(self, nom):
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
        self.t_global += dt
        if state.get("safety", {}).get("fallen"):
            if not self.tombe:
                print(f"[{self.t_global:6.1f}s] CHUTE : cerveau en pause", flush=True)
            self.tombe = True
            self.ctx.calme()
            return
        self.tombe = False

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


def run(client, duree, humeur=None, evenements=None, seed=None, source=None, a_chaque_tick=None):
    """`source()` : appelee a chaque trame, renvoie les noms d'evenements arrives depuis l'exterieur (pont
    Home Assistant...). `a_chaque_tick(brain, state)` : crochet facultatif (publication d'etat...)."""
    brain = Brain(client, humeur=humeur, seed=seed)
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
