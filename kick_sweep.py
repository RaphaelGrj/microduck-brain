#!/usr/bin/env python3
"""Tolerance du tir au placement de la balle : balayage d'erreurs (dx, dy) autour de la position
d'entrainement, pour les deux pieds. Mesure sur la VERITE TERRAIN : vitesse de pointe de la balle
et direction de son depart par rapport au cap du canard.

Succes = vitesse de pointe >= 0.4 m/s ET direction du depart a moins de 35 deg du cap.

Usage : bash ~/run-brain.sh kick_sweep.py [right|left|both] [repetitions=1] [nominal]
"""
import math
import sys
import time

import truth
from poc_robotd_client import RobotdClient, SOCK_PATH

DXS = (-0.04, -0.02, 0.0, 0.02, 0.04)   # erreur en avant (m)
DYS = (-0.03, 0.0, 0.03)                # erreur laterale (m)

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def tenir(secs):
    t0 = time.monotonic()
    s = None
    while time.monotonic() - t0 < secs:
        s = c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
    return s


def essai(cote, bruit):
    s = tenir(1.2)
    if s["safety"]["fallen"] or s["policy"] != "stand":
        return None
    try:
        truth.place_devant_pied("testball", cote, bruit=bruit)
    except TimeoutError:
        return {"vmax": 0.0, "dist1s": 0.0, "ang": float("nan"), "fell": False, "ok": False, "impossible": True}
    tenir(0.8)
    gt0 = truth.read()
    p0 = gt0["bodies"]["testball"]
    yaw0 = truth.trunk_yaw(gt0["ducks"][0]["quat"])
    c.request("robot.do", {"skill": f"kick_{cote}"})
    t0 = time.monotonic()
    vmax, prev, p1s = 0.0, p0, None
    while time.monotonic() - t0 < 3.2:
        c.read_state_frame()
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
        g = truth.read()
        if g:
            p = g["bodies"]["testball"]
            if p != prev:
                vmax = max(vmax, math.dist(p, prev) / 0.1)
                prev = p
            if p1s is None and time.monotonic() - t0 >= 1.0:
                p1s = p
    p1s = p1s or prev
    dx, dy = p1s[0] - p0[0], p1s[1] - p0[1]
    dist = math.hypot(dx, dy)
    ang = math.degrees(math.atan2(dy, dx) - yaw0) if dist > 0.02 else float("nan")
    ang = (ang + 180) % 360 - 180 if not math.isnan(ang) else ang
    fell = c.read_state_frame()["safety"]["fallen"]
    ok = (vmax >= 0.4) and (not math.isnan(ang)) and abs(ang) < 35 and not fell
    return {"vmax": vmax, "dist1s": dist, "ang": ang, "fell": fell, "ok": ok}


if len(sys.argv) > 3 and sys.argv[3] == "nominal":   # repetitions au seul point d'entrainement
    DXS, DYS = (0.0,), (0.0,)
cotes = ["right", "left"] if (sys.argv[1] if len(sys.argv) > 1 else "both") == "both" else [sys.argv[1]]
rep = int(sys.argv[2]) if len(sys.argv) > 2 else 1
res = {}
for cote in cotes:
    print(f"\n=== pied {cote} (erreur dx avant / dy lateral, en cm) ===", flush=True)
    for dy in DYS:
        for dx in DXS:
            for _ in range(rep):
                r = essai(cote, (dx, dy))
                res.setdefault(cote, {}).setdefault((dx, dy), []).append(r)
                if r is None:
                    print(f"  dx={dx*100:+3.0f} dy={dy*100:+3.0f}: canard pas pret / tombe -> arret", flush=True)
                    sys.exit(1)
                if r.get("impossible"):
                    print(f"  dx={dx*100:+3.0f} dy={dy*100:+3.0f}: placement impossible (balle repoussee par la patte)", flush=True)
                    continue
                print(f"  dx={dx*100:+3.0f} dy={dy*100:+3.0f}: vmax={r['vmax']:.2f} m/s  depart={r['ang']:+6.1f} deg "
                      f"balle1s={r['dist1s']:.2f} m  chute={r['fell']}  -> {'OK' if r['ok'] else 'rate'}", flush=True)

print("\n=== grille de succes (ligne = dy lateral, colonne = dx avant ; O=ok .=rate) ===", flush=True)
for cote, d in res.items():
    print(f"pied {cote} :   dx(cm)= " + " ".join(f"{dx*100:+3.0f}" for dx in DXS), flush=True)
    for dy in DYS:
        ligne = " ".join("  " + ("O" if all(x["ok"] for x in d[(dx, dy)]) else ".") for dx in DXS)
        print(f"   dy={dy*100:+3.0f}            {ligne}", flush=True)
