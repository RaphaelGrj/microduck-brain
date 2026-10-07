#!/usr/bin/env python3
"""Se deplacer sur le PLAN de la maison (plan.py, position.py, chemins.py) : aller a un point en contournant les
meubles, rentrer a sa station de charge, faire la ronde du soir.

La marche reste celle de navigation.AllerVers (repere de l'odometrie : pivote puis marche, au-dessus de la zone
morte) : chaque point de passage du plan est converti dans le repere de l'odometrie avec la position du moment, et
reconverti regulierement (la localisation corrige la derive en marchant). Securite inchangee : le capteur de
distance doit voir de la place devant, sinon il s'arrete ; une zone interdite bloque toute marche vers elle
(etats_base.Ctx.move).
"""
import json
import math
import threading

from etats_base import TETE_PROMENADE, V_ROTATION, Etat
from navigation import AllerVers


class Trajet:
    """Suivi d'un trajet du plan, trame par trame. `commande(brain, t)` -> (statut, vx, vyaw) avec statut "avance",
    "arrive" ou "echec:<raison>"."""
    RECONVERSION_S = 1.0
    BLOQUE_S = 1.5
    PERDU_S = 3.0

    def __init__(self, position, cible):
        self.position, self.cible = position, cible
        self.points = position.chemin_vers(*cible) if position is not None else None
        self.i = 0
        self.aller, self.t_conv, self.bloque_depuis, self.perdu_depuis, self.replan = None, -1e9, None, None, False
        if position is not None:
            position.chemin = list(self.points or [])

    def commande(self, brain, t):
        if self.points is None:
            return "echec:pas de chemin", 0.0, 0.0
        s = brain.ctx.state or {}
        o = s.get("odom")
        if o is None:
            return "avance", 0.0, 0.0
        if self.position.pose() is None:
            self.perdu_depuis = t if self.perdu_depuis is None else self.perdu_depuis
            if t - self.perdu_depuis >= self.PERDU_S:
                return "echec:perdu", 0.0, 0.0
            return "avance", 0.0, 0.0                    # il attend que la position redevienne sure
        self.perdu_depuis = None
        if self.aller is None or t - self.t_conv >= self.RECONVERSION_S:
            cible_odom = self.position.vers_odom(*self.points[self.i])
            if cible_odom is None:
                return "avance", 0.0, 0.0
            garde = self.aller
            self.aller = AllerVers(cible_odom)
            if garde is not None:                        # garde l'hysteresis pivot / marche en cours
                self.aller.marche, self.aller.pivot = garde.marche, garde.pivot
            self.t_conv = t
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(s) if tof is not None else None
        statut, vx, vyaw = self.aller.commande(o["position"][0], o["position"][1], o.get("yaw") or 0.0, lib)
        if statut == "arrive":
            self.i += 1
            self.aller = None
            if self.i >= len(self.points):
                self.position.chemin = []
                return "arrive", 0.0, 0.0
            return "avance", 0.0, 0.0
        if statut == "bloque":
            # pas encore bien aligne sur le point suivant (moins de 25 degres : AllerVers ne pivote pas) : c'est souvent
            # l'angle du meuble qu'il vient de longer qui bouche la vue - il finit de pivoter avant de juger
            cx, cy = self.aller.cible
            ecart = math.remainder(math.atan2(cy - o["position"][1], cx - o["position"][0]) - (o.get("yaw") or 0.0),
                                   2 * math.pi)
            if abs(ecart) > math.radians(8):
                return "avance", 0.0, math.copysign(V_ROTATION, ecart)
            # l'obstacle est AU-DELA du point vise (un mur derriere la station, au fond d'un coin) : il y va quand meme
            reste = math.hypot(cx - o["position"][0], cy - o["position"][1])
            if lib is not None and lib["devant"] > reste + 0.1 and lib.get("vide", math.inf) > reste + 0.1:
                self.bloque_depuis = None
                return "avance", 0.3, 0.0
            self.bloque_depuis = t if self.bloque_depuis is None else self.bloque_depuis
            if t - self.bloque_depuis >= self.BLOQUE_S:
                if self.replan:
                    return "echec:bloque", 0.0, 0.0
                self.replan, self.bloque_depuis = True, None      # un nouveau trajet, une fois
                self.points, self.i, self.aller = self.position.chemin_vers(*self.cible), 0, None
                self.position.chemin = list(self.points or [])
            return "avance", 0.0, 0.0
        self.bloque_depuis = None
        return "avance", vx, vyaw


class VaSurPlan(Etat):
    """Va a `cible` (point du plan) en contournant les meubles, puis `ensuite` ; en cas d'echec (pas de chemin,
    position perdue, bloque deux fois) : `si_echec`."""
    DUREE_MAX = 150.0

    def __init__(self, nom, ensuite, motif, si_echec="chill"):
        self.nom, self.ensuite, self.motif, self.si_echec = nom, ensuite, motif, si_echec
        self.cible = None

    def entre(self, brain):
        self.trajet = Trajet(brain.ctx.extras.get("position"), self.cible)
        self.issue = None
        print(f"[{brain.t_global:6.1f}s] va {self.motif} (plan : {self.cible[0]:.2f}, {self.cible[1]:.2f})", flush=True)

    def duree(self, brain):
        return self.DUREE_MAX

    def pas(self, brain, t):
        brain.ctx.head((0.0, 0.0 if self.trajet.aller is not None and self.trajet.aller.pivot else TETE_PROMENADE, 0.0, 0.0))
        statut, vx, vyaw = self.trajet.commande(brain, t)
        brain.ctx.move(vx=vx, vyaw=vyaw)
        if statut == "avance":
            return
        self.issue = statut
        brain.suivant_force = self.ensuite if statut == "arrive" else self.si_echec
        brain.fin_etat = t
        if statut != "arrive":
            print(f"[{brain.t_global:6.1f}s] {self.motif} : abandon ({statut[6:]})", flush=True)

    def sort(self, brain):
        p = brain.ctx.extras.get("position")
        if p is not None:
            p.chemin = []
        brain.ctx.calme()


# -- la station de charge ---------------------------------------------------------------------------------------------
APPROCHE_M = 0.35                # point d'approche : devant la station, dans l'axe


def point_approche(chargeur):
    """Devant la station (dans la direction ou regarde le canard pose dessus), a APPROCHE_M."""
    x, y, cap = chargeur[0], chargeur[1], chargeur[2] or 0.0
    return x + APPROCHE_M * math.cos(cap), y + APPROCHE_M * math.sin(cap)


class Accoste(Etat):
    """Dernier metre jusqu'a la station : face a elle, quelques pas pour monter dessus, demi-tour, assis (recharge).
    Le geste exact depend de la vraie station (Pollen) : a regler a la livraison (ACCOSTAGE)."""
    nom = "accoste"
    ACCOSTAGE = {"monte_s": 1.2, "demi_tour": True}
    TOLERANCE = math.radians(10)

    def entre(self, brain):
        self.phase, self.t0 = "vise", 0.0
        pos = brain.ctx.extras.get("position")
        c = pos.plan.reperes.get("chargeur") if pos is not None and pos.plan is not None else None
        self.vers_station = (c[2] or 0.0) + math.pi if c else None

    def duree(self, brain):
        return 20.0

    def pas(self, brain, t):
        pos = brain.ctx.extras.get("position")
        p = pos.pose() if pos is not None else None
        dt = t - self.t0
        if self.vers_station is None:
            brain.fin_etat = t
            return
        if self.phase == "vise":
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            if p is None:
                brain.ctx.move()
                if dt > 4.0:
                    brain.fin_etat = t                    # perdu : il n'insiste pas
                return
            ecart = math.remainder(self.vers_station - p[2], 2 * math.pi)
            if abs(ecart) <= self.TOLERANCE:
                self.phase, self.t0 = "monte", t
                brain.ctx.move()
            else:
                brain.ctx.move(vyaw=math.copysign(V_ROTATION, ecart))
        elif self.phase == "monte":
            brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
            if dt < self.ACCOSTAGE["monte_s"]:
                brain.ctx.move(vx=0.3)                    # (au-dessus de la zone morte de la marche)
            else:
                brain.ctx.move()
                self.phase, self.t0 = ("demi_tour" if self.ACCOSTAGE["demi_tour"] else "assis"), t
        elif self.phase == "demi_tour":
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            if dt < math.pi / V_ROTATION:
                brain.ctx.move(vyaw=V_ROTATION)
            else:
                brain.ctx.move()
                self.phase, self.t0 = "assis", t
        else:
            brain.ctx.move()
            brain.ctx.sound("coo")
            brain.suivant_force = "nap"                   # assis sur sa station : il recharge en dormant
            brain.fin_etat = t


# -- la ronde du soir ---------------------------------------------------------------------------------------------------
def centre(contour):
    xs, ys = [p[0] for p in contour], [p[1] for p in contour]
    return sum(xs) / len(xs), sum(ys) / len(ys)


class Ronde(Etat):
    """Ronde du soir (mode garde) : il passe dans chaque piece du plan, y regarde autour de lui et mesure la lumiere ;
    a la fin, le releve part dans Home Assistant (evenement « microduck_ronde ») et il rentre a sa station."""
    nom = "ronde"
    REGARDE_S = 5.0

    def entre(self, brain):
        pos = brain.ctx.extras.get("position")
        pl = pos.plan if pos is not None else None
        self.pieces = [(p.get("nom") or f"piece {k + 1}", centre(p["contour"])) for k, p in enumerate(pl.pieces if pl else [])
                       if len(p.get("contour") or []) >= 3]
        self.releve, self.k, self.trajet, self.t0, self.lumiere = {}, 0, None, 0.0, None
        self.phase = "va" if self.pieces else "fin"
        print(f"[{brain.t_global:6.1f}s] ronde : {len(self.pieces)} pieces", flush=True)

    def duree(self, brain):
        return 120.0 * max(1, len(self.pieces)) + 10.0

    def _mesure(self, brain):
        mesure = brain.ctx.extras.get("luminosite")
        if mesure is None:
            return
        cible = self

        def lire():
            try:
                cible.lumiere = round(float(mesure()), 2)
            except Exception:
                cible.lumiere = None
        if brain.ctx.extras.get("luminosite_synchrone"):
            lire()
        else:
            threading.Thread(target=lire, daemon=True).start()

    def pas(self, brain, t):
        if self.phase == "va":
            if self.trajet is None:
                self.trajet = Trajet(brain.ctx.extras.get("position"), self.pieces[self.k][1])
            brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
            statut, vx, vyaw = self.trajet.commande(brain, t)
            brain.ctx.move(vx=vx, vyaw=vyaw)
            if statut == "arrive" or statut.startswith("echec"):
                brain.ctx.move()
                self.phase, self.t0, self.lumiere = "regarde", t, None
                self.atteint = statut == "arrive"
                if self.atteint:
                    self._mesure(brain)
        elif self.phase == "regarde":
            dt = t - self.t0
            brain.ctx.move()
            brain.ctx.head((0.0, 0.0, 0.7 * math.sin(2 * math.pi * dt / self.REGARDE_S), 0.0))
            if dt >= self.REGARDE_S:
                nom = self.pieces[self.k][0]
                self.releve[nom] = {"vu": self.atteint, "lumiere": self.lumiere}
                self.k += 1
                self.trajet = None
                self.phase = "va" if self.k < len(self.pieces) else "fin"
        else:
            brain.ctx.move()
            if self.pieces:
                brain._previent("ronde:" + json.dumps(self.releve, ensure_ascii=False))
                brain.dernier_releve_ronde = self.releve
            station = brain._station_cible()
            if station is not None:
                brain.etats["va_station"].cible = station
            brain.suivant_force = "va_station" if station is not None else "chill"
            brain.fin_etat = t

    def sort(self, brain):
        p = brain.ctx.extras.get("position")
        if p is not None:
            p.chemin = []
        brain.ctx.calme()
