#!/usr/bin/env python3
"""Mesure ce que font `robot.pose` (corps debout : hauteur z, roulis, tangage) et `robot.mouth` (bec) dans duck-sim.

Pour chaque commande tenue 2,5 s : roulis / tangage (gravite projetee de robot.state) et hauteur du tronc (odometrie),
et ouverture du bec
(joint 14 de robot.state si c'est lui). Puis un roulis oscillant (le "tremoussement" de la phase 1) a plusieurs
frequences : amplitude obtenue et chute eventuelle.

Usage : bash ~/run-brain.sh diag_pose.py
"""
import math
import time

from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})


def tenir(secs, pose=None, bouche=None, fn=None):
    """Envoie la commande a chaque trame ; renvoie les mesures (t, roulis, tangage, z, joint14)."""
    t0, mes = time.monotonic(), []
    while (t := time.monotonic() - t0) < secs:
        s = c.read_state_frame()
        p = fn(t) if fn else pose
        if p is not None:
            c.notify("robot.pose", {"z": p[0], "roll": p[1], "pitch": p[2], "active": True})
        if bouche is not None:
            c.notify("robot.mouth", {"open": bouche})
        c.notify("robot.head", {"neck_pitch": 0.0, "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0})
        c.notify("robot.move", {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
        # gravite projetee dans le tronc (50 Hz, plus fin que la verite terrain a 10 Hz) -> roulis / tangage
        gx, gy, gz = s["safety"]["gravity"]
        r, pt = math.degrees(math.atan2(gy, -gz)), math.degrees(math.atan2(-gx, -gz))
        j = s.get("joints") or []
        mes.append((t, r, pt, s["odom"]["position"][2], j[14] if len(j) > 14 else None, s["safety"]["fallen"]))
    return mes


def neutre():
    c.notify("robot.pose", {"z": 0.0, "roll": 0.0, "pitch": 0.0, "active": False})
    tenir(1.5, pose=None, bouche=0.0)


s = c.read_state_frame()
print("joints :", len(s.get("joints") or []), "politique :", s["policy"], flush=True)
neutre()
ref = tenir(1.0)
r0 = sum(m[1] for m in ref) / len(ref)
p0 = sum(m[2] for m in ref) / len(ref)
z0 = sum(m[3] for m in ref) / len(ref)
print(f"repos : roulis {r0:+.1f} deg, tangage {p0:+.1f} deg, tronc a {z0 * 100:.1f} cm", flush=True)

print("\n=== poses tenues (mesure sur la derniere seconde) ===", flush=True)
for nom, pose in [("roulis +0.15", (0, 0.15, 0)), ("roulis -0.15", (0, -0.15, 0)), ("roulis +0.3", (0, 0.3, 0)),
                  ("tangage +0.15", (0, 0, 0.15)), ("tangage -0.15", (0, 0, -0.15)),
                  ("z -0.02", (-0.02, 0, 0)), ("z -0.04", (-0.04, 0, 0)), ("z +0.01", (0.01, 0, 0))]:
    m = [x for x in tenir(2.5, pose=pose) if x[0] > 1.5]
    print(f"  {nom:14s} -> roulis {sum(x[1] for x in m) / len(m) - r0:+5.1f} deg  tangage "
          f"{sum(x[2] for x in m) / len(m) - p0:+5.1f} deg  hauteur {(sum(x[3] for x in m) / len(m) - z0) * 100:+5.1f} cm"
          f"  chute={any(x[5] for x in m)}", flush=True)
    neutre()

print("\n=== bec (robot.mouth) ===", flush=True)
for o in (0.0, 0.5, 1.0, 0.0):
    m = [x for x in tenir(1.2, bouche=o) if x[0] > 0.8]
    j = [x[4] for x in m if x[4] is not None]
    print(f"  open={o:.1f} -> joint 14 = {sum(j) / len(j):+.3f}" if j else f"  open={o:.1f} -> pas de joint 14", flush=True)

print("\n=== tremoussement : roulis oscillant (amplitude crete a crete mesuree) ===", flush=True)
for hz in (1.0, 2.0, 3.0):
    for amp in (0.15, 0.3):
        m = tenir(3.0, fn=lambda t: (0.0, amp * math.sin(2 * math.pi * hz * t), 0.0))
        m = [x for x in m if x[0] > 1.0]
        rs = [x[1] for x in m]
        print(f"  {hz:.0f} Hz, commande +-{amp:.2f} rad -> roulis reel {min(rs) - r0:+5.1f} / {max(rs) - r0:+5.1f} deg"
              f"  chute={any(x[5] for x in m)}", flush=True)
        neutre()
neutre()
