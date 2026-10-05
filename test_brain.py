#!/usr/bin/env python3
"""Tests du cerveau sans robot : faux client, temps simule (1 trame = 20 ms)."""
from brain import Brain, Humeur


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
