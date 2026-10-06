#!/usr/bin/env python3
"""Banc de VALIDATION GROUPEE dans duck-sim : tout ce qui a ete code sans simulateur (sessions cloud des 2026-10-05/06)
et qui touche a la securite ou au mouvement, joue pour de vrai et mesure avec la verite terrain du fork.

La verite terrain (truth.py) sert uniquement a MESURER ; le cerveau decide avec ses capteurs, comme sur le robot.

Usage (WSL, duck-sim lance avec DUCK_SIM_GROUNDTRUTH, DUCK_SIM_CONTROL et la camera) :
    bash ~/run-brain.sh valider_sim.py                     # tous les scenarios de la scene chargee
    bash ~/run-brain.sh valider_sim.py promenade jeu_balle # seulement ceux-la
    bash ~/run-brain.sh valider_sim.py --scenes-auto       # change de scene tout seul (bash ~/run-scene.sh)
    bash ~/run-brain.sh valider_sim.py --liste
Resultats : tableau a l'ecran + ~/.cache/duck-sim/validation.json (un enregistrement par scenario).
"""
import contextlib
import io
import json
import math
import subprocess
import sys
import time
from pathlib import Path

SORTIE = Path.home() / ".cache/duck-sim/validation.json"
SCENARIOS = {}                   # nom -> (scene, fonction, description)


def scenario(nom, scene, description):
    def deco(f):
        SCENARIOS[nom] = (scene, f, description)
        return f
    return deco


# --- outils ----------------------------------------------------------------------------------------------------------
class Banc:
    """Connexion au robot simule, capteurs, et une boucle de vie du cerveau qui enregistre tout ce qu'il faut mesurer."""

    def __init__(self):
        import tof as tofmod
        from poc_robotd_client import RobotdClient, SOCK_PATH
        self.c = RobotdClient(SOCK_PATH)
        self.tof = tofmod.Tof(tofmod.beams_du_robot(self.c))
        self.c.request("robot.subscribe", {})
        self.tof.start()

    def cerveau(self, energie=0.9, eveil=0.3, seed=1, **extras):
        import brain
        ex = {"tof": self.tof, "exploration": True}
        ex.update(extras)
        return brain.Brain(self.c, brain.Humeur(energie=energie, eveil=eveil), seed=seed, extras=ex)

    def tenir(self, secs):
        """Canard immobile, tete au neutre (le temps qu'un teleport se pose)."""
        t0 = time.monotonic()
        s = None
        while time.monotonic() - t0 < secs:
            s = self.c.read_state_frame()
            self.c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
            self.c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
        return s

    def vivre(self, b, secondes, chaque_tick=None, periode_mesure=0.25):
        """Fait vivre le cerveau `secondes` ; renvoie les mesures : chutes, trajectoire verite terrain, etats."""
        import truth
        mesures = {"chutes": 0, "traj": [], "etats": {}}
        t0, t_prec, dernier_t, tombe = time.monotonic(), -1.0, None, False
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                while time.monotonic() - t0 < secondes:
                    s = self.c.read_state_frame()
                    t = s.get("t")
                    dt = (t - dernier_t) if (t is not None and dernier_t is not None and 0 < t - dernier_t < 0.5) else 0.02
                    dernier_t = t
                    b.tick(s, dt)
                    if chaque_tick is not None:
                        chaque_tick(b, s)
                    f = bool((s.get("safety") or {}).get("fallen"))
                    if f and not tombe:
                        mesures["chutes"] += 1
                    tombe = f
                    mesures["etats"][b.courant.nom] = mesures["etats"].get(b.courant.nom, 0) + 1
                    if b.t_global - t_prec >= periode_mesure:
                        t_prec = b.t_global
                        gt = truth.read()
                        if gt:
                            d = gt["ducks"][0]
                            mesures["traj"].append((b.t_global, d["pos"][0], d["pos"][1], truth.trunk_yaw(d["quat"])))
            finally:
                b.arret()
        return mesures

    def facteur_temps_reel(self, secs=3.0):
        t_sim0 = self.c.read_state_frame()["t"]
        t0 = time.monotonic()
        while time.monotonic() - t0 < secs:
            s = self.c.read_state_frame()
        return (s["t"] - t_sim0) / (time.monotonic() - t0)


def deplacer(nom, x, y, z=0.035):
    """Teleporte un objet SANS attendre (truth.teleport attend son arrivee : dans la boucle du cerveau, ca la bloquerait)."""
    import truth
    tmp = truth.CONTROL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"teleport": {nom: [x, y, z]}}))
    tmp.replace(truth.CONTROL_PATH)


def devant(gt, dx, dy=0.0, duck=0):
    """Point monde a (dx, dy) dans le repere du canard (verite terrain)."""
    import truth
    c = gt["ducks"][duck]
    yaw = truth.trunk_yaw(c["quat"])
    return (c["pos"][0] + math.cos(yaw) * dx - math.sin(yaw) * dy,
            c["pos"][1] + math.sin(yaw) * dx + math.cos(yaw) * dy)


def balle(gt):
    """Nom de la balle de la scene (arene : testball)."""
    for nom in ("testball", "ball_0"):
        if nom in gt["bodies"]:
            return nom
    raise KeyError("aucune balle dans la scene")


# --- scenarios -------------------------------------------------------------------------------------------------------
@scenario("promenade", "apartment", "Promenade autonome 5 min : 0 chute, centre jamais a moins de 10 cm d'un obstacle")
def sc_promenade(banc):
    import obstacles
    import truth
    obst = obstacles.charger()
    truth.teleport_duck(-3.0, 1.2, math.radians(90))
    banc.tenir(1.0)
    b = banc.cerveau(energie=1.0, eveil=0.6, seed=5)
    m = banc.vivre(b, 300)

    def dist(p):
        return min(math.hypot(max(x0 - p[0], 0, p[0] - x1), max(y0 - p[1], 0, p[1] - y1)) for _, x0, x1, y0, y1 in obst)
    dmin = min((dist((x, y)) for _, x, y, _ in m["traj"]), default=math.inf)
    parcours = sum(math.dist(m["traj"][i][1:3], m["traj"][i - 1][1:3]) for i in range(1, len(m["traj"])))
    ok = m["chutes"] == 0 and dmin >= 0.10 and parcours > 1.0
    return ok, {"chutes": m["chutes"], "distance_min_obstacle_m": round(dmin, 3), "parcours_m": round(parcours, 2)}


@scenario("main_fantome", "apartment", "Repos face a un mur et a un meuble : aucune fausse main tendue")
def sc_main_fantome(banc):
    import truth
    vues = 0
    for x, y, cap in ((-3.69, 1.2, math.pi), (-3.74, 1.6, math.pi)):     # face au mur ouest de la cuisine, 20-25 cm
        truth.teleport_duck(x, y, cap)
        banc.tenir(1.0)
        b = banc.cerveau(seed=7)
        b.fin_etat = 1e9                          # reste en chill : la situation exacte d'une main tendue
        m = banc.vivre(b, 60)
        vues += m["etats"].get("main_tendue", 0) > 0
    return vues == 0, {"positions_avec_fausse_main": vues}


@scenario("coin_sieste", "arena", "Fatigue : rejoint son coin de sieste appris a ~1,3 m (arrivee a 40 cm pres)")
def sc_coin_sieste(banc):
    import truth
    truth.teleport_duck(0.0, 0.0, 0.0)
    s = banc.tenir(1.0)
    gt = truth.read()
    rel = (1.2, 0.5)
    o = s["odom"]
    coin_odom = (o["position"][0] + math.cos(o["yaw"]) * rel[0] - math.sin(o["yaw"]) * rel[1],
                 o["position"][1] + math.sin(o["yaw"]) * rel[0] + math.cos(o["yaw"]) * rel[1])
    attendu = devant(gt, *rel)
    b = banc.cerveau(energie=0.2, seed=9, exploration=False)
    b.exploration.preference(coin_odom[0], coin_odom[1], "nap", 3600.0, 0.0)
    m = banc.vivre(b, 45)
    fin = m["traj"][-1] if m["traj"] else (0, 0, 0, 0)
    ecart = math.dist(fin[1:3], attendu)
    ok = m["chutes"] == 0 and ecart <= 0.40 and m["etats"].get("va_au_coin", 0) > 0
    return ok, {"ecart_arrivee_m": round(ecart, 2), "issue": getattr(b.etats["va_au_coin"], "issue", None),
                "chutes": m["chutes"]}


@scenario("jeu_balle", "arena", "Jeu de balle autonome : balle a 60 cm -> approche, tir, balle deplacee de 30 cm")
def sc_jeu_balle(banc):
    import balle as balle_mod
    import truth
    import vision
    truth.teleport_duck(0.0, 0.0, 0.0)
    banc.tenir(1.0)
    gt = truth.read()
    nom = balle(gt)
    truth.teleport(nom, *devant(gt, 0.6, 0.05))
    depart = truth.read()["bodies"][nom][:2]
    veille = balle_mod.VeilleBalle(vision.grab_frame)
    veille.start()
    b = banc.cerveau(seed=11, balle=veille)
    b.evenement("jeu_balle")
    m = banc.vivre(b, 120, chaque_tick=veille.etat_robot_hook)
    veille.actif = False
    deplace = math.dist(truth.read()["bodies"][nom][:2], depart)
    jeu = b.etats["balle"]
    return (m["chutes"] == 0 and deplace >= 0.30), {"balle_deplacee_m": round(deplace, 2), "resultat": jeu.resultat,
                                                    "manches": jeu.manche, "chutes": m["chutes"]}


@scenario("soleil", "arena", "1-2-3 soleil : demi-tours sans derive ; un 'joueur' qui bouge est vu")
def sc_soleil(banc):
    import mouvement
    import truth
    import vision
    truth.teleport_duck(0.0, 0.0, 0.0)
    banc.tenir(1.0)
    gt = truth.read()
    nom = balle(gt)
    veille = mouvement.VeilleMouvement(vision.grab_frame)
    veille.start()
    b = banc.cerveau(seed=13, mouvement=veille)
    b.evenement("jeu_soleil")
    caps, k = [], [0]

    def joueur(b, s):
        jeu = b.etats["soleil"]
        if b.courant.nom == "soleil" and jeu.phase == "regarde":
            caps.append(truth.trunk_yaw(truth.read()["ducks"][0]["quat"]))
            k[0] += 1
            if k[0] % 25 == 0:                     # le "joueur" (la balle) bouge devant lui toutes les 0,5 s
                g = truth.read()
                deplacer(nom, *devant(g, 1.0, 0.2 * ((k[0] // 25) % 3 - 1)))
    m = banc.vivre(b, 70, chaque_tick=joueur)
    veille.actif = False
    derive = max((abs(math.remainder(c, 2 * math.pi)) for c in caps), default=math.inf)
    jeu = b.etats["soleil"]
    ok = m["chutes"] == 0 and jeu.vus >= 1 and derive <= math.radians(30)
    return ok, {"vus": jeu.vus, "derive_max_deg": round(math.degrees(derive), 1), "manches": jeu.manche}


@scenario("aspirateur", "arena", "Objet bas qui approche (balle poussee vers lui) : il s'ecarte avant 30 cm")
def sc_aspirateur(banc):
    import truth
    truth.teleport_duck(0.0, 0.0, 0.0)
    banc.tenir(1.0)
    gt = truth.read()
    nom = balle(gt)
    b = banc.cerveau(seed=15, exploration=False)
    b.evenement("aspirateur_on")
    b.fin_etat = 1e9
    etat = {"d": 1.0, "ecarte_a": None, "n": 0}
    asp = b.etats["aspirateur"]

    def approche(b, s):
        if (b.courant.nom == "aspirateur" and etat["ecarte_a"] is None
                and b.t_etat >= getattr(asp, "t_ecart", math.inf)):
            etat["ecarte_a"] = round(etat["d"], 2)   # il commence a s'ecarter : a quelle distance etait l'"aspirateur" ?
        etat["n"] += 1
        if etat["ecarte_a"] is None and etat["d"] > 0.15 and etat["n"] % 5 == 0:
            etat["d"] -= 0.02                      # 2 cm par 0,1 s = 0,2 m/s, comme un robot aspirateur
            deplacer(nom, *devant(truth.read(), etat["d"]))
    simul = banc.vivre(b, 20, chaque_tick=approche)
    ok = simul["chutes"] == 0 and etat["ecarte_a"] is not None and etat["ecarte_a"] >= 0.28
    return ok, {"distance_quand_il_s_ecarte_m": etat["ecarte_a"], "chutes": simul["chutes"]}


@scenario("cascades", "arena", "Fausse chute, Zoomies, toupie : aucune vraie chute ; la toupie fait ~360 deg")
def sc_cascades(banc):
    import truth
    resultats = {}
    for etat, duree in (("fausse_chute", 10), ("zoomies", 12), ("toupie", 11)):
        truth.teleport_duck(0.0, 0.0, 0.0)
        banc.tenir(1.0)
        b = banc.cerveau(energie=0.95, eveil=0.9, seed=17, exploration=False)
        b._bascule(etat)
        m = banc.vivre(b, duree, periode_mesure=0.05)
        tour = sum(abs(math.remainder(m["traj"][i][3] - m["traj"][i - 1][3], 2 * math.pi))
                   for i in range(1, len(m["traj"])))
        resultats[etat] = {"chutes": m["chutes"], "rotation_deg": round(math.degrees(tour))}
    ok = all(r["chutes"] == 0 for r in resultats.values()) and 300 <= resultats["toupie"]["rotation_deg"] <= 420
    return ok, resultats


@scenario("pousse_balle", "arena", "Pousser la balle hors de portee : balle avancee de 3 cm au moins, pas de chute")
def sc_pousse_balle(banc):
    import truth
    truth.teleport_duck(0.0, 0.0, 0.0)
    banc.tenir(1.0)
    gt = truth.read()
    nom = balle(gt)
    truth.teleport(nom, *devant(gt, 0.12, 0.0))
    depart = truth.read()["bodies"][nom][:2]
    b = banc.cerveau(seed=19, exploration=False)
    b._bascule("pousse_balle")
    m = banc.vivre(b, 4)
    deplace = math.dist(truth.read()["bodies"][nom][:2], depart)
    return (m["chutes"] == 0 and deplace >= 0.03), {"balle_deplacee_m": round(deplace, 3), "chutes": m["chutes"]}


# --- programme -------------------------------------------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--liste" in sys.argv:
        for nom, (scene, _, desc) in SCENARIOS.items():
            print(f"{nom:14s} [{scene}] {desc}")
        return
    choisis = args or list(SCENARIOS)
    inconnus = [n for n in choisis if n not in SCENARIOS]
    if inconnus:
        raise SystemExit(f"scenarios inconnus : {inconnus} (--liste)")
    par_scene = {}
    for n in choisis:
        par_scene.setdefault(SCENARIOS[n][0], []).append(n)
    resultats = []
    for scene, noms in par_scene.items():
        if "--scenes-auto" in sys.argv:
            print(f"=== scene {scene} ===", flush=True)
            subprocess.run(["bash", str(Path.home() / "run-scene.sh"), scene], check=True)
        banc = Banc()
        rt = banc.facteur_temps_reel()
        if rt < 0.95:
            print(f"ATTENTION : simulation a {rt:.2f}x le temps reel (< 0,95) : resultats de marche douteux", flush=True)
        for n in noms:
            t0 = time.monotonic()
            try:
                ok, details = SCENARIOS[n][1](banc)
            except Exception as e:                  # un scenario qui plante ne doit pas arreter les autres
                ok, details = False, {"erreur": f"{type(e).__name__}: {e}"}
            r = {"scenario": n, "scene": scene, "ok": bool(ok), "details": details,
                 "duree_s": round(time.monotonic() - t0, 1), "temps_reel": round(rt, 2)}
            resultats.append(r)
            print(f"{'OK   ' if ok else 'ECHEC'} {n:14s} {json.dumps(details, ensure_ascii=False)}", flush=True)
        banc.tof.actif = False
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps(resultats, indent=1, ensure_ascii=False))
    print(f"\n{sum(r['ok'] for r in resultats)}/{len(resultats)} scenarios valides ; detail : {SORTIE}", flush=True)


if __name__ == "__main__":
    main()
