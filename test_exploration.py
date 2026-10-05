#!/usr/bin/env python3
"""Tests de la memoire d'exploration (sans robot). Usage : bash ~/run-brain.sh test_exploration.py"""
import math

from exploration import Exploration


def test():
    e = Exploration()
    for k in range(20):                          # le canard a fait des allers-retours vers l'est (x > 0)
        for x in (0.0, 0.25, 0.5, 0.75, 1.0):
            e.noter(x, 0.0, t=k)
    assert e.nouveaute(0, 0, 0.0, 20) < 0.1, "l'est est connu"
    assert e.nouveaute(0, 0, math.pi / 2, 20) > 0.6, "le nord est nouveau"
    ecart = e.meilleur_ecart(0, 0, 0.0, 20)      # cap actuel : est
    assert abs(math.degrees(ecart)) > 29.9 and e.nouveaute(0, 0, ecart, 20) > 0.6, f"doit quitter la zone connue ({math.degrees(ecart):.0f} deg)"
    assert e.nouveaute(0, 0, 0.0, 20 + 3 * 600) > e.nouveaute(0, 0, 0.0, 20), "l'oubli rend la zone a nouveau interessante"
    murs = Exploration()                         # un mur connu a 40 cm a l'est : on n'y va pas, meme si c'est "nouveau"
    murs.obstacle(0.4, 0.05, 0)
    assert murs.nouveaute(0, 0, 0.0, 1) < 0.3 and abs(murs.meilleur_ecart(0, 0, 0.0, 1)) > 0, "le mur doit detourner"
    vierge = Exploration()
    assert vierge.meilleur_ecart(0, 0, 1.0, 0) == 0.0, "sans souvenir : tout droit"

    # "zone noire" apprise (ROADMAP "Occupation autonome...") : un point precis ou le canard est deja tombe
    # doit etre evite comme un obstacle, meme si rien n'y est jamais detecte par le ToF.
    zone_noire = Exploration()
    zone_noire.chute(0.4, 0.05, 0)
    assert zone_noire.nouveaute(0, 0, 0.0, 1) < 0.3 and abs(zone_noire.meilleur_ecart(0, 0, 0.0, 1)) > 0, \
        "le point de chute doit detourner comme un obstacle"
    assert zone_noire.nouveaute(0, 0, 0.0, 10 * 86400) < 0.3, "la zone noire ne s'oublie pas en quelques jours"

    print("exploration : OK (evite la zone connue, prefere tout droit a nouveaute egale, oubli progressif, "
          "obstacles connus evites, zone noire apprise au point de chute)")


if __name__ == "__main__":
    test()
