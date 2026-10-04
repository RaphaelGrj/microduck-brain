#!/usr/bin/env python3
"""Evaluation du controleur d'approche sur la VERITE TERRAIN (arene ouverte : `run-scene.sh arena`).

Chaque essai : canard replace en (0, 0) cap 0, balle posee a une distance et un relevement tires au
hasard, puis `Approche.run`. On mesure : tir declenche ou non, ou etait vraiment la balle au moment
du tir (repere du tronc), et ce que le tir en a fait (vitesse, direction du depart, distance a 1 s).

Succes = tir declenche ET balle partie a plus de 15 cm dans les 35 deg du cap du canard.

Usage : bash ~/run-brain.sh approach_eval.py [essais=6] [relevement_max_deg=40] [graine=1]
"""
import math
import os
import random
import sys
import time

import approach
import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

n_essais = int(sys.argv[1]) if len(sys.argv) > 1 else 6
rel_max = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
# Variables d'environnement : DEPART="x,y,cap_deg" (point de depart du canard dans le monde, defaut 0,0,0),
# DIST="min,max" (distance de la balle, defaut 0.5,1.0), CAP_VISE="deg" (voir approach.py)
_d = [float(v) for v in os.environ.get("DEPART", "0,0,0").split(",")]
DEPART = (_d[0], _d[1], math.radians(_d[2]))
VISEE = float(os.environ.get("VISEE", "0"))          # demi-ouverture (deg) de la direction voulue ; 0 = pas de visee
# OBSTACLES=1 : la scene est l'appartement -> placements valides seulement (voir obstacles.py)
OBST = None
TAPIS = (-3.3, -1.7, -1.5, -0.5)               # tapis rouge du salon (camouflage de la balle orange)
if os.environ.get("OBSTACLES"):
    import obstacles
    OBST = obstacles.charger()
    if obstacles.dedans(DEPART[:2], OBST, marge=0.12):
        raise SystemExit(f"point de depart dans un obstacle : {obstacles.dedans(DEPART[:2], OBST, marge=0.12)}")
DIST_MIN, DIST_MAX = [float(v) for v in os.environ.get("DIST", "0.5,1.0").split(",")]

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def tenir(secs, move=(0.0, 0.0, 0.0)):
    t0 = time.monotonic()
    s = None
    while time.monotonic() - t0 < secs:
        s = c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": move[0], "vy": move[1], "vyaw": move[2]})
    return s


def remettre_a_zero(dist, rel_deg):
    for _ in range(60):                       # attendre que le canard soit debout (apres un tir)
        s = tenir(0.2)
        if s["policy"] == "stand" and not s["safety"]["fallen"]:
            break
    else:
        return False
    sx, sy, syaw = DEPART
    for nom, pos in (("ball_0", (3.0, -2.2)), ("ball_1", (3.4, -2.4)), ("ball_2", (3.8, -2.0))):
        try:                                   # l'appartement a ses propres balles (une orange dans le salon) : on les range
            truth.teleport(nom, *pos)          # dans la salle de bain pour qu'elles ne soient pas prises pour la cible
        except (KeyError, TimeoutError):
            pass
    truth.teleport_duck(sx, sy, syaw)
    tenir(0.8)
    b = syaw + math.radians(rel_deg)
    try:
        truth.teleport("testball", sx + dist * math.cos(b), sy + dist * math.sin(b))
    except TimeoutError:                       # dans un meuble ou un mur (appartement) : on saute l'essai
        return None
    tenir(0.8)
    gt = truth.read()
    p = gt["bodies"]["testball"]
    if math.dist(p[:2], (sx + dist * math.cos(b), sy + dist * math.sin(b))) > 0.02 or not 0.03 <= p[2] <= 0.04:
        return None                            # repoussee ou tombee : placement invalide
    return True


def mesurer_tir(gt_avant):
    """Suit la balle 3,2 s apres le tir : (vitesse max, distance a 1 s, direction du depart / cap en deg)."""
    p0 = gt_avant["bodies"]["testball"]
    yaw0 = truth.trunk_yaw(gt_avant["ducks"][0]["quat"])
    t0 = time.monotonic()
    vmax, prev, p1 = 0.0, p0, None
    while time.monotonic() - t0 < 3.2:
        s = c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
        g = truth.read()
        if g:
            p = g["bodies"]["testball"]
            if p != prev:
                if math.dist(p, prev) < 0.5:                  # ignore les sauts (teleportation)
                    vmax = max(vmax, math.dist(p, prev) / 0.1)
                prev = p
            if p1 is None and time.monotonic() - t0 >= 1.0:
                p1 = p
    p1 = p1 or prev
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    dist = math.hypot(dx, dy)
    ang = (math.degrees(math.atan2(dy, dx) - yaw0) + 180) % 360 - 180 if dist > 0.02 else float("nan")
    ang_w = math.degrees(math.atan2(dy, dx)) if dist > 0.02 else float("nan")
    return vmax, dist, ang, ang_w


bilan = []
for i in range(n_essais):
    dist = random.uniform(DIST_MIN, DIST_MAX)
    rel = random.uniform(-rel_max, rel_max)
    if OBST is not None:                       # appartement : balle ni dans un meuble ni masquee (banc d'essai, pas cerveau)
        for _ in range(200):
            b = DEPART[2] + math.radians(rel)
            pb = (DEPART[0] + dist * math.cos(b), DEPART[1] + dist * math.sin(b))
            if not obstacles.dedans(pb, OBST) and not obstacles.ligne_libre(DEPART[:2], pb, OBST):
                break
            dist = random.uniform(DIST_MIN, DIST_MAX)
            rel = random.uniform(-rel_max, rel_max)
        else:
            print("aucune position de balle valide autour de ce point de depart", flush=True)
            break
        sur_tapis = TAPIS[0] <= pb[0] <= TAPIS[1] and TAPIS[2] <= pb[1] <= TAPIS[3]
        print(f"(placement verifie : rien entre le canard et la balle{' ; balle SUR LE TAPIS rouge' if sur_tapis else ''})", flush=True)
    print(f"\n##### essai {i + 1}/{n_essais} : balle a {dist:.2f} m, relevement {rel:+.0f} deg #####", flush=True)
    pret = remettre_a_zero(dist, rel)
    if pret is None:
        print("placement de la balle impossible (obstacle) : essai saute", flush=True)
        continue
    if not pret:
        print("canard pas debout : arret", flush=True)
        break
    cap_vise = cap_w = None
    if VISEE:                                  # direction voulue du ballon : au hasard autour de la ligne canard -> balle
        s0 = tenir(0.3)
        gt0 = truth.read()
        pd, pb = gt0["ducks"][0]["pos"], gt0["bodies"]["testball"]
        yaw_w = truth.trunk_yaw(gt0["ducks"][0]["quat"])
        cap_w = math.atan2(pb[1] - pd[1], pb[0] - pd[0]) + math.radians(random.uniform(-VISEE, VISEE))
        cap_vise = cap_w + (s0["odom"]["yaw"] - yaw_w)        # la meme direction dans le repere de l'odometrie
        print(f"direction visee : {math.degrees(cap_w):+.0f} deg (monde), "
              f"{math.degrees(cap_w - math.atan2(pb[1] - pd[1], pb[0] - pd[0])):+.0f} deg de la ligne canard-balle", flush=True)
    ap = approach.Approche(c, "orange", verite=True, log=lambda m: print(m, flush=True), cap_vise=cap_vise)
    ap.avant_tir = lambda: {"verite": truth.in_trunk_frame(truth.read(), "testball"), "gt": truth.read()}
    t0 = time.monotonic()
    res = ap.run(90.0)
    ap.vis.run_flag = False
    ligne = {"dist": dist, "rel": rel, "duree": time.monotonic() - t0, "tir": "avant_tir" in res}
    if "tir" in res and "avant_tir" in res:
        av = res["avant_tir"]
        x, y, _ = av["verite"]
        cote = res["tir"]["cote"]
        ty = 0.042 if cote == "left" else -0.042
        vmax, d1, ang, ang_w = mesurer_tir(av["gt"])
        ligne.update(cote=cote, err_x=x - ap.tir["cible_x"], err_y=y - ty, vmax=vmax, d1=d1, ang=ang, n_ajust=res["tir"]["n_ajust"],
                     ok=(d1 >= 0.15 and not math.isnan(ang) and abs(ang) < 35))
        if VISEE:
            err_cap = (ang_w - math.degrees(cap_w) + 180) % 360 - 180
            ligne["err_cap"] = err_cap
            ligne["ok"] = d1 >= 0.15 and not math.isnan(ang_w) and abs(err_cap) <= 35
            print(f"VISEE : ballon parti a {ang_w:+.0f} deg (monde) pour {math.degrees(cap_w):+.0f} voulus -> ecart {err_cap:+.0f} deg", flush=True)
        print(f"RESULTAT : pied {cote}, balle vraie a ({x:+.3f},{y:+.3f}) -> erreur ({(x - ap.tir["cible_x"]) * 100:+.1f},{(y - ty) * 100:+.1f}) cm ;"
              f" vmax {vmax:.2f} m/s, balle a {d1:.2f} m a 1 s, depart {ang:+.0f} deg -> {'SUCCES' if ligne['ok'] else 'echec'}", flush=True)
    else:
        ligne["ok"] = False
        print(f"RESULTAT : pas de tir ({res.get('etat')})", flush=True)
    bilan.append(ligne)

print(f"\n===== BILAN (profil de tir : {os.environ.get('MICRODUCK_TIR', 'officiel')}) =====", flush=True)
for i, l in enumerate(bilan, 1):
    if l["tir"]:
        print(f"{i}. {l['dist']:.2f} m {l['rel']:+4.0f} deg : {l['duree']:4.0f} s, pied {l['cote']}, erreur ({l['err_x'] * 100:+5.1f},{l['err_y'] * 100:+5.1f}) cm,"
              f" balle a {l['d1']:.2f} m ({l['ang']:+.0f} deg) -> {'OK' if l['ok'] else 'echec'}", flush=True)
    else:
        print(f"{i}. {l['dist']:.2f} m {l['rel']:+4.0f} deg : pas de tir apres {l['duree']:.0f} s", flush=True)
n_tir = sum(1 for l in bilan if l["tir"])
n_ok = sum(1 for l in bilan if l["ok"])
print(f"tirs declenches : {n_tir}/{len(bilan)} ; tirs reussis : {n_ok}/{len(bilan)}", flush=True)
