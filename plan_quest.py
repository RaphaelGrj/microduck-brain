#!/usr/bin/env python3
"""Un scan du Meta Quest 3 -> un plan pour le canard (plan.Plan).

L'appli Unity du dossier quest/ (ExportPlan.cs) ecrit un fichier « microduck-quest-1 » :
  {"format": "microduck-quest-1", "date": "...",
   "reperes": [{"nom": "chargeur", "pos": [x, y, z]}, {"nom": "devant", "pos": [...]},
               {"nom": "entree", "pos": [...]}, {"nom": "marqueur", "id": 0, "pos": [...]}, ...],
   "pieces": [{"nom": "...", "ancres": [{"label": "WALL_FACE", "matrice": [16 nombres, ligne par ligne],
                                         "plan": [xmin, ymin, largeur, hauteur] | null,
                                         "volume": [xmin, ymin, zmin, xmax, ymax, zmax] | null,
                                         "contour": [[x, y], ...], "uuid": "..."}]}]}
Coordonnees Unity : metres, x a droite, y en haut, z devant (main gauche) ; « matrice » : repere local de l'ancre ->
monde. Un plan (mur, porte, fenetre, sol) est dans le plan local XY de son ancre ; un volume (meuble) est une boite
locale. Tout ce qui depend des conventions du Quest est la, et seulement la.

Repere du plan du canard : origine au point « chargeur » (la ou il se pose pour se recharger), x vers le point
« devant » (la direction de son regard quand il est sur le chargeur), y a sa gauche. Hauteurs depuis le sol (ancres
FLOOR). Sans « chargeur »/« devant » : origine au centre du sol, axes du Quest (et un avertissement).

Usage : python3 plan_quest.py scan.json [plan.json] [apercu.png]
  (affiche un resume ; ecrit le plan et/ou une image de controle si demande - sur le PC, avant meme d'avoir le canard)
"""
import json
import math
import sys

import numpy as np

import plan as P

FORMAT = "microduck-quest-1"
NOMS = {"TABLE": "table", "COUCH": "canapé", "BED": "lit", "STORAGE": "rangement", "SCREEN": "écran",
        "LAMP": "lampe", "PLANT": "plante", "DOOR_FRAME": "porte", "WINDOW_FRAME": "fenêtre", "WALL_ART": "tableau",
        "OTHER": "objet"}
MURS = ("WALL_FACE", "INVISIBLE_WALL_FACE", "INNER_WALL_FACE")
DESSOUS_LIBRE = ("TABLE",)       # sous une table, le canard passe : seuls les pieds (aux coins) sont des obstacles
EPAISSEUR_MUR = 0.03             # demi-epaisseur dessinee (m)


class Avertissements(list):
    pass


def _matrice(a):
    m = np.asarray(a.get("matrice") or [], dtype=float)
    if m.size != 16:
        raise ValueError("ancre sans matrice")
    return m.reshape(4, 4)


def _monde(m, pts):
    pts = np.asarray(pts, dtype=float)
    h = np.column_stack([pts, np.ones(len(pts))])
    return (m @ h.T).T[:, :3]


def _coins_plan(a):
    """Les 4 coins (monde) du rectangle d'un plan, ou None."""
    r = a.get("plan")
    if not r:
        return None
    x0, y0, l, h = r
    return _monde(_matrice(a), [[x0, y0, 0], [x0 + l, y0, 0], [x0 + l, y0 + h, 0], [x0, y0 + h, 0]])


def _coins_volume(a):
    v = a.get("volume")
    if not v:
        return None
    x0, y0, z0, x1, y1, z1 = v
    return _monde(_matrice(a), [[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)])


def _contour(a):
    c = a.get("contour") or []
    if len(c) < 3:
        return None
    return _monde(_matrice(a), [[x, y, 0] for x, y in c])


def _enveloppe(pts):
    """Enveloppe convexe 2D (chaine monotone) -> liste de points."""
    pts = sorted(set(map(tuple, np.round(pts, 4))))
    if len(pts) <= 2:
        return pts
    croix = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])  # noqa: E731
    bas, haut = [], []
    for p in pts:
        while len(bas) >= 2 and croix(bas[-2], bas[-1], p) <= 0:
            bas.pop()
        bas.append(p)
    for p in reversed(pts):
        while len(haut) >= 2 and croix(haut[-2], haut[-1], p) <= 0:
            haut.pop()
        haut.append(p)
    return bas[:-1] + haut[:-1]


def convertir(export, nom="Maison", resolution=P.RESOLUTION):
    """export (dict « microduck-quest-1 ») -> (plan.Plan, avertissements)."""
    if not isinstance(export, dict) or export.get("format") != FORMAT:
        raise ValueError("ce n'est pas un export de l'appli Quest du canard (microduck-quest-1)")
    av = Avertissements()
    ancres = [a for piece in export.get("pieces") or [] for a in piece.get("ancres") or []]
    if not ancres:
        raise ValueError("aucune piece dans le scan (le Quest a-t-il une configuration de l'espace ?)")
    reperes = {r.get("nom"): r for r in export.get("reperes") or [] if isinstance(r, dict)}

    sols = [a for a in ancres if a.get("label") == "FLOOR"]
    hauteur_sol = float(np.median([_matrice(a)[1, 3] for a in sols])) if sols else None
    if "chargeur" in reperes and "devant" in reperes:
        c = np.asarray(reperes["chargeur"]["pos"], dtype=float)
        d = np.asarray(reperes["devant"]["pos"], dtype=float)
        f = np.array([d[0] - c[0], d[2] - c[2]])
        if np.linalg.norm(f) < 0.05:
            raise ValueError("« devant » est trop pres du chargeur : le viser a 30 cm ou plus")
        f /= np.linalg.norm(f)
        origine = c
        if hauteur_sol is None:
            hauteur_sol = float(c[1])
    else:
        av.append("pas de repere « chargeur » / « devant » : plan dans les axes du Quest (refaire les reperes)")
        contours = [_contour(a) for a in sols if _contour(a) is not None]
        origine = np.mean(np.vstack(contours), axis=0) if contours else np.zeros(3)
        f = np.array([0.0, 1.0])                    # z du Quest = x du plan
        if hauteur_sol is None:
            hauteur_sol = float(origine[1])

    def vers_plan(pts):
        pts = np.atleast_2d(pts)
        dx, dz = pts[:, 0] - origine[0], pts[:, 2] - origine[2]
        x = dx * f[0] + dz * f[1]
        y = -dx * f[1] + dz * f[0]                  # a gauche (repere main gauche du Quest -> main droite du canard)
        return np.column_stack([x, y, pts[:, 1] - hauteur_sol])

    sols_plan = [vers_plan(_contour(a))[:, :2] for a in sols if _contour(a) is not None]
    tous = [vers_plan(c)[:, :2] for c in ([_contour(a) for a in ancres] + [_coins_plan(a) for a in ancres]
                                          + [_coins_volume(a) for a in ancres]) if c is not None]
    if not tous:
        raise ValueError("scan vide")
    pile = np.vstack(tous)
    (xmin, ymin), (xmax, ymax) = pile.min(axis=0) - 0.1, pile.max(axis=0) + 0.1
    if xmax - xmin > 40 or ymax - ymin > 40:
        raise ValueError("scan de plus de 40 m : les reperes ou le scan semblent faux")
    grille, orig = P.grille_vide(xmin, ymin, xmax, ymax, resolution)
    plan = P.Plan(grille, orig, resolution, nom, "quest", date=None)
    X, Y = plan.centres()
    if sols_plan:
        for poly in sols_plan:
            plan.grille[P.dans_polygone(X, Y, [tuple(p) for p in poly])] = P.LIBRE
    else:
        av.append("pas de sol dans le scan : tout l'interieur des murs est suppose libre")
        plan.grille[:] = P.LIBRE

    objets, portes, fenetres, segments_murs = [], [], [], []
    for a in ancres:
        label = str(a.get("label") or "OTHER").upper()
        if label in ("FLOOR", "CEILING", "GLOBAL_MESH"):
            continue
        coins = _coins_plan(a)
        vol = _coins_volume(a)
        if coins is not None and vol is None:      # un plan vertical : mur, porte, fenetre, tableau
            cp = vers_plan(coins)
            bas = cp[np.argsort(cp[:, 2])[:2]]      # les deux coins du bas
            seg = (tuple(bas[0, :2]), tuple(bas[1, :2]))
            if label in MURS:
                segments_murs.append(seg)
                plan.grille[P.pres_du_segment(X, Y, seg[0], seg[1], EPAISSEUR_MUR)] = P.OBSTACLE
            elif label == "DOOR_FRAME":
                portes.append((seg, float(cp[:, 2].min())))
            elif label == "WINDOW_FRAME":
                fenetres.append(seg)
            continue
        if vol is None:
            continue
        vp = vers_plan(vol)
        bas_h, haut_h = float(vp[:, 2].min()), float(vp[:, 2].max())
        contour = _enveloppe(vp[:, :2])
        objet = {"type": label.lower(), "nom": NOMS.get(label, "objet"),
                 "centre": [round(float(vp[:, 0].mean()), 3), round(float(vp[:, 1].mean()), 3)],
                 "contour": [[round(x, 3), round(y, 3)] for x, y in contour],
                 "hauteur": round(haut_h, 2), "dessous_libre": label in DESSOUS_LIBRE}
        objets.append(objet)
        if haut_h <= P.TRANCHE[0] or bas_h >= P.TRANCHE[1]:
            continue                                # suspendu (etagere murale, ecran fixe au mur) : pas un obstacle
        if objet["dessous_libre"]:
            for x, y in contour:                    # les pieds, aux coins
                plan.grille[np.hypot(X - x, Y - y) <= 0.03] = P.OBSTACLE
        else:
            plan.grille[P.dans_polygone(X, Y, contour)] = P.OBSTACLE

    for (a, b), bas in portes:                      # une porte ouvre le mur
        if bas < 0.10:
            plan.grille[P.pres_du_segment(X, Y, a, b, EPAISSEUR_MUR * 2)] = P.LIBRE
        objets.append({"type": "door_frame", "nom": "porte", "centre": [round((a[0] + b[0]) / 2, 3),
                       round((a[1] + b[1]) / 2, 3)], "contour": [list(map(lambda v: round(v, 3), a)),
                       list(map(lambda v: round(v, 3), b))], "hauteur": None, "dessous_libre": True})
    for a, b in fenetres:
        objets.append({"type": "window_frame", "nom": "fenêtre", "centre": [round((a[0] + b[0]) / 2, 3),
                       round((a[1] + b[1]) / 2, 3)], "contour": [list(a), list(b)], "hauteur": None,
                       "dessous_libre": True})

    reps = {}
    if "chargeur" in reperes and "devant" in reperes:
        reps["chargeur"] = [0.0, 0.0, 0.0]
    if "entree" in reperes:
        e = vers_plan(np.asarray(reperes["entree"]["pos"], dtype=float))[0]
        reps["entree"] = [round(float(e[0]), 3), round(float(e[1]), 3)]
    marqs = {}
    for r in export.get("reperes") or []:
        if r.get("nom") != "marqueur" or r.get("id") is None:
            continue
        m = vers_plan(np.asarray(r["pos"], dtype=float))[0]
        cap = _normale_du_mur(m[:2], segments_murs, sols_plan)
        if cap is None:
            av.append(f"marqueur {r['id']} : aucun mur a moins de 15 cm (le coller sur un mur, et viser son centre)")
            continue
        marqs[str(int(r["id"]))] = [round(float(m[0]), 3), round(float(m[1]), 3), round(cap, 4)]
    if marqs:
        reps["marqueurs"] = marqs
    if sols and "chargeur" in reperes and "devant" in reperes:
        # pour le casque (modes realite mixte) : chargeur et « devant » dans le repere de l'ancre du SOL, qui, elle,
        # se retrouve d'une seance a l'autre (le repere « monde » du Quest, lui, change a chaque demarrage)
        sol = sols[0]
        inv = np.linalg.inv(_matrice(sol))
        local = lambda p: [round(float(v), 5) for v in (inv @ np.append(np.asarray(p, dtype=float), 1.0))[:3]]  # noqa: E731
        reps["quest"] = {"ancre": sol.get("uuid"), "chargeur": local(reperes["chargeur"]["pos"]),
                         "devant": local(reperes["devant"]["pos"])}
    plan.objets = objets
    plan.reperes = reps
    plan.pieces = [{"nom": p.get("nom") or f"Pièce {k + 1}",
                    "contour": [[round(float(x), 3), round(float(y), 3)] for x, y in sols_plan[k]]}
                   for k, p in enumerate(export.get("pieces") or []) if k < len(sols_plan)]
    if "chargeur" in reps and not plan.libre(0.0, 0.0):
        av.append("le chargeur tombe dans un obstacle du plan : verifier le repere « chargeur »")
    return plan.rogne(), av


def _normale_du_mur(p, murs, sols):
    """Direction (cap) de la face d'un marqueur colle sur le mur le plus proche : perpendiculaire au mur, vers
    l'interieur (le cote ou il y a du sol)."""
    meilleur = None
    for a, b in murs:
        a, b = np.asarray(a), np.asarray(b)
        ab = b - a
        l2 = float(ab @ ab)
        if l2 < 1e-6:
            continue
        t = min(1.0, max(0.0, float((p - a) @ ab) / l2))
        d = float(np.linalg.norm(p - (a + t * ab)))
        if meilleur is None or d < meilleur[0]:
            meilleur = (d, ab / math.sqrt(l2))
    if meilleur is None or meilleur[0] > 0.15:
        return None
    u = meilleur[1]
    n = np.array([-u[1], u[0]])
    essai = p + 0.3 * n
    dedans = any(P.dans_polygone(np.array([essai[0]]), np.array([essai[1]]), [tuple(q) for q in s])[0] for s in sols)
    if sols and not dedans:
        n = -n
    return math.atan2(n[1], n[0])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        pl, avert = convertir(json.load(f))
    print(json.dumps(pl.resume(), ensure_ascii=False), *avert, sep="\n")
    for sortie in sys.argv[2:]:
        if sortie.lower().endswith(".png"):
            print("apercu :", pl.image(sortie))
        else:
            with open(sortie, "w", encoding="utf-8") as f:
                json.dump(pl.vers_dict(), f, ensure_ascii=False)
            print("plan :", sortie)
