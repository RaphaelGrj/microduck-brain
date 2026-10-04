#!/usr/bin/env python3
"""Charge un fichier ONNX dans un slot de robotd (robot.loadPolicy), ou remet la politique officielle.

Usage : bash ~/run-brain.sh charge_politique.py <slot> <chemin.onnx | officielle>
  ex.   bash ~/run-brain.sh charge_politique.py kick_right ~/.cache/duck-sim/policies/tol/kick_tol_right.onnx
        bash ~/run-brain.sh charge_politique.py kick_right officielle

robotd ecrit le choix dans son robotd.toml (persistant) : toujours remettre l'officielle apres un essai.
"""
import os
import sys

from poc_robotd_client import RobotdClient, SOCK_PATH

OFFICIELLES = {
    "kick_right": "~/.cache/duck-sim/policies/current/ball_kick_right.onnx",
    "kick_left": "~/.cache/duck-sim/policies/current/ball_kick_left.onnx",
}

slot, chemin = sys.argv[1], sys.argv[2]
if chemin == "officielle":
    chemin = OFFICIELLES[slot]
chemin = os.path.abspath(os.path.expanduser(chemin))
if not os.path.isfile(chemin):
    sys.exit(f"fichier introuvable : {chemin}")

c = RobotdClient(SOCK_PATH)
print(c.request("robot.loadPolicy", {"slot": slot, "path": chemin}))
print(c.request("robot.policies", {}))
