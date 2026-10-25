"""Validation dans duck-sim du branchement des gestes RL dans le cerveau (skills_rl.py).

Installe startle/frisson/curieux comme vrais skills (robot.setSkill), lance le cerveau avec skills_rl=True, declenche les
etats startle / ebouriffe / curious par evenements, et releve : robot.do envoyes, politiques vues, chutes, deplacement.
Retire les skills a la fin.

Usage : PYTHONPATH=~/microduck-brain bash ~/run-brain.sh ~/skills_rl_sim.py
"""
import json
import math
import os
import sys
import time

import brain
from poc_robotd_client import RobotdClient, SOCK_PATH

POL = os.path.expanduser("~/.cache/duck-sim/policies")
TOUS = {"startle": (f"{POL}/startle/startle.onnx", 1.2),
          "frisson": (f"{POL}/shiver/shiver.onnx", 1.3),
          "curieux": (f"{POL}/gestes2/crouch.onnx", 1.3)}
SKILLS = {k: v for k, v in TOUS.items() if k in sys.argv[1:]} or TOUS
GT = os.path.expanduser("~/.cache/duck-sim/groundtruth.json")


def pos():
    try:
        d = json.load(open(GT))["ducks"][0]
        return d["pos"]
    except (OSError, ValueError, KeyError, IndexError):
        return None


class Espion:
    """Enveloppe le client : memorise les robot.do et les trames."""
    def __init__(self, c):
        self.c, self.do, self.pols, self.tombe = c, [], set(), False

    def notify(self, m, p=None):
        return self.c.notify(m, p)

    def request(self, m, p=None, **kw):
        r = self.c.request(m, p, **kw)
        if m == "robot.do":
            self.do.append((round(time.monotonic() - self.t0, 1), p.get("skill"), "error" in r))
        return r

    def read_state_frame(self):
        s = self.c.read_state_frame()
        self.pols.add(s.get("policy"))
        self.tombe = self.tombe or bool((s.get("safety") or {}).get("fallen"))
        return s


c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
for nom, (chemin, duree) in SKILLS.items():
    print("setSkill", nom, c.request("robot.setSkill", {"name": nom, "path": chemin, "duration": duree}).get("result", "ERR"))
time.sleep(5)
print("skills installes :", c.request("robot.skills"))
t0 = time.monotonic()
while True:
    s = c.read_state_frame()
    if s["policy"] in ("walk", "stand") and not s["safety"]["limp"] and time.monotonic() - t0 > 1.5:
        break
    if time.monotonic() - t0 > 25:
        print("pas debout :", s["policy"], s["safety"])
        sys.exit(1)
esp = Espion(c)
esp.t0 = time.monotonic()
p0 = pos()
evts = [(2, "bruit"), (8, "personne")]
force = {"fait": False}


def crochet(b, state):
    if not force["fait"] and b.t_global >= 14:
        force["fait"] = True
        b._bascule("ebouriffe")

try:
    brain.run(esp, 20, evenements=evts, seed=3, a_chaque_tick=crochet, skills_rl=("--off" not in sys.argv))
finally:
    p1 = pos()
    if p0 and p1:
        print(f"deplacement total {math.hypot(p1[0]-p0[0], p1[1]-p0[1])*100:.1f} cm")
    print("robot.do :", esp.do)
    print("politiques vues :", sorted(x for x in esp.pols if x))
    print("chute :", esp.tombe)
    for nom in SKILLS:
        print("removeSkill", nom, c.request("robot.removeSkill", {"name": nom}).get("result", "ERR"))
