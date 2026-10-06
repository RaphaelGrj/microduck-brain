#!/usr/bin/env python3
"""Banc de cout du cerveau, a lancer SUR le canard a la livraison (RK3566) : la boucle de robotd envoie une trame toutes
les 20 ms, le cerveau doit en traiter une bien plus vite. Simule `--duree` secondes de vie (tous les capteurs factices,
evenements au hasard, sans robotd) et mesure le temps de Brain.tick (moyenne, p99, max) puis une sauvegarde de memoire
pleine (plusieurs mois de vie).

Mesures 2026-10-06 sur PC (x86) : tick 0,027 ms en moyenne, p99 0,083 ms, max 2,2 ms ; memoire ~60 Ko, mise en JSON
~1 ms. Sur le RK3566 (Cortex-A55), compter 5 a 10 fois plus : on doit rester loin sous 20 ms.

    uv run python bench_cerveau.py [--duree 1800]
"""
import argparse
import contextlib
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

from brain import Brain, Humeur
from diagnostic import Diagnostic
from memoire import Memoire
from test_endurance import ApprocheFactice, Client, EVENEMENTS_MARCHE, Leurre, TofAleatoire


def bench_tick(duree):
    rng = random.Random(3)
    tof, leurre = TofAleatoire(rng), Leurre(rng)
    leurre.dernier_centre = None
    leurre.armer = lambda periode_s=None: None
    ref = [None]
    with tempfile.TemporaryDirectory() as d:
        mem = Memoire(Path(d) / "m.json", ecriture_differee=True)
        b = Brain(Client(ref), Humeur(energie=0.8), seed=3,
                  extras={"tof": tof, "balle": leurre, "mouvement": leurre, "chat": leurre, "memoire": mem,
                          "fabrique_approche": ApprocheFactice, "circadien": True, "autotest": True, "repas": [(12, 30)]})
        ref[0] = b
        b.presents.add("Raphael")
        durees, t, prochain = [], 0.0, 5.0
        with open(os.devnull, "w") as nul, contextlib.redirect_stdout(nul):
            while t < duree:
                if t >= prochain:
                    b.evenement(rng.choice(EVENEMENTS_MARCHE))
                    prochain = t + rng.expovariate(1 / 30.0)
                s = {"t": t, "safety": {"fallen": False}, "policy": "stand", "battery": {"percent": 70.0 - t / 600.0},
                     "odom": {"position": [rng.uniform(-2, 2), rng.uniform(-2, 2), 0.11], "yaw": 0.0},
                     "joints": [0.0] * 15, "targets": [0.0] * 15, "currents_ma": [100.0] * 15}
                t0 = time.perf_counter()
                b.tick(s, 0.02)
                durees.append(time.perf_counter() - t0)
                t += 0.02
        mem.vider()
    durees.sort()
    return statistics.mean(durees), durees[int(0.99 * len(durees))], durees[-1], len(durees)


def bench_memoire():
    """Memoire de plusieurs mois : 400 cycles de batterie, 60 jours de mesures des servos, 300 chutes, 30 etres."""
    with tempfile.TemporaryDirectory() as d:
        m = Memoire(Path(d) / "m.json")
        vraie = m.sauver
        m.sauver = lambda: None
        diag = Diagnostic(m, mur=lambda: 1.7e9)
        for k in range(400):
            for dt, p in ((0, 100.0), (3600, 30.0), (3700, 40.0)):
                diag.batterie.note(1.7e9 + k * 7200 + dt, p)
        for j in range(60):
            for _ in range(600):
                diag.servos.note_repos(f"j{j:03d}", [0.0] * 15, [0.01] * 15, [100.0] * 15)
        for k in range(300):
            diag.chutes.note(1.7e9 + k * 3600, "wander", (random.random(), random.random()), 1)
        for n in range(30):
            m.rencontre(f"etre{n}")
        m.sauver = vraie
        t0 = time.perf_counter()
        for _ in range(20):
            m.sauver()
        return (time.perf_counter() - t0) / 20, os.path.getsize(Path(d) / "m.json")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--duree", type=float, default=1800.0, help="secondes de vie simulees")
    a = p.parse_args(argv)
    moy, p99, mx, n = bench_tick(a.duree)
    print(f"Brain.tick sur {n} trames : moyenne {moy * 1e3:.3f} ms, p99 {p99 * 1e3:.3f} ms, max {mx * 1e3:.2f} ms "
          f"(budget : 20 ms)")
    dt, taille = bench_memoire()
    print(f"sauvegarde de la memoire ({taille / 1024:.0f} Ko) : {dt * 1e3:.2f} ms")
    return 0 if mx < 0.020 else 1


if __name__ == "__main__":
    sys.exit(main())
