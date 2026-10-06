#!/usr/bin/env python3
"""Diagnostic / auto-surveillance (diagnostic.py) : batterie dans la duree, derive des servos, journal des chutes,
auto-test au reveil, et leur publication dans Home Assistant."""
from brain import Brain, Humeur
from diagnostic import Diagnostic, JournalBatterie, JournalChutes, SanteServos, SERVOS, verdict_sante
from test_brain import FauxHorloge


def cycles(j, vitesses, t0=0.0):
    """Joue des cycles : charge a 100 %, decharge jusqu'a 30 % a `v` %/h (une mesure par minute), puis rebranche."""
    t = t0
    for v in vitesses:
        for p in range(30, 101, 5):             # charge
            j.note(t, float(p))
            t += 300
        for _ in range(60):                     # une heure de plus sur le chargeur, plein
            j.note(t, 100.0)
            t += 60
        pct = 100.0
        while pct > 30.0:                       # decharge
            pct -= v / 60.0
            j.note(t, pct)
            t += 60
    j.note(t, 40.0)                             # rebranche : clot le dernier cycle
    j.note(t + 300, 50.0)
    return t


def test_batterie_cycles_autonomie_et_sante():
    j = JournalBatterie()
    cycles(j, [70.0] * 5)
    assert len(j.d["cycles"]) == 5
    assert abs(j.autonomie_h() - 100 / 70) < 0.05
    assert j.sante_pct() is None, "pas de verdict avant 10 cycles"
    cycles(j, [70.0] * 3 + [110.0] * 5, t0=1e7)   # elle vieillit : se vide 57 % plus vite
    assert 60.0 <= j.sante_pct() <= 67.0 and j.a_remplacer()


def test_batterie_pas_de_faux_cycle_sur_un_rebond_de_tension():
    j = JournalBatterie()
    t, pct = 0.0, 100.0
    for k in range(240):                        # 4 h : la tension remonte de 3 % a chaque arret de marche
        pct -= 0.25
        j.note(t, pct + (3.0 if k % 20 < 5 else 0.0))
        t += 60
    assert not j.en_charge and j.d["cycles"] == []


def jour_de_repos(s, jour, courant_genou=100.0, ecart_genou=0.01):
    for _ in range(600):
        joints = [0.0] * 15
        targets = [0.01] * 15
        targets[3] = ecart_genou
        courants = [100.0] * 15
        courants[3] = courant_genou
        s.note_repos(jour, joints, targets, courants)


def test_servos_derive_par_rapport_au_temoin():
    s = SanteServos()
    for j in range(4):
        jour_de_repos(s, f"j{j}")
    assert s.derives() == []
    jour_de_repos(s, "j5", courant_genou=180.0, ecart_genou=0.08)
    d = s.derives()
    assert {(n, q) for n, q, _, _ in d} == {("left_knee", "courant"), ("left_knee", "ecart")}, d
    assert SERVOS[3] == "left_knee"


def test_servo_le_plus_souvent_chaud():
    s = SanteServos()
    for _ in range(15):
        s.note_plus_chaud("right_hip_pitch")
    for _ in range(10):
        s.note_plus_chaud("left_knee")
    assert s.plus_chaud_habituel() == "right_hip_pitch"
    for _ in range(30):
        s.note_plus_chaud("left_knee")
    assert s.plus_chaud_habituel() == "left_knee"


def test_journal_des_chutes_lieu_et_activite():
    j = JournalChutes()
    t = 1e9
    for k in range(3):
        j.note(t + k * 3600, "wander", (1.0 + 0.1 * k, 2.0), session=1)
    j.note(t + 4 * 3600, "zoomies", (5.0, 5.0), session=1)
    j.note(t + 5 * 3600, "wander", (1.0, 2.0), session=2)        # autre session : repere odometrique different
    assert len(j.recentes(t + 6 * 3600)) == 5
    assert j.activite_risquee(t + 6 * 3600) == "wander"
    lieux = j.lieux_a_risque(t + 6 * 3600)
    assert len(lieux) == 1 and lieux[0][0] == 1 and lieux[0][3] == 3
    assert j.recentes(t + 30 * 86400) == []


def test_verdict_sante_robotd():
    ok = verdict_sante({"healthy": True, "control_loop": {"target_hz": 50, "achieved_hz": 49.8},
                        "bus": {"consecutive_errors": 0}, "imu": {"ready": True, "consecutive_stale_blocks": 0}})
    assert all(v[0] for v in ok.values()) and set(ok) == {"robotd", "boucle", "bus", "imu"}
    ko = verdict_sante({"healthy": False, "reason": "bus", "control_loop": {"target_hz": 50, "achieved_hz": 40},
                        "bus": {"consecutive_errors": 3}, "imu": {"ready": True, "consecutive_stale_blocks": 30}})
    assert not any(v[0] for v in ko.values())
    assert verdict_sante(None) == {"robotd": (False, "robot.health sans reponse")}


class ClientRobot:
    """Faux robotd : la tete suit ses consignes (ou pas, si `tete_bloquee`)."""
    def __init__(self, tete_bloquee=False, sante=None):
        self.appels, self.tete = [], [0.0] * 4
        self.tete_bloquee = tete_bloquee
        self.sante = sante or {"healthy": True, "bus": {}, "imu": {"ready": True},
                               "motors": {"hottest": "left_knee", "max_c": 40.0, "mean_c": 35.0}}

    def notify(self, m, p=None):
        self.appels.append((m, p))
        b = getattr(self, "b", None)
        if m == "robot.move" and (p["vx"] or p["vyaw"]) and b is not None and b.courant.nom == "autotest":
            self.pas_en_autotest = True
        if m == "robot.head" and not self.tete_bloquee:
            self.tete = [p["neck_pitch"], p["head_pitch"], p["head_yaw"], p["head_roll"]]

    def request(self, m, p=None, **kw):
        self.appels.append((m, p))
        if m == "robot.health":
            return {"result": self.sante}
        return {"result": {"accepted": True}}


class Tof:
    def noter_etat(self, s):
        pass

    def points(self, s):
        return []

    def libre(self, s):
        return {"devant": 2.0, "gauche": 2.0, "droite": 2.0, "vide": float("inf"), "n": 12}


def faire_vivre(b, c, secondes, t0=0.0, pct=80.0):
    for k in range(int(secondes / 0.02)):
        joints = [0.0] * 15
        joints[5:9] = [0.95 * x for x in c.tete]
        b.tick({"t": t0 + k * 0.02, "safety": {"fallen": False}, "policy": "stand", "joints": joints,
                "targets": [0.0] * 15, "battery": {"percent": pct}}, 0.02)


def cerveau(client, camera=lambda: True, **extras):
    return Brain(client, Humeur(energie=0.9), seed=3, horloge=FauxHorloge(9),
                 extras={"tof": Tof(), "exploration": False, "autotest": True, "camera_test": camera,
                         "mur": lambda: 1.7e9, **extras})


def test_autotest_au_premier_reveil_du_jour_tout_va_bien():
    c = ClientRobot()
    b = cerveau(c)
    c.b = b
    b.fin_etat = 0.0
    faire_vivre(b, c, 40)
    assert "autotest" in [e[1] for e in b.journal]
    assert b.diagnostic.autotest.ok(), b.diagnostic.autotest.resultats
    assert {"robotd", "bus", "imu", "tof", "camera", "tete_lacet", "tete_tangage"} <= set(b.diagnostic.autotest.resultats)
    assert ("robot.sound", {"tag": "chirp"}) in c.appels
    faire_vivre(b, c, 120)
    assert [e[1] for e in b.journal].count("autotest") == 1, "une seule fois par jour"
    assert not getattr(c, "pas_en_autotest", False), "aucun pas pendant l'auto-test"


def test_autotest_tete_bloquee_et_camera_muette():
    def camera():
        raise TimeoutError
    c = ClientRobot(tete_bloquee=True)
    b = cerveau(c, camera=camera)
    b.fin_etat = 0.0
    faire_vivre(b, c, 40)
    assert set(b.diagnostic.autotest.echecs()) == {"tete_lacet", "tete_tangage", "camera"}
    assert ("robot.sound", {"tag": "inquire"}) in c.appels and ("robot.sound", {"tag": "alarm"}) not in c.appels


def test_autotest_desactive_par_defaut():
    c = ClientRobot()
    b = Brain(c, Humeur(energie=0.9), seed=3, extras={"exploration": False})
    b.fin_etat = 0.0
    faire_vivre(b, c, 60)
    assert "autotest" not in [e[1] for e in b.journal]


def test_chute_journalisee_et_servo_chaud_note():
    c = ClientRobot()
    b = cerveau(c)
    b._jour_autotest = 100                      # deja fait aujourd'hui
    b._bascule("wander")
    faire_vivre(b, c, 1)
    b.tick({"t": 1.0, "safety": {"fallen": True}, "policy": None, "odom": {"position": [0.5, 0.2, 0.1], "yaw": 0.0}}, 0.02)
    ch = b.diagnostic.chutes.d["chutes"]
    assert len(ch) == 1 and ch[0]["activite"] == "wander" and ch[0]["x"] == 0.5 and ch[0]["heure"] == 9
    assert b.diagnostic.servos.d["plus_chaud"].get("left_knee", 0) >= 1


def test_servos_mesures_seulement_au_repos_debout():
    c = ClientRobot()
    b = cerveau(c)
    b._jour_autotest = 100
    b._bascule("chill")
    b.fin_etat = 1e9
    faire_vivre(b, c, 5)
    n = sum(v["n"] for v in b.diagnostic.servos.d["jours"].values())
    assert 120 <= n <= 160, n                   # 3 s sur 5 (2 s de stabilisation)
    b._bascule("wander")
    faire_vivre(b, c, 5)
    assert sum(v["n"] for v in b.diagnostic.servos.d["jours"].values()) == n


def test_diagnostic_persiste_dans_la_memoire():
    class Mem:
        def __init__(self):
            self.donnees, self.sauvegardes = {}, 0

        def sauver(self):
            self.sauvegardes += 1
    m = Mem()
    d = Diagnostic(m, mur=lambda: 1e9)
    d.chutes.note(1e9, "wander")
    assert m.donnees["diagnostic"]["chutes"]["chutes"] and m.sauvegardes == 1
    d2 = Diagnostic(m, mur=lambda: 1e9)
    assert d2.resume()["chutes_7j"] == 1


def test_entites_home_assistant():
    import pont_ha
    cfg = {"url": "http://ha.local:8123", "entites": {}, "publier_toutes_les_s": 30, "ignorees": [], "appareils": [],
           "declencheurs": [], "mqtt": None}
    c = ClientRobot()
    b = cerveau(c)
    b.fin_etat = 0.0
    faire_vivre(b, c, 40)
    b.diagnostic.chutes.note(1.7e9, "zoomies")
    try:
        pont = pont_ha.PontHA(cfg, "jeton", log=lambda m: None)
    except Exception:
        pont = pont_ha.PontHA.__new__(pont_ha.PontHA)
        pont._derniere_vue_chat = None
    pont.photographier(b, {"battery": {"percent": 80.0}})
    ent = pont.entites_du_canard()
    assert ent["binary_sensor.microduck_autotest"][0] == "off"
    assert ent["sensor.microduck_chutes_7j"][0] == 1
    assert ent["binary_sensor.microduck_servos_derive"][0] == "off"
    assert "sensor.microduck_sante_batterie" not in ent, "pas de verdict sans historique"


def test_batterie_un_rebond_de_tension_durable_ne_coupe_pas_le_cycle():
    j = JournalBatterie()
    t, pct = 0.0, 100.0
    for k in range(300):                        # 5 h : decharge, avec un palier de rebond de +6 % pendant 15 min
        pct -= 0.2
        rebond = 6.0 if 100 <= k < 115 else 0.0
        j.note(t, pct + rebond)
        t += 60
    assert not j.en_charge and j.d["cycles"] == [], "un rebond qui plafonne n'est pas une charge"
