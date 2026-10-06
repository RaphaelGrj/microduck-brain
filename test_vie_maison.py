#!/usr/bin/env python3
"""Pistes "vivant" du 2026-10-06 : rythme circadien, sons gratuits, discretion au telephone, visiteur inconnu, jour
special du calendrier, baillement contagieux, coup d'oeil peripherique, heure des repas, tenir compagnie."""
from brain import Brain, Humeur
from etats_base import SONS_CANARD
from test_brain import FauxClient, FauxHorloge


def vivre(b, secondes, pos=(0.0, 0.0), evenements=None, t0=None):
    evenements = sorted(evenements or [])
    t0 = b.t_global if t0 is None else t0
    for i in range(int(secondes / 0.02)):
        t = i * 0.02
        while evenements and evenements[0][0] <= t:
            b.evenement(evenements.pop(0)[1])
        b.tick({"t": t0 + t, "safety": {"fallen": False}, "policy": "stand",
                "odom": {"position": [pos[0], pos[1], 0.11], "yaw": 0.0}}, 0.02)


def sons(c, depuis=0):
    return [p["tag"] for m, p in c.appels[depuis:] if m == "robot.sound"]


class Tof:
    def noter_etat(self, s):
        pass

    def points(self, s):
        return []

    def libre(self, s):
        return {"devant": 3.0, "gauche": 3.0, "droite": 3.0, "vide": float("inf"), "n": 10}


def cerveau(heure=14, seed=50, **extras):
    c = FauxClient()
    horloge = FauxHorloge(heure)
    b = Brain(c, Humeur(energie=0.7), seed=seed, horloge=horloge, extras={"exploration": False, **extras})
    return b, c, horloge


# -- rythme circadien ---------------------------------------------------------------------------------------------
def test_vivacite_selon_l_heure_et_fatigue_plus_vite_la_nuit():
    b, _, h = cerveau(circadien=True)
    v = {}
    for heure in (3, 8, 13, 17, 21, 23):
        h.heure = heure
        v[heure] = b.vivacite()
    assert v[3] < v[23] < v[21] < v[17] and v[8] < v[17] and v[13] < v[17]
    assert max(v.values()) == v[17], "plus vif en fin d'apres-midi"
    sans, _, _ = cerveau()
    assert sans.vivacite() == 1.0, "opt-in : sans extras['circadien'], rien ne change"
    from etats_base import Humeur as H
    jour, nuit = H(energie=0.8), H(energie=0.8)
    for _ in range(500):
        jour.avance(0.02, "wander", 1.15)
        nuit.avance(0.02, "wander", 0.55)
    assert nuit.energie < jour.energie


# -- sons gratuits ------------------------------------------------------------------------------------------------
def test_sons_gratuits_rares_et_de_canard():
    b, c, _ = cerveau()
    b.etats["chill"].duree = lambda brain: 1e9
    b.fin_etat = 1e9
    vivre(b, 3600)
    s = sons(c)
    assert 1 <= len(s) <= 12, s
    assert set(s) <= SONS_CANARD
    b2, c2, _ = cerveau()
    b2.etats["chill"].duree = lambda brain: 1e9
    b2.fin_etat = 1e9
    vivre(b2, 3600, evenements=[(1.0, "calme_on")])
    assert sons(c2) == [], "jamais en mode calme"


# -- discretion au telephone --------------------------------------------------------------------------------------
def test_discret_pendant_un_appel_puis_reprend():
    b, c, _ = cerveau(tof=Tof())
    b.P_TAQUINE = 1.0
    vivre(b, 5)
    b._bascule("wander")
    n = len(c.appels)
    vivre(b, 600, evenements=[(0.5, "telephone"), (5.0, "intonation:monte"), (20.0, "appel"), (40.0, "musique:110")])
    assert b.discret
    assert sons(c, n) == [], "pas un son pendant l'appel"
    pendant = {e[1] for e in b.journal if e[0] > 5.2}     # apres la promenade lancee par le test
    assert pendant <= {"chill", "look", "appel", "danse", "sourde_oreille", "faux_endormi"}, pendant
    assert not any(m == "robot.move" and p["vx"] > 0 for m, p in c.appels[n + 50:]), "il ne se promene pas"
    vivre(b, 5, evenements=[(0.5, "telephone_fin")])
    assert not b.discret and not b.ctx.silence


def test_discretion_a_une_duree_maximale():
    b, _, _ = cerveau()
    b.evenement("telephone")
    vivre(b, b.DISCRET_MAX_S + 10)
    assert not b.discret


# -- visiteur inconnu ---------------------------------------------------------------------------------------------
def test_visiteur_apres_la_sonnette_timide_puis_apprivoise():
    b, c, _ = cerveau()
    vivre(b, 30, evenements=[(1.0, "sonnette:Entree"), (60.0, "voix")])
    vivre(b, 60, evenements=[(1.0, "voix")])
    assert b.visite is not None and b.timidite() > 0.9
    assert not b.malice.permise(b, "feinte_bec", humain=True), "pas de blague a un inconnu"
    vivre(b, 1300)
    noms = [e[1] for e in b.journal]
    debut = [e[1] for e in b.journal if e[0] < b.visite + 400].count("timide")
    fin = [e[1] for e in b.journal if e[0] > b.visite + 800].count("timide")
    assert debut > fin and "apprivoise" in noms, noms
    assert sons(c).count("inquire") >= 1


def test_un_habitant_qui_rentre_n_est_pas_un_visiteur():
    b, _, _ = cerveau()
    vivre(b, 30, evenements=[(1.0, "sonnette:Entree"), (3.0, "retour:Raphael|3600"), (10.0, "voix")])
    assert b.visite is None


# -- calendrier ---------------------------------------------------------------------------------------------------
def test_jour_special_une_fois_puis_a_chaque_habitant_qui_rentre():
    b, c, h = cerveau()
    vivre(b, 20, evenements=[(1.0, "jour_special:Anniversaire"), (10.0, "jour_special:Anniversaire")])
    assert [e[1] for e in b.journal].count("jour_special") == 1
    assert "wheee" in sons(c)
    vivre(b, 40, evenements=[(1.0, "retour:Raphael|3600")])
    noms = [e[1] for e in b.journal]
    assert noms.count("jour_special") == 2 and noms.index("accueil") < len(noms) - 1 - noms[::-1].index("jour_special")
    h.jour += 1
    vivre(b, 40, evenements=[(1.0, "depart:Raphael"), (5.0, "retour:Raphael|3600")])
    assert [e[1] for e in b.journal].count("jour_special") == 2, "le lendemain, ce n'est plus un jour special"


def test_calendrier_home_assistant():
    import pont_ha
    assert pont_ha.REACTIONS_PAR_TYPE["calendrier"] == {"on": "jour_special"}


# -- baillement contagieux ----------------------------------------------------------------------------------------
def test_baillement_contagieux_mais_pas_en_boucle():
    b, c, _ = cerveau()
    b.P_BAILLEMENT_CONTAGIEUX = 1.0
    vivre(b, 30, evenements=[(1.0, "baillement_entendu"), (15.0, "baillement_entendu")])
    assert [e[1] for e in b.journal].count("baillement_contagieux") == 1
    assert any(m == "robot.mouth" for m, _ in c.appels), "il ouvre le bec"


# -- coup d'oeil peripherique -------------------------------------------------------------------------------------
class VeilleMvt:
    def __init__(self):
        self.arme, self.dernier_centre, self.armements = False, None, 0

    def armer(self, periode_s=None):
        self.arme, self.dernier_centre = True, None
        self.armements += 1

    def desarmer(self):
        self.arme = False

    def a_bouge(self):
        return self.dernier_centre is not None


def test_coup_d_oeil_vers_un_mouvement_au_bord_seulement():
    for x, attendu in ((0.1, 0.5), (0.9, -0.5), (0.5, None)):
        v = VeilleMvt()
        b, c, _ = cerveau(mouvement=v)
        b.etats["chill"].duree = lambda brain: 1e9
        b.fin_etat = 1e9
        vivre(b, 3)
        assert v.arme, "veille armee au repos"
        v.dernier_centre = (0.0, x, 0.01)
        vivre(b, 2)
        noms = [e[1] for e in b.journal]
        if attendu is None:
            assert "coup_oeil" not in noms
        else:
            assert "coup_oeil" in noms and b.etats["coup_oeil"].lacet == attendu and not v.arme
            assert max(abs(p["head_yaw"]) for m, p in c.appels if m == "robot.head") > 0.3


def test_pas_de_coup_d_oeil_sur_son_propre_mouvement():
    v = VeilleMvt()
    b, _, _ = cerveau(mouvement=v)
    b.etats["chill"].duree = lambda brain: 1e9
    b.fin_etat = 1e9
    vivre(b, 3)
    v.dernier_centre = (0.0, 0.1, 0.4)          # toute l'image bouge : c'est lui qui bouge
    vivre(b, 2)
    assert "coup_oeil" not in [e[1] for e in b.journal]


# -- repas --------------------------------------------------------------------------------------------------------
def test_repas_appris_puis_rejoint_a_l_heure():
    b, c, h = cerveau(heure=12, tof=Tof(), repas=[(12, 30)])
    b.presents.add("Raphael")
    h.minute = 40
    for k in range(10):
        vivre(b, 2, pos=(2.0, 1.0), evenements=[(0.5, "voix")])       # on parle a table
    h.heure, h.jour = 15, h.jour + 1
    vivre(b, 30, pos=(0.0, 0.0))
    assert "va_repas" not in [e[1] for e in b.journal], "pas en dehors de l'heure"
    h.heure, h.minute = 12, 25
    b.fin_etat = 0.0
    vivre(b, 30, pos=(0.0, 0.0))
    noms = [e[1] for e in b.journal]
    assert noms.count("va_repas") == 1, noms
    assert b.etats["va_repas"].cible == (2.25, 1.25) or abs(b.etats["va_repas"].cible[0] - 2.0) < 0.5
    vivre(b, 60, pos=(0.0, 0.0))
    assert [e[1] for e in b.journal].count("va_repas") == 1, "une fois par repas"


def test_pas_de_repas_sans_horaires_ni_personne():
    b, _, h = cerveau(heure=12, tof=Tof())
    b.presents.add("Raphael")
    b.fin_etat = 0.0
    vivre(b, 30)
    assert "va_repas" not in [e[1] for e in b.journal]


# -- tenir compagnie ----------------------------------------------------------------------------------------------
def test_tenir_compagnie_la_ou_l_on_s_occupe_de_lui():
    b, c, _ = cerveau(tof=Tof())
    for _ in range(3):
        vivre(b, 5, pos=(1.5, 0.0), evenements=[(0.5, "caresse")])
    vivre(b, 10, pos=(0.0, 0.0))
    vivre(b, 2, pos=(0.0, 0.0), evenements=[(0.5, "compagnie")])
    assert b.courant.nom == "va_compagnie"
    b._bascule("compagnie")                      # arrive (navigation testee dans test_navigation.py)
    n = len(c.appels)
    b._t_babil = 1e9                             # (les sons gratuits ne jouent qu'en chill/look/wander de toute facon)
    vivre(b, 60, pos=(1.5, 0.0))
    assert b.courant.nom == "compagnie" and b.ctx.sitting
    assert sons(c, n) == [], "une presence silencieuse"
    assert not any(m == "robot.move" and (p["vx"] or p["vyaw"]) for m, p in c.appels[n:])
    vivre(b, 3, pos=(1.5, 0.0), evenements=[(0.5, "compagnie_fin")])
    assert b.courant.nom != "compagnie" and not b.ctx.sitting


def test_pas_de_compagnie_sans_lieu_appris():
    b, _, _ = cerveau(tof=Tof())
    vivre(b, 3, evenements=[(0.5, "compagnie")])
    assert "va_compagnie" not in [e[1] for e in b.journal] and "compagnie" not in [e[1] for e in b.journal]


# -- capteurs maison par la camera --------------------------------------------------------------------------------
def test_lumiere_oubliee_la_nuit_quand_la_maison_est_vide():
    lum = [0.6]
    b, _, h = cerveau(heure=23, luminosite=lambda: lum[0], luminosite_synchrone=True)
    vivre(b, 5, evenements=[(0.2, "presence:Raphael|home"), (0.3, "presence:Julie|absent")])
    vivre(b, 700)
    assert not b.lumiere_oubliee, "quelqu'un est a la maison"
    vivre(b, 700, evenements=[(0.5, "depart:Raphael")])
    assert b.lumiere_oubliee and b.lumiere == 0.6
    lum[0] = 0.05
    vivre(b, 700)
    assert not b.lumiere_oubliee, "eteinte"
    lum[0], h.heure = 0.6, 15
    vivre(b, 700)
    assert not b.lumiere_oubliee, "le jour, la piece est eclairee par le soleil"


def test_lumiere_rien_sans_suivi_de_presence():
    b, _, _ = cerveau(heure=23, luminosite=lambda: 0.9, luminosite_synchrone=True)
    vivre(b, 700)
    assert not b.lumiere_oubliee, "sans presence HA, 'personne a la maison' n'a pas de sens"


def test_objets_au_sol_et_lumiere_publies_dans_home_assistant():
    import time
    import pont_ha
    b, _, _ = cerveau()
    b.objets_au_sol = [(time.time() - 120, 1.2, 0.4)]
    b.lumiere_oubliee, b.lumiere = True, 0.42
    pont = pont_ha.PontHA.__new__(pont_ha.PontHA)
    pont._derniere_vue_chat = None
    pont.photographier(b, {})
    ent = pont.entites_du_canard()
    assert ent["sensor.microduck_objets_au_sol"][0] == 1
    assert ent["sensor.microduck_objets_au_sol"][1]["dernier_position_odom"] == "1.20,0.40"
    assert ent["binary_sensor.microduck_lumiere_oubliee"] == ("on", {
        "friendly_name": "Microduck - lumiere allumee sans personne", "icon": "mdi:lightbulb-alert", "luminosite": 0.42})


def test_luminosite_d_une_image():
    import numpy as np
    from vision import luminosite
    assert luminosite(np.zeros((64, 36, 3), np.uint8)) == 0.0
    assert abs(luminosite(np.full((64, 36, 3), 255, np.uint8)) - 1.0) < 1e-9


# -- ambiance, appareils, aspirateur -------------------------------------------------------------------------------
def test_vacarme_il_se_retire_puis_revient():
    b, c, _ = cerveau()
    vivre(b, 120, evenements=[(1.0, "vacarme")])
    noms = [e[1] for e in b.journal]
    assert "retrait" in noms and set(noms[noms.index("retrait") + 1:]) <= {"nap"}, noms
    assert b.ctx.sitting
    vivre(b, 60, evenements=[(1.0, "vacarme_fin")])
    assert not b.vacarme and not b.ctx.sitting, "le calme revenu, il se releve"


def test_bips_d_appareil_curiosite_rare():
    b, c, _ = cerveau()
    vivre(b, 30, evenements=[(1.0, "bips_appareil"), (15.0, "bips_appareil")])
    assert [e[1] for e in b.journal].count("bips") == 1 and "inquire" in sons(c)


def test_aspirateur_mefiance_puis_curiosite_puis_indifference():
    class Mem:
        def __init__(self):
            self.n = 0

        def familiarite(self, nom):
            return 1 - 0.85 ** self.n

        def rencontre(self, nom):
            self.n += 1
    m = Mem()
    b, _, _ = cerveau(memoire=m)
    reactions = []
    for k in range(10):
        b._bascule("chill")
        b.fin_etat = 1e9
        n = len(b.journal)
        vivre(b, 6, evenements=[(0.5, "aspirateur_on"), (5.0, "aspirateur_off")])
        reactions.append(b.journal[n][1] if len(b.journal) > n else None)
    assert reactions[0] == "mefiant" and "curious" in reactions and reactions[-1] is None, reactions


def test_visiteur_recurrent_de_moins_en_moins_timide():
    class Mem:
        def __init__(self):
            self.n = {}

        def familiarite(self, qui):
            return 1 - 0.7 ** self.n.get(qui, 0)

        def rencontre(self, qui):
            self.n[qui] = self.n.get(qui, 0) + 1
    m = Mem()
    b, _, _ = cerveau(memoire=m)
    departs = []
    for semaine in range(8):
        vivre(b, 2, evenements=[(0.5, "visiteur:Josiane")])
        departs.append(b.timidite())
        vivre(b, 2, evenements=[(0.5, "visiteur_fin:Josiane")])
    assert departs[0] > 0.95 and departs == sorted(departs, reverse=True), departs
    assert departs[-1] == 0.0, "bien connue : plus de timidite"
    vivre(b, 2, evenements=[(0.5, "visiteur")])
    assert b.timidite() > 0.95, "un inconnu reste un inconnu"


def test_batterie_faible_va_voir_quelqu_un_avant_la_prise_une_fois():
    b, _, _ = cerveau(tof=Tof())
    for _ in range(3):
        vivre(b, 5, pos=(1.5, 0.0), evenements=[(0.5, "caresse")])
    b.presents.add("Raphael")
    b.fin_etat = 0.0
    b._batterie_pct = 35.0
    vivre(b, 60, pos=(0.0, 0.0))
    b._batterie_pct = 35.0
    noms = [e[1] for e in b.journal]
    assert noms.count("va_social") == 1, noms
    b.presents.clear()
    b._social_fait = False
    vivre(b, 60, pos=(0.0, 0.0))
    assert [e[1] for e in b.journal].count("va_social") == 1, "personne a la maison : rien"


def test_personnalite_saisonniere():
    b, _, h = cerveau(heure=8, circadien=True)
    assert b.saison() == "mi_saison"
    b.evenement("temperature_ext:30.0")
    vivre(b, 0.1)
    assert b.saison() == "ete"
    matin = b.vivacite()
    h.heure = 15
    apres_midi = b.vivacite()
    b.evenement("temperature_ext:2.0")
    vivre(b, 0.1)
    assert b.saison() == "hiver" and b.facteur_sieste() == 1.3
    h.heure = 8
    assert matin > b.vivacite(), "l'ete, plus vif le matin qu'en hiver"
    assert apres_midi < 1.0, "l'ete, ramolli l'apres-midi"
    sans, _, _ = cerveau()
    sans.evenement("temperature_ext:2.0")
    vivre(sans, 0.1)
    assert sans.saison() == "mi_saison" and sans.facteur_sieste() == 1.0, "opt-in, comme le circadien"


def test_temperature_exterieure_depuis_home_assistant():
    import queue
    import pont_ha
    pont = pont_ha.PontHA.__new__(pont_ha.PontHA)
    pont.evenements, pont.log = queue.Queue(), lambda m: None
    pont.surveillance = {"sensor.dehors": {"temperature": True, "nom": "dehors"}}
    for v in ("12.0", "12.4", "13.1", "unavailable", "7.9"):
        pont._sur_changement("sensor.dehors", "11", v)
    assert [pont.evenements.get_nowait() for _ in range(pont.evenements.qsize())] == [
        "temperature_ext:12.0", "temperature_ext:13.1", "temperature_ext:7.9"]


def test_petarades_abri_prolonge():
    b, _, _ = cerveau()
    vivre(b, 120, evenements=[(1.0, "petarades")])
    noms = [e[1] for e in b.journal]
    assert noms[0] == "startle" and set(noms[1:]) <= {"nap", "va_au_coin"}, noms
    assert b.veille_jusqua > b.t_global and b.perso.trait("prudence") > 0.5


def test_voix_personnelle_renforcee_par_les_reactions_et_qui_derive():
    import random
    from personnalite import Personnalite
    p = Personnalite()
    rng = random.Random(1)
    for _ in range(10):
        p.renforce_son("peck")
    tirages = [p.choisit_son(rng) for _ in range(2000)]
    assert tirages.count("peck") > tirages.count("coo") * 2, "le son qui fait reagir la maison revient plus souvent"
    avant = dict(p.d["sons"])
    for _ in range(30):
        p.derive_sons(rng)
    assert p.d["sons"] != avant and all(0.3 <= v <= 3.0 for v in p.d["sons"].values())
    b, c, _ = cerveau()
    b.etats["chill"].duree = lambda brain: 1e9
    b.fin_etat = 1e9
    b._t_babil, b._dernier_babil = 0.0, "coo"
    b.t_global = 10.0
    poids = b.perso.d.setdefault("sons", {"coo": 1.0, "chirp": 1.0, "peck": 1.0})["coo"]
    vivre(b, 1, evenements=[(0.2, "caresse")])
    assert b.perso.d["sons"]["coo"] > poids, "une caresse juste apres un roucoulement : il le retient"


def test_journal_de_bord_du_jour_et_journal_borne():
    import pont_ha
    b, _, h = cerveau()
    for etat in ("wander", "nap", "balle", "caresse", "feinte_bec", "wander", "chill"):
        b._bascule(etat)
    assert b.du_jour == {"promenades": 2, "siestes": 1, "jeux": 1, "caresses": 1, "blagues": 1}
    pont = pont_ha.PontHA.__new__(pont_ha.PontHA)
    pont._derniere_vue_chat = None
    pont.photographier(b, {})
    etat, attrs = pont.entites_du_canard()["sensor.microduck_journal"]
    assert etat == 6 and attrs["promenades"] == 2 and attrs["danses"] == 0
    h.jour += 1
    b._bascule("nap")
    assert b.du_jour == {"siestes": 1}, "nouveau jour, nouveau journal"
    b.JOURNAL_MAX = 100
    for k in range(500):
        b._bascule("chill" if k % 2 else "look")
    assert len(b.journal) <= 100
