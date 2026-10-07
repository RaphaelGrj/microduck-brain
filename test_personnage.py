#!/usr/bin/env python3
"""personnage.py et son branchement (vivant II) : hoquet, gaffe, nid, fierte/deception au jeu de balle, cabotinage,
rituels par habitant, objet nouveau inspecte, doudou, rythme rejoue, nom sonore, ambiance (rires, voix tendues),
bain de soleil."""
import numpy as np

import audio
import personnage
from etats_base import SONS_CANARD
from memoire import Memoire
from test_brain import FauxHorloge
from test_vie_maison import Tof, cerveau, sons, vivre


def zero(b):
    b._rng_vie.random = lambda: 0.0                       # les tirages « vie » toujours gagnants (essai)


class TofDevant(Tof):
    def __init__(self, devant=3.0):
        self.devant = devant

    def libre(self, s):
        return {"devant": self.devant, "gauche": 3.0, "droite": 1.0, "vide": float("inf"), "n": 10}


# -- hoquet ---------------------------------------------------------------------------------------------------------
def test_hoquet_puis_gueri_par_une_caresse():
    b, c, _ = cerveau()
    b._bascule("hoquet")
    b.fin_etat = 1e9
    n = len(c.appels)
    vivre(b, 8)
    assert sons(c, n).count("peck") >= 2, "hic... hic..."
    vivre(b, 1, evenements=[(0.1, "caresse")])
    assert "gueri" in [e[1] for e in b.journal]


def test_une_surprise_fait_passer_le_hoquet():
    b, _, _ = cerveau()
    b._bascule("hoquet")
    b._bascule("startle")
    assert b.suivant_force == "gueri"


# -- gaffe ------------------------------------------------------------------------------------------------------------
def test_il_bute_se_vexe_et_contourne_en_exagerant():
    tof = TofDevant(0.25)
    b, c, _ = cerveau(tof=tof)
    zero(b)
    b._bascule("wander")
    vivre(b, 0.6)                                         # (la tete se place 0,4 s avant de juger le sol)
    assert b.courant.nom == "gaffe" or "gaffe" in [e[1] for e in b.journal]
    n = len(c.appels)
    vivre(b, 9)
    assert any(m == "robot.move" and abs(p["vyaw"]) > 1.0 for m, p in c.appels[n:]), "le grand detour"
    assert all(not (m == "robot.move" and p["vx"] > 0) for m, p in c.appels[n:] if b.courant.nom == "gaffe")


# -- nid --------------------------------------------------------------------------------------------------------------
def test_deux_tours_avant_la_sieste():
    b, c, _ = cerveau(tof=Tof())
    zero(b)
    b.humeur.energie = 0.1
    b.fin_etat = 0.0
    vivre(b, 12)
    noms = [e[1] for e in b.journal]
    assert "nid" in noms and noms[noms.index("nid") + 1] == "nap", noms
    assert "coo" in sons(c)


# -- fierte / deception au jeu de balle --------------------------------------------------------------------------------
def test_record_et_deception():
    from test_jeu_balle import cerveau as cerveau_balle, simule
    b, c, _ = cerveau_balle(None)
    b.ctx.extras["memoire"] = type("M", (), {"donnees": {"balle": {"parties": 5, "reussies": 4, "tirs": 6, "serie": 2,
                                                                     "record": 2}}})()
    simule(b, 18, evenements=[(0.2, "jeu_balle")])
    assert b.etats["balle"].resultat == "reussi"
    assert any(m == "robot.move" and p["vyaw"] > 1.0 for m, p in c.appels), "un nouveau record : tour de victoire"
    b2, c2, _ = cerveau_balle((0.1, 0.0))                 # balle restee a ses pieds, trois fois
    b2.rng.random = lambda: 0.99                          # (il ne retente pas)
    simule(b2, 15, evenements=[(0.2, "jeu_balle")])
    assert b2.etats["balle"].resultat == "rate" and any(m == "robot.head" and p["head_pitch"] > 0.3
                                                         for m, p in c2.appels), "tete basse, decu"


# -- cabotinage --------------------------------------------------------------------------------------------------------
def test_succes_et_flop():
    s = personnage.Succes({})
    s.joue("lissage", 0.0)
    assert s.reaction(5.0) == "lissage" and s.poids("lissage") > 1.0
    s.joue("eternuement", 10.0)
    assert s.juge(40.0, public=True) == "eternuement" and s.poids("eternuement") < 1.0
    s.joue("lissage", 50.0)
    assert s.reaction(100.0) is None, "trop tard : ce n'etait pas pour lui"


def test_on_rit_de_son_numero_il_cabotine():
    b, _, _ = cerveau()
    b.presents.add("Raphael")
    b._bascule("lissage")
    vivre(b, 6, evenements=[(1.0, "rire")])
    assert "cabotine" in [e[1] for e in b.journal] and b.succes.poids("lissage") > 1.0
    b2, _, _ = cerveau()
    vivre(b2, 1, evenements=[(0.1, "rire")])
    assert b2.courant.nom == "rit", "un rire sans lui : contagieux"


# -- rituels par habitant ------------------------------------------------------------------------------------------------
def test_rituel_appris_puis_reclame(tmp_path):
    d = {}
    for jour in (10, 11, 13, 14):
        personnage.noter_rituel(d, "Clémence", 20, jour)
    assert personnage.rituel_maintenant(d, "Clémence", 20, 15)
    assert not personnage.rituel_maintenant(d, "Clémence", 19, 15), "pas a cette heure-la"
    personnage.noter_rituel(d, "Clémence", 20, 15)
    assert not personnage.rituel_maintenant(d, "Clémence", 20, 15), "deja fait aujourd'hui"
    mem = Memoire(tmp_path / "m.json")
    mem.donnees.update(d)
    b, _, horloge = cerveau(heure=20, memoire=mem, mur=lambda: 16 * 86400 + 3600.0)
    b.presents.add("Clémence")
    b.etats["chill"].duree = lambda brain: 0.1
    b.fin_etat = 0.0
    vivre(b, 2)
    noms = [e[1] for e in b.journal]
    assert "reclame" in noms or "nomme" in noms
    n = len(b.journal)
    vivre(b, 5)
    assert not {"reclame", "nomme"} & {e[1] for e in b.journal[n:]}, "une fois par jour"


# -- objet nouveau ------------------------------------------------------------------------------------------------------
def test_objet_nouveau_il_va_le_picorer():
    b, c, _ = cerveau(tof=TofDevant(0.8))
    zero(b)
    b.objet_nouveau = 0.8
    vivre(b, 12, evenements=[(0.1, "objet_nouveau")])
    noms = [e[1] for e in b.journal]
    assert "remarque" in noms and "inspecte" in noms and "peck" in sons(c)


# -- doudou -------------------------------------------------------------------------------------------------------------
class Balle:
    def position(self, age_max=1.5):
        return (1.0, 0.0)


def test_doudou_apres_quelques_parties():
    mem = type("M", (), {"donnees": {"balle": {"parties": 3}}, "familiarite": lambda self, q: 0.0,
                         "sauver": lambda self: None})()
    b, _, _ = cerveau(tof=Tof(), balle=Balle(), memoire=mem)
    zero(b)
    b.ctx.state = {"odom": {"position": [0.0, 0.0, 0.11], "yaw": 0.0}}
    assert b._va_doudou() == "va_doudou"
    x, y = b.etats["va_doudou"].cible
    assert abs(x - 0.75) < 1e-6 and abs(y) < 1e-6, "il s'arrete a 25 cm de sa balle"
    mem.donnees["balle"]["parties"] = 1
    b.derniere_fois.pop("doudou")
    assert b._va_doudou() is None, "pas encore son doudou"


# -- rythme -------------------------------------------------------------------------------------------------------------
def test_audio_motif():
    from test_audio import analyse, clap, fond, noms
    s = fond(6)
    for t in (2.0, 2.3, 2.6, 3.2):
        clap(s, t)
    m = [e for e in noms(analyse(s), motifs=True) if e.startswith("motif:")]
    ecarts = [int(x) for x in m[0][6:].split(",")] if len(m) == 1 else []
    assert len(ecarts) == 3 and all(abs(a - b) <= 25 for a, b in zip(ecarts, [300, 300, 600]))


def test_il_rejoue_le_rythme_tape():
    b, c, _ = cerveau()
    vivre(b, 6, evenements=[(0.1, "appel")])
    n = len(c.appels)
    vivre(b, 5, evenements=[(0.1, "motif:300,300,600"), (0.1, "appel")])
    assert "rythme" in [e[1] for e in b.journal]
    assert sons(c, n).count("peck") >= 4, "quatre coups de bec (un de plus s'il fait le malin)"
    b2, c2, _ = cerveau()
    vivre(b2, 2, evenements=[(0.1, "motif:300,300")])
    assert "rythme" not in [e[1] for e in b2.journal], "personne ne joue avec lui"


# -- nom sonore -----------------------------------------------------------------------------------------------------------
def test_nom_sonore():
    a, z = personnage.nom_sonore("Raphael"), personnage.nom_sonore("Clémence")
    assert a == personnage.nom_sonore("Raphael") and 2 <= len(a) <= 3 and set(a) <= SONS_CANARD and len(set(a)) > 1
    assert len({personnage.nom_sonore(q) for q in ("Raphael", "Clémence", "Léo", "Mamie", "Papi")}) >= 3

    class Mem:
        donnees = {}

        def familiarite(self, qui):
            return 0.9

        def rencontre(self, qui):
            pass

        def sauver(self):
            pass

    b, c, _ = cerveau(memoire=Mem())
    zero(b)
    b.malice.permise = lambda *a, **k: False
    b.presents.add("Raphael")
    n = len(c.appels)
    vivre(b, 10, evenements=[(0.1, "appel")])
    assert "nomme" in [e[1] for e in b.journal]
    s = sons(c, n)
    assert all(x in s for x in a), "il dit ton nom, a sa facon"


# -- ambiance ---------------------------------------------------------------------------------------------------------------
def voix(s, t0, duree, amp=0.3, f0=180.0):
    i0, n = int(t0 * audio.TAUX), int(duree * audio.TAUX)
    t = np.arange(n) / audio.TAUX
    s[i0:i0 + n] += amp * np.hanning(n) ** 0.3 * (np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(4 * np.pi * f0 * t))


def passe(s):
    a = audio.AnalyseurSon()
    out = []
    for i in range(0, len(s) - audio.BLOC + 1, audio.BLOC):
        out += a.bloc(s[i:i + audio.BLOC])
    return out


def test_audio_rire_et_voix_tendues():
    rng = np.random.default_rng(1)
    s = rng.normal(0, 0.0005, int(5 * audio.TAUX))
    for k in range(6):
        voix(s, 1.0 + 0.22 * k, 0.11, amp=0.2)            # ha-ha-ha-ha-ha-ha
    out = passe(s)
    assert "rire" in out and not any(e.startswith("enonce:") for e in out)
    s2 = rng.normal(0, 0.0005, int(5 * audio.TAUX))
    voix(s2, 1.0, 1.2, amp=0.2)                            # une phrase normale : pas un rire
    assert "rire" not in passe(s2)
    s3 = rng.normal(0, 0.0005, int(16 * audio.TAUX))
    for k in range(4):
        voix(s3, 1.0 + 3.0 * k, 1.5, amp=0.9)              # quatre eclats de voix tres forts
    assert "ambiance:tendue" in passe(s3)


def test_voix_tendues_il_se_fait_petit():
    b, c, _ = cerveau()
    n = len(c.appels)
    vivre(b, 3, evenements=[(0.1, "ambiance:tendue")])
    assert b.courant.nom == "petit" and not sons(c, n) and not b.malice.permise(b, "x", humain=True)


# -- bain de soleil -----------------------------------------------------------------------------------------------------------
def test_tache_de_soleil():
    img = np.full((640, 360, 3), 60, np.uint8)
    assert personnage.tache_soleil(img) is None
    img[450:600, 230:340] = 250                             # en bas a droite : une tache de lumiere au sol
    x, f = personnage.tache_soleil(img)
    assert x > 0.6 and f > 0.03
    haut = np.full((640, 360, 3), 60, np.uint8)
    haut[50:200, 100:300] = 250                             # une fenetre (en haut) : pas le sol
    assert personnage.tache_soleil(haut) is None


def test_il_va_au_soleil():
    b, c, _ = cerveau(tof=Tof(), soleil=lambda: (0.8, 0.1), soleil_synchrone=True)
    b.etats["chill"].duree = lambda brain: 0.5
    b.fin_etat = 1.0
    vivre(b, 20)
    assert "bain_soleil" in [e[1] for e in b.journal]
    assert any(m == "robot.do" for m, _ in c.appels) or b.ctx.sitting or "coo" in sons(c)
    b2, _, h = cerveau(heure=22, tof=Tof(), soleil=lambda: (0.5, 0.1), soleil_synchrone=True)
    b2.etats["chill"].duree = lambda brain: 0.5
    vivre(b2, 5)
    assert "bain_soleil" not in [e[1] for e in b2.journal], "la nuit, pas de soleil"
