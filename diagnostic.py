#!/usr/bin/env python3
"""Diagnostic / auto-surveillance du canard (ROADMAP "Diagnostic / auto-surveillance") : savoir quand quelque chose
chez le robot LUI-MEME derive, avant que ca devienne une panne, et le remonter dans Home Assistant.

Quatre briques, logique pure (testable sans robot), donnees dans la memoire locale du canard (memoire.py) :

  JournalBatterie : cycles de decharge (de la fin d'une charge au debut de la suivante) -> vitesse de decharge en %/h,
                    autonomie estimee, "sante" = vitesse des premiers cycles / vitesse des derniers (une batterie qui
                    vieillit se vide plus vite). Utile pour faire tourner les 2 batteries de rechange.
  SanteServos     : au repos debout (etat chill, politique stand), courant moyen et ecart consigne-position de chaque
                    servo, moyennes par jour ; une derive par rapport aux premiers jours (le "temoin") signale une
                    piece a surveiller (frottement, jeu qui grandit). Plus : quel servo est le plus souvent le plus
                    chaud (robot.health.motors.hottest - robotd ne donne pas la temperature de chaque servo).
  JournalChutes   : chaque chute (date, heure, ce qu'il faisait, position odometrique de la session) -> chutes sur 7 j,
                    activite la plus risquee, endroit qui revient (un tapis, un seuil de porte).
  AutoTest        : verdict d'une petite sequence jouee au premier reveil de la journee (etat `autotest` de
                    etats_maison.py) : robotd en bonne sante (boucle, bus, IMU), trame ToF, image camera, la tete qui
                    suit ses consignes. Publie dans HA plutot que decouvert en plein jeu.

Rien n'est envoye ailleurs qu'a Home Assistant, et seulement des nombres et des verdicts.
"""
import math
import statistics
import time

# robot.state.joints / targets / currents_ma : 15 entrees dans l'ordre de duck-ipc-proto JOINT_NAMES - le BEC est a
# l'index 9, entre la tete et la jambe droite (il bouge avec la voix et les baillements : exclu des derives).
SERVOS = ("left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
          "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth",
          "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle")
N = len(SERVOS)
SUIVIS = [i for i, nom in enumerate(SERVOS) if nom != "mouth"]


# -- batterie ---------------------------------------------------------------------------------------------------------
class JournalBatterie:
    CHARGE_PCT = 5.0            # +5 % : en charge (la tension remonte un peu toute seule quand il arrete de marcher)
    CYCLE_MIN_PCT = 20.0        # un cycle de decharge compte s'il a fait baisser la batterie d'au moins 20 %
    CYCLE_MIN_H = 0.25
    CYCLES_MAX = 120            # historique garde
    N_COMPARE = 5               # sante = 5 premiers cycles contre 5 derniers
    REMPLACER_PCT = 70.0        # sante en dessous : batterie a remplacer (prevenir avant l'arret sec)

    def __init__(self, donnees=None, sauver=None):
        self.d = donnees if donnees is not None else {}
        self.d.setdefault("cycles", [])
        self.sauver = sauver
        # cycle en cours, PERSISTANT : canard eteint batterie vide puis rallume avec une batterie chargee (les 2 de
        # rechange du pack) -> le cycle d'avant est clos au redemarrage au lieu d'etre perdu
        en_cours = self.d.get("en_cours") or {}
        self.haut = tuple(en_cours["haut"]) if en_cours.get("haut") else None   # (t_mur, pct) : debut du cycle
        self.bas = tuple(en_cours["bas"]) if en_cours.get("bas") else None      # (t_mur, pct) : plus bas depuis
        self.en_charge = bool(en_cours.get("en_charge", False))
        self._t_garde = None

    def _garde(self, t):
        """Sauve le cycle en cours (au plus une fois par minute : la memoire est sauvee sur le disque du canard)."""
        self.d["en_cours"] = {"haut": list(self.haut), "bas": list(self.bas), "en_charge": self.en_charge}
        if self.sauver is not None and (self._t_garde is None or t - self._t_garde >= 60.0):
            self._t_garde = t
            self.sauver()

    def note(self, t, pct):
        """`t` : heure murale (s) ; `pct` : robot.state.battery.percent."""
        if self.haut is None:
            self.haut = self.bas = (t, pct)
            self._garde(t)
            return
        try:
            self._note(t, pct)
        finally:
            self._garde(t)

    def _note(self, t, pct):
        if pct >= self.bas[1] + self.CHARGE_PCT:           # elle remonte : en charge
            if not self.en_charge:
                self._clos_cycle()
                self.en_charge = True
            self.haut = self.bas = (t, pct)
            return
        if self.en_charge:
            if pct >= self.haut[1]:
                self.haut = self.bas = (t, pct)                # toujours sur le chargeur (plein : le cycle commence
                return                                         # quand on le debranche, pas quand il a atteint 100 %)
            if pct <= self.haut[1] - 1.0:
                self.en_charge = False                         # debranche : un nouveau cycle commence au sommet
        if pct < self.bas[1]:
            self.bas = (t, pct)

    def _clos_cycle(self):
        (t0, p0), (t1, p1) = self.haut, self.bas
        h = (t1 - t0) / 3600.0
        if p0 - p1 >= self.CYCLE_MIN_PCT and h >= self.CYCLE_MIN_H:
            self.d["cycles"] = (self.d["cycles"] + [{"debut": round(t0), "de": round(p0, 1), "a": round(p1, 1),
                                                     "h": round(h, 3)}])[-self.CYCLES_MAX:]
            if self.sauver is not None:
                self.sauver()

    @staticmethod
    def _vitesse(c):
        return (c["de"] - c["a"]) / c["h"]

    def vitesse_pct_h(self, derniers=N_COMPARE):
        c = self.d["cycles"][-derniers:]
        return statistics.median(self._vitesse(x) for x in c) if c else None

    def autonomie_h(self):
        """Autonomie estimee d'une charge pleine, d'apres les derniers cycles (None avant le premier cycle)."""
        v = self.vitesse_pct_h()
        return round(100.0 / v, 2) if v else None

    def sante_pct(self):
        """100 % = comme a ses debuts ; None tant qu'il n'y a pas 2 x N_COMPARE cycles."""
        c = self.d["cycles"]
        if len(c) < 2 * self.N_COMPARE:
            return None
        neuf = statistics.median(self._vitesse(x) for x in c[:self.N_COMPARE])
        recent = statistics.median(self._vitesse(x) for x in c[-self.N_COMPARE:])
        return round(min(100.0, 100.0 * neuf / recent), 1)

    def a_remplacer(self):
        s = self.sante_pct()
        return s is not None and s < self.REMPLACER_PCT


# -- servos -----------------------------------------------------------------------------------------------------------
class SanteServos:
    JOURS_TEMOIN = 3            # les 3 premiers jours de mesures font le temoin
    MESURES_MIN_JOUR = 500      # trames de repos minimum pour qu'une journee compte (~10 s a 50 Hz)
    DERIVE_COURANT = 1.5        # courant de repos 50 % au-dessus du temoin
    DERIVE_ECART_RAD = 0.05     # ecart consigne-position 0,05 rad (~3 degres) de plus que le temoin
    JOURS_GARDES = 60

    def __init__(self, donnees=None, sauver=None):
        self.d = donnees if donnees is not None else {}
        self.d.setdefault("jours", {})          # "2026-10-06" -> {"n", "courant": [14], "ecart": [14]}
        self.d.setdefault("plus_chaud", {})     # servo -> nombre de fois qu'il a ete le plus chaud
        self.sauver = sauver
        self._jour = None

    def note_repos(self, jour, joints, targets, courants=None):
        """Une trame de repos debout (chill, politique stand) : moyenne par jour du |courant| et de |consigne - position|."""
        if not joints or not targets or len(joints) < N or len(targets) < N:
            return
        if jour != self._jour:
            if self._jour is not None and self.sauver is not None:
                self.sauver()
            self._jour = jour
            self._range_vieux()
        j = self.d["jours"].setdefault(jour, {"n": 0, "courant": [0.0] * N, "ecart": [0.0] * N})
        j["n"] += 1
        k = 1.0 / j["n"]
        for i in SUIVIS:
            j["ecart"][i] += k * (abs(targets[i] - joints[i]) - j["ecart"][i])
            if courants is not None and len(courants) >= N:
                j["courant"][i] += k * (abs(courants[i]) - j["courant"][i])
        if j["n"] % 15000 == 0 and self.sauver is not None:
            self.sauver()                       # ~5 min de repos : une journee de mesures ne se perd pas au plantage

    def note_plus_chaud(self, nom):
        if nom:
            self.d["plus_chaud"][nom] = self.d["plus_chaud"].get(nom, 0) + 1

    def _range_vieux(self):
        jours = sorted(self.d["jours"])
        for j in jours[:-self.JOURS_GARDES]:
            del self.d["jours"][j]

    def _valides(self):
        return [(j, v) for j, v in sorted(self.d["jours"].items()) if v["n"] >= self.MESURES_MIN_JOUR]

    def derives(self):
        """-> [(servo, "courant"|"ecart", valeur recente, temoin)] : servos qui derivent par rapport aux premiers jours."""
        jours = self._valides()
        if len(jours) <= self.JOURS_TEMOIN:
            return []
        temoin, recent = jours[:self.JOURS_TEMOIN], jours[-1][1]
        out = []
        for i in SUIVIS:
            nom = SERVOS[i]
            c0 = statistics.mean(v["courant"][i] for _, v in temoin)
            e0 = statistics.mean(v["ecart"][i] for _, v in temoin)
            if c0 > 1.0 and recent["courant"][i] >= self.DERIVE_COURANT * c0:
                out.append((nom, "courant", round(recent["courant"][i]), round(c0)))
            if recent["ecart"][i] >= e0 + self.DERIVE_ECART_RAD:
                out.append((nom, "ecart", round(recent["ecart"][i], 3), round(e0, 3)))
        return out

    def plus_chaud_habituel(self):
        pc = self.d["plus_chaud"]
        if sum(pc.values()) < 20:
            return None
        nom = max(pc, key=pc.get)
        return nom if pc[nom] >= 0.5 * sum(pc.values()) else None    # un servo qui chauffe plus que les autres


# -- chutes -----------------------------------------------------------------------------------------------------------
class JournalChutes:
    RAYON_LIEU_M = 0.4          # chutes a moins de 40 cm l'une de l'autre (meme session odometrique) : meme endroit
    LIEU_A_RISQUE = 3
    GARDEES = 300

    def __init__(self, donnees=None, sauver=None):
        self.d = donnees if donnees is not None else {}
        self.d.setdefault("chutes", [])
        self.sauver = sauver

    def note(self, t, activite, position=None, session=None, heure=None):
        c = {"t": round(t), "activite": activite, "heure": heure}
        if position is not None:
            c["x"], c["y"], c["session"] = round(position[0], 2), round(position[1], 2), session
        self.d["chutes"] = (self.d["chutes"] + [c])[-self.GARDEES:]
        if self.sauver is not None:
            self.sauver()

    def recentes(self, t, jours=7.0):
        return [c for c in self.d["chutes"] if t - c["t"] <= jours * 86400]

    def activite_risquee(self, t, jours=30.0):
        r = [c["activite"] for c in self.recentes(t, jours)]
        if len(r) < 3:
            return None
        nom = max(set(r), key=r.count)
        return nom if r.count(nom) >= 0.4 * len(r) else None

    def lieux_a_risque(self, t, jours=30.0):
        """[(session, x, y, nombre)] : endroits (repere odometrique de la session) ou il est tombe LIEU_A_RISQUE fois."""
        pts = [c for c in self.recentes(t, jours) if "x" in c]
        lieux = []
        for c in pts:
            voisins = [o for o in pts if o["session"] == c["session"]
                       and math.hypot(o["x"] - c["x"], o["y"] - c["y"]) <= self.RAYON_LIEU_M]
            if len(voisins) >= self.LIEU_A_RISQUE and not any(
                    l[0] == c["session"] and math.hypot(l[1] - c["x"], l[2] - c["y"]) <= self.RAYON_LIEU_M for l in lieux):
                lieux.append((c["session"], c["x"], c["y"], len(voisins)))
        return lieux


# -- auto-test --------------------------------------------------------------------------------------------------------
def verdict_sante(sante):
    """robot.health -> {verification: (ok, detail)} pour ce que robotd sait de lui-meme."""
    out = {}
    if not isinstance(sante, dict):
        return {"robotd": (False, "robot.health sans reponse")}
    out["robotd"] = (bool(sante.get("healthy")), sante.get("reason") or "")
    boucle = sante.get("control_loop") or {}
    hz, cible = boucle.get("achieved_hz"), boucle.get("target_hz")
    if hz is not None and cible:
        out["boucle"] = (hz >= 0.95 * cible, f"{hz:.1f}/{cible:.0f} Hz")
    bus = sante.get("bus") or {}
    out["bus"] = (bus.get("consecutive_errors", 0) == 0 and bus.get("startup_failures", 0) == 0,
                  f"{bus.get('consecutive_errors', 0)} erreur(s)")
    imu = sante.get("imu")
    if imu is not None:
        gelee = imu.get("consecutive_stale_blocks", 0) >= 25
        out["imu"] = (bool(imu.get("ready")) and not gelee, "gelee" if gelee else ("prete" if imu.get("ready") else "pas prete"))
    return out


class AutoTest:
    """Resultat du dernier auto-test (rempli par l'etat `autotest`)."""

    def __init__(self):
        self.resultats = None   # {verification: (ok, detail)}
        self.t = None

    def termine(self, t, resultats):
        self.t, self.resultats = t, dict(resultats)

    def ok(self):
        return None if self.resultats is None else all(v[0] for v in self.resultats.values())

    def echecs(self):
        return [] if self.resultats is None else [k for k, v in self.resultats.items() if not v[0]]


class Diagnostic:
    """Regroupe les quatre briques, branche sur la memoire du canard (ou en memoire vive sans elle)."""

    def __init__(self, memoire=None, mur=time.time):
        self.mur = mur
        d = memoire.donnees.setdefault("diagnostic", {}) if memoire is not None and hasattr(memoire, "donnees") else {}
        sauver = memoire.sauver if memoire is not None and hasattr(memoire, "sauver") else None
        self.batterie = JournalBatterie(d.setdefault("batterie", {}), sauver)
        self.servos = SanteServos(d.setdefault("servos", {}), sauver)
        self.chutes = JournalChutes(d.setdefault("chutes", {}), sauver)
        self.autotest = AutoTest()
        self.session = int(mur())   # les positions odometriques ne valent qu'a l'interieur d'une session

    def resume(self):
        """Pour Home Assistant (pont_ha.py)."""
        t = self.mur()
        lieux = self.chutes.lieux_a_risque(t)
        derives = self.servos.derives()
        return {
            "autonomie_h": self.batterie.autonomie_h(), "sante_batterie": self.batterie.sante_pct(),
            "batterie_a_remplacer": self.batterie.a_remplacer(), "cycles": len(self.batterie.d["cycles"]),
            "servos_derive": [f"{n} ({q})" for n, q, _, _ in derives],
            "servo_chaud_habituel": self.servos.plus_chaud_habituel(),
            "chutes_7j": len(self.chutes.recentes(t)), "activite_risquee": self.chutes.activite_risquee(t),
            "lieux_a_risque": len(lieux),
            "autotest_ok": self.autotest.ok(), "autotest_echecs": self.autotest.echecs(),
        }
