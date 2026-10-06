#!/usr/bin/env python3
"""Jeux avec les habitants : 1-2-3 soleil.
"""
import math

import gestures
from etats_base import Etat, V_ROTATION


class Soleil(Etat):
    """Jeu "1-2-3 soleil" (ROADMAP, table Humains "Jeux" et prochaine etape n°4) : le canard se retourne, compte en
    chirps (rythme variable : c'est tout le jeu), se retourne d'un coup et regarde ; s'il voit quelque chose bouger
    (mouvement.py, difference d'images, camera immobile), "vu !" (alarme + non de la tete). Le joueur gagne s'il
    arrive tout pres (ToF devant < 30 cm au moment ou le canard regarde) ou s'il le caresse : tremoussement + wheee.
    Fin apres MANCHES_MAX manches, sur "fin_jeu", ou si le joueur ne se fait jamais voir ni n'arrive (parti ?).

    Les demi-tours se font a l'odometrie, vers des caps absolus (le joueur, puis le dos au joueur) (vyaw 1,5 au-dessus de la zone morte, ~50 deg/s : ~3,5 s par demi-tour) ; la
    detection de mouvement n'est armee qu'une fois le canard stabilise (STABILISATION_S apres l'arret)."""
    nom = "soleil"
    MANCHES_MAX = 10
    REGARD_S = 3.5
    STABILISATION_S = 0.8
    DEMI_TOUR_MAX_S = 5.0
    ARRIVEE_M = 0.30
    ABANDON_MANCHES = 6          # manches d'affilee sans mouvement vu ni arrivee : le joueur est sans doute parti

    def entre(self, brain):
        self.veille = brain.ctx.extras.get("mouvement")
        self.manche, self.vus, self.calmes = 0, 0, 0
        self.resultat = None
        o = (brain.ctx.state or {}).get("odom")
        self.cap_joueur = o["yaw"] if o else None          # le joueur est en face au moment ou il lance le jeu
        brain.ctx.sound("greet")
        self._phase(brain, "annonce", 0.0)

    def duree(self, brain):
        return 600.0                             # le jeu decide lui-meme de sa fin (brain.fin_etat)

    def _phase(self, brain, nom, t):
        self.phase, self.t_phase = nom, t
        if self.veille is not None:
            self.veille.desarmer()
        if nom == "compte":
            self.duree_compte = brain.rng.uniform(1.5, 4.0)
            self.bips = sorted(brain.rng.uniform(0.2, self.duree_compte - 0.3) for _ in range(2)) + [self.duree_compte - 0.2]
            self.n_bips = 0
        elif nom == "regarde":
            self.arme = False

    def _tourne(self, brain, t, cap):
        """Rotation sur place vers le cap ABSOLU `cap` (odometrie), par le plus court : le cap du joueur est memorise
        au debut du jeu, sinon les petites erreurs de chaque demi-tour s'additionnent et le canard finit par ne plus
        lui faire face. True quand c'est fait (a ~20 deg pres, l'inertie finit le virage), ou au bout de
        DEMI_TOUR_MAX_S."""
        o = (brain.ctx.state or {}).get("odom")
        fait, signe = t - self.t_phase >= self.DEMI_TOUR_MAX_S, 1.0
        if o and cap is not None:
            ecart = math.remainder(cap - o["yaw"], 2 * math.pi)
            fait = fait or abs(ecart) <= 0.35
            signe = 1.0 if ecart > 0 else -1.0
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))
        brain.ctx.move(vyaw=0.0 if fait else V_ROTATION * signe)
        return fait

    def _fin(self, brain, t, resultat):
        self.resultat = resultat
        print(f"[{brain.t_global:6.1f}s] 1-2-3 soleil : {resultat} (manche {self.manche}, vu {self.vus} fois)", flush=True)
        if self.veille is not None:
            self.veille.desarmer()
        if resultat == "gagne":
            brain.ctx.sound("wheee")
            self._phase(brain, "fete", t)
        else:
            brain.ctx.sound("coo")
            self._phase(brain, "salut", t)

    def sur_evenement(self, brain, base):
        """Evenements pendant le jeu : une caresse = le joueur l'a touche, il a gagne ; fin_jeu = on arrete."""
        if self.resultat is not None:
            return base in ("caresse", "fin_jeu")
        if base == "caresse":
            self._fin(brain, brain.t_etat, "gagne")
            return True
        if base == "fin_jeu":
            self._fin(brain, brain.t_etat, "arrete")
            return True
        return False

    def pas(self, brain, t):
        ctx, dt = brain.ctx, t - self.t_phase
        if self.phase == "annonce":
            ctx.head(gestures.oui(min(dt, 1.2)) if dt < 1.2 else (0, 0, 0, 0))
            ctx.move()
            if dt >= 1.5:
                self.manche += 1
                self._phase(brain, "demi_tour", t)
        elif self.phase == "demi_tour":
            dos = None if self.cap_joueur is None else self.cap_joueur + math.pi
            if self._tourne(brain, t, dos):
                self._phase(brain, "compte", t)
        elif self.phase == "compte":
            ctx.head((0.0, 0.3, 0.0, 0.0))       # tete baissee : "les yeux fermes"
            ctx.move()
            if self.n_bips < len(self.bips) and dt >= self.bips[self.n_bips]:
                ctx.sound("chirp" if self.n_bips < 2 else "inquire")
                self.n_bips += 1
            if dt >= self.duree_compte:
                self._phase(brain, "retour", t)
        elif self.phase == "retour":
            if self._tourne(brain, t, self.cap_joueur):
                self._phase(brain, "regarde", t)
        elif self.phase == "regarde":
            ctx.head((0.0, -0.15, 0.0, 0.0))     # le regard un peu leve, vers le joueur debout
            ctx.move()
            if not self.arme and dt >= self.STABILISATION_S and self.veille is not None:
                self.veille.armer()
                self.arme = True
            tof = ctx.extras.get("tof")
            lib = tof.libre(ctx.state) if tof is not None and ctx.state is not None and dt >= self.STABILISATION_S else None
            if lib is not None and lib["devant"] < self.ARRIVEE_M:
                self._fin(brain, t, "gagne")
            elif self.arme and self.veille.a_bouge():
                self.vus += 1
                self.calmes = 0
                ctx.sound("alarm")
                self._phase(brain, "vu", t)
            elif dt >= self.REGARD_S:
                self.calmes += 1
                if self.manche >= self.MANCHES_MAX:
                    self._fin(brain, t, "fini")
                elif self.calmes >= self.ABANDON_MANCHES:
                    self._fin(brain, t, "abandon")
                else:
                    self.manche += 1
                    ctx.sound("chirp")
                    self._phase(brain, "demi_tour", t)
        elif self.phase == "vu":
            d, fn = gestures.GESTES["non"]
            ctx.head(fn(dt) if dt < d else (0, 0, 0, 0))
            ctx.move()
            if dt >= d + 0.3:
                if self.manche >= self.MANCHES_MAX:
                    self._fin(brain, t, "fini")
                else:
                    self.manche += 1
                    self._phase(brain, "demi_tour", t)
        elif self.phase == "fete":
            d, fn = gestures.GESTES["content"]
            ctx.head(fn(dt) if dt < d else (0, 0, 0, 0))
            ctx.pose(gestures.content_corps(dt) if dt < d else None)
            ctx.move()
            if dt >= d + 0.3:
                brain.fin_etat = t
        else:                                    # salut : un petit "oui" et on rend la main
            ctx.head(gestures.oui(dt) if dt < 1.2 else (0, 0, 0, 0))
            ctx.move()
            if dt >= 1.5:
                brain.fin_etat = t

    def sort(self, brain):
        if self.veille is not None:
            self.veille.desarmer()
        brain.ctx.calme()


class CacheCache(Etat):
    """Cache-cache lance par le canard (ROADMAP "Lance lui-meme une partie de cache-cache" et table Humains "cache-cache
    au son") : un "greet" (c'est parti !), il file se cacher - vers un coin connu (navigation.AllerVers) ou, a defaut, un
    petit trajet droit devant, toujours avec le capteur de distance -, s'assoit sans bouger, et laisse echapper de temps
    en temps un petit "peck" : l'indice pour le trouver a l'oreille. Trouve (caresse, main tendue, "trouve !", quelqu'un
    a moins de 30 cm) -> "wheee" et tremoussement. Personne apres CACHE_MAX_S -> il sort tout seul, un peu decu."""
    nom = "cache_cache"
    ALLER_MAX_S = 12.0
    CACHE_MAX_S = 300.0
    TROUVE_M = 0.30

    def __init__(self):
        self.cible = None                        # coin ou se cacher (odom), choisi par le cerveau ; None = droit devant

    def entre(self, brain):
        from navigation import AllerVers
        brain.ctx.sound("greet")
        self.phase, self.t_phase, self.resultat = "aller", 0.0, None
        self.nav = AllerVers(self.cible) if self.cible is not None else None
        self.prochain_indice = None

    def duree(self, brain):
        return self.ALLER_MAX_S + self.CACHE_MAX_S + 20.0

    def _phase(self, nom, t):
        self.phase, self.t_phase = nom, t

    def sur_evenement(self, brain, base):
        """Une caresse ou une main tendue pendant qu'il est cache : trouve ! (les commandes vocales "trouve" passent par
        Brain._sur_commande)."""
        if self.phase == "cache" and base in ("caresse", "main"):
            self._trouve(brain, brain.t_etat)
            return True
        return False

    def _trouve(self, brain, t):
        self.resultat = "trouve"
        brain.ctx.sound("wheee")
        self._phase("fin", t)

    def pas(self, brain, t):
        ctx, dt = brain.ctx, t - self.t_phase
        s = ctx.state or {}
        tof = ctx.extras.get("tof")
        lib = tof.libre(s) if tof is not None and s else None
        if self.phase == "aller":
            ctx.head((0.0, 0.3, 0.0, 0.0))
            o = s.get("odom")
            if self.nav is not None and o is not None:
                statut, vx, vyaw = self.nav.commande(o["position"][0], o["position"][1], o["yaw"], lib)
                fini = statut in ("arrive", "bloque")
            else:                                # droit devant 3 s, si c'est libre
                libre = lib is not None and lib["devant"] >= 0.45
                vx, vyaw = (0.4 if libre else 0.0), 0.0
                fini = dt >= 3.0 or not libre
            ctx.move(vx=0.0 if fini else vx, vyaw=0.0 if fini else vyaw)
            if fini or dt >= self.ALLER_MAX_S:
                if not ctx.sitting:
                    ctx.toggle_sit()
                self._phase("cache", t)
                self.prochain_indice = t + brain.rng.uniform(15.0, 30.0)
        elif self.phase == "cache":
            ctx.head((0.0, 0.35, 0.0, 0.0))     # tete basse, il se fait tout petit
            if t >= self.prochain_indice:
                ctx.sound("peck")                # l'indice sonore
                self.prochain_indice = t + brain.rng.uniform(20.0, 40.0)
            if dt >= 3.0 and lib is not None and lib["devant"] < self.TROUVE_M:
                self._trouve(brain, t)
            elif dt >= self.CACHE_MAX_S:
                self.resultat = "abandon"
                ctx.sound("inquire")             # "vous ne me cherchez pas ?"
                self._phase("fin", t)
        else:                                    # fin : il se releve, fete (trouve) ou petit salut (abandon)
            if ctx.sitting and dt >= 0.3:
                ctx.toggle_sit()
            if self.resultat == "trouve" and dt >= 2.0:
                d, fn = gestures.GESTES["content"]
                u = dt - 2.0
                ctx.head(fn(u) if u < d else (0, 0, 0, 0))
                ctx.pose(gestures.content_corps(u) if u < d else None)
            else:
                ctx.head(gestures.oui(min(max(dt - 2.0, 0.0), 1.2)) if dt >= 2.0 else (0, 0, 0, 0))
            ctx.move()
            if dt >= 5.0:
                brain.fin_etat = t

    def sort(self, brain):
        if brain.ctx.sitting and not brain.reste_assis():
            brain.ctx.toggle_sit()
        brain.ctx.calme()
