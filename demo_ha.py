#!/usr/bin/env python3
"""Demonstration de bout en bout contre duck-sim : faux Home Assistant local + pont + cerveau.

Scenario (temps depuis le debut) : 4 s impression demarre, 10 s impression terminee (MK4S), 20 s echec
(Saturn). On mesure sur le robot SIMULE : amplitude reelle de la tete pendant chaque reaction, acceptation de
`robot.sound` (le journal de robotd), et ce que le canard a publie dans le faux HA.

Usage : bash ~/run-brain.sh demo_ha.py [duree_s=32]
"""
import sys
import threading
import time

import brain
import mock_ha
import pont_ha
from poc_robotd_client import RobotdClient, SOCK_PATH

DUREE = float(sys.argv[1]) if len(sys.argv) > 1 else 32.0
JETON = "JETON_DE_TEST"
CFG = {"surveillance": [
    {"entite": "sensor.prusa_mk4s", "nom": "MK4S",
     "reactions": {"finished": "impression_finie", "error": "impression_echec", "printing": "impression_commencee"}},
    {"entite": "sensor.elegoo_saturn", "nom": "Saturn", "reactions": {"Failed": "impression_echec"}},
], "publier_toutes_les_s": 5}

ha = mock_ha.MockHA(JETON)
pont = pont_ha.PontHA({**CFG, "url": ha.url, "url_ws": ha.url_ws}, JETON, log=lambda m: print(m, flush=True))
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
pont.demarrer()


def scenario():
    for t, entite, etat in ((4, "sensor.prusa_mk4s", "printing"), (10, "sensor.prusa_mk4s", "finished"),
                            (20, "sensor.elegoo_saturn", "Failed")):
        time.sleep(max(0.0, t - (time.monotonic() - t0)))
        print(f"--- HA ({t} s) : {entite} -> {etat}", flush=True)
        ha.set_state(entite, etat)


amplitudes = {}
etat_prec = {"nom": None, "base": None, "pic": None}


def mesure(b, state):
    """Memorise, par etat du cerveau, l'amplitude max de la tete par rapport a sa position au debut de l'etat."""
    pont.photographier(b, state)
    nom = b.courant.nom
    tete = state["joints"][5:9]
    if nom != etat_prec["nom"]:
        etat_prec.update(nom=nom, base=list(tete), pic=[0.0] * 4)
    for i in range(4):
        etat_prec["pic"][i] = max(etat_prec["pic"][i], abs(tete[i] - etat_prec["base"][i]))
    amplitudes[nom] = [round(v, 2) for v in etat_prec["pic"]]


t0 = time.monotonic()
threading.Thread(target=scenario, daemon=True).start()
try:
    brain.run(c, DUREE, source=pont.source, a_chaque_tick=mesure, seed=3)
finally:
    pont.stop()

print("\n=== bilan ===")
for nom in ("info", "celebre", "alerte"):
    print(f"  etat {nom:8s}: amplitude max de la tete (cou, tete, lacet, roulis) = {amplitudes.get(nom)}")
print("  entites publiees dans le faux HA :")
for e, v in sorted(ha.etats.items()):
    if e.startswith(("sensor.microduck", "binary_sensor.microduck")):
        print(f"    {e} = {v['state']}")
ha.arreter()
