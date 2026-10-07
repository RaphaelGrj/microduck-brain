#!/usr/bin/env python3
"""Ce que le plan de la maison apporte a sa vie de tous les jours (ROADMAP « Plan II ») :

  - cachette : un endroit du plan qu'on ne voit pas depuis la ou on l'a laisse (derriere un meuble), tout contre un
    obstacle, atteignable - pour un cache-cache ou il se cache VRAIMENT ;
  - LieuxHeure : ou il aime etre selon le moment de la journee (temps passe au repos, par case de 50 cm) ;
  - soleil : quelle fenetre donne du soleil a quelle heure, appris de ce qu'il a vu (bain de soleil a la camera) -
    ensuite il y va sans avoir besoin de voir la tache ;
  - noms : les points nommes et les pieces du plan, pour « emmene-moi a la cuisine » (commandes vocales locales).
Tout reste sur le canard (memoire).
"""
import math

import numpy as np

import chemins
import plan as P

# -- cachette ------------------------------------------------------------------------------------------------------------
def visible(pl, a, b, pas=0.04):
    """Ligne de vue de a a b sans obstacle du plan (a hauteur de canard)."""
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, int(d / pas))
    for k in range(1, n):
        t = k / n
        if pl.valeur(a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])) == P.OBSTACLE:
            return False
    return True


def cachette(pl, depuis, rng, essais=400, portee=(1.0, 4.5)):
    """Un point du plan cache de `depuis` (personne ne le voit de la), tout contre un obstacle (< 35 cm), atteignable.
    -> (x, y) ou None."""
    ok = chemins.praticable(pl)
    libres = np.argwhere(ok)
    if len(libres) == 0:
        return None
    dist = pl.distance()
    candidats = []
    for i, j in libres[rng.choice(len(libres), min(essais, len(libres)), replace=False)]:
        x = pl.origine[0] + (j + 0.5) * pl.resolution
        y = pl.origine[1] + (i + 0.5) * pl.resolution
        d = math.hypot(x - depuis[0], y - depuis[1])
        if not portee[0] <= d <= portee[1] or dist[i, j] > 0.35 or visible(pl, depuis, (x, y)):
            continue
        candidats.append((dist[i, j] + 0.1 * abs(d - 2.5), x, y))     # tout contre un meuble, ni trop pres ni trop loin
    for _, x, y in sorted(candidats)[:6]:
        if chemins.chemin(pl, depuis, (x, y)) is not None:
            return x, y
    return None


# -- ou il aime etre selon l'heure -----------------------------------------------------------------------------------------
CRENEAUX = ((6, "matin"), (11, "midi"), (14, "apres-midi"), (18, "soir"), (23, "nuit"))
CASE_M = 0.5
HABITUDE_MIN_S = 600.0          # au moins 10 min cumulees au meme endroit, a ce moment de la journee


def creneau(heure):
    nom = "nuit"
    for debut, n in CRENEAUX:
        if heure >= debut:
            nom = n
    return nom


class LieuxHeure:
    def __init__(self, donnees=None):
        self.d = donnees.setdefault("lieux_heure", {}) if donnees is not None else {}

    def noter(self, lieu, heure, x, y, dt):
        cle = f"{math.floor(x / CASE_M)},{math.floor(y / CASE_M)}"
        cases = self.d.setdefault(str(lieu), {}).setdefault(creneau(heure), {})
        cases[cle] = round(cases.get(cle, 0.0) + dt, 1)
        if len(cases) > 200:                         # on oublie les cases les moins frequentees
            for k, _ in sorted(cases.items(), key=lambda kv: kv[1])[:50]:
                del cases[k]

    def favori(self, lieu, heure):
        cases = (self.d.get(str(lieu)) or {}).get(creneau(heure)) or {}
        if not cases:
            return None
        cle, s = max(cases.items(), key=lambda kv: kv[1])
        if s < HABITUDE_MIN_S:
            return None
        i, j = (int(v) for v in cle.split(","))
        return (i + 0.5) * CASE_M, (j + 0.5) * CASE_M


# -- le soleil, fenetre par fenetre ---------------------------------------------------------------------------------------
SOLEIL_MIN = 3                  # au moins 3 jours de soleil vus a cette heure-la par cette fenetre
SOLEIL_FENETRE_MIN = 45         # a +- 45 min


def fenetres(pl):
    return [o for o in pl.objets if o.get("type") == "window_frame"]


def cle_fenetre(o):
    return f"{o['centre'][0]:.1f},{o['centre'][1]:.1f}"


def noter_soleil(donnees, lieu, pl, x, y, minute):
    """Il voit une tache de soleil en (x, y) a `minute` (du jour) : la fenetre la plus proche (< 5 m) en est la source."""
    f = min(fenetres(pl), key=lambda o: math.hypot(o["centre"][0] - x, o["centre"][1] - y), default=None)
    if f is None or math.hypot(f["centre"][0] - x, f["centre"][1] - y) > 5.0:
        return None
    l = donnees.setdefault("soleil", {}).setdefault(str(lieu), {}).setdefault(cle_fenetre(f), [])
    l.append(int(minute))
    del l[:-40]
    return cle_fenetre(f)


def fenetre_au_soleil(donnees, lieu, pl, minute):
    """La fenetre qui, d'habitude, donne du soleil maintenant -> l'objet du plan, ou None."""
    appris = ((donnees.get("soleil") or {}).get(str(lieu)) or {})
    for f in fenetres(pl):
        vus = appris.get(cle_fenetre(f), [])
        if sum(1 for m in vus if abs(m - minute) <= SOLEIL_FENETRE_MIN) >= SOLEIL_MIN:
            return f
    return None


def devant_la_fenetre(pl, f, recul=0.7):
    """Un point praticable a ~70 cm de la fenetre, cote interieur (la ou tombe le soleil)."""
    (ax, ay), (bx, by) = f["contour"][0], f["contour"][-1]
    cx, cy = f["centre"]
    nx, ny = -(by - ay), bx - ax
    n = math.hypot(nx, ny) or 1.0
    ok = chemins.praticable(pl)
    for signe in (1, -1):
        x, y = cx + signe * recul * nx / n, cy + signe * recul * ny / n
        i, j = pl.case(x, y)
        if 0 <= i < pl.hauteur and 0 <= j < pl.largeur and ok[i, j]:
            return x, y
    return None


# -- des noms pour la voix -------------------------------------------------------------------------------------------------
def noms(plan_dict):
    """Points nommes et pieces d'un plan (dict) -> noms en minuscules (pour la grammaire de commandes.py)."""
    if not plan_dict:
        return []
    out = [str(k).lower() for k in (plan_dict.get("points") or {})]
    out += [str(p.get("nom")).lower() for p in plan_dict.get("pieces") or [] if p.get("nom")]
    return sorted(set(n for n in out if n and len(n) <= 30))


def resoudre(pl, nom):
    """« cuisine » -> (x, y) : un point nomme, sinon le centre d'une piece. None si inconnu."""
    nom = str(nom).lower().strip()
    for k, v in pl.points.items():
        if k.lower() == nom:
            return float(v[0]), float(v[1])
    for p in pl.pieces:
        if str(p.get("nom", "")).lower() == nom and len(p.get("contour") or []) >= 3:
            xs, ys = [q[0] for q in p["contour"]], [q[1] for q in p["contour"]]
            return _praticable_dans(pl, p.get("nom"), sum(xs) / len(xs), sum(ys) / len(ys))
    return None


def _praticable_dans(pl, piece, cx, cy):
    """Le centre d'une piece tombe souvent sur un meuble (la table du salon) : le point praticable de la piece le plus
    proche du centre. Le centre tel quel si rien ne convient."""
    ok = chemins.praticable(pl)
    i, j = pl.case(cx, cy)
    if 0 <= i < pl.hauteur and 0 <= j < pl.largeur and ok[i, j]:
        return cx, cy
    cases = np.argwhere(ok)
    if len(cases) == 0:
        return cx, cy
    xs = pl.origine[0] + (cases[:, 1] + 0.5) * pl.resolution
    ys = pl.origine[1] + (cases[:, 0] + 0.5) * pl.resolution
    proches = np.argsort((xs - cx) ** 2 + (ys - cy) ** 2)[:6000]
    for marge in (0.3, 0.0):            # de preference bien dans la piece, pas sur le seuil
        for k in proches:
            x, y = float(xs[k]), float(ys[k])
            if all(pl.piece_de(x + dx, y + dy) == piece for dx, dy in ((0, 0), (marge, 0), (-marge, 0), (0, marge), (0, -marge))):
                return x, y
    return cx, cy


def avant(depuis, cible, recul):
    """Le point a `recul` m avant `cible`, sur la droite depuis `depuis` (s'arreter devant une balle, une imprimante)."""
    dx, dy = cible[0] - depuis[0], cible[1] - depuis[1]
    d = math.hypot(dx, dy)
    if d <= recul:
        return depuis
    return cible[0] - recul * dx / d, cible[1] - recul * dy / d
