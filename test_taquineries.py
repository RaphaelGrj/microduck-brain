#!/usr/bin/env python3
"""Tests du socle des taquineries (taquineries.py) et du lot A (etats de brain.py), sans robot."""
import tempfile
from pathlib import Path

import memoire
import taquineries
from brain import Brain, Humeur
from taquineries import Malice
from test_brain import FauxClient, FauxHorloge, simule


class FausseMemoire:
    def __init__(self, fam=0.8):
        self.fam, self.b = fam, {}

    def familiarite(self, qui):
        return self.fam

    def blague(self, nom):
        self.b[nom] = self.b.get(nom, 0) + 1

    def blagues(self):
        return dict(self.b)

    def rencontre(self, qui):
        pass

    def absence_s(self, qui):
        return None

    def depart(self, qui):
        pass


def cerveau(fam=0.8, heure=15, presents=("Raphael",), seed=100, extras=None):
    c = FauxClient()
    mem = FausseMemoire(fam)
    b = Brain(c, Humeur(energie=0.9), seed=seed, horloge=FauxHorloge(heure), extras={"memoire": mem, **(extras or {})})
    b.presents.update(presents)
    b.t_global = 1000.0
    return b, c, mem


def test_budget_ecart_et_pas_deux_fois_la_meme():
    b, c, mem = cerveau()
    m = b.malice
    assert m.permise(b, "regard_mystere")
    m.noter(b, "regard_mystere")
    b.t_global += 400
    assert not m.permise(b, "regard_mystere"), "jamais la meme deux fois de suite"
    assert m.permise(b, "feinte_bec")
    b.t_global -= 200
    assert not m.permise(b, "feinte_bec"), "ecart minimal entre deux taquineries"
    b.t_global += 200
    for nom in ("feinte_bec", "esquive", "baillement"):
        m.noter(b, nom)
        b.t_global += 301
    assert not m.permise(b, "sourde_oreille"), "budget horaire depasse (4 par heure)"
    b.t_global += 3600
    assert m.permise(b, "sourde_oreille")


def test_familiarite_presence_nuit_calme_accueil():
    b, _, _ = cerveau(fam=0.3)
    assert not b.malice.permise(b, "regard_mystere"), "pas avec quelqu'un de peu familier"
    b, _, _ = cerveau(presents=())
    assert not b.malice.permise(b, "regard_mystere"), "spontanee : il faut quelqu'un"
    assert b.malice.permise(b, "feinte_bec", humain=True), "declenchee par un geste humain : quelqu'un est la"
    b, _, _ = cerveau(heure=23)
    assert not b.malice.permise(b, "feinte_bec", humain=True), "pas la nuit"
    b, _, _ = cerveau()
    b.mode_calme = True
    assert not b.malice.permise(b, "feinte_bec", humain=True), "pas en mode calme"
    b, _, _ = cerveau()
    b.t_dernier_accueil = b.t_global - 60
    assert not b.malice.permise(b, "feinte_bec", humain=True), "on dit bonjour d'abord"


def test_dernier_mot_son_propre_budget():
    b, _, _ = cerveau()
    for _ in range(3):
        assert b.malice.permise(b, "dernier_mot", humain=True)
        b.malice.noter(b, "dernier_mot")
        b.t_global += 30
    assert not b.malice.permise(b, "dernier_mot", humain=True), "3 par 10 min au plus"
    assert b.malice.permise(b, "feinte_bec", humain=True), "hors budget general"


def test_fierte_running_gag_et_trophee():
    m = Malice(FausseMemoire())
    b, _, _ = cerveau()
    for _ in range(4):
        m.noter(b, "faux_endormi")
    assert m.fierte("faux_endormi") == 0.0
    m.noter(b, "faux_endormi")
    f5 = m.fierte("faux_endormi")
    for _ in range(30):
        m.noter(b, "regard_mystere")
    assert 0.4 <= f5 < m.fierte("faux_endormi") <= 1.0, "la fierte grandit avec l'historique des blagues"


def test_memoire_des_blagues_persistante():
    with tempfile.TemporaryDirectory() as d:
        mem = memoire.Memoire(Path(d) / "m.json")
        mem.blague("esquive")
        mem.blague("esquive")
        assert memoire.Memoire(Path(d) / "m.json").blagues() == {"esquive": 2}


def _main(b, c, t0, duree=4.0):
    """Une main tendue arrive devant le canard (comme main_tendue.py l'annoncerait)."""
    b.detecteur_main.main = (b.t_global, 0.12, 0.0, 0.1)
    b.evenement("main")
    simule(b, duree)


def test_esquive_puis_accepte_la_main():
    b, c, _ = cerveau(seed=101)
    b.P_TAQUINE = 1.0
    b.malice.permise = lambda brain, nom, humain=False: nom == "esquive"
    _main(b, c, 0)
    assert b.journal[-2][1] == "esquive" or "esquive" in [e[1] for e in b.journal], b.journal
    _main(b, c, 5)
    noms = [e[1] for e in b.journal]
    assert noms[noms.index("esquive") + 1:].count("main_tendue") == 1, noms
    sons = [p["tag"] for m, p in c.appels if m == "robot.sound"]
    assert "coo" in sons, "la deuxieme main est acceptee avec un roucoulement"


def test_feinte_de_bec_recule_un_peu():
    b, c, _ = cerveau(seed=102)
    b.P_TAQUINE = 1.0
    b.malice.permise = lambda brain, nom, humain=False: nom == "feinte_bec"
    _main(b, c, 0)
    assert "feinte_bec" in [e[1] for e in b.journal]
    vx = [p["vx"] for m, p in c.appels if m == "robot.move" and p["vx"] < 0]
    assert vx and min(vx) == -0.4 and len(vx) <= 30, "un petit bond en arriere (0,5 s), pas une fuite"


def test_appel_taquine_ou_repond():
    b, c, _ = cerveau(seed=103)
    b.P_TAQUINE = 1.0
    simule(b, 10, evenements=[(0.5, "appel")])
    assert {"faux_endormi", "sourde_oreille"} & {e[1] for e in b.journal}, b.journal
    b, c, _ = cerveau(seed=103, heure=2)
    b.P_TAQUINE = 1.0
    simule(b, 5, evenements=[(0.5, "appel")])
    assert "appel" in {e[1] for e in b.journal}, "la nuit, il repond simplement"


def test_stop_coupe_net_et_bloque():
    b, c, _ = cerveau(seed=104)
    b.P_TAQUINE = 1.0
    simule(b, 2, evenements=[(0.5, "appel")])
    assert getattr(b.courant, "taquinerie", False)
    simule(b, 1, evenements=[(0.1, "stop_taquinerie")])
    assert b.courant.nom == "chill", "la taquinerie s'arrete net"
    simule(b, 5, evenements=[(0.5, "appel")])
    assert b.courant.nom in ("appel", "chill") and b.journal[-1][1] in ("appel", "chill"), b.journal
    assert not b.malice.permise(b, "feinte_bec", humain=True), "plus de taquinerie pendant 30 min"


def test_baillement_ouvre_et_referme_le_bec():
    b, c, _ = cerveau(seed=105)
    simule(b, 5, evenements=[(0.5, "discussion_longue")])
    assert "baillement" in [e[1] for e in b.journal]
    bouche = [p["open"] for m, p in c.appels if m == "robot.mouth"]
    assert max(bouche) > 0.8 and bouche[-1] == 0.0, "bec grand ouvert, puis referme"


def test_regard_mystere_spontane_seulement_avec_un_familier():
    vus = 0
    for seed in range(30):
        b, c, _ = cerveau(seed=seed)
        b.t_global = 0.0
        simule(b, 600)
        vus += "regard_mystere" in {e[1] for e in b.journal}
    assert vus >= 3, f"jamais de regard mysterieux ({vus}/30)"
    for seed in range(10):
        b, c, _ = cerveau(seed=seed, fam=0.2)
        b.t_global = 0.0
        simule(b, 600)
        assert "regard_mystere" not in {e[1] for e in b.journal}


def test_running_gag_air_fier():
    b, c, mem = cerveau(seed=106)
    mem.b["faux_endormi"] = taquineries.RUNNING_GAG
    b.P_TAQUINE = 1.0
    b.malice.permise = lambda brain, nom, humain=False: nom == "faux_endormi"
    simule(b, 15, evenements=[(0.5, "appel")])
    noms = [e[1] for e in b.journal]
    assert "fier" in noms and noms.index("fier") == noms.index("faux_endormi") + 1, noms


def test_fausse_feinte_avant_le_tir():
    import approach
    tetes = []

    class FauxRobot:
        def notify(self, m, p=None):
            if m == "robot.head":
                tetes.append(p["head_yaw"])

        def request(self, m, p=None, **kw):
            tetes.append(("tir", p))
            return {"result": {"accepted": True}}

        def read_state_frame(self):
            return {"odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0}}

    ap = object.__new__(approach.Approche)          # sans la vision (fil camera) : seulement la fin de sequence
    ap.c, ap.log, ap.feinte, ap.cote, ap.n_ajust = FauxRobot(), lambda m: None, True, "left", 0
    ap.resultat, ap.burst, ap.yaw, ap.pitch, ap.arret, ap.avant_tir, ap.verite = {}, None, 0.0, 0.0, None, None, None
    ap.tirer((0.07, 0.0), "test")
    assert ap.etat == "FEINTE" and ap.yaw == -approach.YAW_FEINTE
    ap.vis = None
    ap.run(duree_max=approach.T_FEINTE + approach.T_TETE_NEUTRE + 1.0)
    i_tir = next(i for i, x in enumerate(tetes) if isinstance(x, tuple))
    avant = tetes[:i_tir]
    assert min(avant) == -approach.YAW_FEINTE, "la tete regarde d'un cote"
    assert all(y == 0.0 for y in avant[-20:]), "tete au neutre au moment du tir (la fenetre de tir l'exige)"
    assert tetes[i_tir][1] == {"skill": "kick_left"} and ap.resultat["feinte"]
