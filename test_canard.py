#!/usr/bin/env python3
"""Test du lanceur canard.py : assemblage selon ce qui est disponible, puis une seconde de vie complete contre un faux
robotd (aucun reseau, aucune camera : les fils ne sont pas demarres)."""
import tempfile
from pathlib import Path

import brain
import canard
import memoire
import tof as tof_mod


class FauxRobotd:
    def __init__(self):
        self.appels, self.t = [], 0.0

    def notify(self, method, params=None):
        self.appels.append((method, params))

    def request(self, method, params=None, **kw):
        self.appels.append((method, params))
        if method == "robot.model":
            return {"result": {"tof_beams": [[1.0, 0.0, 0.0]] * 64}}
        return {"result": {"accepted": True}}

    def read_state_frame(self):
        self.t += 0.02
        return {"t": self.t, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0}, "battery": {"percent": 80.0}}


def _assemble(args, sock_tof_existe, cfg=None):
    with tempfile.TemporaryDirectory() as d:
        ancien_sock, ancienne_mem = tof_mod.SOCK_TOF, memoire.Memoire
        tof_mod.SOCK_TOF = Path(d) / "tof.sock"
        if sock_tof_existe:
            tof_mod.SOCK_TOF.touch()
        memoire.Memoire = lambda: ancienne_mem(Path(d) / "memoire.json")
        try:
            return canard.assembler(FauxRobotd(), args, log=lambda m: None, cfg=cfg)
        finally:
            tof_mod.SOCK_TOF, memoire.Memoire = ancien_sock, ancienne_mem


def test_assemblage_selon_disponibilite():
    a = _assemble([], sock_tof_existe=True)
    assert set(a["extras"]) == {"memoire", "tof", "mouvement"}, a["extras"]
    assert len(a["extras"]["tof"].beams) == 64 and a["pont"] is None and a["options"] == {}
    a = _assemble(["--sans-camera"], sock_tof_existe=False)
    assert set(a["extras"]) == {"memoire"}, "sans tofd ni camera : seulement la memoire"


def test_assemblage_avec_home_assistant():
    cfg = {"url": "http://ha.local:8123", "token": "JETON", "surveillance": [], "publier_toutes_les_s": 30,
           "cerveau": {"heures_calmes": [23, 7], "bonjour": "7:30"}}
    a = _assemble(["--sans-camera"], sock_tof_existe=False, cfg=cfg)
    assert a["pont"] is not None and a["options"] == {"heures_calmes": (23, 7), "bonjour": (7, 30)}
    assert a["pont"].source in a["sources"] and a["pont"].photographier in a["crochets"]


def test_une_seconde_de_vie():
    a = _assemble([], sock_tof_existe=False)
    c = FauxRobotd()
    b = brain.run(c, 1.0, source=lambda: [e for s in a["sources"] for e in s()], extras=a["extras"], seed=1)
    assert b.t_global > 0.5 and any(m == "robot.head" for m, _ in c.appels)
