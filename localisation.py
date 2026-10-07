#!/usr/bin/env python3
"""Ou est-il sur le plan ? Localisation Monte-Carlo (filtre particulaire), SUR le canard.

Chaque particule est une hypothese (x, y, cap) dans le repere du plan (plan.py) :
  - mouvement : le deplacement mesure par l'odometrie de robotd (odom.position, odom.yaw) est applique a chaque
    particule, avec un bruit proportionnel (l'odometrie d'un bipede glisse) ;
  - mesure : les points d'obstacle du capteur de distance (tof.points : repere du tronc, 3-30 cm de haut) sont places
    selon chaque hypothese ; plus ils tombent pres d'un obstacle du plan (champ de distance), plus l'hypothese est
    croyable (modele « champ de vraisemblance ») ; une hypothese dans un mur ou hors du plan ne vaut rien ;
  - reechantillonnage quand trop peu de particules portent le poids ; quelques particules au hasard si plus rien ne
    colle (on l'a deplace a la main : « enlevement »).

Depart : sur son chargeur (repere connu du plan) = position quasi certaine ; sinon recherche globale (plus lente :
le champ du capteur est etroit, ~45 degres). Rien ne sort du canard.
"""
import math

import numpy as np

import plan as plan_mod


class Localisation:
    N = 800                        # 400 suffisent souvent ; 800 evitent les decrochages passagers (banc : 6/6)
    SIGMA_M = 0.06                 # ecart toleré entre un point mesure et l'obstacle du plan le plus proche
    BRUIT_ROTATION = (0.10, 0.15)  # rad par rad tourne, rad par m parcouru (un bipede derive en cap en marchant)
    BRUIT_TRANSLATION = (0.12, 0.05)  # m par m parcouru, m par rad tourne
    INDEPENDANTS = 6               # poids d'une trame : comme 6 mesures independantes
    POINTS_MAX = 24                # points du capteur utilises par mise a jour (au hasard parmi les 64)
    PAS_MIN = (0.02, math.radians(3))  # mise a jour seulement apres un petit deplacement (m, rad)

    def __init__(self, plan, n=None, graine=None):
        self.plan = plan
        self.n = n or self.N
        self.rng = np.random.default_rng(graine)
        self.dist = plan.distance()
        self.p = np.zeros((self.n, 3))
        self.w = np.full(self.n, 1.0 / self.n)
        self.odom = None                       # derniere odometrie (x, y, cap) appliquee
        self.w_lent, self.w_rapide = 1e-3, 1e-3
        libres = np.argwhere(plan.grille == plan_mod.LIBRE)
        self._libres = libres
        self.mises_a_jour = 0

    # -- initialisation ---------------------------------------------------------------------------------------------
    def depuis(self, x, y, cap, ecart=0.05, ecart_cap=math.radians(5)):
        """Depart connu (sur le chargeur...) : nuage serre autour de (x, y, cap)."""
        self.p[:, 0] = self.rng.normal(x, ecart, self.n)
        self.p[:, 1] = self.rng.normal(y, ecart, self.n)
        self.p[:, 2] = self.rng.normal(cap, ecart_cap, self.n)
        self.w[:] = 1.0 / self.n

    def _au_hasard(self, k):
        cases = self._libres[self.rng.integers(0, len(self._libres), k)]
        r = self.plan.resolution
        x = self.plan.origine[0] + (cases[:, 1] + self.rng.random(k)) * r
        y = self.plan.origine[1] + (cases[:, 0] + self.rng.random(k)) * r
        return np.column_stack([x, y, self.rng.uniform(-math.pi, math.pi, k)])

    def partout(self):
        """Depart inconnu : particules sur tout l'espace libre."""
        self.p = self._au_hasard(self.n)
        self.w[:] = 1.0 / self.n

    # -- mouvement ---------------------------------------------------------------------------------------------------
    def mouvement(self, ox, oy, ocap):
        """Odometrie actuelle (repere odom de robotd). -> True si le deplacement depuis la derniere fois est assez grand
        pour une mise a jour (alors appliquer `mesure` ensuite)."""
        if self.odom is None:
            self.odom = (ox, oy, ocap)
            return False
        x0, y0, c0 = self.odom
        dx, dy = ox - x0, oy - y0
        dcap = (ocap - c0 + math.pi) % (2 * math.pi) - math.pi
        # deplacement exprime dans le repere du canard a l'instant precedent
        avant = math.cos(c0) * dx + math.sin(c0) * dy
        cote = -math.sin(c0) * dx + math.cos(c0) * dy
        trans = math.hypot(avant, cote)
        if trans < self.PAS_MIN[0] and abs(dcap) < self.PAS_MIN[1]:
            return False
        self.odom = (ox, oy, ocap)
        a1, a2 = self.BRUIT_ROTATION
        a3, a4 = self.BRUIT_TRANSLATION
        n = self.n
        da = avant + self.rng.normal(0, a3 * trans + a4 * abs(dcap) + 1e-4, n)
        dc = cote + self.rng.normal(0, a3 * trans + a4 * abs(dcap) + 1e-4, n)
        dr = dcap + self.rng.normal(0, a1 * abs(dcap) + a2 * trans + 1e-4, n)
        c, s = np.cos(self.p[:, 2]), np.sin(self.p[:, 2])
        self.p[:, 0] += c * da - s * dc
        self.p[:, 1] += s * da + c * dc
        self.p[:, 2] = (self.p[:, 2] + dr + math.pi) % (2 * math.pi) - math.pi
        return True

    # -- mesure ------------------------------------------------------------------------------------------------------
    def mesure(self, points):
        """Points d'obstacle du capteur [(x, y, hauteur), ...] dans le repere du tronc (tof.points)."""
        if not points:
            return
        pts = np.asarray([(p[0], p[1]) for p in points], dtype=float)
        if len(pts) > self.POINTS_MAX:
            pts = pts[self.rng.choice(len(pts), self.POINTS_MAX, replace=False)]
        c, s = np.cos(self.p[:, 2])[:, None], np.sin(self.p[:, 2])[:, None]
        gx = self.p[:, 0:1] + c * pts[:, 0] - s * pts[:, 1]
        gy = self.p[:, 1:2] + s * pts[:, 0] + c * pts[:, 1]
        r, (x0, y0) = self.plan.resolution, self.plan.origine
        i = np.floor((gy - y0) / r).astype(int)
        j = np.floor((gx - x0) / r).astype(int)
        h, l = self.dist.shape
        dedans = (i >= 0) & (i < h) & (j >= 0) & (j < l)
        d = np.full(gx.shape, plan_mod.DISTANCE_MAX)
        d[dedans] = self.dist[i[dedans], j[dedans]]
        # vraisemblance par point : un melange (bonne mesure ~ gaussienne, sinon bruit uniforme) -> robuste a un chat
        # ou un sac pose qui n'est pas sur le plan
        par_point = 0.85 * np.exp(-0.5 * (d / self.SIGMA_M) ** 2) + 0.15 * 0.2
        # les points voisins d'une trame ne sont pas des preuves independantes (plusieurs rangees du capteur touchent le
        # meme mur) : on les compte comme INDEPENDANTS points au plus, sinon le nuage devient sur de lui trop vite
        log_l = np.sum(np.log(par_point), axis=1) * min(1.0, self.INDEPENDANTS / len(pts))
        # la particule elle-meme : dans un obstacle ou hors du plan, tres peu probable - pas impossible : un scan a
        # quelques centimetres d'erreur et des bords imparfaits, et le canard frole les pieds de table
        ci = np.floor((self.p[:, 1] - y0) / r).astype(int)
        cj = np.floor((self.p[:, 0] - x0) / r).astype(int)
        ok = (ci >= 0) & (ci < h) & (cj >= 0) & (cj < l)
        case = np.full(self.n, plan_mod.DEHORS, dtype=np.uint8)
        case[ok] = self.plan.grille[ci[ok], cj[ok]]
        log_l[case == plan_mod.OBSTACLE] -= 6.0
        log_l[case == plan_mod.DEHORS] -= 10.0
        m = log_l.max()
        if m <= -1e8:                                  # plus aucune hypothese possible : on recommence
            self.p = self._au_hasard(self.n)
            self.w[:] = 1.0 / self.n
            return
        l_rel = np.exp(log_l - m)
        w = self.w * l_rel
        moyenne = float(np.mean(np.exp(log_l / len(pts))))  # vraisemblance moyenne par point (adaptation)
        self.w_lent += 0.01 * (moyenne - self.w_lent)
        self.w_rapide += 0.2 * (moyenne - self.w_rapide)
        self.w = w / w.sum()
        self.mises_a_jour += 1
        if 1.0 / np.sum(self.w ** 2) < self.n / 2:
            self._reechantillonne()

    def _reechantillonne(self):
        """Echantillonnage systematique ; une part de particules au hasard si les mesures collent soudain beaucoup
        moins bien qu'avant (on l'a porte ailleurs)."""
        rapport = self.w_rapide / max(self.w_lent, 1e-12)
        k = int(min(0.05, 1.0 - rapport) * self.n) if self.mises_a_jour > 20 and rapport < 0.3 else 0
        pas = (self.rng.random() + np.arange(self.n - k)) / (self.n - k)
        idx = np.searchsorted(np.cumsum(self.w), pas)
        idx = np.minimum(idx, self.n - 1)
        nouv = self.p[idx]
        if k:
            nouv = np.vstack([nouv, self._au_hasard(k)])
        self.p = nouv
        self.w = np.full(self.n, 1.0 / self.n)

    # -- recalage absolu (marqueurs.py) ----------------------------------------------------------------------------
    def recaler(self, x, y, cap, ecart=0.08, ecart_cap=math.radians(6)):
        """Un marqueur vu : position absolue (x, y, cap) a `ecart` pres. Si le nuage est deja d'accord, on le resserre
        (reponderation) ; sinon (derive, ou on l'a porte ailleurs) on repart de la."""
        ex, ey, ecap, disp = self.estimation()
        dcap = abs((ecap - cap + math.pi) % (2 * math.pi) - math.pi)
        if math.hypot(ex - x, ey - y) > 0.4 or dcap > math.radians(25) or disp > 0.4:
            self.depuis(x, y, cap, ecart, ecart_cap)
            return "reparti"
        d2 = (self.p[:, 0] - x) ** 2 + (self.p[:, 1] - y) ** 2
        dc = (self.p[:, 2] - cap + math.pi) % (2 * math.pi) - math.pi
        w = self.w * np.exp(-0.5 * d2 / ecart ** 2 - 0.5 * (dc / ecart_cap) ** 2)
        if w.sum() <= 0 or not np.isfinite(w.sum()):
            self.depuis(x, y, cap, ecart, ecart_cap)
            return "reparti"
        self.w = w / w.sum()
        self._reechantillonne()
        return "resserre"

    # -- resultat ----------------------------------------------------------------------------------------------------
    def estimation(self):
        """-> (x, y, cap, ecart_m) : moyenne ponderee et dispersion (m) du nuage. ecart < 0,15 m : il sait ou il est."""
        x = float(np.sum(self.w * self.p[:, 0]))
        y = float(np.sum(self.w * self.p[:, 1]))
        cap = math.atan2(float(np.sum(self.w * np.sin(self.p[:, 2]))), float(np.sum(self.w * np.cos(self.p[:, 2]))))
        ecart = float(np.sqrt(np.sum(self.w * ((self.p[:, 0] - x) ** 2 + (self.p[:, 1] - y) ** 2))))
        return x, y, cap, ecart

    def sur(self, seuil=0.15):
        return self.estimation()[3] < seuil
