#!/usr/bin/env python3
"""vivant.py et son branchement : respiration et saccades, habituation, tour de parole, bouderie, jalousie du chat,
attente a la porte, souvenirs de lieux, age (timidite de jeunesse, assurance des blagues), suis-moi / je te suis,
excitation devant la balle soulevee."""
import math
from types import SimpleNamespace

import caresse
import chat
import vivant
from memoire import Memoire
from test_brain import FauxHorloge
from test_vie_maison import Tof, cerveau, sons, vivre


def tetes(c, depuis=0):
    return [p for m, p in c.appels[depuis:] if m == "robot.head"]


# -- respiration et saccades ---------------------------------------------------------------------------------------
def test_il_respire_au_repos_sans_gener_la_caresse():
    b, c, _ = cerveau()
    b.etats["chill"].duree = lambda brain: 1e9
    b.etats["chill"].aux_aguets = False
    b.fin_etat = 1e9
    vivre(b, 12)
    t = tetes(c)
    cous = [p["neck_pitch"] for p in t[-500:]]
    assert max(cous) - min(cous) > 0.02, "le cou monte et descend"
    assert all(abs(p["neck_pitch"]) <= 0.02 and abs(p["head_yaw"]) <= vivant.SACCADE_RAD + 1e-9 for p in t[-500:])
    # une main posee pendant la respiration : la tete suit sa consigne, puis s'en ecarte -> caresse reconnue
    d = caresse.DetecteurCaresse()
    evts = []
    for i in range(300):
        tt = i * 0.02
        consigne = (0.015 * math.sin(2 * math.pi * tt / 4.0), 0.0, 0.0, 0.0)
        joints = [consigne[0] + 0.01, 0.0, 0.0, 0.0]
        if tt > 4.0:
            joints[1] += 0.1                                  # la main appuie sur la tete
        evts += d.mise_a_jour(tt, consigne, joints)
    assert evts == ["caresse"]


def test_aux_aguets_il_se_fige():
    b, c, _ = cerveau()
    b.etats["chill"].duree = lambda brain: 1e9
    b.etats["chill"].aux_aguets = True
    b.fin_etat = 1e9
    n = len(c.appels)
    vivre(b, 3)
    assert all(p["neck_pitch"] == 0.0 and p["head_yaw"] == 0.0 for p in tetes(c, n))


# -- habituation -------------------------------------------------------------------------------------------------------
def test_habituation_puis_oubli():
    h = vivant.Habituation()
    i = [h.noter("bruit", t) for t in (0, 60, 120, 180)]
    assert i[0] == 1.0 and i[0] > i[1] > i[2] > i[3]
    assert h.intensite("bruit", 6 * 3600) > 0.95, "apres des heures sans lui, il redevient neuf"


def test_bruit_isole_qui_revient_il_sursaute_de_moins_en_moins():
    b, _, _ = cerveau()
    reactions = []
    for k in range(5):                                       # un bruit toutes les 2 minutes : jamais une serie
        n = len(b.journal)
        vivre(b, 120, evenements=[(0.5, "bruit")])
        reactions.append([e[1] for e in b.journal[n:]][:1])
    assert reactions[0] == ["startle"] and ["startle"] not in reactions[2:], reactions


# -- tour de parole -----------------------------------------------------------------------------------------------------
def test_il_repond_quand_on_lui_parle_seulement():
    b, c, _ = cerveau()
    b.malice.permise = lambda *a, **k: False             # (pas de faux sommeil taquin a l'appel, pour l'essai)
    n = len(c.appels)
    vivre(b, 1, evenements=[(0.1, "enonce:1.2|monte")])
    assert b.courant.nom != "repond", "on ne s'adressait pas a lui (la tele, une conversation)"
    vivre(b, 4, evenements=[(0.1, "appel"), (3.5, "enonce:1.2|monte")])
    assert any(e[1] == "repond" for e in b.journal) and "inquire" in sons(c, n)
    assert vivant.Reponse.choisir(0.5, None) == ("chirp", "oui") and vivant.Reponse.choisir(1.5, "descend")[0] == "coo"


# -- bouderie -----------------------------------------------------------------------------------------------------------
def test_bouderie_et_reconciliation():
    b, c, _ = cerveau()
    b._bascule("boude")
    vivre(b, 2, evenements=[(0.5, "appel")])
    assert b.courant.nom == "boude", "il ne repond plus aux appels (un regard en coin)"
    vivre(b, 1, evenements=[(0.1, "caresse")])
    assert any(e[1] == "reconcilie" for e in b.journal) and b.courant.nom in ("reconcilie", "chill")


# -- jalousie du chat ---------------------------------------------------------------------------------------------------
def test_chat_caresse_devant_lui():
    o = lambda classe, x, y, w, h: SimpleNamespace(classe=classe, x=x, y=y, w=w, h=h, score=0.9)
    s = chat.SuiviCaresse(horloge=lambda: 100.0)
    c, p = [o("cat", 100, 300, 80, 60)], [o("person", 150, 100, 120, 400)]
    assert s.mise_a_jour(c, p) == [] and s.mise_a_jour(c, p) == [] and s.mise_a_jour(c, p) == ["chat_caresse"]
    assert s.mise_a_jour(c, p) == [], "une fois, pas a chaque image"
    loin = chat.SuiviCaresse()
    assert all(loin.mise_a_jour(c, [o("person", 600, 100, 100, 400)]) == [] for _ in range(5))
    b, _, _ = cerveau()
    b.presents.add("Raphael")
    vivre(b, 2, evenements=[(0.1, "chat_caresse")])
    assert [e[1] for e in b.journal][-2:] in (["jaloux", "cherche_attention"], ["jaloux"])


# -- attente a la porte -------------------------------------------------------------------------------------------------
def test_heure_de_retour_apprise_et_attente():
    d = {}
    for j in range(5):
        vivant.noter_retour(d, "Raphael", SimpleNamespace(tm_hour=18, tm_min=j * 5, tm_wday=j % 5))
    assert vivant.retour_prevu(d, "Raphael", weekend=False) == 18 * 60 + 10
    assert vivant.retour_prevu(d, "Raphael", weekend=True) is None, "pas d'habitude le week-end"
    eparpille = {}
    for h in (9, 13, 18, 21):
        vivant.noter_retour(eparpille, "X", SimpleNamespace(tm_hour=h, tm_min=0, tm_wday=1))
    vivant.noter_retour(eparpille, "X", SimpleNamespace(tm_hour=23, tm_min=0, tm_wday=1))
    assert vivant.retour_prevu(eparpille, "X", False) is None

    class Mem:
        donnees = d

        def familiarite(self, qui):
            return 0.8

        def rencontre(self, qui):
            pass

        def sauver(self):
            pass

    horloge = FauxHorloge(18, 0, semaine=2)                  # 18 h 00, retour habituel a 18 h 10
    b, _, _ = cerveau(memoire=Mem())
    b.horloge = horloge
    b.etats["chill"].duree = lambda brain: 0.1
    b.fin_etat = 0.0
    vivre(b, 3)
    assert "attend_porte" in [e[1] for e in b.journal]
    n = len(b.journal)
    vivre(b, 3)
    assert "attend_porte" not in [e[1] for e in b.journal[n:]], "une fois par jour"


# -- souvenirs de lieux -------------------------------------------------------------------------------------------------
def test_souvenirs_de_lieux():
    b, _, _ = cerveau()
    vivre(b, 1, pos=(2.0, 1.0), evenements=[(0.1, "caresse")])
    lieu = b.exploration.coin_favori("bon", b.t_global)
    assert lieu is not None and math.hypot(lieu[0] - 2.0, lieu[1] - 1.0) < 0.3
    vivre(b, 1, pos=(-1.0, 0.0), evenements=[(0.1, "bruit")])
    assert b.exploration.coin_favori("mauvais", b.t_global) is not None


# -- age ------------------------------------------------------------------------------------------------------------------
def test_jeune_timide_et_peu_sur_de_ses_blagues_puis_assure(tmp_path):
    t = [1_000_000.0]
    b, _, _ = cerveau(memoire=Memoire(tmp_path / "m.json"), mur=lambda: t[0])
    assert b.age() < 0.01 and b.perso.jeunesse == 1.0 and b.perso.assurance == 0.5
    jeune = b.perso.envie_taquiner() / b.perso.jour[1]          # (hors humeur du jour, qui change chaque jour)
    b._sur_visiteur(True)
    assert b.timidite_depart > 1.0, "tout jeune, plus timide avec un inconnu"
    t[0] += 70 * 86400
    b._vieillit()
    assert b.perso.jeunesse == 0.0 and b.perso.assurance == 1.0 and abs(b.perso.envie_taquiner() / b.perso.jour[1] - 2 * jeune) < 1e-9
    sans, _, _ = cerveau()
    assert sans.perso.assurance == 1.0 and sans.perso.jeunesse == 0.0, "sans memoire : aucun effet (essais)"


# -- suis-moi, je te suis -------------------------------------------------------------------------------------------------
class TofJambe(Tof):
    def __init__(self, x=1.0, y=0.0):
        self.p = [(x, y, 0.2)]

    def points(self, s):
        return list(self.p)


def mouvements(c, depuis=0):
    return [p for m, p in c.appels[depuis:] if m == "robot.move"]


def test_suis_moi():
    assert vivant.SuisMoi.cible([(1.0, 0.0, 0.2), (0.6, 0.1, 0.2), (0.5, 1.0, 0.2)])[0] == math.hypot(0.6, 0.1)
    tof = TofJambe()
    b, c, _ = cerveau(tof=tof)
    n = len(c.appels)
    vivre(b, 1, evenements=[(0.1, "suis_moi")])
    assert b.courant.nom == "suis_moi" and any(m["vx"] >= 0.3 for m in mouvements(c, n)), "elle s'eloigne : il avance"
    tof.p = [(0.8, 0.6, 0.2)]
    n = len(c.appels)
    vivre(b, 0.5)
    assert any(abs(m["vyaw"]) >= 1.2 for m in mouvements(c, n)), "elle est sur le cote : il pivote"
    tof.p = []
    vivre(b, 4)
    assert b.courant.nom != "suis_moi", "perdue : il abandonne"


def test_suis_moi_jamais_sans_capteur():
    b, _, _ = cerveau()
    vivre(b, 1, evenements=[(0.1, "suis_moi")])
    assert b.courant.nom != "suis_moi"


def test_je_te_suis_verifie_qu_on_le_suit():
    b, c, _ = cerveau(tof=TofJambe(1.0))
    n = len(c.appels)
    vivre(b, 40, evenements=[(0.1, "je_te_suis")])
    assert "mene" in [e[1] for e in b.journal]
    assert sons(c, n).count("wheee") >= 1, "on le suit : content"


# -- la balle soulevee --------------------------------------------------------------------------------------------------
class BalleLevee:
    def levee(self):
        return True

    def position(self):
        return None


def test_balle_soulevee_il_trepigne():
    b, _, _ = cerveau(balle=BalleLevee())
    vivre(b, 2)
    assert "excite" in [e[1] for e in b.journal]
    n = len(b.journal)
    vivre(b, 10)
    assert "excite" not in [e[1] for e in b.journal[n:]], "pas en boucle"
