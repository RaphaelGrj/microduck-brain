#!/usr/bin/env python3
"""Tests de la main tendue (main_tendue.py + etat main_tendue de brain.py), sans robot : points ToF synthetiques."""
from brain import Brain, Humeur
from main_tendue import DetecteurMain
from test_brain import FauxClient

MUR = [(0.25, y / 100, h / 100) for y in (-10, 0, 10) for h in (5, 15)]       # un meuble a 25 cm, la depuis toujours
MAIN = [(0.12, 0.02, 0.10), (0.13, 0.0, 0.11), (0.12, -0.02, 0.09)]


def deroule(det, trames, t0=0.0, dt=0.066):
    """trames : liste de listes de points (une par trame ToF ~15 Hz). Renvoie [(t, evenements)]."""
    out = []
    for i, pts in enumerate(trames):
        t = t0 + i * dt
        out.append((t, det.mise_a_jour(pts, t)))
    return out


def evenements(res):
    return [t for t, e in res if e]


def test_main_qui_apparait():
    det = DetecteurMain()
    res = deroule(det, [[]] * 20 + [MAIN] * 10)
    ev = evenements(res)
    assert len(ev) == 1, res
    assert ev[0] >= 20 * 0.066 + 0.25 - 1e-6, "confirmation trop rapide"
    assert det.presente(res[-1][0]) and abs(det.main[1] - 0.123) < 0.01


def test_meuble_deja_la_ne_declenche_pas():
    det = DetecteurMain()
    assert evenements(deroule(det, [MUR] * 60)) == []


def test_main_devant_un_meuble():
    # le meuble est a 25 cm, la main arrive a 12 cm : 13 cm d'ecart seulement -> pas assez net... sauf si le meuble
    # est plus loin. Ici on la tend devant un meuble a 40 cm.
    det = DetecteurMain()
    loin = [(0.40, 0.0, 0.10), (0.40, 0.05, 0.10)]
    assert len(evenements(deroule(det, [loin] * 20 + [loin + MAIN] * 10))) == 1


def test_passage_bref_ignore():
    det = DetecteurMain()
    assert evenements(deroule(det, [[]] * 20 + [MAIN] * 2 + [[]] * 20)) == [], "un objet qui passe n'est pas une main"


def test_main_hors_zone_ignoree():
    det = DetecteurMain()
    haut = [(0.12, 0.0, 0.45)]          # au-dessus de 30 cm (dessus d'une table, pas une main tendue a sa hauteur)
    cote = [(0.12, 0.30, 0.10)]         # a 30 cm sur le cote
    assert evenements(deroule(det, [[]] * 20 + [haut] * 10 + [cote] * 10)) == []


def test_delai_entre_deux_mains():
    det = DetecteurMain(delai_s=20.0)
    res = deroule(det, ([[]] * 20 + [MAIN] * 10) * 3)       # trois fois en ~6 s
    assert len(evenements(res)) == 1, "ne jamais insister"
    res = deroule(det, [[]] * 20 + [MAIN] * 10, t0=30.0)
    assert len(evenements(res)) == 1


def test_pas_de_trame_fraiche():
    det = DetecteurMain()
    assert det.mise_a_jour(None, 0.0) == []


class FauxTofPoints:
    """Imite tof.Tof : points() pilotes par le test, libre() sans obstacle."""
    def __init__(self):
        self.pts = []

    def noter_etat(self, state):
        pass

    def points(self, state):
        return list(self.pts)

    def libre(self, state):
        return {"devant": 2.0, "gauche": 2.0, "droite": 2.0, "vide": float("inf"), "n": 0}


def simule(b, secondes, tof=None, main_entre=None, t0=0.0):
    for i in range(int(secondes / 0.02)):
        t = t0 + i * 0.02
        if tof is not None:
            tof.pts = MAIN if main_entre and main_entre[0] <= t < main_entre[1] else []
        b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0}}, 0.02)


def test_cerveau_picore_la_main():
    c, tof = FauxClient(), FauxTofPoints()
    b = Brain(c, Humeur(energie=0.9), seed=40, extras={"tof": tof, "exploration": False})
    b.fin_etat = 1e9                                  # reste en chill : canard immobile
    simule(b, 3.0, tof)
    simule(b, 6.0, tof, main_entre=(0.0, 4.0), t0=3.0)
    assert "main_tendue" in {e[1] for e in b.journal}, b.journal
    sons = [p["tag"] for m, p in c.appels if m == "robot.sound"]
    assert "inquire" in sons and "peck" in sons and "chirp" in sons, sons
    assert any(m == "robot.look" for m, p in c.appels), "il ne regarde pas la main"
    assert not any(m == "robot.move" and (p["vx"] or p["vyaw"]) for m, p in c.appels), "le corps ne doit pas bouger"
    assert b.courant.nom != "main_tendue", "la main est partie : l'etat doit se terminer"


def test_cerveau_pas_de_main_en_mode_calme_ni_en_marche():
    c, tof = FauxClient(), FauxTofPoints()
    b = Brain(c, Humeur(energie=0.9), seed=41, extras={"tof": tof, "exploration": False})
    b.evenement("calme_on")
    simule(b, 3.0, tof)
    simule(b, 3.0, tof, main_entre=(0.0, 3.0), t0=3.0)
    assert "main_tendue" not in {e[1] for e in b.journal}
    b = Brain(FauxClient(), Humeur(energie=0.9), seed=41, extras={"tof": tof, "exploration": False})
    b._bascule("wander")
    b.fin_etat = 1e9
    simule(b, 3.0, tof)
    simule(b, 3.0, tof, main_entre=(0.0, 3.0), t0=3.0)
    assert "main_tendue" not in {e[1] for e in b.journal}, "en marchant, un obstacle n'est pas une main"


class FauxChatVisible:
    suivi = type("S", (), {"visible": True})()
    estimation = None

    def cible_regard(self, h):
        return None


def test_cerveau_pas_de_main_si_le_chat_est_la():
    c, tof = FauxClient(), FauxTofPoints()
    b = Brain(c, Humeur(energie=0.9), seed=42, extras={"tof": tof, "exploration": False, "chat": FauxChatVisible()})
    b.fin_etat = 1e9
    simule(b, 3.0, tof)
    simule(b, 3.0, tof, main_entre=(0.0, 3.0), t0=3.0)
    assert "main_tendue" not in {e[1] for e in b.journal}
