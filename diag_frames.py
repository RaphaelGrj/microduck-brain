#!/usr/bin/env python3
"""Affiche le contenu de `frames` et `odom` d'une trame robot.state, pour la geometrie camera."""
import json

from poc_robotd_client import RobotdClient, SOCK_PATH

c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
s = c.read_state_frame()
print("cles :", sorted(s.keys()))
print("frames :", json.dumps(s.get("frames"), indent=1)[:1500])
print("odom :", s.get("odom"))
print("head :", s.get("head"))
m = c.request("robot.model", {})
print("model :", json.dumps(m, indent=1)[:2500])
