#!/usr/bin/env python3
"""Ou il est sur le plan du lieu actuel, en continu - dans un fil a part (la localisation coute ~1 ms sur PC, sans
doute ~10 ms sur le canard : jamais dans la boucle a 50 Hz du cerveau).

- Le plan est celui du lieu actuel (lieux.py) ; un autre lieu, ou un nouveau scan, et il recharge tout seul.
- Depart : sur son chargeur s'il est connu sur le plan (nuage large : il n'en est pas sur) ; un marqueur vu par la
  camera (marqueurs.py) le recale exactement ; le casque peut aussi le recaler (vérité terrain, appli Quest).
- Le cerveau lit `pose()` (None tant qu'il n'est pas sur), convertit plan <-> odometrie (`vers_odom`, `vers_plan`)
  pour reutiliser la marche existante (navigation.AllerVers, repere de l'odometrie), et demande des trajets
  (`chemin_vers`, chemins.py).

Rien ne sort du canard ; l'appli et le casque ne recoivent que des positions.
"""
import math
import threading
import time

import chemins
import localisation
import marqueurs as marqueurs_mod
import plan as plan_mod

SUR_M = 0.20                     # dispersion du nuage sous laquelle on se fie a la position


class PositionPlan(threading.Thread):
    PERIODE_S = 0.1
    MARQUEURS_S = 1.0

    def __init__(self, lieux, tof=None, grab=None, log=print):
        super().__init__(daemon=True, name="position")
        self.lieux, self.tof, self.grab, self.log = lieux, tof, grab, log
        self.verrou = threading.RLock()
        self.actif = True
        self.plan = None
        self.loc = None
        self._cle = None                          # (lieu, date du plan) charge
        self.etat = None                          # derniere trame robot.state (ecrite par le cerveau)
        self.chemin = []                          # trajet en cours (points du plan), pour l'appli et le casque
        self._t_marqueurs = 0.0
        self.dernier_marqueur = None              # (instant, id)
        self.tof_plan = []                        # derniers points du capteur, repere du plan (casque)
        self._det = None
        self.bloque_zone = False                  # lu par etats_base.Ctx.move : pas un pas vers une zone interdite
        self.chercher = set()                     # marqueurs recherches hors plan (le tresor) : camera active
        self.vus_marqueurs = {}                   # id -> instant (time.time) de la derniere vue
        self.indices = {}                         # changements du decor : case -> {n, x, y, premier, dernier}
        self.changements = []                     # [(x, y, instant)] signales (appli) ; a_signaler : pour le cerveau
        self.a_signaler = []

    # -- alimentation ---------------------------------------------------------------------------------------------
    def etat_robot_hook(self, brain, state):
        """Crochet a_chaque_tick du cerveau : la derniere trame d'etat (rien d'autre dans la boucle a 50 Hz)."""
        self.etat = state

    def _recharger(self):
        lid = self.lieux.d.get("actuel") if self.lieux is not None else None
        d = self.lieux.plan(lid) if self.lieux is not None else None
        cle = (lid, d.get("date"), len(d.get("zones") or []), len(d.get("points") or [])) if d else None
        if cle == self._cle:
            return
        meme_scan = self._cle is not None and cle is not None and self._cle[:2] == cle[:2]
        self._cle = cle
        if d is None:
            with self.verrou:
                self.plan, self.loc = None, None
            return
        try:
            pl = plan_mod.Plan.depuis_dict(d)
        except ValueError as e:
            self.log(f"position : plan illisible ({e})")
            with self.verrou:
                self.plan, self.loc = None, None
            return
        if not meme_scan:
            self.indices, self.changements, self.a_signaler = {}, [], []
        with self.verrou:
            if meme_scan and self.loc is not None:      # seules les annotations ont change : on garde le nuage
                self.loc.plan = pl
                self.plan = pl
                return
            self.plan = pl
            self.loc = localisation.Localisation(pl)
            c = pl.reperes.get("chargeur")
            if c:
                self.loc.depuis(c[0], c[1], c[2] or 0.0, ecart=0.3, ecart_cap=math.radians(30))
            else:
                self.loc.partout()
            self.log(f"position : plan « {pl.nom} » charge ({'depart au chargeur' if c else 'depart inconnu'})")

    def pas(self):
        """Une iteration (appelee par le fil ; directement dans les essais)."""
        self._recharger()
        s = self.etat
        with self.verrou:
            loc = self.loc
        if loc is None or not s or not s.get("odom"):
            return
        o = s["odom"]
        with self.verrou:
            if loc.mouvement(o["position"][0], o["position"][1], o.get("yaw") or 0.0) and self.tof is not None:
                pts = self.tof.points(s) or []
                loc.mesure(pts)
                x, y, cap, _ = loc.estimation()
                c, si = math.cos(cap), math.sin(cap)
                self.tof_plan = [(round(x + c * px - si * py, 3), round(y + si * px + c * py, 3)) for px, py, _ in pts[:64]]
                if loc.estimation()[3] <= SUR_M:
                    self._compare_au_plan(self.tof_plan)
        self._voir_marqueurs(s)
        self.bloque_zone = self._zone_devant()

    def _zone_devant(self, distance=0.3):
        """Vrai si le point a `distance` devant lui est dans une zone interdite ou il n'est pas deja (s'il y est - pose
        la a la main - il peut en sortir)."""
        p = self.pose()
        if p is None or self.plan is None or not self.plan.zones or self.plan.dans_zone_interdite(p[0], p[1]):
            return False
        return self.plan.dans_zone_interdite(p[0] + distance * math.cos(p[2]), p[1] + distance * math.sin(p[2]))

    def _voir_marqueurs(self, s):
        if self.grab is None or self.plan is None or not (self.plan.reperes.get("marqueurs") or self.chercher):
            return
        now = time.monotonic()
        if now - self._t_marqueurs < self.MARQUEURS_S or not (s.get("frames") or {}).get("camera"):
            return
        self._t_marqueurs = now
        try:
            img = self.grab()
        except Exception:
            return
        if img is None:
            return
        self._det = self._det or marqueurs_mod.detecteur()
        connus = self.plan.reperes.get("marqueurs") or {}
        for ident, x, y, cn in marqueurs_mod.detecter(img, s["frames"]["camera"], det=self._det):
            self.vus_marqueurs[ident] = time.time()
            m = connus.get(str(ident))
            if m is None:
                continue
            px, py, pc = marqueurs_mod.pose_du_canard((x, y, cn), m)
            with self.verrou:
                issue = self.loc.recaler(px, py, pc)
            self.dernier_marqueur = (time.time(), ident)
            self.log(f"position : marqueur {ident} vu -> ({px:.2f}, {py:.2f}) [{issue}]")

    # -- le decor a-t-il change ? -------------------------------------------------------------------------------------
    CASE_CHANGEMENT_M = 0.2
    INDICES_MIN = 60               # points vus la ou le plan ne connait rien...
    DUREE_MIN_S = 1800.0           # ... sur au moins 30 min (pas une jambe qui passe, pas le chat qui traverse)

    def _compare_au_plan(self, points):
        """Des points d'obstacle la ou le plan n'a rien a moins de 25 cm : un meuble deplace, un carton pose. Signale
        une fois par case, quand c'est durable."""
        pl, dist, now = self.plan, self.plan.distance(), time.time()
        for x, y in points:
            i, j = pl.case(x, y)
            if not (0 <= i < pl.hauteur and 0 <= j < pl.largeur) or pl.grille[i, j] != plan_mod.LIBRE or dist[i, j] < 0.25:
                continue
            cle = (math.floor(x / self.CASE_CHANGEMENT_M), math.floor(y / self.CASE_CHANGEMENT_M))
            e = self.indices.setdefault(cle, {"n": 0, "x": x, "y": y, "premier": now, "dernier": now, "signale": False})
            e["n"] += 1
            e["dernier"] = now
            if not e["signale"] and e["n"] >= self.INDICES_MIN and e["dernier"] - e["premier"] >= self.DUREE_MIN_S:
                e["signale"] = True
                self.changements = (self.changements + [(round(x, 2), round(y, 2), round(now))])[-10:]
                self.a_signaler.append((x, y))
                self.log(f"position : quelque chose a change en ({x:.2f}, {y:.2f}) (pas sur le plan)")

    def run(self):
        while self.actif:
            try:
                self.pas()
            except Exception as e:                       # jamais d'arret du canard pour un calcul rate
                self.log(f"position : {type(e).__name__}: {e}")
            time.sleep(self.PERIODE_S)

    # -- lecture (cerveau, appli, casque) ---------------------------------------------------------------------------
    def estimation(self):
        with self.verrou:
            return None if self.loc is None else self.loc.estimation()

    def pose(self):
        """(x, y, cap) sur le plan si la position est sure, sinon None."""
        e = self.estimation()
        return None if e is None or e[3] > SUR_M else e[:3]

    def _transformation(self):
        """(dcap, tx, ty) tel que plan = R(dcap) . odom + t, d'apres la derniere trame ; None si inconnu."""
        p, s = self.pose(), self.etat
        if p is None or not s or not s.get("odom"):
            return None
        o = s["odom"]
        dcap = p[2] - (o.get("yaw") or 0.0)
        c, si = math.cos(dcap), math.sin(dcap)
        return dcap, p[0] - (c * o["position"][0] - si * o["position"][1]), p[1] - (si * o["position"][0] + c * o["position"][1])

    def vers_odom(self, x, y):
        t = self._transformation()
        if t is None:
            return None
        dcap, tx, ty = t
        c, si = math.cos(-dcap), math.sin(-dcap)
        return c * (x - tx) - si * (y - ty), si * (x - tx) + c * (y - ty)

    def vers_plan(self, x, y):
        t = self._transformation()
        if t is None:
            return None
        dcap, tx, ty = t
        c, si = math.cos(dcap), math.sin(dcap)
        return c * x - si * y + tx, si * x + c * y + ty

    def piece(self):
        p = self.pose()
        return None if p is None or self.plan is None else self.plan.piece_de(p[0], p[1])

    def chemin_vers(self, x, y):
        """Trajet (points du plan) de sa position a (x, y), ou None (position incertaine, pas de passage)."""
        p = self.pose()
        if p is None or self.plan is None:
            return None
        return chemins.chemin(self.plan, p[:2], (x, y))

    def recaler(self, x, y, cap):
        with self.verrou:
            return None if self.loc is None else self.loc.recaler(x, y, cap)

    def resume(self, particules=80):
        """Pour l'appli et le casque : position, dispersion, un echantillon du nuage, le capteur, le trajet."""
        with self.verrou:
            if self.loc is None:
                return {"plan": False}
            x, y, cap, ecart = self.loc.estimation()
            idx = self.loc.rng.choice(self.loc.n, min(particules, self.loc.n), replace=False, p=self.loc.w)
            nuage = [[round(float(a), 3), round(float(b), 3)] for a, b in self.loc.p[idx, :2]]
        return {"plan": True, "lieu": (self._cle or [None])[0], "x": round(x, 3), "y": round(y, 3), "cap": round(cap, 3),
                "ecart": round(ecart, 3), "sur": ecart <= SUR_M, "nuage": nuage, "tof": list(self.tof_plan),
                "chemin": [[round(a, 3), round(b, 3)] for a, b in self.chemin], "piece": self.piece(),
                "marqueur": self.dernier_marqueur, "changements": list(self.changements)}
