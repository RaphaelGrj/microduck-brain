#!/usr/bin/env python3
"""Tests du cerveau sans robot : faux client, temps simule (1 trame = 20 ms)."""
import math

from brain import Brain, Humeur, RegardeChat, fatigue, FATIGUE_PLEIN, FATIGUE_BAS, FATIGUE_MIN, V_PROMENADE


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
    if nap.reves:
        assert any(m == "robot.sound" and p == {"tag": "chirp"} for m, p in c.appels), \
            "aucun murmure sonore pendant un reve"
    for t0, duree, _, _ in nap.reves:
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


def test_ebrouement_apres_longue_immobilite_reelle():
    # odom quasi fixe pendant SEUIL_IMMOBILE_S depuis un etat de repos (chill) -> ebouriffe se declenche, sans
    # attendre le tirage RARES habituel (ici rendu impossible : rng truque pour ne jamais le tirer au hasard).
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=16)
    b._bascule("chill")
    b.fin_etat = 10 ** 9              # on reste en chill (pas de bascule naturelle, donc pas de tirage RARES non
                                       # plus) pour isoler l'effet de l'immobilite elle-meme
    n = int((Brain.SEUIL_IMMOBILE_S + 2.0) / 0.02)
    for i in range(n):
        t = i * 0.02
        b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [3.0, 3.0, 0.0], "yaw": 0.0}}, 0.02)
    assert "ebouriffe" in {e[1] for e in b.journal}, f"pas d'ebrouement apres une longue immobilite: {b.journal}"


def test_ebrouement_immobilite_pas_declenche_si_ca_bouge():
    # le meme odom, mais qui derive doucement au-dela de SEUIL_DEPLACEMENT a chaque fois : jamais d'ebrouement
    # "immobilite" (la reference se redemarre en continu).
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=17)
    b._bascule("chill")
    b.fin_etat = 10 ** 9
    n = int((Brain.SEUIL_IMMOBILE_S + 2.0) / 0.02)
    for i in range(n):
        t = i * 0.02
        x = 3.0 + 0.2 * t            # derive continue, toujours > SEUIL_DEPLACEMENT par rapport a la reference
        b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [x, 3.0, 0.0], "yaw": 0.0}}, 0.02)
    assert "ebouriffe" not in {e[1] for e in b.journal}


def test_batterie_basse_force_le_repos():
    # une VRAIE batterie basse (state["battery"]["percent"]) force le repos (nap) meme avec une energie "jouee"
    # (Humeur) au maximum - anticipation plutot qu'arret force (ROADMAP "chantier actif").
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.95), seed=18)
    for i in range(2000):
        t = i * 0.02
        b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand", "battery": {"percent": 18.0}}, 0.02)
        if b.courant.nom == "nap":
            break
    assert b.courant.nom == "nap", "la batterie basse doit forcer le repos malgre une energie jouee elevee"


def test_batterie_normale_ne_force_pas_le_repos():
    # a l'inverse, une batterie correcte ne doit rien changer au comportement habituel (energie jouee elevee).
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.95), seed=19)
    for i in range(2000):
        t = i * 0.02
        b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand", "battery": {"percent": 80.0}}, 0.02)
    assert b.courant.nom != "nap"


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


def test_integration_longue_simulation_toutes_fonctions():
    # filet de securite : depart, retour, chute et ennui dans la MEME simulation longue, pour verifier que les
    # fonctionnalites de cette session (occupation autonome, rituel de depart, zone noire, coin favori) ne
    # s'interferent pas entre elles (pas de crash, pas de blocage, pas d'incoherence d'etat).
    c = FauxClient()
    chat = FauxVeilleChat(visible=False)
    b = Brain(c, Humeur(energie=0.95), seed=42, extras={"chat": chat})
    evenements = sorted([(100.0, "depart:Raphael"), (200.0, "retour:Raphael|0")])
    n = int(900 / 0.02)
    for i in range(n):
        t = i * 0.02
        while evenements and evenements[0][0] <= t:
            b.evenement(evenements.pop(0)[1])
        fallen = 650.0 <= t < 652.0
        policy = None if fallen else "stand"
        b.tick({"t": t, "safety": {"fallen": fallen}, "policy": policy,
                "odom": {"position": [1.0, 1.0, 0.0], "yaw": 0.0}}, 0.02)
    vus = {e[1] for e in b.journal}
    assert {"accueil", "rituel_depart", "cherche_attention"} <= vus, f"etats attendus manquants: {vus}"
    assert b.presents == {"Raphael"}
    assert b.exploration.chutes, "la chute doit laisser une zone noire"
    assert b.exploration.coin_favori("chill", b.t_global) is not None
    assert b.tombe is False and 0.0 <= b.humeur.energie <= 1.0


class FauxVeilleChatDistance:
    """Imite VeilleChat juste assez pour RegardeChat.pas : .estimation piloté pas à pas par le test (instant, x, y
    au sol, repère du tronc), .cible_regard renvoie un point fixe (le regard lui-même n'est pas sous test ici)."""
    def __init__(self):
        class _Suivi:
            pass
        self.suivi = _Suivi()
        self.suivi.visible = True
        self.estimation = None

    def cible_regard(self, hauteur_tronc, age_max=1.5):
        return (1.0, 0.0, 0.0)


def dernier_vx(client):
    for m, p in reversed(client.appels):
        if m == "robot.move":
            return p["vx"]
    return None


def test_recule_si_chat_approche_vite():
    # garde-fou "reculer s'il approche vite" (ROADMAP, table chat) : une approche rapide sous le seuil de
    # proximite declenche un petit pas en arriere (|vx| >= 0.3, zone morte respectee) ; une approche lente, ou
    # une distance encore confortable, ne doit rien declencher (une visite normale ne doit pas faire fuir le canard).
    c = FauxClient()
    chat = FauxVeilleChatDistance()
    b = Brain(c, Humeur(energie=0.9), seed=11, extras={"chat": chat})
    b.ctx.state = {"odom": {"position": [0.0, 0.0, 0.0], "yaw": 0.0}}
    etat = b.etats["regarde_chat"]
    etat.entre(b)

    chat.estimation = (0.0, 0.5, 0.0)      # 0,5 m devant : encore loin du seuil de proximite (0,35 m)
    etat.pas(b, 0.0)
    assert dernier_vx(c) == 0.0, "pas de recul alors que le chat est encore loin"

    chat.estimation = (0.1, 0.1, 0.0)      # 0,4 m parcourus en 0,1 s = 4 m/s de fermeture, sous 0,35 m
    etat.pas(b, 0.1)
    assert dernier_vx(c) == RegardeChat.VX_RECUL, "pas de recul malgre une approche rapide et proche"

    etat.pas(b, 0.5)                       # toujours dans la fenetre de recul (DUREE_RECUL_S = 1.0 s)
    assert dernier_vx(c) == RegardeChat.VX_RECUL

    etat.pas(b, 2.0)                       # fenetre de recul passee, pas de nouvelle approche rapide
    assert dernier_vx(c) == 0.0, "le recul doit s'arreter, pas devenir une fuite continue"


class FauxHorloge:
    """Imite time.localtime() juste assez pour Brain (heures_calmes, bonjour) : heure, minute, jour pilotes par le test."""
    def __init__(self, heure, minute=0, jour=100):
        self.heure, self.minute, self.jour = heure, minute, jour

    def __call__(self):
        return type("T", (), {"tm_hour": self.heure, "tm_min": self.minute, "tm_yday": self.jour})()


def test_heures_calmes_nuit_force_le_repos():
    # routine "heures calmes" (ROADMAP, table Humains) : pendant la plage nocturne configuree, le cerveau se met
    # au repos tout seul, exactement comme l'interrupteur "calme" de Home Assistant (meme chemin, meme effet).
    c = FauxClient()
    horloge = FauxHorloge(2)        # 2h du matin, dans la plage (23h-7h)
    b = Brain(c, Humeur(energie=0.9), seed=20, heures_calmes=(23, 7), horloge=horloge)
    simule(b, 2.0)
    assert b.mode_calme, "les heures calmes nocturnes doivent forcer le mode calme"
    assert b.courant.nom == "nap"


def test_heures_calmes_matin_reveille():
    c = FauxClient()
    horloge = FauxHorloge(2)
    b = Brain(c, Humeur(energie=0.9), seed=21, heures_calmes=(23, 7), horloge=horloge)
    simule(b, 2.0)
    assert b.mode_calme
    horloge.heure = 8               # le matin arrive, hors plage
    simule(b, 2.0)
    assert not b.mode_calme, "le matin doit lever les heures calmes toutes seules"


def test_heures_calmes_desactivees_par_defaut():
    # heures_calmes=None (valeur par defaut) : rien ne doit changer de comportement existant - cette
    # fonctionnalite est opt-in, jamais imposee a un cerveau qui ne la configure pas.
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=22)
    simule(b, 5.0)
    assert not b.mode_calme, "sans heures_calmes configurees, rien ne doit se declencher tout seul"


def test_heures_calmes_respecte_un_reveil_manuel_pendant_la_nuit():
    # un toggle HA explicite pendant la nuit doit etre respecte jusqu'au prochain changement d'heure, pas
    # reimpose tick apres tick par l'horloge (une seule transition par changement d'etat, pas une insistance).
    c = FauxClient()
    horloge = FauxHorloge(2)
    b = Brain(c, Humeur(energie=0.9), seed=23, heures_calmes=(23, 7), horloge=horloge)
    simule(b, 2.0)
    assert b.mode_calme
    b.evenement("calme_off")
    simule(b, 2.0)
    assert not b.mode_calme, "le reveil manuel pendant la nuit doit etre respecte"


def test_pas_de_recul_si_approche_lente():
    # le chat se rapproche, mais lentement (visite normale) : aucun recul, meme tres pres.
    c = FauxClient()
    chat = FauxVeilleChatDistance()
    b = Brain(c, Humeur(energie=0.9), seed=12, extras={"chat": chat})
    b.ctx.state = {"odom": {"position": [0.0, 0.0, 0.0], "yaw": 0.0}}
    etat = b.etats["regarde_chat"]
    etat.entre(b)

    chat.estimation = (0.0, 0.5, 0.0)
    etat.pas(b, 0.0)
    chat.estimation = (1.0, 0.3, 0.0)      # 0,2 m parcourus en 1 s = 0,2 m/s, sous le seuil (0,3 m/s)
    etat.pas(b, 1.0)
    assert dernier_vx(c) == 0.0, "une approche lente ne doit pas declencher de recul"


def test_bonjour_une_fois_par_jour_a_heure_reelle():
    # routine du matin (ROADMAP, prochaine etape n°6) : avant l'heure, rien ; a l'heure, un bonjour des que le canard
    # est au repos ; jamais deux fois le meme jour ; de nouveau le lendemain.
    c = FauxClient()
    horloge = FauxHorloge(7, 10)
    b = Brain(c, Humeur(energie=0.9), seed=30, horloge=horloge, bonjour=(7, 30))
    simule(b, 30)
    assert "bonjour" not in {e[1] for e in b.journal}, "bonjour avant l'heure"
    horloge.minute = 31
    simule(b, 60)
    assert [e[1] for e in b.journal].count("bonjour") == 1, b.journal
    simule(b, 60)
    assert [e[1] for e in b.journal].count("bonjour") == 1, "deux bonjours le meme jour"
    horloge.jour += 1
    simule(b, 60)
    assert [e[1] for e in b.journal].count("bonjour") == 2, "pas de bonjour le lendemain"


def test_bonjour_hors_fenetre_et_desactive_par_defaut():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=31, horloge=FauxHorloge(17), bonjour=8)    # 17h : trop tard
    simule(b, 60)
    assert "bonjour" not in {e[1] for e in b.journal}
    b = Brain(FauxClient(), Humeur(energie=0.9), seed=31, horloge=FauxHorloge(8, 5))  # pas configure
    simule(b, 60)
    assert "bonjour" not in {e[1] for e in b.journal}


def test_bonjour_attend_la_fin_des_heures_calmes_et_salue_les_presents():
    c = FauxClient()
    horloge = FauxHorloge(6, 50)
    b = Brain(c, Humeur(energie=0.9), seed=32, horloge=horloge, heures_calmes=(23, 7), bonjour=(6, 45))
    b.presents.add("Raphael")
    simule(b, 30)
    assert b.mode_calme and "bonjour" not in {e[1] for e in b.journal}, "bonjour pendant les heures calmes"
    horloge.heure, horloge.minute = 7, 0
    simule(b, 90)
    assert "bonjour" in {e[1] for e in b.journal}
    assert any(m == "robot.sound" and p == {"tag": "greet"} for m, p in c.appels), "pas de bonjour a l'habitant"


def test_messager_sonnette_et_machine():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=33)
    simule(b, 3, evenements=[(1.0, "sonnette:Entree")])
    assert "sonnette" in {e[1] for e in b.journal}
    assert any(m == "robot.sound" and p == {"tag": "alarm"} for m, p in c.appels)
    simule(b, 8, evenements=[(1.0, "machine_finie:Lave-linge")])
    assert "messager" in {e[1] for e in b.journal}
    assert b.messages == ["machine_finie:Lave-linge"], "personne a la maison : le message doit etre garde"
    assert b.etats["sonnette"] is not None and "sonnette" not in " ".join(b.messages)


def test_message_transmis_au_retour_puis_oublie():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=34)
    simule(b, 8, evenements=[(1.0, "impression_finie:MK4S")])
    assert b.messages == ["impression_finie:MK4S"]
    n_avant = sum(1 for m, p in c.appels if m == "robot.sound" and p == {"tag": "inquire"})
    simule(b, 15, evenements=[(1.0, "retour:Raphael|3600")])
    assert b.messages == [], "message non transmis"
    acc = b.etats["accueil"]
    assert acc.messages == ["impression_finie:MK4S"]
    assert sum(1 for m, p in c.appels if m == "robot.sound" and p == {"tag": "inquire"}) > n_avant
    simule(b, 8, evenements=[(1.0, "impression_finie:MK4S")])
    assert b.messages == [], "quelqu'un est la : rien a garder, il l'a vu en direct"


def test_chat_agace_trois_chutes_veille_assis():
    # garde-fou "chat agace" (ROADMAP, non negociable) : renverse 3 fois en 10 min -> il s'assoit et passe en veille
    # au lieu de recommencer ; au bout de la veille, il reprend sa vie.
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=80)
    for k in range(3):
        simule(b, 30, tombe_entre=(10.0, 13.0))
    assert b.veille_jusqua > b.t_global, "pas de veille apres 3 chutes"
    noms = [e[1] for e in b.journal]
    assert noms[-1] == "nap" and noms.count("ebouriffe") == 2, noms
    simule(b, 600)
    assert {e[1] for e in b.journal[len(noms):]} <= {"nap"}, "pendant la veille : seulement des siestes"
    assert b.ctx.sitting, "il reste assis pendant la veille"
    simule(b, 400)
    assert b.t_global > b.veille_jusqua and not b.ctx.sitting, "la veille finie, il se releve"


def test_deux_chutes_espacees_pas_de_veille():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=81)
    simule(b, 30, tombe_entre=(10.0, 13.0))
    simule(b, 700)
    simule(b, 30, tombe_entre=(10.0, 13.0))
    simule(b, 30, tombe_entre=(10.0, 13.0))
    assert b.veille_jusqua < 0, "3 chutes, mais pas dans la meme fenetre de 10 min"


def test_taquinerie_non_puis_joue_quand_meme():
    class Veille:
        def armer(self): pass
        def desarmer(self): pass
        def a_bouge(self): return False
    vus = 0
    for seed in range(40):
        c = FauxClient()
        b = Brain(c, Humeur(energie=0.9), seed=seed, extras={"mouvement": Veille()})
        b.fin_etat = 1e9
        simule(b, 6, evenements=[(0.5, "jeu_soleil")])
        noms = [e[1] for e in b.journal]
        assert "soleil" in noms, (seed, noms)
        if "taquin" in noms:
            vus += 1
            assert noms.index("taquin") + 1 == noms.index("soleil"), "apres le non, il joue"
    assert 2 <= vus <= 16, f"taquinerie {vus}/40 : elle doit rester occasionnelle"


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
