#!/usr/bin/env python3
"""Le canard sur le plan de la maison : trajets qui contournent les meubles, zones interdites, station de charge,
ronde du soir, piece ou l'on est (HA), routes de l'appli pour le casque (position, verite terrain, « va la »,
annotations, vue camera en opt-in). Petite simulation : le canard bouge selon ses propres commandes robot.move."""
import json
import math

import pytest

import chemins
import plan as P
import plan_quest
import position as position_mod
from brain import Brain, Humeur
from test_brain import FauxClient, FauxHorloge
from test_plan import export_piece


def plan_maison():
    p, _ = plan_quest.convertir(export_piece(), "Maison")
    p.pieces = [{"nom": "Salon", "contour": [[0.0, 0.25], [1.6, 0.25], [1.6, -1.8], [0.0, -1.8]]},
                {"nom": "Fond", "contour": [[1.6, 0.25], [2.65, 0.25], [2.65, -3.65], [1.6, -3.65]]}]
    return p


class Simu:
    """Position « parfaite » (odometrie = repere du plan) + capteur de distance lu sur le plan."""

    def __init__(self, plan, x=0.4, y=-0.3, cap=0.0):
        self.plan, self.x, self.y, self.cap = plan, x, y, cap
        self.chemin, self.bloque_zone, self._cle = [], False, ("l1", 0)
        self.dans_obstacle = 0

    # interface de position.PositionPlan utilisee par le cerveau
    def pose(self):
        return self.x, self.y, self.cap

    def estimation(self):
        return self.x, self.y, self.cap, 0.03

    def vers_odom(self, x, y):
        return x, y

    def vers_plan(self, x, y):
        return x, y

    def piece(self):
        return self.plan.piece_de(self.x, self.y)

    def chemin_vers(self, x, y):
        return chemins.chemin(self.plan, (self.x, self.y), (x, y))

    def recaler(self, x, y, cap):
        self.x, self.y, self.cap = x, y, cap
        return "reparti"

    def resume(self):
        return {"plan": True, "x": self.x, "y": self.y, "cap": self.cap, "ecart": 0.03, "sur": True, "nuage": [],
                "tof": [], "chemin": self.chemin, "piece": self.piece()}

    # capteur de distance (tof.Tof.libre) d'apres le plan
    def libre(self, s):
        devant = min(self.plan.rayon(self.x + 0.08 * math.cos(self.cap), self.y + 0.08 * math.sin(self.cap), self.cap + a, 2.0)
                     for a in (-0.15, 0.0, 0.15))
        return {"devant": devant, "gauche": 3.0, "droite": 3.0, "vide": math.inf, "n": 10}

    def points(self, s):
        return []

    def noter_etat(self, s):
        pass

    def avance(self, client, dt=0.02):
        mv = next((p for m, p in reversed(client.appels[-12:]) if m == "robot.move"), None)
        if mv:
            self.cap += mv["vyaw"] * dt
            self.x += mv["vx"] * dt * math.cos(self.cap)
            self.y += mv["vx"] * dt * math.sin(self.cap)
            if self.plan.valeur(self.x, self.y) == P.OBSTACLE:
                self.dans_obstacle += 1
        self.bloque_zone = position_mod.PositionPlan._zone_devant(self) if self.plan.zones else False


def cerveau(simu, heure=14, **extras):
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.8), seed=4, horloge=FauxHorloge(heure),
              extras={"exploration": False, "position": simu, "tof": simu, **extras})
    return b, c


def vivre(b, c, simu, secondes, evenements=None):
    evenements = sorted(evenements or [])
    for i in range(int(secondes / 0.02)):
        t = i * 0.02
        while evenements and evenements[0][0] <= t:
            b.evenement(evenements.pop(0)[1])
        b.tick({"t": b.t_global + 0.02, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [simu.x, simu.y, 0.11], "yaw": simu.cap}}, 0.02)
        simu.avance(c)


def test_va_la_en_contournant_le_canape():
    pl = plan_maison()
    simu = Simu(pl, 0.4, -0.3, 0.0)
    cible = (2.2, -3.15)                                  # de l'autre cote du canape (plan x 1,8..2,6, y -0,8..-2,6)
    assert pl.valeur(2.2, -1.7) == P.OBSTACLE
    b, c = cerveau(simu)
    vivre(b, c, simu, 90, evenements=[(0.1, f"aller:{cible[0]}|{cible[1]}")])
    assert "va_point" in [e[1] for e in b.journal]
    assert math.hypot(simu.x - cible[0], simu.y - cible[1]) < 0.35, (simu.x, simu.y)
    assert simu.dans_obstacle == 0, "jamais dans un meuble"


def test_zone_interdite_jamais_franchie():
    pl = plan_maison().annoter(zones=[{"nom": "litière", "contour": [[1.0, -0.6], [1.6, -0.6], [1.6, 0.2], [1.0, 0.2]]}])
    simu = Simu(pl, 0.4, -0.2, 0.0)
    simu.avance(FauxClient())
    assert not simu.bloque_zone
    simu.x = 0.75
    simu.avance(FauxClient())
    assert simu.bloque_zone, "30 cm devant : la litiere"
    b, c = cerveau(simu)
    b.ctx.move(vx=0.4, vyaw=0.5)
    assert c.appels[-1] == ("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.5}), "il tourne, mais n'avance pas"
    # et un trajet la contourne
    pts = chemins.chemin(pl, (0.4, -0.2), (2.2, -0.2))
    assert pts and not any(pl.dans_zone_interdite(x, y) for x, y in pts)
    simu.x = 1.3                                          # pose dans la zone a la main : il peut en sortir
    simu.avance(FauxClient())
    assert not simu.bloque_zone


def test_rentre_a_sa_station_quand_la_batterie_baisse():
    pl = plan_maison()
    simu = Simu(pl, 2.0, -3.0, math.pi / 2)
    b, c = cerveau(simu)
    b._batterie_pct = 15
    b.fin_etat = 0.0
    vivre(b, c, simu, 70)
    noms = [e[1] for e in b.journal]
    assert "va_station" in noms and "accoste" in noms and noms[noms.index("accoste") + 1] == "nap", noms
    assert math.hypot(simu.x, simu.y) < 0.5, "sur (ou tout contre) sa station"


def test_ronde_du_soir():
    pl = plan_maison()
    simu = Simu(pl, 0.4, -0.3, 0.0)
    vu = []
    b, c = cerveau(simu, heure=22, garde=True, ronde=(22, 0), luminosite=lambda: 0.6, luminosite_synchrone=True)
    b.ecouteurs.append(vu.append)
    b.etats["chill"].duree = lambda brain: 0.5
    b.fin_etat = 0.0
    vivre(b, c, simu, 120)
    rondes = [json.loads(v[6:]) for v in vu if v.startswith("ronde:")]
    assert rondes and set(rondes[0]) == {"Salon", "Fond"} and rondes[0]["Salon"]["lumiere"] == 0.6
    assert "va_station" in [e[1] for e in b.journal], "puis il rentre"
    n = len(vu)
    vivre(b, c, simu, 20)
    assert not [v for v in vu[n:] if v.startswith("ronde:")], "une fois par soir"


def test_va_dans_la_piece_ou_l_on_est():
    pl = plan_maison()
    simu = Simu(pl, 0.4, -0.3, 0.0)
    b, c = cerveau(simu)
    b.evenement("presence_piece:Fond|on")
    vivre(b, c, simu, 0.1)
    assert b._piece_a_rejoindre() is not None and simu.piece() == "Salon"
    b.evenement("presence_piece:Fond|off")
    vivre(b, c, simu, 0.1)
    assert b._piece_a_rejoindre() is None


def test_position_suit_le_plan_du_lieu(tmp_path):
    import lieux
    li = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)
    pos = position_mod.PositionPlan(li, log=lambda m: None)
    pos.pas()
    assert pos.plan is None and pos.pose() is None
    li.importer_plan(li.d["actuel"], export_piece())
    pos.etat = {"odom": {"position": [5.0, 1.0, 0.11], "yaw": 0.3}}
    pos.pas()
    assert pos.plan is not None and pos.estimation() is not None
    pos.recaler(0.5, -0.4, 0.2)
    pos.loc.depuis(0.5, -0.4, 0.2, ecart=0.01, ecart_cap=0.01)
    assert pos.pose() is not None
    ox, oy = pos.vers_odom(0.5, -0.4)
    assert ox == pytest.approx(5.0, abs=0.05) and oy == pytest.approx(1.0, abs=0.05)
    px, py = pos.vers_plan(5.0, 1.0)
    assert px == pytest.approx(0.5, abs=0.05) and py == pytest.approx(-0.4, abs=0.05)
    li.annoter(None, zones=[{"nom": "x", "contour": [[2, -1], [2.5, -1], [2.5, -2]]}])
    pos.pas()
    assert pos.plan.zones and pos.pose() is not None, "nouvelle zone : meme nuage, pas de redemarrage"
    r = pos.resume()
    assert r["plan"] and r["sur"] and r["piece"] == "Salon"


def test_routes_du_casque(tmp_path):
    import appli
    import lieux
    from test_appli import CODE, requete
    a = appli.Appli(CODE, port=0, log=lambda m: None)
    a.lieux = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)
    a.lieux.importer_plan(a.lieux.d["actuel"], export_piece())
    simu = Simu(plan_maison(), 0.6, -0.5, 0.0)
    a.position = simu
    a.demarrer()
    try:
        x = json.loads(requete(a.port, "/api/xr")[1])
        assert x["sur"] and x["piece"] == "Salon"
        r = json.loads(requete(a.port, "/api/verite", corps={"x": 0.9, "y": -0.5, "cap": 0.0})[1])
        assert r["erreur_m"] == pytest.approx(0.3, abs=0.01) and "recale" not in r
        r = json.loads(requete(a.port, "/api/verite", corps={"x": 0.9, "y": -0.5, "cap": 0.1, "recaler": True})[1])
        assert r["recale"] == "reparti" and simu.x == 0.9
        assert requete(a.port, "/api/verite", corps={"x": "loin"})[0] == 400
        assert requete(a.port, "/api/aller", corps={"x": 1.0, "y": -1.0})[0] == 200
        assert "aller:1.000|-1.000" in a.source()
        z = {"zones": [{"nom": "litière", "contour": [[1, -0.6], [1.6, -0.6], [1.6, 0.2]]}], "points": {"panier": [0.3, -1.2]}}
        r = json.loads(requete(a.port, "/api/plan-annoter", corps=z)[1])
        assert r["plan"]["zones"] == 1 and r["plan"]["points"] == 1
        p = json.loads(requete(a.port, "/api/plan")[1])
        assert p["points"]["panier"] == [0.3, -1.2] and p["zones"][0]["nom"] == "litière"
        # rescanner garde les annotations
        a.lieux.importer_plan(a.lieux.d["actuel"], export_piece())
        assert json.loads(requete(a.port, "/api/plan")[1])["points"] == {"panier": [0.3, -1.2]}
        assert requete(a.port, "/api/vue")[0] == 403, "pas de photos permises : pas d'image"
        assert requete(a.port, "/api/commande", corps={"commande": "ronde"})[0] == 200
    finally:
        a.arreter()


def test_ha_presence_par_piece_et_ronde():
    import pont_ha
    cfg = pont_ha.normaliser({"home_assistant": {"url": "http://ha.local:8123", "token": "x"},
                                 "piece": [{"nom": "Salon", "entite": "binary_sensor.presence_salon"}]}) \
        if hasattr(pont_ha, "normaliser") else None
    if cfg is None:
        pytest.skip("lecture de configuration HA sous un autre nom")
    s = next(s for s in cfg["surveillance"] if s["entite"] == "binary_sensor.presence_salon")
    assert s["reactions"] == {"on": "presence_piece:Salon|on", "off": "presence_piece:Salon|off"}
    # de bout en bout : un vrai changement d'etat HA -> l'evenement exact (sans « :nom » ajoute)
    p = pont_ha.PontHA(cfg, "x", log=lambda m: None)
    p._sur_changement("binary_sensor.presence_salon", "off", "on")
    assert p.source() == ["presence_piece:Salon|on"]


# == plan II ==============================================================================================================
import time

import plan_vie
from memoire import Memoire


class SimuPlus(Simu):
    """+ ce que position.PositionPlan expose en plus : marqueurs recherches et vus, changements du decor."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.chercher, self.vus_marqueurs, self.a_signaler, self.changements = set(), {}, [], []


def test_chasse_au_tresor():
    pl = plan_maison()
    simu = SimuPlus(pl, 0.4, -0.3, 0.0)
    b, c = cerveau(simu)
    vivre(b, c, simu, 1, evenements=[(0.1, "commande:tresor")])
    assert b.courant.nom == "tresor" and 9 in simu.chercher, "sa camera cherche le marqueur n 9"
    vivre(b, c, simu, 12)
    simu.vus_marqueurs[9] = time.time()                    # le voila !
    n = len(c.appels)
    vivre(b, c, simu, 6)
    assert "wheee" in [p["tag"] for m, p in c.appels[n:] if m == "robot.sound"] and 9 not in simu.chercher


def test_cachette_invisible_et_contre_un_meuble():
    import numpy as np
    pl = plan_maison()
    depart = (0.4, -0.3)
    x, y = plan_vie.cachette(pl, depart, np.random.default_rng(1))
    assert not plan_vie.visible(pl, depart, (x, y)) and pl.distance()[pl.case(x, y)] <= 0.35
    simu = SimuPlus(pl, *depart)
    b, c = cerveau(simu)
    b._prepare_cache_cache()
    assert b.etats["cache_cache"].cible_plan is not None
    vivre(b, c, simu, 30, evenements=[(0.1, "jeu_cache")])
    assert math.hypot(simu.x - b.etats["cache_cache"].cible_plan[0], simu.y - b.etats["cache_cache"].cible_plan[1]) < 0.5


def test_va_chercher_sa_balle():
    from test_jeu_balle import FausseApproche
    pl = plan_maison()
    simu = SimuPlus(pl, 0.4, -0.3, 0.0)
    b, c = cerveau(simu, fabrique_approche=FausseApproche)
    b.balle_plan = ("l1", 1.2, -3.2, time.time())
    vivre(b, c, simu, 40, evenements=[(0.1, "commande:cherche_balle")])
    noms = [e[1] for e in b.journal]
    assert "va_balle" in noms and "balle" in noms, noms
    assert math.hypot(simu.x - 1.2, simu.y + 3.2) < 0.8


def test_va_t_attendre_a_la_porte_quand_tu_approches():
    pl = plan_maison()
    simu = SimuPlus(pl, 2.0, -3.0, 0.0)
    b, c = cerveau(simu)
    vivre(b, c, simu, 40, evenements=[(0.1, "arrivee_proche:Raphael")])
    noms = [e[1] for e in b.journal]
    assert "va_entree" in noms and "attend_porte" in noms, noms
    assert math.hypot(simu.x - 1.2, simu.y - 0.1) < 0.4, "a la vraie porte d'entree"


def test_recharge_avant_ton_retour(tmp_path):
    pl = plan_maison()
    simu = SimuPlus(pl, 2.0, -3.0, 0.0)
    mem = Memoire(tmp_path / "m.json")
    mem.donnees["retours"] = {"Raphael": [[0, 18 * 60 + 30]] * 6}      # rentre vers 18 h 30 en semaine
    b, c = cerveau(simu, heure=18, memoire=mem)
    b.horloge = FauxHorloge(18, 0, semaine=2)
    b._batterie_pct = 40
    assert b._recharge_avant() == "va_station" and b.recharge_jusqua > b.t_global
    b._bascule("va_station")
    vivre(b, c, simu, 80)
    noms = [e[1] for e in b.journal]
    assert noms.count("nap") >= 2 or (noms[-1] == "nap" and "accoste" in noms), noms


def test_va_voir_l_impression():
    pl = plan_maison().annoter(points={"imprimante": [2.2, -3.2]})
    simu = SimuPlus(pl, 0.4, -0.3, 0.0)
    b, c = cerveau(simu)
    vivre(b, c, simu, 50, evenements=[(0.1, "impression_finie:MK4S")])
    noms = [e[1] for e in b.journal]
    assert "va_imprimante" in noms and "regarde_impression" in noms, noms
    import photos
    assert photos.MOTIFS.get("etat:regarde_impression") == "impression", "la photo (opt-in) se prend devant l'imprimante"


def test_guide_vocal():
    from test_commandes import FauxVosk
    import commandes as cmd
    com = cmd.Commandes(lambda g: FauxVosk(g), nom="daffy", lieux=plan_vie.noms(plan_maison().vers_dict()))
    assert com.comprendre({"text": "daffy emmene moi au fond"}) == ["emmene:fond"]
    pl = plan_maison()
    simu = SimuPlus(pl, 0.4, -0.3, 0.0)
    b, c = cerveau(simu)
    vivre(b, c, simu, 40, evenements=[(0.1, "emmene:fond")])
    assert "guide" in [e[1] for e in b.journal] and simu.piece() == "Fond"
    assert "chirp" in [p["tag"] for m, p in c.appels if m == "robot.sound"]
    vivre(b, c, simu, 1, evenements=[(0.1, "emmene:grenier")])
    assert "hesite" in [e[1] for e in b.journal], "un lieu inconnu : il hesite"


def test_sa_place_selon_l_heure(tmp_path):
    lh = plan_vie.LieuxHeure({})
    for _ in range(130):
        lh.noter("l1", 9, 2.2, -3.1, 5.0)
    lh.noter("l1", 9, 0.4, -0.3, 60.0)
    assert lh.favori("l1", 9) == pytest.approx((2.25, -3.25)) and lh.favori("l1", 20) is None
    pl = plan_maison()
    simu = SimuPlus(pl, 0.4, -0.3, 0.0)
    b, c = cerveau(simu, heure=9, memoire=Memoire(tmp_path / "m.json"))
    b.lieux_heure = lh
    b._rng_vie.random = lambda: 0.0
    assert b._habitude_du_moment() == "va_habitude"


def test_soleil_appris_par_fenetre():
    pl = plan_maison()
    pl.objets.append({"type": "window_frame", "nom": "fenêtre", "centre": [1.5, -3.65], "contour": [[1.0, -3.65], [2.0, -3.65]]})
    d = {}
    for jour in range(3):
        assert plan_vie.noter_soleil(d, "l1", pl, 1.5, -3.0, 10 * 60 + 5 * jour) is not None
    assert plan_vie.fenetre_au_soleil(d, "l1", pl, 10 * 60 + 20) is not None
    assert plan_vie.fenetre_au_soleil(d, "l1", pl, 15 * 60) is None, "pas a 15 h"
    x, y = plan_vie.devant_la_fenetre(pl, pl.objets[-1])
    assert y > -3.65 and pl.libre(x, y)


def test_le_decor_a_change(tmp_path):
    import lieux
    li = lieux.Lieux(tmp_path / "lieux.json", log=lambda m: None)
    li.importer_plan(li.d["actuel"], export_piece())
    pos = position_mod.PositionPlan(li, log=lambda m: None)
    pos.pas()
    t = [1000.0]
    reel = time.time
    try:
        time.time = lambda: t[0]
        for k in range(70):                                 # un carton, la ou le plan ne connait rien, pendant 35 min
            t[0] += 30.0
            pos._compare_au_plan([(1.2, -2.5)])
    finally:
        time.time = reel
    assert pos.a_signaler and pos.changements and abs(pos.changements[0][0] - 1.2) < 0.11
    pos.indices.clear()
    pos._compare_au_plan([(0.0, 0.29)] * 100)              # contre le mur : connu du plan, rien a signaler
    assert len(pos.changements) == 1
    simu = SimuPlus(plan_maison(), 0.4, -0.3, 0.0)
    simu.a_signaler.append((1.6, -1.2))
    b, c = cerveau(simu)
    vivre(b, c, simu, 15)
    assert "va_changement" in [e[1] for e in b.journal] and "inspecte" in [e[1] for e in b.journal]
