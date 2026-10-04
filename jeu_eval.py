#!/usr/bin/env python3
"""Banc du jeu de balle avec le chat (scene `bash ~/run-scene.sh arena_chat` : affiche du chat debout en (1,2 ; 0)).

Chaque essai : canard replace a un depart ou l'affiche est sur le cote (pas droit devant), balle posee a 0,5-0,8 m,
puis UNE manche de jeu.Partie (cherche le chat, la balle, et passe). Verite terrain : la balle part-elle VERS le chat ?
Succes = balle partie a plus de 15 cm, a moins de 25 deg de la direction balle -> chat.

Usage : bash ~/run-brain.sh jeu_eval.py [essais=6] [graine=1]
"""
import math
import random
import sys
import time

import jeu
import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

CHAT = (1.2, 0.0)
DEPARTS = [(0.0, -0.9, 0.0), (0.0, 0.9, 0.0), (-0.3, -0.6, -0.5), (-0.3, 0.6, 0.5), (-0.5, 0.0, 0.0), (0.2, -1.0, 1.2),
           (-0.2, -1.2, 1.0), (-0.2, 1.2, -1.0)]

n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
p = jeu.Partie(c, "chat", log=lambda m: print(m, flush=True), verite=True)
bilan = []
for k in range(n):
    x0, y0, yaw0 = DEPARTS[k % len(DEPARTS)]
    p.tenir(1.0)
    truth.teleport_duck(x0, y0, yaw0)
    p.tenir(0.8)
    while True:                                      # balle a 0,5-0,8 m du canard ET a plus d'1 m du chat (sinon le
        d, b = random.uniform(0.5, 0.8), math.radians(random.uniform(-40, 40))   # garde-fou refuse, a juste titre)
        bx, by = x0 + d * math.cos(yaw0 + b), y0 + d * math.sin(yaw0 + b)
        if math.hypot(bx - CHAT[0], by - CHAT[1]) >= 1.0:
            break
    try:
        truth.teleport("testball", bx, by)
    except TimeoutError:
        print("placement de la balle impossible : essai saute", flush=True)
        continue
    p.tenir(0.8)
    rel = math.degrees(math.atan2(CHAT[1] - y0, CHAT[0] - x0) - yaw0)
    print(f"\n##### essai {k + 1}/{n} : canard ({x0:+.1f},{y0:+.1f}) cap {math.degrees(yaw0):+.0f}, chat a {rel:+.0f} deg, "
          f"balle a {d:.2f} m #####", flush=True)
    t0 = time.monotonic()
    r = p.manche(k + 1)
    ligne = {"essai": k + 1, "issue": r, "duree": time.monotonic() - t0, "ok": False}
    j = p.journal[-1] if p.journal else {}
    if r == "passe" and "avant_tir" in j:
        p0 = j["avant_tir"]["gt"]["bodies"]["testball"]
        time.sleep(0.2)
        p1 = truth.read()["bodies"]["testball"]       # ~6 s apres le tir (attente de retour de la manche)
        dep = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        vise = math.atan2(CHAT[1] - p0[1], CHAT[0] - p0[0])
        err = math.degrees((dep - vise + math.pi) % (2 * math.pi) - math.pi)
        dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        ligne.update(err=err, dist=dist, ok=dist > 0.15 and abs(err) <= 25)
        print(f"RESULTAT : balle partie {dist:.2f} m, ecart a la direction du chat {err:+.0f} deg -> "
              f"{'SUCCES' if ligne['ok'] else 'echec'}", flush=True)
    else:
        print(f"RESULTAT : {r}", flush=True)
    bilan.append(ligne)

print("\n===== BILAN jeu avec le chat =====", flush=True)
for l in bilan:
    print(f"{l['essai']}. {l['issue']:10s} {l['duree']:4.0f} s" +
          (f"  ecart {l['err']:+4.0f} deg, {l['dist']:.2f} m" if "err" in l else "") + ("  OK" if l["ok"] else ""), flush=True)
print(f"passes vers le chat reussies : {sum(l['ok'] for l in bilan)}/{len(bilan)}", flush=True)
