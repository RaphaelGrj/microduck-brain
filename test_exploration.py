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

    # "coin favori" distinct par activite : memoire longue, separee de la novelty grid.
    coins = Exploration()
    for k in range(200):
        coins.preference(2.0, 2.0, "chill", 0.1, k * 0.1)       # passe 20 s en chill toujours au meme endroit
        coins.preference(-1.0, -1.0, "nap", 0.1, k * 0.1)       # et 20 s en nap ailleurs
    assert coins.coin_favori("chill", 20.0) == (2.125, 2.125)
    assert coins.coin_favori("nap", 20.0) == (-0.875, -0.875)
    assert coins.coin_favori("chill", 20.0) != coins.coin_favori("nap", 20.0), "les deux coins doivent differer"
    assert Exploration().coin_favori("chill", 0.0) is None, "rien appris : pas de coin favori"

    print("exploration : OK (evite la zone connue, prefere tout droit a nouveaute egale, oubli progressif, "
          "obstacles connus evites, zone noire apprise au point de chute, coin favori distinct par activite)")


if __name__ == "__main__":
    test()


def test_objet_nouveau_dans_une_case_ou_il_est_passe():
    from exploration import Exploration
    e = Exploration()
    e.noter(1.1, 0.1, 0.0)                         # il est passe par la (la case etait libre)
    assert e.obstacle(1.1, 0.1, 300.0), "un obstacle la ou il est passe : c'est nouveau"
    assert not e.obstacle(1.1, 0.1, 400.0), "deja remarque"
    assert not e.obstacle(3.0, 3.0, 400.0), "case jamais traversee : rien a comparer"
    e.noter(2.0, 0.0, 500.0)
    assert not e.obstacle(2.0, 0.0, 520.0), "il vient juste d'y passer : c'est lui qui bouge, pas l'objet"


def test_le_cerveau_remarque_l_objet_nouveau():
    import math
    from brain import Brain, Humeur
    from test_brain import FauxClient

    class Tof:
        def noter_etat(self, s):
            pass

        def libre(self, s):
            return {"devant": 0.6, "gauche": 2.0, "droite": 2.0, "vide": math.inf, "n": 3}

    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=600, extras={"tof": Tof(), "exploration": False})
    b.exploration.noter(0.6, 0.0, 0.0)            # il etait passe la, il y a longtemps
    b.t_global = 1000.0
    b._bascule("wander")
    b.fin_etat = 1e9
    for i in range(100):
        b.tick({"t": i * 0.02, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0}}, 0.02)
    noms = [e[1] for e in b.journal]
    assert "remarque" in noms, noms
    assert any(m == "robot.sound" and p == {"tag": "inquire"} for m, p in c.appels)
    assert len(b.objets_au_sol) == 1 and b.objets_au_sol[0][1:] == (0.6, 0.0), "signale a Home Assistant"
