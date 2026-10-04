#!/usr/bin/env python3
"""Verite terrain du simulateur (desactivee sur le vrai robot, evidemment).

Lit ~/.cache/duck-sim/groundtruth.json, ecrit toutes les 0,1 s par le corps simule de notre fork
(DUCK_SIM_GROUNDTRUTH). Sert de REGLE pour evaluer la perception et l'approche : le cerveau ne
doit jamais s'en servir pour decider, seulement pour mesurer.
"""
import json
import math
import time
from pathlib import Path

GT_PATH = Path.home() / ".cache/duck-sim/groundtruth.json"


def read(max_age=1.0):
    """Derniere verite terrain (dict) ou None si absente / trop ancienne."""
    for _ in range(5):
        try:
            gt = json.loads(GT_PATH.read_text())
            return gt
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.02)
    return None


def trunk_yaw(quat):
    w, x, y, z = quat
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def in_trunk_frame(gt, name, duck=0):
    """Position (x avant, y gauche, z haut) de l'objet `name` dans le repere du tronc, en m."""
    d = gt["ducks"][duck]
    p = gt["bodies"][name]
    dx, dy = p[0] - d["pos"][0], p[1] - d["pos"][1]
    yaw = trunk_yaw(d["quat"])
    c, s = math.cos(yaw), math.sin(yaw)
    return c * dx + s * dy, -s * dx + c * dy, p[2]


CONTROL_PATH = Path.home() / ".cache/duck-sim/control.json"


def teleport(name, x, y, z=0.035, attente=3.0):
    """Place l'objet `name` en (x, y, z) MONDE (balle de 35 mm : z=0.035) et attend de le voir arriver."""
    tmp = CONTROL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"teleport": {name: [x, y, z]}}))
    tmp.replace(CONTROL_PATH)
    t0 = time.monotonic()
    while time.monotonic() - t0 < attente:
        gt = read()
        if gt and math.dist(gt["bodies"][name][:2], (x, y)) < 0.02:
            return gt
        time.sleep(0.05)
    raise TimeoutError(f"{name} n'est pas arrive en ({x:.2f},{y:.2f}) : DUCK_SIM_CONTROL actif ?")


def coucher_duck(x=0.0, y=0.0, yaw=0.0, pitch=math.pi / 2, roll=0.0, z=0.07, index=0):
    """Couche le canard (essais de relevement) : pitch +pi/2 = sur le ventre, -pi/2 = sur le dos ; roll = sur le cote."""
    tmp = CONTROL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"teleport_duck": [{"index": index, "pos": [x, y], "yaw": yaw, "pitch": pitch,
                                                  "roll": roll, "z": z}]}))
    tmp.replace(CONTROL_PATH)


def teleport_duck(x=0.0, y=0.0, yaw=0.0, index=0, attente=3.0):
    """Replace le canard (tronc) en (x, y) monde, cap `yaw` rad, a l'arret : permet d'enchainer des
    essais depuis le meme point au lieu de deriver vers un mur. A appeler canard debout et immobile."""
    tmp = CONTROL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"teleport_duck": [{"index": index, "pos": [x, y], "yaw": yaw}]}))
    tmp.replace(CONTROL_PATH)
    t0 = time.monotonic()
    while time.monotonic() - t0 < attente:
        gt = read()
        if gt and math.dist(gt["ducks"][index]["pos"][:2], (x, y)) < 0.03 and \
                abs((trunk_yaw(gt["ducks"][index]["quat"]) - yaw + math.pi) % (2 * math.pi) - math.pi) < math.radians(3):
            return gt          # position ET cap appliques (sinon un canard deja en (x, y) repondait avant de tourner)
        time.sleep(0.05)
    raise TimeoutError(f"le canard n'est pas arrive en ({x:.2f},{y:.2f}) : DUCK_SIM_CONTROL actif ?")


def place_devant_pied(name, cote, dx=0.09, dy=0.042, bruit=(0.0, 0.0), duck=0):
    """Pose la balle a la position de tir d'entrainement, DANS LE REPERE ACTUEL du canard
    (x=0.09 devant le tronc, y=-0.042 pied droit / +0.042 pied gauche), plus un decalage `bruit`."""
    gt = read()
    d = gt["ducks"][duck]
    yaw = trunk_yaw(d["quat"])
    lx, ly = dx + bruit[0], (-dy if cote == "right" else dy) + bruit[1]
    wx = d["pos"][0] + math.cos(yaw) * lx - math.sin(yaw) * ly
    wy = d["pos"][1] + math.sin(yaw) * lx + math.cos(yaw) * ly
    return teleport(name, wx, wy)


def describe(gt, name="testball", duck=0):
    x, y, z = in_trunk_frame(gt, name, duck)
    d = gt["ducks"][duck]
    return (f"{name} dans le repere du tronc : x={x:+.3f} m (avant) y={y:+.3f} m (gauche) z={z:.3f} | "
            f"canard monde=({d['pos'][0]:+.3f},{d['pos'][1]:+.3f}) cap={math.degrees(trunk_yaw(d['quat'])):+.1f} deg")
