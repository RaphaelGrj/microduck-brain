#!/usr/bin/env python3
"""Etats de la vie quotidienne et du lien social : le chat, la main tendue, la caresse, la danse, l'accueil, le
bonjour du matin, l'occupation autonome, les deplacements vers un coin appris, etre porte.
"""
import math
import zlib

import gestures
from etats_base import Etat, Sequence, TETE_PROMENADE, _regarder
from navigation import AllerVers


class RegardeChat(Etat):
    """Le chat vient d'apparaitre : petit son interrogatif, puis on le suit des yeux quelques secondes. La position du
    chat vient de la veille (chat.py) ; c'est robotd qui calcule l'orientation de la tete (`robot.look`), on renvoie
    ensuite ces angles a chaque trame pour tenir le regard.

    Garde-fou "reculer s'il approche vite" (ROADMAP, table chat) : si le chat se rapproche tres vite en dessous d'un
    seuil de proximite, petit pas en arriere (vx negatif) le temps qu'il passe le seuil - jamais une poursuite dans
    l'autre sens, jamais si le chat est deja loin ou s'approche lentement (une visite normale ne doit pas le faire
    fuir). vx reste dans la plage marche arriere documentee pour le chat (ZONE_MORTE.md : |vx| >= 0.3)."""
    nom = "regarde_chat"

    # familiarite (memoire.py) -> (son, duree du regard) : mefiant au debut, chaleureux avec le temps
    ACCUEIL = ((0.3, "inquire", 8.0), (0.6, "greet", 7.0), (1.01, "coo", 6.0))

    SEUIL_PROXIMITE_M = 0.35       # distance chat-robot en dessous de laquelle une approche rapide inquiete
    SEUIL_VITESSE_APPROCHE = 0.3   # m/s de fermeture pour declencher le recul (bruit normal du suivi sinon)
    VX_RECUL = -0.35               # au-dessus de la zone morte en valeur absolue (vx >= 0.3)
    DUREE_RECUL_S = 1.0            # un seul petit pas, pas une fuite continue

    def entre(self, brain):
        mem = brain.ctx.extras.get("memoire")
        self.familiarite = mem.familiarite("chat") if mem is not None else 0.0
        _, son, self.duree_s = next(a for a in self.ACCUEIL if self.familiarite < a[0])
        brain.ctx.sound(son)
        self.son = son
        self.tete = (0.0, 0.0, 0.0, 0.0)
        self.t_vise = None
        self.n_look = 0
        self._dist_prec = None
        self._t_dist_prec = None
        self._recule_jusqua = -1.0

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
        veille, s = brain.ctx.extras.get("chat"), brain.ctx.state
        recul = t < self._recule_jusqua
        if veille is not None and s is not None:
            e = veille.estimation
            if e is not None and e[0] != self.t_vise:
                self.t_vise = e[0]
                cible = veille.cible_regard(s["odom"]["position"][2])
                if cible:
                    r = brain.ctx.client.request("robot.look", {"x": float(cible[0]), "y": float(cible[1]), "z": float(cible[2])})
                    h = (r.get("result") or {}).get("head") if isinstance(r, dict) else None
                    if h:
                        self.tete = (h["neck_pitch"], h["head_pitch"], h["head_yaw"], h["head_roll"])
                        self.n_look += 1
                distance = math.hypot(e[1], e[2])
                if self._dist_prec is not None and e[0] > self._t_dist_prec:
                    vitesse_approche = (self._dist_prec - distance) / (e[0] - self._t_dist_prec)
                    if distance < self.SEUIL_PROXIMITE_M and vitesse_approche > self.SEUIL_VITESSE_APPROCHE:
                        self._recule_jusqua = t + self.DUREE_RECUL_S
                        recul = True
                self._dist_prec, self._t_dist_prec = distance, e[0]
        brain.ctx.head(self.tete)
        brain.ctx.move(vx=self.VX_RECUL if recul else 0.0)

class MainTendue(Etat):
    """Une main vient d'etre tendue devant le canard (main_tendue.py, ToF) : petit son interrogatif, il la regarde
    (`robot.look`, comme le chat), puis la "picore" doucement - de petits coups de tete vers elle. Le corps ne bouge
    pas : approcher de quelques centimetres est impossible a la marche (ZONE_MORTE.md : pas de pas plus fin que
    ~2-3 cm, et le pied pourrait cogner la main). La main retiree, un petit chirp et c'est fini."""
    nom = "main_tendue"
    DUREE_MAX = 10.0
    PERIODE_PICORE = 1.2         # s entre deux coups de bec
    COUP = 0.3                   # s, duree d'un coup de bec
    AMPLITUDE = 0.25             # rad de head_pitch en plus du regard

    son_entree = "inquire"           # "coo" quand il accepte la main apres l'avoir esquivee (taquinerie)

    def entre(self, brain):
        brain.ctx.sound(self.son_entree)
        self.son_entree = MainTendue.son_entree
        self.tete = (0.0, 0.25, 0.0, 0.0)       # en attendant robot.look : la tete se baisse un peu vers l'avant
        self.t_vise = None
        self.n_coups = 0
        self.parti = False

    def duree(self, brain):
        return self.DUREE_MAX

    def pas(self, brain, t):
        det, s = brain.detecteur_main, brain.ctx.state
        if not det.presente(brain.t_global):
            if t > 0.5 and not self.parti:
                self.parti = True
                brain.ctx.sound("chirp")
                brain.fin_etat = min(brain.fin_etat, t + 0.6)     # on laisse le chirp sonner, puis on se remet
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            brain.ctx.move()
            return
        m = det.main
        if m[0] != self.t_vise and s is not None and s.get("odom"):
            self.t_vise = m[0]
            r = brain.ctx.client.request("robot.look", {"x": float(m[1]), "y": float(m[2]),
                                                        "z": float(m[3] - s["odom"]["position"][2])})
            h = (r.get("result") or {}).get("head") if isinstance(r, dict) else None
            if h:
                self.tete = (h["neck_pitch"], h["head_pitch"], h["head_yaw"], h["head_roll"])
        tete = list(self.tete)
        if t >= 1.0:                             # une seconde a la regarder, puis les coups de bec
            phase = (t - 1.0) % self.PERIODE_PICORE
            k = int((t - 1.0) / self.PERIODE_PICORE)       # numero du coup de bec en cours (robuste a 10-50 Hz)
            if k >= self.n_coups:
                self.n_coups = k + 1
                if self.n_coups <= 3:
                    brain.ctx.sound("peck")
            if phase < self.COUP:
                tete[1] += self.AMPLITUDE * math.sin(math.pi * phase / self.COUP)
        brain.ctx.head(tuple(tete))
        brain.ctx.move()

class Caresse(Etat):
    """On le caresse (caresse.py, ou `pet-detect` officiel plus tard) - etat "Petted" du M9 : roucoulement, la tete
    s'appuie doucement contre la main et frotte un peu, puis un petit tremoussement de contentement. Calme l'eveil."""
    nom = "caresse"
    APPUI_S = 3.0

    def entre(self, brain):
        brain.ctx.sound("coo")
        brain.humeur.eveil = max(0.0, brain.humeur.eveil - 0.15)
        self.d_content, self.f_content = gestures.GESTES["content"]

    def duree(self, brain):
        return self.APPUI_S + self.d_content + 0.3

    def pas(self, brain, t):
        if t < self.APPUI_S:
            k = gestures._smooth(t, 0.0, 0.6) * (1.0 - gestures._smooth(t, self.APPUI_S - 0.5, self.APPUI_S))
            brain.ctx.head((0.0, 0.1 * k, 0.08 * k * math.sin(2 * math.pi * 0.7 * t), 0.15 * k))
            brain.ctx.pose(None)
        elif t < self.APPUI_S + self.d_content:
            u = t - self.APPUI_S
            brain.ctx.head(self.f_content(u))
            brain.ctx.pose(gestures.content_corps(u))
        else:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            brain.ctx.pose(None)
        brain.ctx.move()

class VaAuCoin(Etat):
    """Fatigue : avant la sieste, il rejoint son coin de sieste prefere (Exploration.coin_favori("nap")) - pivote,
    marche droit, tete un peu baissee comme en promenade. Arrive, bloque (obstacle, capteur muet plus d'1 s) ou trop
    long : il fait la sieste la ou il est. Jamais un detour : c'est une envie, pas une mission."""
    DUREE_MAX = 25.0
    BLOQUE_MAX_S = 1.0

    def __init__(self, nom="va_au_coin", ensuite="nap", motif="faire la sieste dans son coin"):
        """Meme mecanique pour d'autres destinations : `ensuite` = etat a l'arrivee (ou en cas d'abandon)."""
        self.nom, self.ensuite, self.motif = nom, ensuite, motif
        self.cible = None

    def entre(self, brain):
        self.nav = AllerVers(self.cible)
        self.bloque_depuis = None
        print(f"[{brain.t_global:6.1f}s] va {self.motif} ({self.cible[0]:.2f}, {self.cible[1]:.2f})", flush=True)

    def duree(self, brain):
        return self.DUREE_MAX

    def _fin(self, brain, t, pourquoi):
        brain.ctx.move()
        brain.suivant_force = self.ensuite
        brain.fin_etat = t
        self.issue = pourquoi

    def pas(self, brain, t):
        s = brain.ctx.state or {}
        o = s.get("odom")
        brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
        if t < 0.4 or o is None:
            brain.ctx.move()
            return
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(s) if tof is not None else None
        statut, vx, vyaw = self.nav.commande(o["position"][0], o["position"][1], o["yaw"], lib)
        if statut == "arrive":
            return self._fin(brain, t, "arrive")
        if statut == "bloque":
            self.bloque_depuis = self.bloque_depuis if self.bloque_depuis is not None else t
            if t - self.bloque_depuis >= self.BLOQUE_MAX_S:
                return self._fin(brain, t, "bloque")
        else:
            self.bloque_depuis = None
        if statut == "pivote":
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))     # tete baissee, la rotation est morte (ZONE_MORTE.md)
        brain.ctx.move(vx=vx, vyaw=vyaw)

class Danse(Etat):
    """De la musique (audio.py : battement regulier) : il hoche la tete en rythme et se dandine un peu, s'arrete avec
    la musique (musique_fin) ou au bout de DUREE_MAX - pas un juke-box : DELAI_DANSE_S avant de recommencer."""
    nom = "danse"
    DUREE_MAX = 30.0

    def __init__(self):
        self.bpm = 100

    def entre(self, brain):
        self.periode = 60.0 / (self.bpm / 2 if self.bpm > 130 else self.bpm)    # a 180 BPM, un hochement sur deux
        brain.ctx.sound("chirp")

    def duree(self, brain):
        return self.DUREE_MAX

    def sur_evenement(self, brain, base):
        if base == "musique_fin":
            brain.fin_etat = brain.t_etat + 0.5
            return True
        return base.startswith("musique")

    def pas(self, brain, t):
        k = gestures._smooth(t, 0.0, 1.0) * (1.0 - gestures._smooth(t, brain.fin_etat - 1.0, brain.fin_etat))
        phase = 2 * math.pi * t / self.periode
        brain.ctx.head((0.0, 0.2 * k * max(0.0, math.sin(phase)), 0.0, 0.12 * k * math.sin(phase / 2)))
        brain.ctx.pose((0.0, 0.12 * k * math.sin(phase / 2), 0.0) if k > 0.05 else None)
        brain.ctx.move()

class Porte(Etat):
    """On le prend dans les bras (robot.state.safety.picked_up, detecteur officiel de robotd, qui met aussi la marche
    en pause) - etat "Held" du M9 : un "wheee" surpris et ravi, la tete qui regarde partout ce monde vu d'en haut,
    aucune commande de marche. Reposé : il s'ebroue (Brain.tick)."""
    nom = "porte"

    def entre(self, brain):
        brain.ctx.sound("wheee")

    def duree(self, brain):
        return 300.0

    def pas(self, brain, t):
        if t >= 3.0:
            brain.son_une_fois(f"inquire{int((t - 3.0) / 12.0)}", "inquire")    # toutes les 12 s
        brain.ctx.head((0.0, 0.2 * math.sin(2 * math.pi * t / 7.0), 0.6 * math.sin(2 * math.pi * t / 5.0), 0.0))
        brain.ctx.move()

class Accueil(Etat):
    """Un habitant rentre a la maison (presence Home Assistant, voir pont_ha.py). L'accueil depend de la familiarite
    (memoire.py : reservee au debut, chaleureuse avec le temps) et de la duree de l'absence (simple signe s'il est sorti
    cinq minutes, joie apres une longue journee). Pas encore de marche vers l'entree : il faudrait une position fiable
    (odometrie qui derive ; balises UWB plus tard)."""
    nom = "accueil"
    ABSENCE_COURTE_S = 15 * 60
    ABSENCE_LONGUE_S = 4 * 3600

    def __init__(self):
        self.qui, self.absence_s = None, None

    # Salutation individualisee (ROADMAP) : une fois familier, chaque habitant a SON salut, toujours le meme (choisi
    # d'apres son nom : stable d'un redemarrage a l'autre, sans rien stocker).
    SIGNATURES = (("oui", "greet"), ("curieux", "greet"), ("ebouriffe", "greet"), ("content", "greet"))

    @classmethod
    def signature(cls, qui):
        return cls.SIGNATURES[zlib.crc32(qui.encode()) % len(cls.SIGNATURES)]

    @classmethod
    def sequence(cls, familiarite, absence_s, qui=None):
        """-> [(geste de gestures.py, son robot.sound)] joues l'un apres l'autre."""
        if absence_s is not None and absence_s < cls.ABSENCE_COURTE_S:
            return [("oui", "chirp")]                         # il vient de sortir : un petit signe, pas une fete
        if familiarite < 0.3:
            return [("curieux", "inquire")]                   # encore un peu reserve
        seq = [("oui", "greet")]
        if familiarite >= 0.6:
            seq = [cls.signature(qui) if qui else ("oui", "greet"), ("curieux", "coo")]
        if absence_s is not None and absence_s >= cls.ABSENCE_LONGUE_S:
            seq.append(("content", "wheee"))                  # tremoussement de joie apres une longue absence
        return seq

    def entre(self, brain):
        mem = brain.ctx.extras.get("memoire")
        familiarite = mem.familiarite(self.qui) if mem is not None and self.qui else 0.0
        if self.absence_s is None and mem is not None and self.qui:
            self.absence_s = mem.absence_s(self.qui)
        if mem is not None and self.qui:
            mem.rencontre(self.qui)
        self.etapes = []
        t = 0.0
        seq = self.sequence(familiarite, self.absence_s, self.qui)
        self.messages, brain.messages = brain.messages, []
        if self.messages:
            seq = seq + [("curieux", "inquire"), ("oui", "chirp")]   # "pendant ton absence, il s'est passe quelque chose"
        for geste, son in seq:
            d, fn = gestures.GESTES[geste]
            self.etapes.append((t, d, fn, son, gestures.GESTES_CORPS.get(geste)))
            t += d + 0.3
        self.total = t
        self.joues = set()
        print(f"[{brain.t_global:6.1f}s] accueil de {self.qui} (familiarite {familiarite:.2f}, absence "
              f"{'?' if self.absence_s is None else f'{self.absence_s / 60:.0f} min'}) : "
              f"{' + '.join(e[3] for e in self.etapes)}"
              + (f" ; messages transmis : {', '.join(self.messages)}" if self.messages else ""), flush=True)

    def duree(self, brain):
        return self.total + 0.3

    def pas(self, brain, t):
        tete, corps = (0, 0, 0, 0), None
        for i, (t0, d, fn, son, fn_corps) in enumerate(self.etapes):
            if t0 <= t < t0 + d:
                if i not in self.joues:
                    self.joues.add(i)
                    brain.ctx.sound(son)
                tete = fn(t - t0)
                corps = fn_corps(t - t0) if fn_corps else None
        brain.ctx.head(tete)
        brain.ctx.pose(corps)

class JeuSolitaire(Etat):
    """Occupation autonome (ROADMAP "Occupation autonome et recherche d'attention") : personne n'est disponible pour
    s'en occuper, le canard s'amuse seul plutot que de rester simplement passif. Petit mouvement ludique sur place
    (avance/recule comme s'il poussait un objet, tete qui suit), pas une vraie recherche de balle (ca demande la
    vision, Phase 2) : juste de quoi distinguer visuellement ce moment d'un `Chill` au repos."""
    nom = "jeu_solitaire"

    def duree(self, brain):
        return brain.rng.uniform(5.0, 9.0)

    def entre(self, brain):
        brain.ctx.sound("chirp")

    def pas(self, brain, t):
        brain.ctx.head((0.0, 0.0, 0.5 * math.sin(2 * math.pi * t / 2.0), 0.0))
        brain.ctx.move(vx=0.2 * math.sin(2 * math.pi * t / 2.0))

class RechercheAttention(Etat):
    """Occupation autonome, variante "aller chercher l'attention" : un habitant (presence HA) ou le chat (veille
    camera) est disponible, le canard va vers lui plutot que de jouer seul. Une seule tentative, jamais insistee
    (regle de vie) : `brain.derniere_fois["ennui"]` sert de temporisation, pas de boucle ici.

    Vers le chat : on reutilise `cible_regard` comme `RegardeChat`, on a sa position. Vers un humain : pas de
    position fiable sans balises UWB (meme limite que `Accueil`, voir sa docstring) -> juste un appel sonore et un
    regard qui balaie, sans deplacement vers une direction qu'on ne connait pas."""
    nom = "cherche_attention"

    def __init__(self):
        self.cible = None   # "humain" ou "chat", pose par Brain._choisit_suivant avant la bascule

    def duree(self, brain):
        return 5.0

    def entre(self, brain):
        brain.ctx.sound("inquire" if self.cible == "humain" else "chirp")
        self.t_vise = None

    def pas(self, brain, t):
        if self.cible == "chat":
            veille, s = brain.ctx.extras.get("chat"), brain.ctx.state
            if veille is not None and s is not None:
                e = veille.estimation
                if e is not None and e[0] != self.t_vise:
                    self.t_vise = e[0]
                    cible = veille.cible_regard(s["odom"]["position"][2])
                    if cible:
                        r = brain.ctx.client.request("robot.look", {"x": float(cible[0]), "y": float(cible[1]), "z": float(cible[2])})
                        h = (r.get("result") or {}).get("head") if isinstance(r, dict) else None
                        if h:
                            brain.ctx.head((h["neck_pitch"], h["head_pitch"], h["head_yaw"], h["head_roll"]))
                            return
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            return
        yaw = 0.5 * math.sin(2 * math.pi * t / 4.0)       # pas de position connue : un regard qui balaie, pas une marche
        brain.ctx.head((0.0, 0.0, yaw, 0.0))

class Bonjour(Sequence):
    """Routine du matin (ROADMAP, table Humains : "etirement du matin", prochaine etape n°6) : une fois par jour, a
    l'heure reelle configuree, un grand etirement puis un bonjour - plus chaleureux si quelqu'un est a la maison
    (presence HA), un simple roucoulement sinon. Independant du reveil de sieste (qui s'etire deja)."""

    def __init__(self):
        super().__init__("bonjour", [])

    def etapes_pour(self, brain):
        if brain.presents:
            return [("etirement", "coo"), ("oui", "greet")]
        return [("etirement", "coo")]


class Remarque(Etat):
    """Un objet qui n'etait pas la avant (Exploration.obstacle : obstacle dans une case ou il est deja passe) : il
    s'arrete, le regarde (robot.look, un peu au-dessus du sol), un "inquire" et la tete qui se penche - puis il reprend
    sa vie (et contourne, comme tout obstacle)."""
    nom = "remarque"

    def entre(self, brain):
        d = brain.objet_nouveau or 0.5
        h = ((brain.ctx.state or {}).get("odom") or {}).get("position", [0, 0, 0.1])[2]
        self.vise = _regarder(brain, d, 0.0, 0.06 - h, (0.0, 0.3, 0.0, 0.0))
        brain.ctx.sound("inquire")

    def duree(self, brain):
        return 3.5

    def pas(self, brain, t):
        n, p, y, r = self.vise
        penche = 0.2 * gestures._smooth(t, 1.2, 1.8) * (1.0 - gestures._smooth(t, 2.8, 3.4))
        brain.ctx.head((n, p, y, r + penche))
        brain.ctx.move()


class Zoomies(Etat):
    """Zoomies (M9) : un trop-plein d'energie - quelques pirouettes et sprints courts, tete haute, "wheee". Chaque sprint
    exige 80 cm libres devant (il va plus vite qu'en promenade) et s'arrete des que ce n'est plus le cas ; un vide
    ou un capteur muet termine tout. 3 a 5 segments, jamais plus de 10 s."""
    nom = "zoomies"
    V_SPRINT = 0.5
    LIBRE_SPRINT = 0.8

    def entre(self, brain):
        brain.ctx.sound("wheee")
        self.segments = []
        for _ in range(brain.rng.randint(3, 5)):
            self.segments.append(("tourne", brain.rng.uniform(0.5, 1.0), brain.rng.choice((-1.0, 1.0))))
            self.segments.append(("sprint", brain.rng.uniform(0.8, 1.3), 0.0))
        self.total = min(10.0, sum(d for _, d, _ in self.segments))

    def duree(self, brain):
        return self.total + 0.5

    def pas(self, brain, t):
        s = brain.ctx.state or {}
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(s) if tof is not None and s else None
        if lib is None or lib.get("vide", float("inf")) < 0.4:
            brain.ctx.move()
            brain.fin_etat = min(brain.fin_etat, t + 0.3)
            return
        u = 0.0
        for genre, d, signe in self.segments:
            if t < u + d:
                if genre == "tourne":
                    brain.ctx.head((0.0, 0.0, 0.2 * signe, 0.0))   # tete haute : la rotation est morte tete baissee
                    brain.ctx.move(vyaw=1.5 * signe)
                else:
                    # tete baissee comme en promenade (sinon le ToF voit les bords de marche trop tard), placee 0,3 s
                    # avant de sprinter ; plus de marge qu'en promenade, il va plus vite
                    brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
                    pret = t - u >= 0.3 and lib["devant"] >= self.LIBRE_SPRINT and lib.get("vide", math.inf) >= 0.6
                    brain.ctx.move(vx=self.V_SPRINT if pret else 0.0)
                return
            u += d
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))
        brain.ctx.move()


class Picore(Etat):
    """GroundPick (M9) spontane : il pique le sol par curiosite (skill officiel `ground_pick`, pilote par le robot),
    puis un petit "peck" content."""
    nom = "picore"

    def entre(self, brain):
        r = brain.ctx.client.request("robot.do", {"skill": "ground_pick"})
        self.refuse = isinstance(r, dict) and "error" in r
        self.fini = None

    def duree(self, brain):
        return 0.5 if self.refuse else 8.0

    def pas(self, brain, t):
        if self.refuse:
            return
        pol = (brain.ctx.state or {}).get("policy")
        if self.fini is None and ((t >= 1.0 and pol != "ground_pick") or t >= 6.0):
            self.fini = t
            brain.ctx.sound("peck")
        if self.fini is not None:
            brain.ctx.head(gestures.oui(min(t - self.fini, 1.2)))
            brain.ctx.move()
            if t - self.fini >= 1.4:
                brain.fin_etat = t
