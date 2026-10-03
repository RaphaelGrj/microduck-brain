#!/usr/bin/env python3
"""Evaluation du controleur d'approche sur la VERITE TERRAIN (arene ouverte : `run-scene.sh arena`).

Chaque essai : canard replace en (0, 0) cap 0, balle posee a une distance et un relevement tires au
hasard, puis `Approche.run`. On mesure : tir declenche ou non, ou etait vraiment la balle au moment
du tir (repere du tronc), et ce que le tir en a fait (vitesse, direction du depart, distance a 1 s).

Succes = tir declenche ET balle partie a plus de 15 cm dans les 35 deg du cap du canard.

Usage : bash ~/run-brain.sh approach_eval.py [essais=6] [relevement_max_deg=40] [graine=1]
"""
import math
import random
import sys
import time

import approach
import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

n_essais = int(sys.argv[1]) if len(sys.argv) > 1 else 6
rel_max = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)

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
    truth.teleport_duck(0.0, 0.0, 0.0)
    tenir(0.8)
    b = math.radians(rel_deg)
    truth.teleport("testball", dist * math.cos(b), dist * math.sin(b))
    tenir(0.8)
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
    return vmax, dist, ang


bilan = []
for i in range(n_essais):
    dist = random.uniform(0.5, 1.0)
    rel = random.uniform(-rel_max, rel_max)
    print(f"\n##### essai {i + 1}/{n_essais} : balle a {dist:.2f} m, relevement {rel:+.0f} deg #####", flush=True)
    if not remettre_a_zero(dist, rel):
        print("canard pas debout : arret", flush=True)
        break
    ap = approach.Approche(c, "orange", verite=True, log=lambda m: print(m, flush=True))
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
        vmax, d1, ang = mesurer_tir(av["gt"])
        ligne.update(cote=cote, err_x=x - 0.07, err_y=y - ty, vmax=vmax, d1=d1, ang=ang, n_ajust=res["tir"]["n_ajust"],
                     ok=(d1 >= 0.15 and not math.isnan(ang) and abs(ang) < 35))
        print(f"RESULTAT : pied {cote}, balle vraie a ({x:+.3f},{y:+.3f}) -> erreur ({(x - 0.07) * 100:+.1f},{(y - ty) * 100:+.1f}) cm ;"
              f" vmax {vmax:.2f} m/s, balle a {d1:.2f} m a 1 s, depart {ang:+.0f} deg -> {'SUCCES' if ligne['ok'] else 'echec'}", flush=True)
    else:
        ligne["ok"] = False
        print(f"RESULTAT : pas de tir ({res.get('etat')})", flush=True)
    bilan.append(ligne)

print("\n===== BILAN =====", flush=True)
for i, l in enumerate(bilan, 1):
    if l["tir"]:
        print(f"{i}. {l['dist']:.2f} m {l['rel']:+4.0f} deg : {l['duree']:4.0f} s, pied {l['cote']}, erreur ({l['err_x'] * 100:+5.1f},{l['err_y'] * 100:+5.1f}) cm,"
              f" balle a {l['d1']:.2f} m ({l['ang']:+.0f} deg) -> {'OK' if l['ok'] else 'echec'}", flush=True)
    else:
        print(f"{i}. {l['dist']:.2f} m {l['rel']:+4.0f} deg : pas de tir apres {l['duree']:.0f} s", flush=True)
n_tir = sum(1 for l in bilan if l["tir"])
n_ok = sum(1 for l in bilan if l["ok"])
print(f"tirs declenches : {n_tir}/{len(bilan)} ; tirs reussis : {n_ok}/{len(bilan)}", flush=True)
