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


# -- commandes du jumeau depuis l'appli (Reglages -> Casque) ------------------------------------------------------------
SCENES = ("maison", "testball", "apartment", "arena", "arena_chat")


def fichier_scene():
    """La scene que jumeau.sh (scripts-wsl) lance au prochain tour de sa boucle."""
    return Path(os.environ.get("MICRODUCK_SCENE_VOULUE", Path.home() / ".cache/duck-sim/scene_voulue"))


def _commande(contenu, chemin_ctl=None):
    f = Path(chemin_ctl) if chemin_ctl is not None else chemin_commande()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(contenu))
    os.replace(tmp, f)


def _cap(q):
    w, x, y, z = q
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def balle_devant(chemin_ctl=None, chemin_gt=None, distance=0.6, vitesse=0.4):
    """La balle a 60 cm devant lui, qui roule doucement vers lui -> (code, reponse)."""
    gt = lire_verite(chemin_gt)
    if gt is None:
        return 404, {"erreur": "pas de simulateur (duck-sim)"}
    d = gt["ducks"][0]
    cap = _cap(d.get("quat", [1, 0, 0, 0]))
    x, y = d["pos"][0] + distance * math.cos(cap), d["pos"][1] + distance * math.sin(cap)
    _commande({"throw": {"testball": {"pos": [x, y, 0.036],
                                      "vel": [-vitesse * math.cos(cap), -vitesse * math.sin(cap), 0.0]}}}, chemin_ctl)
    return 200, {"ok": True}


def au_chargeur(chemin_ctl=None, chemin_gt=None):
    """Le canard simule remis a son point de depart (le chargeur, dans la scene de la maison) -> (code, reponse)."""
    if lire_verite(chemin_gt) is None:
        return 404, {"erreur": "pas de simulateur (duck-sim)"}
    _commande({"teleport_duck": [{"index": 0, "pos": [0.0, 0.0], "yaw": 0.0}]}, chemin_ctl)
    return 200, {"ok": True}


def demander_scene(nom):
    """Ecrit la scene voulue ; jumeau.sh relance duck-sim dessus des que le cerveau sort. -> (code, reponse)."""
    if nom not in SCENES:
        return 400, {"erreur": f"scene inconnue (au choix : {', '.join(SCENES)})"}
    if os.environ.get("MICRODUCK_JUMEAU") != "1":
        return 409, {"erreur": "le cerveau n'a pas ete lance par jumeau.sh : changer de scene a la main (run-scene.sh)"}
    f = fichier_scene()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(nom + "\n")
    return 200, {"ok": True, "redemarre": True}


def adresses_locales():
    """Les adresses IPv4 de cette machine sur le reseau local (ce qu'on tape dans le casque) : `hostname -I`, aucune
    connexion ouverte (regle : seul le pont HA parle au reseau, test_regles.py)."""
    import ipaddress
    import subprocess
    try:
        sortie = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for mot in sortie.split():
        try:
            ip = ipaddress.ip_address(mot)
        except ValueError:
            continue
        if ip.version == 4 and ip.is_private and not ip.is_loopback and mot not in out:
            out.append(mot)
    # le Wi-Fi de la maison d'abord (192.168.x), les reseaux internes (Docker, WSL...) ensuite
    return sorted(out, key=lambda a: (not a.startswith("192.168."), a))


# -- apercu du design space dans le casque (couleurs pas encore enregistrees) -------------------------------------------
APERCU_S = 15 * 60


def valider_apercu(corps):
    """{"couleurs": {groupe: "#rrggbb"}} -> dict propre, ou None (vide : fin de l'apercu)."""
    import re
    c = corps.get("couleurs") if isinstance(corps, dict) else None
    if not isinstance(c, dict) or not c:
        return None
    hexa = re.compile(r"^#[0-9a-fA-F]{6}$")
    return {str(k)[:40]: str(v).lower() for k, v in list(c.items())[:60] if hexa.match(str(v))}
