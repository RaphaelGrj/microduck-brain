#!/usr/bin/env python3
"""Le banc de validation duck-sim ne peut pas tourner sans simulateur ; on verifie au moins qu'il s'importe SANS
toucher au robot, que chaque scenario est declare proprement, et que la liste s'affiche."""
import subprocess
import sys
from pathlib import Path

import valider_sim


def test_scenarios_declares():
    assert {"promenade", "main_fantome", "coin_sieste", "jeu_balle", "soleil", "aspirateur", "cascades",
            "pousse_balle"} <= set(valider_sim.SCENARIOS)
    for nom, (scene, fn, desc) in valider_sim.SCENARIOS.items():
        assert scene in ("apartment", "arena") and callable(fn) and desc, nom


def test_liste_sans_simulateur():
    r = subprocess.run([sys.executable, str(Path(valider_sim.__file__)), "--liste"], capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0 and "jeu_balle" in r.stdout


def test_devant_repere_du_canard():
    import math
    gt = {"ducks": [{"pos": [1.0, 2.0, 0.1], "quat": [math.cos(math.pi / 4), 0, 0, math.sin(math.pi / 4)]}]}
    x, y = valider_sim.devant(gt, 0.5, 0.0)            # canard tourne de 90 deg : "devant" = +y monde
    assert abs(x - 1.0) < 1e-9 and abs(y - 2.5) < 1e-9
