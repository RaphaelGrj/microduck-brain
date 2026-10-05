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


# --- lot B : objets au sol, aspirateur ---------------------------------------------------------------------------
import math  # noqa: E402

from main_tendue import DetecteurApproche  # noqa: E402


class FauxTofScene:
    """ToF factice : points() et libre() pilotes par le test."""
    def __init__(self):
        self.pts, self.devant, self.vide = [], 3.0, math.inf

    def noter_etat(self, s):
        pass

    def points(self, s):
        return list(self.pts)

    def libre(self, s):
        return {"devant": self.devant, "gauche": 3.0, "droite": 3.0, "vide": self.vide, "n": len(self.pts)}


class FausseVeilleBalle:
    def __init__(self, pos=None):
        self.pos = pos

    def position(self, age_max=1.5):
        return self.pos


def test_detecteur_approche_objet_bas():
    d = DetecteurApproche()
    ev = []
    for i in range(60):                               # de 1,0 m a 0,4 m en 3 s, a 6 cm du sol
        t = i * 0.05
        ev += d.mise_a_jour([(1.0 - 0.2 * t, 0.0, 0.06)], t)
    assert ev == ["objet_approche"]
    d = DetecteurApproche()
    assert not any(d.mise_a_jour([(0.5, 0.0, 0.06)], i * 0.05) for i in range(60)), "un meuble immobile"
    d = DetecteurApproche()
    assert not any(d.mise_a_jour([(1.0 - 0.01 * i, 0.0, 0.25)], i * 0.05) for i in range(60)), "trop haut (une jambe)"


def _simule_aspirateur(b, c, tof, secondes, vitesse=0.25, d0=1.2, t0=0.0):
    """L'aspirateur avance vers le canard ; le canard qui pivote le sort de son couloir (le test le simplifie : des
    que le canard tourne, l'aspirateur n'est plus devant)."""
    d = d0
    dists = []
    for i in range(int(secondes / 0.02)):
        moves = [p for m, p in c.appels[-6:] if m == "robot.move"]
        tourne = any(p["vyaw"] for p in moves)
        d -= vitesse * 0.02
        tof.pts = [] if tourne or d < 0.05 else [(d, 0.0, 0.06)]
        dists.append((round(t0 + i * 0.02, 2), d, b.courant.nom, tourne))
        b.tick({"t": t0 + i * 0.02, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0}}, 0.02)
    return dists


def test_aspirateur_s_ecarte_avant_30_cm():
    for taquine in (False, True):
        tof = FauxTofScene()
        b, c, _ = cerveau(seed=110, extras={"tof": tof, "exploration": False})
        b.fin_etat = 1e9
        b.evenement("aspirateur_on")
        simule(b, 3.0)                                # regard curieux, puis repos
        b.fin_etat = 1e9
        b._bascule("chill")
        b.fin_etat = 1e9
        if taquine:
            b.malice.permise = lambda brain, nom, humain=False: nom == "barre_aspirateur"
            b.P_TAQUINE = 1.0
        trace = _simule_aspirateur(b, c, tof, 6.0)
        assert "aspirateur" in [e[1] for e in b.journal], b.journal
        premier_tour = next(i for i, x in enumerate(trace) if x[3])
        assert trace[premier_tour][1] > 0.28, f"il doit s'ecarter avant 30 cm (taquine={taquine}) : {trace[premier_tour]}"
        if taquine:
            debut = next(i for i, x in enumerate(trace) if x[2] == "aspirateur")
            assert premier_tour - debut >= 50, "en taquinerie, il lui barre d'abord le chemin un instant"


def test_aspirateur_curiosite_a_son_arrivee():
    b, c, _ = cerveau(seed=111)
    simule(b, 2, evenements=[(0.5, "aspirateur_on")])
    assert "curious" in [e[1] for e in b.journal] and b.aspirateur_actif
    simule(b, 2, evenements=[(0.5, "aspirateur_off")])
    assert not b.aspirateur_actif


def test_pousse_la_balle_hors_de_portee_deux_fois_au_plus():
    tof = FauxTofScene()
    b, c, _ = cerveau(seed=112, extras={"tof": tof, "exploration": False, "balle": FausseVeilleBalle((0.12, 0.0))})
    b.P_TAQUINE = b.P_POUSSE_BALLE = 1.0
    for k in range(3):
        b.detecteur_main.main = (b.t_global, 0.14, 0.02, 0.05)       # la main descend vers la balle
        b.evenement("main")
        simule(b, 4)
        b.t_esquive = -1e9
    noms = [e[1] for e in b.journal]
    assert noms.count("pousse_balle") == 2, noms
    rafales = [p["vx"] for m, p in c.appels if m == "robot.move" and p["vx"] > 0]
    assert rafales and max(rafales) == 0.4 and len(rafales) <= 2 * 31, "deux rafales de 0,6 s, rien de plus"


def test_pas_de_poussee_au_bord_d_un_vide():
    tof = FauxTofScene()
    tof.vide = 0.2
    b, c, _ = cerveau(seed=113, extras={"tof": tof, "exploration": False, "balle": FausseVeilleBalle((0.12, 0.0))})
    b.malice.permise = lambda brain, nom, humain=False: nom == "pousse_balle"
    b.P_TAQUINE = b.P_POUSSE_BALLE = 1.0
    b.detecteur_main.main = (b.t_global, 0.14, 0.02, 0.05)
    b.evenement("main")
    simule(b, 3)
    assert "pousse_balle" in [e[1] for e in b.journal]
    assert not any(m == "robot.move" and p["vx"] > 0 for m, p in c.appels), "jamais de pas vers un vide"


def test_mime_de_vol_avec_ground_pick():
    b, c, _ = cerveau(seed=114, extras={"balle": FausseVeilleBalle((0.15, 0.02))})
    b.P_MIME_VOL = 1.0
    b.t_global = 0.0
    simule(b, 60)
    assert "mime_vol" in [e[1] for e in b.journal], b.journal
    assert ("robot.do", {"skill": "ground_pick"}) in c.appels
    assert any(m == "robot.move" and p["vyaw"] for m, p in c.appels), "il se detourne avec son butin"
    sans_balle, c2, _ = cerveau(seed=114, extras={"balle": FausseVeilleBalle(None)})
    sans_balle.P_MIME_VOL = 1.0
    sans_balle.t_global = 0.0
    simule(sans_balle, 60)
    assert "mime_vol" not in [e[1] for e in sans_balle.journal]
