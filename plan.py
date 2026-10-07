#!/usr/bin/env python3
"""Le plan de la maison : une grille vue de dessus, a la hauteur du canard, plus ce qu'on sait des lieux (meubles
nommes, pieces, chargeur, entree). Un plan par LIEU (lieux.py) : demenager = un nouveau lieu, un nouveau scan.

D'ou vient un plan :
  - d'un scan du Meta Quest 3 (plan_quest.py : export de l'appli Unity du dossier quest/) ;
  - d'une scene MuJoCo (depuis_mjcf : l'appartement de duck-sim), pour mettre au point la localisation avant le robot.

Repere du plan : metres, x vers l'avant du canard pose sur son chargeur, y a sa gauche, origine au chargeur (quand le
scan l'indique). Cases de RESOLUTION m : 0 = libre, 1 = obstacle (entre 3 et 30 cm de haut : ce que voit son capteur de
distance), 2 = hors du plan (dehors, ou pas scanne).

Format de fichier (JSON, « microduck-plan-1 ») : la grille en plages (rle : valeur, longueur, valeur, longueur... ligne
par ligne depuis le coin (origine)), les objets, les pieces, les reperes. Lisible par l'appli sans bibliotheque.
Annotations (dessinees dans le casque ou l'appli, gardees si l'on remplace le scan) : `zones` interdites (polygones
qu'il ne franchit jamais : escalier, litiere, cuisine pendant les repas) et `points` nommes (« panier », « gamelle »).
"""
import json
import math
import time
import unicodedata
import xml.etree.ElementTree as ET

import numpy as np

FORMAT = "microduck-plan-1"
RESOLUTION = 0.02
LIBRE, OBSTACLE, DEHORS = 0, 1, 2
TRANCHE = (0.03, 0.30)           # hauteurs (m) vues par le capteur de distance (tof.HAUTEUR_UTILE)
DISTANCE_MAX = 0.5               # champ de distance aux obstacles, plafonne (localisation)


class Plan:
    def __init__(self, grille, origine, resolution=RESOLUTION, nom="Plan", source="?", objets=None, pieces=None,
                 reperes=None, date=None, zones=None, points=None):
        self.grille = np.asarray(grille, dtype=np.uint8)
        self.origine = (float(origine[0]), float(origine[1]))
        self.resolution = float(resolution)
        self.nom, self.source = nom, source
        self.objets, self.pieces = list(objets or []), list(pieces or [])
        self.reperes = dict(reperes or {})
        self.date = date if date is not None else round(time.time())
        self.zones = [z for z in (zones or []) if isinstance(z, dict) and len(z.get("contour") or []) >= 3]
        self.points = {str(k): v for k, v in (points or {}).items() if isinstance(v, (list, tuple)) and len(v) >= 2}
        self._distance = None
        self._interdit = None

    # -- geometrie ----------------------------------------------------------------------------------------------------
    @property
    def hauteur(self):
        return self.grille.shape[0]

    @property
    def largeur(self):
        return self.grille.shape[1]

    def case(self, x, y):
        """(ligne, colonne) de la case qui contient (x, y) ; peut sortir de la grille."""
        return (int(math.floor((y - self.origine[1]) / self.resolution)),
                int(math.floor((x - self.origine[0]) / self.resolution)))

    def centres(self):
        """Coordonnees (x, y) des centres de toutes les cases : deux tableaux (hauteur, largeur)."""
        xs = self.origine[0] + (np.arange(self.largeur) + 0.5) * self.resolution
        ys = self.origine[1] + (np.arange(self.hauteur) + 0.5) * self.resolution
        return np.meshgrid(xs, ys)

    def valeur(self, x, y):
        i, j = self.case(x, y)
        if not (0 <= i < self.hauteur and 0 <= j < self.largeur):
            return DEHORS
        return int(self.grille[i, j])

    def libre(self, x, y):
        return self.valeur(x, y) == LIBRE

    # -- zones interdites -----------------------------------------------------------------------------------------------
    def interdit(self):
        """Masque (hauteur, largeur) des cases dans une zone interdite (calcule une fois, refait si les zones changent)."""
        if self._interdit is None:
            X, Y = self.centres()
            m = np.zeros(self.grille.shape, dtype=bool)
            for z in self.zones:
                m |= dans_polygone(X, Y, [tuple(p[:2]) for p in z["contour"]])
            self._interdit = m
        return self._interdit

    def dans_zone_interdite(self, x, y):
        i, j = self.case(x, y)
        return 0 <= i < self.hauteur and 0 <= j < self.largeur and bool(self.interdit()[i, j])

    def zone_de(self, x, y):
        for z in self.zones:
            if dans_polygone(np.array([x]), np.array([y]), [tuple(p[:2]) for p in z["contour"]])[0]:
                return z.get("nom") or "zone interdite"
        return None

    def piece_de(self, x, y):
        """Nom de la piece (scan Quest) qui contient (x, y), ou None."""
        for p in self.pieces:
            if len(p.get("contour") or []) >= 3 and dans_polygone(np.array([x]), np.array([y]),
                                                                   [tuple(q) for q in p["contour"]])[0]:
                return p.get("nom")
        return None

    def annoter(self, zones=None, points=None):
        """Remplace les annotations (zones interdites, points nommes) ; valeurs nettoyees. -> self."""
        if zones is not None:
            propres = []
            for z in zones[:30]:
                c = [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in (z.get("contour") or [])[:60]
                     if isinstance(p, (list, tuple)) and len(p) >= 2 and all(math.isfinite(float(v)) for v in p[:2])]
                if len(c) >= 3:
                    propres.append({"nom": str(z.get("nom") or "zone interdite")[:40], "contour": c})
            self.zones, self._interdit = propres, None
        if points is not None:
            self.points = {str(k)[:40]: [round(float(v[0]), 3), round(float(v[1]), 3)] for k, v in list(points.items())[:40]
                           if isinstance(v, (list, tuple)) and len(v) >= 2 and all(math.isfinite(float(c)) for c in v[:2])}
        return self

    def rogne(self, marge=5):
        """Retire les bandes « hors du plan » autour (garde `marge` cases)."""
        utile = np.argwhere(self.grille != DEHORS)
        if utile.size == 0:
            return self
        (i0, j0), (i1, j1) = utile.min(axis=0), utile.max(axis=0)
        i0, j0 = max(0, i0 - marge), max(0, j0 - marge)
        i1, j1 = min(self.hauteur, i1 + marge + 1), min(self.largeur, j1 + marge + 1)
        self.grille = self.grille[i0:i1, j0:j1].copy()
        self.origine = (self.origine[0] + j0 * self.resolution, self.origine[1] + i0 * self.resolution)
        self._distance = None
        return self

    # -- champ de distance (localisation) -----------------------------------------------------------------------------
    def distance(self):
        """Distance (m) de chaque case a l'obstacle le plus proche, plafonnee a DISTANCE_MAX (chanfrein 3-4, sans
        scipy). Calculee une fois, gardee."""
        if self._distance is not None:
            return self._distance
        inf = 1e9
        d = np.where(self.grille == OBSTACLE, 0.0, inf)
        n = int(math.ceil(DISTANCE_MAX / self.resolution)) + 1
        r = self.resolution
        for _ in range(n):
            avant = d
            p = np.pad(d, 1, constant_values=inf)
            voisins = [p[1:-1, :-2] + r, p[1:-1, 2:] + r, p[:-2, 1:-1] + r, p[2:, 1:-1] + r,
                       p[:-2, :-2] + r * 1.4142, p[:-2, 2:] + r * 1.4142, p[2:, :-2] + r * 1.4142, p[2:, 2:] + r * 1.4142]
            d = np.minimum(d, np.minimum.reduce(voisins))
            if np.array_equal(avant, d):
                break
        self._distance = np.minimum(d, DISTANCE_MAX)
        return self._distance

    def rayon(self, x, y, angle, portee=2.0):
        """Distance au premier obstacle dans la direction `angle` (lancer de rayon, pas d'une demi-case) ; inf si rien."""
        pas = self.resolution / 2
        c, s = math.cos(angle), math.sin(angle)
        d = pas
        while d <= portee:
            if self.valeur(x + d * c, y + d * s) == OBSTACLE:
                return d
            d += pas
        return math.inf

    # -- fichier ------------------------------------------------------------------------------------------------------
    def vers_dict(self):
        plat = self.grille.ravel()
        rle = []
        if plat.size:
            ruptures = np.flatnonzero(np.diff(plat)) + 1
            debuts = np.concatenate([[0], ruptures])
            fins = np.concatenate([ruptures, [plat.size]])
            for a, b in zip(debuts, fins):
                rle += [int(plat[a]), int(b - a)]
        return {"format": FORMAT, "nom": self.nom, "source": self.source, "date": self.date,
                "resolution": self.resolution, "origine": [round(self.origine[0], 4), round(self.origine[1], 4)],
                "largeur": self.largeur, "hauteur": self.hauteur, "rle": rle, "objets": self.objets,
                "pieces": self.pieces, "reperes": self.reperes, "zones": self.zones, "points": self.points}

    @classmethod
    def depuis_dict(cls, d):
        if not isinstance(d, dict) or d.get("format") != FORMAT:
            raise ValueError("ce n'est pas un plan Microduck")
        l, h = int(d["largeur"]), int(d["hauteur"])
        if not (0 < l <= 2000 and 0 < h <= 2000):
            raise ValueError("plan trop grand (40 m au plus de chaque cote)")
        rle = d.get("rle") or []
        valeurs = np.asarray(rle[0::2], dtype=np.uint8)
        longueurs = np.asarray(rle[1::2], dtype=np.int64)
        if longueurs.sum() != l * h or valeurs.max(initial=0) > DEHORS:
            raise ValueError("grille du plan abimee")
        grille = np.repeat(valeurs, longueurs).reshape(h, l)
        return cls(grille, d["origine"], d.get("resolution", RESOLUTION), d.get("nom", "Plan"), d.get("source", "?"),
                   d.get("objets"), d.get("pieces"), d.get("reperes"), d.get("date"), d.get("zones"), d.get("points"))

    def image(self, chemin, px_par_case=3):
        """Apercu PNG (comme dans l'appli : devant du chargeur en haut, sa gauche a gauche) : libre clair, obstacles
        sombres, hors plan blanc, chargeur en orange, entree en vert, marqueurs en bleu."""
        import cv2
        g = self.grille[::-1, ::-1].T                     # ligne = x decroissant, colonne = y decroissant
        couleurs = np.array([[230, 239, 244], [82, 74, 70], [255, 255, 255]], dtype=np.uint8)   # BGR
        img = cv2.resize(couleurs[g], None, fx=px_par_case, fy=px_par_case, interpolation=cv2.INTER_NEAREST)

        def pixel(x, y):
            j, i = (x - self.origine[0]) / self.resolution, (y - self.origine[1]) / self.resolution
            return int((self.hauteur - i) * px_par_case), int((self.largeur - j) * px_par_case)

        rep = self.reperes
        if rep.get("chargeur"):
            cv2.circle(img, pixel(*rep["chargeur"][:2]), 4 * px_par_case, (27, 106, 242), -1)
        if rep.get("entree"):
            cv2.circle(img, pixel(*rep["entree"][:2]), 4 * px_par_case, (80, 170, 60), -1)
        for m in (rep.get("marqueurs") or {}).values():
            cv2.circle(img, pixel(m[0], m[1]), 3 * px_par_case, (200, 120, 30), -1)
        for o in self.objets:
            if o.get("nom") and o.get("type") != "door_frame":
                sans_accent = unicodedata.normalize("NFKD", o["nom"]).encode("ascii", "ignore").decode()
                cv2.putText(img, sans_accent, pixel(*o["centre"]),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (40, 40, 40), 1)
        cv2.imwrite(str(chemin), img)
        return chemin

    def resume(self):
        return {"nom": self.nom, "source": self.source, "date": self.date,
                "taille_m": [round(self.largeur * self.resolution, 2), round(self.hauteur * self.resolution, 2)],
                "objets": len(self.objets), "chargeur": "chargeur" in self.reperes, "zones": len(self.zones),
                "points": len(self.points)}


# -- remplissage de la grille (outils communs aux sources) --------------------------------------------------------------
def grille_vide(xmin, ymin, xmax, ymax, resolution=RESOLUTION, valeur=DEHORS):
    l = max(1, int(math.ceil((xmax - xmin) / resolution)))
    h = max(1, int(math.ceil((ymax - ymin) / resolution)))
    return np.full((h, l), valeur, dtype=np.uint8), (xmin, ymin)


def dans_polygone(xs, ys, poly):
    """Masque des points (xs, ys) a l'interieur du polygone [(x, y), ...] (regle pair-impair)."""
    dedans = np.zeros(xs.shape, dtype=bool)
    n = len(poly)
    for k in range(n):
        x1, y1 = poly[k]
        x2, y2 = poly[(k + 1) % n]
        if y1 == y2:
            continue
        coupe = ((y1 > ys) != (y2 > ys)) & (xs < (x2 - x1) * (ys - y1) / (y2 - y1) + x1)
        dedans ^= coupe
    return dedans


def pres_du_segment(xs, ys, a, b, demi_epaisseur):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = np.clip(((xs - ax) * dx + (ys - ay) * dy) / l2, 0.0, 1.0) if l2 > 0 else 0.0
    return np.hypot(xs - (ax + t * dx), ys - (ay + t * dy)) <= demi_epaisseur


# -- depuis une scene MuJoCo (duck-sim) ----------------------------------------------------------------------------------
IGNORES_MJCF = ("ball_", "obj_")          # objets deplacables (balles, objets a ramasser) : pas dans le plan fixe


def _floats(texte, n=None, defaut=0.0):
    v = [float(x) for x in (texte or "").split()]
    return v + [defaut] * ((n or len(v)) - len(v))


def _lacet(attrib):
    """Rotation autour de z (les scenes d'appartement n'en ont pas d'autre) : euler="0 0 a" ou quat="w 0 0 z"."""
    if "euler" in attrib:
        return _floats(attrib["euler"], 3)[2]
    if "quat" in attrib:
        w, _, _, z = _floats(attrib["quat"], 4)
        return 2.0 * math.atan2(z, w)
    return 0.0


def depuis_mjcf(chemin, nom="Appartement (duck-sim)", resolution=RESOLUTION):
    """Plan d'une scene MuJoCo d'appartement : sols (floor_*, rug_*) = libre ; toute geometrie qui occupe la tranche
    3-30 cm = obstacle ; balles et objets mobiles ignores ; la station de charge (corps « dock ») = repere chargeur."""
    racine = ET.parse(chemin).getroot()
    monde = racine.find("worldbody")
    geoms = []
    reperes = {}

    def parcourir(noeud, ox, oy, oz, lacet_parent):
        for g in noeud.findall("geom"):
            geoms.append((g.attrib, ox, oy, oz, lacet_parent))
        for b in noeud.findall("body"):
            nom_corps = b.get("name", "")
            if nom_corps.startswith(IGNORES_MJCF):
                continue
            px, py, pz = _floats(b.get("pos"), 3)
            c, s = math.cos(lacet_parent), math.sin(lacet_parent)
            bx, by = ox + c * px - s * py, oy + s * px + c * py
            if nom_corps == "dock":
                reperes["chargeur"] = [round(bx, 3), round(by, 3), None]
            parcourir(b, bx, by, oz + pz, lacet_parent + _lacet(b.attrib))

    parcourir(monde, 0.0, 0.0, 0.0, 0.0)
    formes = []                                   # (genre, sol?, parametres)
    xmin = ymin = math.inf
    xmax = ymax = -math.inf
    for a, ox, oy, oz, lac in geoms:
        nom = a.get("name", "")
        if nom.startswith(IGNORES_MJCF):
            continue
        typ = a.get("type", "sphere")
        size = _floats(a.get("size"))
        px, py, pz = _floats(a.get("pos"), 3)
        c, s = math.cos(lac), math.sin(lac)
        cx, cy, cz = ox + c * px - s * py, oy + s * px + c * py, oz + pz
        yaw = lac + _lacet(a)
        if typ == "box":
            demi_z = size[2]
        elif typ == "cylinder":
            demi_z = size[1]
        elif typ == "capsule":
            demi_z = size[1] + size[0]
        elif typ == "ellipsoid":
            demi_z = size[2]
        else:
            demi_z = size[0]
        sol = nom.startswith(("floor", "rug"))
        if not sol and (cz + demi_z <= TRANCHE[0] or cz - demi_z >= TRANCHE[1]):
            continue                              # trop bas (tapis, plinthe) ou trop haut (dessus d'une etagere)
        if typ == "box" or (typ == "ellipsoid"):
            rx, ry = size[0], size[1]
        else:
            rx = ry = size[0]
        formes.append((typ, sol, (cx, cy, rx, ry, yaw)))
        ex = abs(math.cos(yaw)) * rx + abs(math.sin(yaw)) * ry       # emprise reelle (une boite tournee)
        ey = abs(math.sin(yaw)) * rx + abs(math.cos(yaw)) * ry
        xmin, xmax, ymin, ymax = min(xmin, cx - ex), max(xmax, cx + ex), min(ymin, cy - ey), max(ymax, cy + ey)
    grille, origine = grille_vide(xmin - 0.1, ymin - 0.1, xmax + 0.1, ymax + 0.1, resolution)
    p = Plan(grille, origine, resolution, nom, "scene")
    X, Y = p.centres()
    for typ, sol, (cx, cy, rx, ry, yaw) in sorted(formes, key=lambda f: not f[1]):   # les sols d'abord
        c, s = math.cos(-yaw), math.sin(-yaw)
        lx, ly = c * (X - cx) - s * (Y - cy), s * (X - cx) + c * (Y - cy)
        if typ == "box":
            masque = (np.abs(lx) <= rx) & (np.abs(ly) <= ry)
        elif typ == "ellipsoid":
            masque = (lx / rx) ** 2 + (ly / ry) ** 2 <= 1.0
        else:
            masque = lx ** 2 + ly ** 2 <= rx ** 2
        if sol:
            p.grille[masque & (p.grille == DEHORS)] = LIBRE
        else:
            p.grille[masque] = OBSTACLE
    p.reperes = reperes
    return p.rogne()
