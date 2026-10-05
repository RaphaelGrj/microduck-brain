#!/usr/bin/env python3
"""Tests du cerveau sans robot : faux client, temps simule (1 trame = 20 ms)."""
import math

from brain import Brain, Humeur, fatigue, FATIGUE_PLEIN, FATIGUE_BAS, FATIGUE_MIN, V_PROMENADE


class FauxClient:
    def __init__(self):
        self.appels = []

    def notify(self, method, params=None):
        self.appels.append((method, params))

    def request(self, method, params=None, **kw):
        self.appels.append((method, params))
        return {"result": {"accepted": True}}


def simule(brain, secondes, tombe_entre=None, evenements=None):
    evenements = sorted(evenements or [])
    n = int(secondes / 0.02)
    for i in range(n):
        t = i * 0.02
        while evenements and evenements[0][0] <= t:
            brain.evenement(evenements.pop(0)[1])
        fallen = bool(tombe_entre and tombe_entre[0] <= t < tombe_entre[1])
        # policy="stand" hors chute : imite robotd, qui annonce toujours une politique active (ici debout immobile) ;
        # sans ce champ le cerveau ne peut jamais detecter le relevement (policy reste a None pour toujours).
        policy = None if fallen else "stand"
        brain.tick({"t": t, "safety": {"fallen": fallen}, "policy": policy}, 0.02)


def nb(client, skill):
    return sum(1 for m, p in client.appels if m == "robot.do" and p == {"skill": skill})


def test_diversite_et_bornes():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=1)
    simule(b, 400)
    vus = {e[1] for e in b.journal}
    assert len(vus) >= 3, f"trop peu d'etats visites: {vus}"
    assert 0.0 <= b.humeur.energie <= 1.0 and 0.0 <= b.humeur.eveil <= 1.0


def test_sieste_quand_fatigue_et_se_leve():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.1), seed=2)
    simule(b, 120)
    assert "nap" in {e[1] for e in b.journal}, "pas de sieste malgre energie basse"
    b.arret()
    assert nb(c, "sit_toggle") % 2 == 0, "le canard est reste assis (toggles impairs)"
    assert not b.ctx.sitting


def test_arret_au_milieu_de_la_sieste_releve():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.1), seed=3)
    # on coupe pendant la sieste (apres l'assise, avant le reveil)
    simule(b, 12)
    assert b.courant.nom == "nap" and b.ctx.sitting
    b.arret()
    assert not b.ctx.sitting and nb(c, "sit_toggle") % 2 == 0


def test_bruit_declenche_sursaut_et_eveil():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9, eveil=0.0), seed=4)
    simule(b, 10, evenements=[(5.0, "bruit")])
    assert any(e[1] == "startle" for e in b.journal)
    moves = [p for m, p in c.appels if m == "robot.move" and p["vx"] < 0]
    assert moves, "pas de recul pendant le sursaut"


def test_evenement_ignore_pendant_sieste():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.1), seed=5)
    # le chill initial dure <= ~11 s, la sieste dure >= 18 s : a 18 s on dort forcement
    simule(b, 20, evenements=[(18.0, "bruit")])
    assert b.courant.nom == "nap"
    assert not any(e[1] == "startle" for e in b.journal)


def test_chute_met_le_cerveau_en_pause():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=6)
    simule(b, 30, tombe_entre=(10.0, 20.0))
    # verifie : pas de changement d'etat pendant la chute, et reprise ensuite
    assert b.tombe is False
    j = [e for e in b.journal if 10.0 <= e[0] < 20.0]
    assert not j, f"transition pendant la chute: {j}"


def test_reves_pendant_sieste_profonde():
    # sieste assez longue pour garantir une phase de sommeil profond -> au moins un tressaillement de tete
    # (robot.head avec un petit yaw non nul), jamais pendant les 2 premieres s (endormissement) ni les 4
    # dernieres (reveil).
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.1), seed=11)
    simule(b, 30)
    assert b.courant.nom in ("nap", "etirement"), f"pas en sieste: {b.courant.nom}"
    nap = b.etats["nap"]
    assert nap.total - 2.0 - 4.0 >= 3.0, "la sieste de ce test doit avoir une phase profonde"
    yaws = [p["head_yaw"] for m, p in c.appels if m == "robot.head" and p["head_yaw"] != 0.0]
    assert yaws, "aucun tressaillement de tete pendant la sieste"
    for t0, duree, _ in nap.reves:
        assert t0 >= 2.0 and t0 + duree <= nap.total - 4.0, f"reve hors de la phase profonde: {t0}, {duree}"


def test_rituel_depart_signe_discret():
    # un depart (presence HA) declenche le petit rituel discret, pas une fete, et met bien a jour presents/memoire.
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=12)
    b.presents.add("Raphael")
    simule(b, 5, evenements=[(2.0, "depart:Raphael")])
    assert "rituel_depart" in {e[1] for e in b.journal}, f"pas de rituel au depart: {b.journal}"
    assert "Raphael" not in b.presents


def test_rituel_depart_ignore_pendant_sieste():
    # ne jamais interrompre une sieste pour un simple depart (pas d'insistance, coherent avec l'accueil au retour).
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.1), seed=13)
    simule(b, 20, evenements=[(18.0, "depart:Raphael")])
    assert b.courant.nom == "nap"
    assert "rituel_depart" not in {e[1] for e in b.journal}


def test_fatigue_progressive_amplitude_tete():
    # fatigue() ne descend jamais sous FATIGUE_MIN, reste a 1.0 bien reposee, et un "look" a basse energie a une
    # amplitude de tete reduite par rapport a un "look" bien repose - jamais vx/vyaw (zone morte de la marche).
    c = FauxClient()
    b_repose = Brain(c, Humeur(energie=0.9), seed=20)
    assert fatigue(b_repose) == 1.0
    b_fatigue = Brain(c, Humeur(energie=FATIGUE_BAS), seed=21)
    assert abs(fatigue(b_fatigue) - FATIGUE_MIN) < 1e-9
    b_mi = Brain(c, Humeur(energie=(FATIGUE_PLEIN + FATIGUE_BAS) / 2), seed=22)
    assert FATIGUE_MIN < fatigue(b_mi) < 1.0

    c2 = FauxClient()
    b2 = Brain(c2, Humeur(energie=0.3), seed=23)
    b2._bascule("look")
    yaws_fatigue = []
    for i in range(300):
        b2.courant.pas(b2, i * 0.02)
    yaws_fatigue = [p["head_yaw"] for m, p in c2.appels if m == "robot.head"]
    c3 = FauxClient()
    b3 = Brain(c3, Humeur(energie=0.9), seed=24)
    b3._bascule("look")
    for i in range(300):
        b3.courant.pas(b3, i * 0.02)
    yaws_repose = [p["head_yaw"] for m, p in c3.appels if m == "robot.head"]
    assert max(abs(y) for y in yaws_fatigue) < max(abs(y) for y in yaws_repose), \
        "l'amplitude de tete en 'look' devrait etre reduite a basse energie"


def test_coin_favori_accumule_pendant_chill():
    # tick() avec odom connu, en chill, accumule bien la preference pour le coin favori ("deux coins favoris
    # distincts selon l'activite").
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=14)
    assert b.courant.nom == "chill"
    for i in range(50):      # 1 s, toujours a la meme position
        b.tick({"t": i * 0.02, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [0.6, 0.6, 0.0], "yaw": 0.0}}, 0.02)
    favori = b.exploration.coin_favori("chill", b.t_global)
    assert favori is not None, "aucun coin favori appris pendant le chill"
    assert favori == (int(0.6 // 0.25) * 0.25 + 0.125, int(0.6 // 0.25) * 0.25 + 0.125)


class FauxTof:
    """Imite tof.py.Tof.libre() : couloir etroit des deux cotes, rien devant."""
    def libre(self, state):
        return {"devant": 2.0, "gauche": 0.3, "droite": 0.3, "vide": math.inf, "n": 10}


def test_pause_avant_passage_etroit():
    # Wander marque une pause (vx=0) avant de s'engager dans un passage etroit detecte par le ToF, puis reprend
    # la marche normale - une seule pause par traversee, pas un arret repete (ROADMAP "chantier actif").
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=15, extras={"tof": FauxTof(), "exploration": False})
    b.ctx.state = {"t": 0.0, "odom": {"position": [0.0, 0.0], "yaw": 0.0}}
    b._bascule("wander")
    w = b.etats["wander"]
    for i in range(20):                              # 0.4 s de reglage de la tete, pas encore de detection
        w.pas(b, i * 0.02)
    assert w.pause_jusqua is None
    w.pas(b, 0.42)                                    # premiere trame post-reglage : couloir etroit detecte
    assert w.pause_faite and w.pause_jusqua is not None
    assert [p["vx"] for m, p in c.appels if m == "robot.move"][-1] == 0.0
    w.pas(b, 0.42 + 0.6 + 0.02)                        # fin de la pause (detectee cette trame, encore immobile)
    assert w.pause_jusqua is None
    w.pas(b, 0.42 + 0.6 + 0.04)                        # trame suivante : reprend la marche normale
    assert [p["vx"] for m, p in c.appels if m == "robot.move"][-1] == V_PROMENADE


def test_chute_memorise_une_zone_noire():
    # une chute avec odom connu note une "zone noire" a l'endroit precis (exploration.py), pas seulement
    # la pause du cerveau deja testee par test_chute_met_le_cerveau_en_pause.
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=10)
    for i in range(50):      # 1 s, debout, odom connu a (1.2, 0.3)
        b.tick({"t": i * 0.02, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [1.2, 0.3, 0.0], "yaw": 0.0}}, 0.02)
    b.tick({"t": 1.0, "safety": {"fallen": True}, "policy": None}, 0.02)   # chute, sans odom dans cette trame
    assert b.exploration.chutes, "aucune zone noire memorisee a la chute"
    cle = next(iter(b.exploration.chutes))
    assert cle == (int(1.2 // 0.25), int(0.3 // 0.25)), f"mauvaise case memorisee: {cle}"


class FauxVeilleChat:
    """Imite VeilleChat (chat.py) juste assez pour _choisit_suivant/RechercheAttention.pas : .suivi.visible pour
    le choix de cible, .estimation=None pour que pas() se contente du regard qui balaie (pas de position connue)."""
    def __init__(self, visible):
        class _Suivi:
            pass
        self.suivi = _Suivi()
        self.suivi.visible = visible
        self.estimation = None


def test_ennui_sans_personne_disponible_jeu_solitaire():
    # personne a la maison, pas de chat visible : au-dela de SEUIL_ENNUI_S sans interaction, le canard
    # s'occupe seul plutot que de rester simplement passif en chill.
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=7)
    simule(b, 650)
    assert "jeu_solitaire" in {e[1] for e in b.journal}, f"pas de jeu solitaire apres l'ennui: {b.journal}"
    assert "cherche_attention" not in {e[1] for e in b.journal}


def test_ennui_avec_humain_present_cherche_attention():
    # un habitant est present (retour/depart HA, pas un evenement ici pour ne pas remettre a zero le
    # compteur d'ennui) : le canard va chercher son attention plutot que de jouer seul.
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=8)
    b.presents.add("Raphael")
    simule(b, 650)
    assert "cherche_attention" in {e[1] for e in b.journal}, f"pas de recherche d'attention: {b.journal}"
    assert b.etats["cherche_attention"].cible == "humain"
    assert "jeu_solitaire" not in {e[1] for e in b.journal}


def test_ennui_avec_chat_visible_cherche_attention():
    # pas d'habitant present, mais le chat est visible a la camera : cible = "chat".
    c = FauxClient()
    chat = FauxVeilleChat(visible=True)
    b = Brain(c, Humeur(energie=0.9), seed=9, extras={"chat": chat})
    simule(b, 650)
    assert "cherche_attention" in {e[1] for e in b.journal}, f"pas de recherche d'attention: {b.journal}"
    assert b.etats["cherche_attention"].cible == "chat"


if __name__ == "__main__":
    import sys
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    echecs = 0
    for t in tests:
        try:
            t()
            print(f"OK    {t.__name__}")
        except AssertionError as e:
            echecs += 1
            print(f"ECHEC {t.__name__}: {e}")
    sys.exit(1 if echecs else 0)
