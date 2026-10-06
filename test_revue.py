#!/usr/bin/env python3
"""Non-regression des defauts trouves par la revue de code du 2026-10-06 (un test par defaut corrige)."""
import numpy as np
import pytest

from audio import AnalyseurSon, BLOC, TAUX, VoixPropre
from brain import Brain, Humeur
from test_brain import FauxClient, simule
from test_jeu_balle import cerveau as cerveau_balle


def sons(c):
    return [p["tag"] for m, p in c.appels if m == "robot.sound"]


def _tick(b, t, dt):
    b.tick({"t": t, "safety": {"fallen": False}, "policy": "stand"}, dt)


@pytest.mark.parametrize("hz", [10, 50])
def test_son_une_fois_quelle_que_soit_la_cadence(hz):
    # avant : fenetre de temps -> 2-3 fois a 50 Hz, jamais a 10 Hz
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=1)
    b.fin_etat = 1e9
    n0 = len(sons(c))
    for k in range(hz * 2):
        b.son_une_fois("cle", "chirp")
        _tick(b, k / hz, 1.0 / hz)
    assert sons(c)[n0:].count("chirp") == 1
    b._bascule("chill")                         # nouvelle entree dans un etat : le son peut rejouer
    b.son_une_fois("cle", "chirp")
    assert sons(c)[n0:].count("chirp") == 2


def test_fin_jeu_arrete_le_jeu_de_balle():
    b, c, _ = cerveau_balle(None)
    b._bascule("balle")
    simule(b, 1)
    b.evenement("fin_jeu")
    simule(b, 0.1)
    assert b.etats["balle"].resultat == "arrete" or b.courant.nom != "balle"
    simule(b, 10)
    assert b.courant.nom != "balle", "fin_jeu doit sortir du jeu de balle"


def test_fin_jeu_arrete_le_cache_cache():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=3, extras={"exploration": False})
    b._bascule("cache_cache")
    simule(b, 2)
    b.evenement("fin_jeu")
    simule(b, 15)
    assert b.courant.nom != "cache_cache"


def test_chute_en_mode_calme_puis_releve_se_recale_debout_puis_se_rassoit():
    c = FauxClient()
    b = Brain(c, Humeur(energie=0.9), seed=4)
    b.evenement("calme_on")
    simule(b, 20)
    assert b.ctx.sitting
    simule(b, 10, tombe_entre=(1.0, 4.0))       # renverse ; robotd le releve DEBOUT (policy stand)
    assert b.courant.nom == "nap"
    assert b.ctx.sitting, "remis debout par robotd, il doit se rasseoir pour sa sieste (etat assis resynchronise)"
    n = sum(1 for m, p in c.appels if m == "robot.do" and p == {"skill": "sit_toggle"})
    assert n >= 2, "un sit_toggle pour s'asseoir, un autre apres le relevement"


def test_camera_distante_refusee():
    from vision import grab_frame
    with pytest.raises(RuntimeError, match="distante"):
        grab_frame("http://192.168.1.20:8080/frame")


def test_voix_propre_rend_le_micro_sourd_pendant_le_son():
    t = [0.0]
    v = VoixPropre(horloge=lambda: t[0])
    assert not v.muet()
    v.parle("alarm")
    t[0] = 1.0
    assert v.muet()
    t[0] = 1.2 + VoixPropre.MARGE_S + 0.01
    assert not v.muet()


def test_bloc_muet_ne_declenche_rien():
    # le "wheee" ou l'alarm du canard lui-meme ne doivent ni declencher un sursaut, ni passer pour une alarme incendie
    a = AnalyseurSon()
    rng = np.random.default_rng(0)
    for _ in range(int(3 * TAUX / BLOC)):
        assert a.bloc(rng.normal(0, 0.003, BLOC)) == []
    t0 = a.t
    for _ in range(int(2 * TAUX / BLOC)):
        a.bloc_muet(BLOC)                       # le canard joue un son tres fort : rien n'est analyse
    assert a.t > t0
    evts = []
    for _ in range(int(2 * TAUX / BLOC)):
        evts += a.bloc(rng.normal(0, 0.003, BLOC))
    assert evts == [], evts


# --- relecture du 2026-10-06 (nuit) : diagnostic, pistes "vivant", capteurs maison -------------------------------
from test_vie_maison import Tof, cerveau as cerveau_vie, vivre


def test_r1_au_telephone_il_fait_quand_meme_la_sieste_s_il_est_fatigue():
    b, _, _ = cerveau_vie()
    b.humeur.energie = 0.1
    vivre(b, 120, evenements=[(0.5, "telephone")])
    assert "nap" in [e[1] for e in b.journal]


def test_r2_compagnie_ne_detourne_pas_d_une_activite():
    b, _, _ = cerveau_vie(tof=Tof())
    for _ in range(3):
        vivre(b, 5, pos=(1.5, 0.0), evenements=[(0.5, "caresse")])
    for etat in ("va_chargeur", "soleil", "danse", "autotest", "chaud"):
        if etat == "va_chargeur":
            b.etats["va_chargeur"].cible = (3.0, 0.0)
        b._bascule(etat)
        b.evenement("compagnie")
        vivre(b, 0.1)
        assert b.courant.nom not in ("va_compagnie", "compagnie"), etat
    b._bascule("chill")
    b._batterie_pct = 10.0
    b.evenement("compagnie")
    vivre(b, 0.1)
    assert b.courant.nom not in ("va_compagnie", "compagnie"), "batterie basse"


def test_r3_r4_l_alarme_parle_pendant_un_appel_et_le_silence_revient_apres():
    b, c, _ = cerveau_vie()
    vivre(b, 1, evenements=[(0.2, "alarme_fumee:Salon")])
    vivre(b, 6, evenements=[(0.2, "telephone")])
    n_avant = sum(1 for m, p in c.appels if m == "robot.sound" and p["tag"] == "alarm")
    vivre(b, 6)
    assert sum(1 for m, p in c.appels if m == "robot.sound" and p["tag"] == "alarm") > n_avant, "l'alarme continue"
    vivre(b, 20)
    assert b.courant.nom != "alarme" and b.ctx.silence, "fin d'alarme pendant l'appel : il se tait de nouveau"


def test_r5_le_bec_n_est_pas_un_servo_de_la_jambe():
    from diagnostic import SanteServos, SERVOS
    assert len(SERVOS) == 15 and SERVOS[9] == "mouth" and SERVOS[14] == "right_ankle"
    s = SanteServos()
    for j in range(5):
        for _ in range(600):
            joints, targets = [0.0] * 15, [0.01] * 15
            targets[9] = 0.5 if j == 4 else 0.01            # le dernier jour, le bec s'ouvre (baillement, voix)
            targets[14] = 0.1 if j == 4 else 0.01           # ... et la cheville droite derive vraiment
            s.note_repos(f"j{j}", joints, targets)
    assert {n for n, _, _, _ in s.derives()} == {"right_ankle"}


def test_r6_une_danse_interrompue_relache_la_pose_du_corps():
    b, c, _ = cerveau_vie()
    vivre(b, 4, evenements=[(0.2, "musique:110")])
    assert b.courant.nom == "danse" and b.ctx.pose_active
    vivre(b, 1, evenements=[(0.2, "bruit")])
    assert not b.ctx.pose_active
    assert c.appels[-1] != ("robot.pose", None)


def test_r7_le_resume_de_diagnostic_n_est_pas_recalcule_a_chaque_trame():
    import pont_ha
    b, _, _ = cerveau_vie()
    n = [0]
    vrai = b.diagnostic.resume
    b.diagnostic.resume = lambda: (n.__setitem__(0, n[0] + 1), vrai())[1]
    pont = pont_ha.PontHA.__new__(pont_ha.PontHA)
    pont._derniere_vue_chat = None
    for _ in range(500):
        pont.photographier(b, {})
    assert n[0] == 1


def test_r8_autotest_tof_ok_dans_une_piece_degagee():
    from test_diagnostic import ClientRobot, faire_vivre, cerveau as cerveau_diag

    class TofVide(Tof):
        def libre(self, s):
            return {"devant": 4.0, "gauche": 4.0, "droite": 4.0, "vide": float("inf"), "n": 0}
    c = ClientRobot()
    b = cerveau_diag(c, tof=TofVide())
    b.fin_etat = 0.0
    faire_vivre(b, c, 40)
    assert b.diagnostic.autotest.resultats["tof"][0]


def test_r9_une_longue_tirade_n_est_ni_un_baillement_ni_un_appel_telephonique():
    from test_audio import analyse, fond, noms, voix as voix_synth
    s = fond(12)
    voix_synth(s, 2.0, 6.0, 260, 120)                  # 6 s qui descendent, apres un silence
    evts = noms(analyse(s))
    assert "baillement_entendu" not in evts and not any(e.startswith("intonation") for e in evts), evts
    s = fond(100)
    t = 1.0
    while t < 70:
        voix_synth(s, t, 5.0, 180, 185)                # monologue : 5 s de parole, 0,5 s de blanc
        t += 5.5
    assert "telephone" not in noms(analyse(s)), "parle presque sans arret : pas un appel"


def test_r10_lumiere_seulement_avec_la_presence_initiale_de_ha():
    b, _, _ = cerveau_vie(heure=23, luminosite=lambda: 0.9, luminosite_synchrone=True)
    vivre(b, 700, evenements=[(0.5, "depart:Raphael")])      # Julie etait la avant le demarrage : on ne le sait pas
    assert not b.lumiere_oubliee
    import pont_ha

    class Cli:
        def _get(self, chemin):
            return {"state": {"/api/states/person.raphael": "not_home", "/api/states/person.julie": "home"}[chemin]}
    pont = pont_ha.PontHA.__new__(pont_ha.PontHA)
    pont.client, pont.log = Cli(), lambda m: None
    pont.surveillance = {"person.raphael": {"habitant": True, "nom": "Raphael"},
                         "person.julie": {"habitant": True, "nom": "Julie"}, "sensor.x": {}}
    import queue
    pont.evenements = queue.Queue()
    pont.lire_presence_initiale()
    lus = [pont.evenements.get_nowait() for _ in range(pont.evenements.qsize())]
    assert lus == ["presence:Raphael|absent", "presence:Julie|home"]
    vivre(b, 700, evenements=[(0.5, lus[0]), (0.6, lus[1])])
    assert not b.lumiere_oubliee, "Julie est la"
    vivre(b, 700, evenements=[(0.5, "depart:Julie")])
    assert b.lumiere_oubliee, "maison vide pour de bon"


def test_r11_le_cycle_de_batterie_survit_au_redemarrage():
    from diagnostic import JournalBatterie
    d = {}
    j = JournalBatterie(d)
    t = 0.0
    for p in range(100, 29, -1):                       # decharge de 100 a 30 %, une mesure par minute
        j.note(t, float(p))
        t += 60
    j2 = JournalBatterie(d)                             # eteint, batterie changee, rallume a 95 %
    j2.note(t + 600, 95.0)
    assert len(d["cycles"]) == 1 and d["cycles"][0]["de"] == 100.0 and d["cycles"][0]["a"] == 30.0


def test_r12_compagnie_fin_pendant_le_trajet_annule():
    b, _, _ = cerveau_vie(tof=Tof())
    for _ in range(3):
        vivre(b, 5, pos=(1.5, 0.0), evenements=[(0.5, "caresse")])
    vivre(b, 10, pos=(0.0, 0.0))
    vivre(b, 2, pos=(0.0, 0.0), evenements=[(0.5, "compagnie")])
    assert b.courant.nom == "va_compagnie"
    vivre(b, 3, pos=(0.0, 0.0), evenements=[(0.5, "compagnie_fin")])
    assert "compagnie" not in [e[1] for e in b.journal]


def test_r13_carte_chaude_pas_de_veille_peripherique():
    from test_vie_maison import VeilleMvt
    v = VeilleMvt()
    b, _, _ = cerveau_vie(mouvement=v)
    b.cpu_chaud = True
    b.etats["chill"].duree = lambda brain: 1e9
    b.fin_etat = 1e9
    vivre(b, 5)
    assert v.armements == 0


def test_memoire_compacte_et_ecriture_differee():
    import json
    import tempfile
    import time
    from pathlib import Path
    from memoire import Memoire
    with tempfile.TemporaryDirectory() as d:
        m = Memoire(Path(d) / "m.json", ecriture_differee=True)
        for k in range(50):
            m.rencontre(f"etre{k}")
        m.vider()
        texte = (Path(d) / "m.json").read_text()
        assert "\n" not in texte and len(json.loads(texte)["etres"]) == 50, "JSON compact, complet"
        m.blague("pousse_balle")
        for _ in range(100):                     # le fil ecrivain finit par l'ecrire seul
            if "pousse_balle" in (Path(d) / "m.json").read_text():
                break
            time.sleep(0.01)
        assert Memoire(Path(d) / "m.json").blagues() == {"pousse_balle": 1}


# --- relecture de l'utilisateur (2026-10-07) ---------------------------------------------------------------------
def test_u1_heures_calmes_de_ha_toml_jusqu_au_cerveau():
    """La chaine complete : [cerveau] de ha.toml -> options_cerveau -> brain.run -> Brain. La nuit, il passe en calme."""
    import brain
    import pont_ha
    from test_brain import FauxHorloge
    for valeur in ([23, 7], "23-7"):
        options = pont_ha.options_cerveau({"cerveau": {"heures_calmes": valeur}})
        assert options == {"heures_calmes": (23, 7)}, valeur

        class Client:
            def __init__(self):
                self.appels, self.t = [], 0.0

            def notify(self, m, p=None):
                self.appels.append((m, p))

            def request(self, m, p=None, **kw):
                self.appels.append((m, p))
                return {"result": {"accepted": True}}

            def read_state_frame(self):
                self.t += 0.02
                return {"t": self.t, "safety": {"fallen": False}, "policy": "stand"}
        vus = []
        brain.run(Client(), 0.3, a_chaque_tick=lambda b, s: vus.append(b.mode_calme), horloge=FauxHorloge(2), **options)
        assert vus and vus[-1], "a 2 h du matin, les heures calmes 23-7 doivent mettre le canard en calme"
    assert pont_ha.options_cerveau({"cerveau": {"heures_calmes": "nuit"}}) == {}


def test_u2_champs_null_de_robotd_ne_plantent_pas_le_tick():
    """robotd peut envoyer "battery": null (bus pas encore lu), "safety": null, "odom": null, "frames": null."""
    from test_vie_maison import cerveau as cerveau_vie
    b, _, _ = cerveau_vie()
    b._bascule("regarde_chat")
    for k in range(200):
        b.tick({"t": k * 0.02, "battery": None, "safety": None, "odom": None, "frames": None, "joints": None,
                "policy": "stand"}, 0.02)
    import collections
    import tof
    t = tof.Tof.__new__(tof.Tof)
    t.historique = collections.deque(maxlen=60)
    for etat in ({"t_ns": 1, "frames": None}, {"t_ns": 2, "frames": {"tof": {"pos": [0, 0, 0]}}, "odom": None}, None):
        t.noter_etat(etat)                      # trames incompletes : ignorees, sans exception
    assert not t.historique


def test_u3_regarder_le_chat_sans_odometrie_ne_plante_pas():
    from etats_vie import regarde_chat
    from test_vie_maison import cerveau as cerveau_vie
    b, c, _ = cerveau_vie()

    class Veille:
        def cible_regard(self, h):
            return (1.0, 0.0, 0.1)
    assert regarde_chat(b, Veille(), {"odom": None}) is None
    assert regarde_chat(b, Veille(), None) is None
    regarde_chat(b, Veille(), {"odom": {"position": [0, 0, 0.11]}})
    assert ("robot.look", {"x": 1.0, "y": 0.0, "z": 0.1}) in c.appels


# --- relecture du dernier lot (2026-10-07) -----------------------------------------------------------------------
def test_v4_visiteur_sans_prenom_reste_un_inconnu():
    import tempfile
    from pathlib import Path
    import pont_ha
    toml = """
[home_assistant]
url = "http://ha.local:8123"
[[declencheur]]
evenement = "visiteur"
entite = "binary_sensor.porte_entree"
etat = "on"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "ha.toml").write_text(toml)
        cfg = pont_ha.lire_config(Path(d) / "ha.toml")
    pont = pont_ha.PontHA(cfg, "jeton", log=lambda m: None)
    pont._sur_changement("binary_sensor.porte_entree", "off", "on")
    assert pont.source() == ["visiteur"], "pas 'visiteur:binary_sensor.porte_entree' (memorise comme un etre)"


def test_v_infos_maison_ne_comptent_pas_comme_une_interaction():
    from test_vie_maison import cerveau as cerveau_vie, vivre
    b, _, _ = cerveau_vie()
    vivre(b, 5)
    avant = b.derniere_interaction
    vivre(b, 2, evenements=[(0.5, "temperature_ext:12.0"), (0.6, "presence:Raphael|home")])
    assert b.derniere_interaction == avant and b.temperature_ext == 12.0 and "Raphael" in b.presents


def test_v_ton_recu_dans_les_bras_n_est_pas_rejoue():
    from test_vie_maison import cerveau as cerveau_vie
    b, _, _ = cerveau_vie()
    for k in range(50):
        b.tick({"t": k * 0.02, "safety": {"fallen": False, "picked_up": True}, "policy": "stand"}, 0.02)
    b.evenement("ton:gronde")
    for k in range(50, 100):
        b.tick({"t": k * 0.02, "safety": {"fallen": False, "picked_up": True}, "policy": "stand"}, 0.02)
    for k in range(100, 300):
        b.tick({"t": k * 0.02, "safety": {"fallen": False, "picked_up": False}, "policy": "stand"}, 0.02)
    assert "penaud" not in [e[1] for e in b.journal]


def test_v_temperatures_par_capteur():
    import queue
    import pont_ha
    pont = pont_ha.PontHA.__new__(pont_ha.PontHA)
    pont.evenements, pont.log = queue.Queue(), lambda m: None
    pont.surveillance = {"sensor.nord": {"temperature": True}, "sensor.sud": {"temperature": True}}
    for e, v in (("sensor.nord", "10.0"), ("sensor.sud", "18.0"), ("sensor.nord", "10.2"), ("sensor.sud", "18.3")):
        pont._sur_changement(e, "0", v)
    assert pont.evenements.qsize() == 2, "deux capteurs differents ne se reveillent pas l'un l'autre"


def test_v_memoire_fermer_sauve_l_etat_actuel():
    import tempfile
    from pathlib import Path
    from memoire import Memoire
    with tempfile.TemporaryDirectory() as d:
        m = Memoire(Path(d) / "m.json", ecriture_differee=True)
        m.donnees["personnalite"] = {"traits": {"curiosite": 0.7}}     # change sans sauvegarde (comme les traits)
        m.fermer()
        assert Memoire(Path(d) / "m.json").donnees["personnalite"]["traits"]["curiosite"] == 0.7


def test_w_enchainement_force_respecte_l_appel_et_le_visiteur():
    from test_vie_maison import cerveau as cerveau_vie, vivre
    b, _, _ = cerveau_vie()
    b.evenement("telephone")
    vivre(b, 1)
    b.suivant_force = "zoomies"
    b.fin_etat = 0.0
    vivre(b, 0.1)
    assert b.courant.nom != "zoomies"
    b.suivant_force = "nap"                     # une sieste, elle, reste permise
    b.fin_etat = 0.0
    vivre(b, 0.1)
    assert b.courant.nom == "nap"


def test_w_autotest_tete_mesuree_meme_a_10_hz():
    from test_diagnostic import ClientRobot, cerveau as cerveau_diag
    c = ClientRobot()
    b = cerveau_diag(c)
    b._bascule("autotest")
    for k in range(60):                         # 10 trames par seconde : aucune ne tombe dans [1,6 ; 1,7)
        joints = [0.0] * 15
        joints[5:9] = [0.95 * x for x in c.tete]
        b.tick({"t": 0.05 + k * 0.1, "safety": {"fallen": False}, "policy": "stand", "joints": joints,
                "targets": [0.0] * 15}, 0.1)
    assert b.diagnostic.autotest.resultats["tete_lacet"][0], b.diagnostic.autotest.resultats


# --- relecture des actions HA et du mode garde ---------------------------------------------------------------------
def test_x_actions_dangereuses_ou_mal_ecrites_ignorees():
    import pont_ha
    la = pont_ha.lire_action
    assert la({"quand": "accueil", "service": "light.turn_on"}) is None, "sans cible : toute la maison"
    assert la({"quand": "accueil", "service": "light.turn_on", "donnees": {"entity_id": "A_REMPLIR"}}) is None
    assert la({"quand": "accueil", "service": "notify.notify", "donnees": {"message": "coucou"}}) is not None
    assert la({"quand": "accueil", "service": "light.turn_on", "donnees": {"area_id": "salon"}}) is not None
    for h in (["22", "6"], "22-6"):
        assert la({"quand": "nap", "service": "scene.turn_on", "entite": "scene.nuit", "heures": h})["heures"] == (22, 6)
    for h in ([22], [7, 7], [25, 6], "nuit"):
        assert la({"quand": "nap", "service": "scene.turn_on", "entite": "scene.nuit", "heures": h}) is None, h
    assert la({"quand": "nap", "service": "scene.turn_on", "entite": "scene.nuit", "delai_min_s": "vite"}) is None
    assert la({"voix": "danse", "service": "light.toggle", "entite": "light.x"}, interdites={"danse"}) is None


def test_x_voix_et_quand_ne_se_melangent_pas_et_pas_de_double_sonnette():
    import pont_ha
    a = pont_ha.lire_action({"voix": "ouvre", "quand": "sonnette", "service": "lock.unlock", "entite": "lock.x"})
    assert a["voix_evt"] == "maison:ouvre"
    etats = {"sonnette", "chill"}
    assert pont_ha.action_concernee(a, "maison:ouvre", etats)
    assert pont_ha.action_concernee(a, "etat:sonnette", etats) and not pont_ha.action_concernee(a, "sonnette:Entree", etats)
    e = pont_ha.lire_action({"quand": "evenement:sonnette", "service": "notify.notify"})
    assert pont_ha.action_concernee(e, "sonnette:Entree", etats) and not pont_ha.action_concernee(e, "etat:sonnette", etats)


def test_x_garde_ne_s_entend_pas_lui_meme_et_presence_incomplete():
    import time as _t
    from test_vie_maison import cerveau as cerveau_vie, vivre
    b, _, _ = cerveau_vie(garde=True)
    alertes = []
    b.ecouteurs.append(lambda e: alertes.append(e) if e.startswith("garde:") else None)
    vivre(b, 1, evenements=[(0.1, "presence:Raphael|absent"), (0.2, "presence:Julie|inconnu")])
    vivre(b, 1, evenements=[(0.1, "voix")])
    assert alertes == [], "Julie : etat inconnu, la maison n'est pas vide"
    vivre(b, 1, evenements=[(0.1, "depart:Julie")])
    b.ctx.t_dernier_son = _t.monotonic()        # il vient de faire "coo"
    vivre(b, 1, evenements=[(0.1, "voix")])
    assert alertes == [], "c'etait lui"
    b.ctx.t_dernier_son = -1e9
    b._bascule("chill")
    vivre(b, 1, evenements=[(0.1, "voix")])
    assert alertes == ["garde:voix"]


def test_x_journal_du_jour_a_minuit_et_apres_redemarrage():
    from test_vie_maison import cerveau as cerveau_vie, vivre

    class Mem:
        donnees = {}

        def sauver(self):
            pass
    m = Mem()
    b, _, h = cerveau_vie(memoire=m)
    b._bascule("wander")
    b._bascule("nap")
    b.etats["nap"].total = 1e9
    b.fin_etat = 1e9
    b2, _, _ = cerveau_vie(memoire=m)           # redemarrage dans la journee
    vivre(b2, 61)
    assert b2.du_jour.get("siestes", 0) >= 1, "la matinee est reprise"
    h.jour += 1                                 # (meme horloge partagee ? non : on avance celle de b)
    b.horloge.jour = h.jour
    vivre(b, 61)
    assert b.du_jour == {}, "minuit : remis a zero sans changer d'etat"
