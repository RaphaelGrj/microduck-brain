#!/usr/bin/env python3
"""Canard jumeau (Quest, mode « Jumeau ») : le canard SIMULE (duck-sim) dessine en realite augmentee dans ta piece,
pilote par le vrai cerveau et la vraie appli - pour tout essayer avant la livraison.

Le simulateur (fork microduck_rl, `DUCK_SIM_GROUNDTRUTH`) ecrit la pose de chaque piece du canard et des balles ;
l'appli du canard la relaie au casque (/api/jumeau), avec ses derniers sons. Le casque peut lancer la balle
(/api/jumeau-balle, fichier de commande `DUCK_SIM_CONTROL`) et le caresser (/api/jumeau-caresse, evenement
« caresse »). Rien de tout cela n'existe sur le vrai robot : sans simulateur, ces routes repondent 404.
"""
import json
import math
import os
import time
from pathlib import Path

FRAIS_S = 3.0                   # au-dela, le simulateur est arrete
BALLES = ("testball", "ball_0", "ball_1", "ball_2")
SCENE_PLAN = "scene_maison.xml"  # scene generee depuis le plan (plan_vers_mjcf.py) : son repere EST celui du plan


def chemin_verite():
    return Path(os.environ.get("DUCK_SIM_GROUNDTRUTH", Path.home() / ".cache/duck-sim/groundtruth.json"))


def chemin_commande():
    return Path(os.environ.get("DUCK_SIM_CONTROL", Path.home() / ".cache/duck-sim/control.json"))


def lire_verite(chemin=None, frais_s=FRAIS_S):
    """La verite du simulateur, ou None (pas de simulateur, ou arrete)."""
    f = Path(chemin) if chemin is not None else chemin_verite()
    try:
        if time.time() - f.stat().st_mtime > frais_s:
            return None
        gt = json.loads(f.read_text())
    except (OSError, ValueError):
        return None
    return gt if isinstance(gt, dict) and gt.get("ducks") else None


def etat(sons=(), depuis=0.0, chemin=None):
    """-> dict pour le casque, ou None sans simulateur.
    corps : nom -> [x, y, z, qw, qx, qy, qz] (repere du simulateur, z en haut) ; balles : nom -> [x, y, z] ;
    repere : « plan » si la scene est celle du plan de la maison (le casque la pose avec son repere Quest), sinon
    « libre » (le casque demande ou poser l'origine du simulateur)."""
    gt = lire_verite(chemin)
    if gt is None:
        return None
    canard = gt["ducks"][0]
    corps = canard.get("parts") or {}
    if not corps:                       # ancien simulateur : le tronc seul
        corps = {"trunk_base": list(canard.get("pos", [0, 0, 0])) + list(canard.get("quat", [1, 0, 0, 0]))}
    corps_bodies = gt.get("bodies") or {}
    return {"t": gt.get("t"), "maintenant": round(time.time(), 3),
            "repere": "plan" if gt.get("scene") == SCENE_PLAN else "libre",
            "corps": corps,
            "balles": {n: p for n, p in corps_bodies.items() if n in BALLES},
            "sons": [[t, tag] for t, tag in sons if t > depuis]}


def _vecteur(v, borne):
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        return None
    try:
        out = [float(x) for x in v]
    except (TypeError, ValueError):
        return None
    return out if all(math.isfinite(x) and abs(x) <= borne for x in out) else None


def lancer(corps, chemin_ctl=None, chemin_gt=None):
    """{"pos": [x, y, z], "vel": [vx, vy, vz], "balle": "testball"} -> (code HTTP, reponse). Ecrit la commande que le
    simulateur applique (et efface) a sa prochaine passe."""
    if lire_verite(chemin_gt) is None:
        return 404, {"erreur": "pas de simulateur (duck-sim)"}
    pos, vel = _vecteur(corps.get("pos"), 50.0), _vecteur(corps.get("vel", [0, 0, 0]), 20.0)
    balle = corps.get("balle", "testball")
    if pos is None or vel is None or balle not in BALLES:
        return 400, {"erreur": "pos/vel attendus ([x, y, z], m et m/s)"}
    pos[2] = min(max(pos[2], 0.036), 2.0)          # jamais sous le sol
    f = Path(chemin_ctl) if chemin_ctl is not None else chemin_commande()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"throw": {balle: {"pos": pos, "vel": vel}}}))
    os.replace(tmp, f)
    return 200, {"ok": True}
