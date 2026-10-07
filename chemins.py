#!/usr/bin/env python3
"""Trajets sur le plan (plan.py) : le canard contourne les meubles et ne traverse jamais une zone interdite.

- Espace praticable : libre sur le plan, a plus de MARGE_M d'un obstacle (le canard fait ~16 cm de large, plus une
  marge pour l'imprecision de la localisation), hors des zones interdites.
- A* sur une grille plus grossiere (PAS_M) pour rester rapide sur le petit processeur du canard, puis lissage : on
  ne garde que les points de passage necessaires (ligne droite praticable de l'un a l'autre).
- Depart ou arrivee dans une case non praticable (pres d'un mur, sur le chargeur) : on part de / vise la case
  praticable la plus proche, sans jamais entrer dans une zone interdite.
"""
import heapq
import math

import numpy as np

import plan as P

MARGE_M = 0.13
PAS_M = 0.06


def praticable(pl, marge=MARGE_M):
    """Masque (hauteur, largeur) des cases ou le centre du canard peut passer."""
    return (pl.grille == P.LIBRE) & (pl.distance() >= marge) & ~pl.interdit()


def _grossier(masque, k):
    """Une case grossiere est praticable si toutes ses cases fines le sont."""
    h, l = masque.shape[0] // k, masque.shape[1] // k
    return masque[:h * k, :l * k].reshape(h, k, l, k).all(axis=(1, 3))


def _plus_proche(g, i, j, rayon=15):
    if 0 <= i < g.shape[0] and 0 <= j < g.shape[1] and g[i, j]:
        return i, j
    best = None
    for di in range(-rayon, rayon + 1):
        for dj in range(-rayon, rayon + 1):
            a, b = i + di, j + dj
            if 0 <= a < g.shape[0] and 0 <= b < g.shape[1] and g[a, b]:
                d = di * di + dj * dj
                if best is None or d < best[0]:
                    best = (d, a, b)
    return None if best is None else (best[1], best[2])


def _visible(g, a, b):
    """Ligne droite praticable entre deux cases grossieres (echantillonnage a la demi-case)."""
    (i0, j0), (i1, j1) = a, b
    n = int(max(abs(i1 - i0), abs(j1 - j0)) * 2) + 1
    for t in np.linspace(0.0, 1.0, n + 1):
        i, j = int(round(i0 + t * (i1 - i0))), int(round(j0 + t * (j1 - j0)))
        if not g[i, j]:
            return False
    return True


def chemin(pl, depart, arrivee, marge=MARGE_M, pas=PAS_M):
    """Points de passage [(x, y), ...] de `depart` a `arrivee` (repere du plan, m), arrivee comprise ; None si aucun
    passage. Le premier point de passage n'est pas le depart lui-meme."""
    k = max(1, int(round(pas / pl.resolution)))
    g = _grossier(praticable(pl, marge), k)
    taille = pl.resolution * k

    def case(x, y):
        return (int(math.floor((y - pl.origine[1]) / taille)), int(math.floor((x - pl.origine[0]) / taille)))

    def centre(c):
        return (pl.origine[0] + (c[1] + 0.5) * taille, pl.origine[1] + (c[0] + 0.5) * taille)

    a, b = _plus_proche(g, *case(*depart)), _plus_proche(g, *case(*arrivee))
    if a is None or b is None:
        return None
    voisins = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
               (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
    ouverts = [(0.0, a)]
    cout = {a: 0.0}
    parent = {a: None}
    while ouverts:
        _, c = heapq.heappop(ouverts)
        if c == b:
            break
        for di, dj, w in voisins:
            n = (c[0] + di, c[1] + dj)
            if not (0 <= n[0] < g.shape[0] and 0 <= n[1] < g.shape[1]) or not g[n]:
                continue
            if di and dj and not (g[c[0] + di, c[1]] and g[c[0], c[1] + dj]):
                continue                                   # pas de coin coupe
            nc = cout[c] + w
            if nc < cout.get(n, math.inf):
                cout[n], parent[n] = nc, c
                heapq.heappush(ouverts, (nc + math.hypot(n[0] - b[0], n[1] - b[1]), n))
    if b not in parent:
        return None
    brut = []
    c = b
    while c is not None:
        brut.append(c)
        c = parent[c]
    brut.reverse()
    lisse = [brut[0]]
    i = 0
    while i < len(brut) - 1:
        j = len(brut) - 1
        while j > i + 1 and not _visible(g, brut[i], brut[j]):
            j -= 1
        lisse.append(brut[j])
        i = j
    points = [centre(c) for c in lisse[1:]]
    if b == case(*arrivee) and points:
        points[-1] = (float(arrivee[0]), float(arrivee[1]))   # la vraie cible, si elle-meme est praticable
    return points or [(float(arrivee[0]), float(arrivee[1]))]


def longueur(depart, points):
    total, p = 0.0, depart
    for q in points:
        total += math.hypot(q[0] - p[0], q[1] - p[1])
        p = q
    return total
