#!/usr/bin/env python3
"""Mesure ce que coute l'ensemble pont Home Assistant + cerveau (le profil d'un petit Raspberry Pi) :
memoire residente max et part de coeur CPU utilisee, contre duck-sim. Usage : bash ~/run-brain.sh bench_pont.py [duree_s]
"""
import resource
import sys
import time

import brain
import mock_ha
import pont_ha
from poc_robotd_client import RobotdClient, SOCK_PATH

DUREE = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
JETON = "T"
ha = mock_ha.MockHA(JETON)
cfg = {"url": ha.url, "url_ws": ha.url_ws, "surveillance": [], "publier_toutes_les_s": 10}
pont = pont_ha.PontHA(cfg, JETON, log=lambda m: None)
c = RobotdClient(SOCK_PATH)
import os
hz = int(os.environ.get("HZ", "0"))
c.request("robot.subscribe", {"hz": hz} if hz else {})
pont.demarrer()
cpu0, t0 = time.process_time(), time.monotonic()
trames = [0]


def tick(b, state):
    trames[0] += 1
    pont.photographier(b, state)


import io
import contextlib
with contextlib.redirect_stdout(io.StringIO()):          # le cerveau est bavard
    brain.run(c, DUREE, a_chaque_tick=tick, source=pont.source, seed=1)
cpu, dt = time.process_time() - cpu0, time.monotonic() - t0
pont.stop()
ha.arreter()
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
print(f"{trames[0]} trames en {dt:.0f} s ({trames[0] / dt:.0f}/s) ; CPU = {100 * cpu / dt:.1f} % d'un coeur ; "
      f"memoire residente max = {rss:.0f} Mo (Python {sys.version.split()[0]}, avec le faux HA dans le meme processus)")
