#!/usr/bin/env python3
"""Socle du cerveau : humeur, contexte de commande (Ctx), etat de base et etats elementaires (repos, regard,
rotation, promenade, gestes, sequences, sieste, ecoute). Les autres modules etats_*.py s'appuient sur celui-ci.
"""
import math
import time

import gestures


DT_DEFAUT = 0.02  # une trame robot.state = 20 ms

class Humeur:
    """Energie 0..1 (baisse en activite, remonte au repos/sieste) et eveil 0..1
    (monte sur evenement, retombe seul)."""

    def __init__(self, energie=0.8, eveil=0.2):
        self.energie = energie
        self.eveil = eveil

    def avance(self, dt, etat, vivacite=1.0):
        """`vivacite` (rythme circadien, Brain.vivacite) : < 1 le soir et la nuit, l'activite fatigue plus vite et
        l'eveil retombe plus vite ; > 1 en fin d'apres-midi, l'inverse."""
        taux = {"chill": +0.004, "nap": +0.03, "wander": -0.02,
                "turn": -0.01, "look": -0.004, "startle": -0.01, "curious": -0.003}
        t = taux.get(etat, 0.0)
        frein = min(1.5, max(0.8, 2.0 - vivacite))
        self.energie += (t * frein if t < 0 else t) * dt
        self.eveil -= 0.05 * frein * dt
        self.energie = min(1.0, max(0.0, self.energie))
        self.eveil = min(1.0, max(0.0, self.eveil))

# Fatigue progressive VISIBLE a basse energie (ROADMAP "chantier actif", 2026-10-05) : amplitude et cadence des
# mouvements de tete seulement. Jamais vx/vyaw - ils doivent rester au-dessus de la zone morte de la politique de
# marche (ZONE_MORTE.md : vx >= 0.3, |vyaw| >= 1.2), sous peine de jambes figees malgre la commande envoyee.
FATIGUE_PLEIN = 0.6   # energie au-dessus de laquelle : aucun ralentissement visible

FATIGUE_BAS = 0.25    # = Brain.SEUIL_SIESTE (juste avant la sieste) : lenteur la plus marquee prevue ici

FATIGUE_MIN = 0.6     # jamais moins de 60% : il continue de bouger, pas un arret visuel

def fatigue(brain):
    """Multiplicateur (FATIGUE_MIN..1.0) applique a l'amplitude ET a la frequence d'un mouvement de tete : plus
    l'energie est basse, plus les gestes sont lents et discrets, sans jamais s'arreter net."""
    e = brain.humeur.energie
    if e >= FATIGUE_PLEIN:
        return 1.0
    k = max(0.0, (e - FATIGUE_BAS) / (FATIGUE_PLEIN - FATIGUE_BAS))
    return FATIGUE_MIN + (1.0 - FATIGUE_MIN) * k

# La SEULE voix du canard : les sons de canard de sa banque officielle (duck-ipc-proto, SoundTag). Jamais de voix humaine,
# de synthese vocale ni de mot : regle d'identite du projet (CLAUDE.md, ROADMAP "Commandes vocales" -> sons de canard).
SONS_CANARD = frozenset({"alarm", "greet", "inquire", "peck", "chirp", "coo", "wheee"})


class Ctx:
    """Ce que voit un etat : client robotd, derniere trame, aide pour commander."""

    def __init__(self, client):
        self.client = client
        self.state = None
        self.sitting = False

    def head(self, vals):
        self.tete_cmd = tuple(vals)             # derniere consigne de tete (detecteurs : main tendue, caresse)
        self.client.notify("robot.head", {"neck_pitch": vals[0], "head_pitch": vals[1],
                                          "head_yaw": vals[2], "head_roll": vals[3]})

    def move(self, vx=0.0, vy=0.0, vyaw=0.0):
        # zones interdites du plan (position.py) : AUCUN etat ne peut y faire entrer le canard - on garde la rotation
        pos = (getattr(self, "extras", None) or {}).get("position")
        if vx > 0 and pos is not None and getattr(pos, "bloque_zone", False):
            vx = 0.0
        self.client.notify("robot.move", {"vx": vx, "vy": vy, "vyaw": vyaw})

    def pose(self, p=None):
        """Pose du corps debout (robot.pose : z m, roulis rad, tangage rad), lissee par robotd. None = retour au neutre
        (active=false, une seule fois) : un client qui laisse une pose active la laisse au robot."""
        if p is None:
            if getattr(self, "pose_active", False):
                self.client.notify("robot.pose", {"z": 0.0, "roll": 0.0, "pitch": 0.0, "active": False})
                self.pose_active = False
            return
        self.client.notify("robot.pose", {"z": p[0], "roll": p[1], "pitch": p[2], "active": True})
        self.pose_active = True

    def toggle_sit(self):
        self.client.request("robot.do", {"skill": "sit_toggle"})
        self.sitting = not self.sitting

    # duree d'ouverture du bec par son (s) : le bec bouge avec la voix (robot.mouth, que seul le cerveau pilote)
    BEC_S = {"chirp": 0.25, "peck": 0.15, "greet": 0.5, "coo": 0.6, "inquire": 0.45, "alarm": 0.8, "wheee": 1.2}

    def sound(self, tag, meme_en_silence=False):
        """La voix du canard (robot.sound) : alarm, greet, inquire, peck, chirp, coo, wheee. Muette en mode calme, sauf
        `meme_en_silence` : un signal demande expres (minuteur, rappel, reveil de l'application)."""
        if tag not in SONS_CANARD:
            self.sons_refuses = getattr(self, "sons_refuses", 0) + 1
            print(f"  (son {tag!r} refuse : le canard ne s'exprime qu'avec ses sons de canard)", flush=True)
            return
        if getattr(self, "silence", False) and not meme_en_silence:
            return
        try:
            r = self.client.request("robot.sound", {"tag": tag})
            if isinstance(r, dict) and "error" in r:     # un robot sans voix refuse (JSON-RPC error, pas d'exception)
                print(f"  (son {tag} refuse : {r['error']})", flush=True)
                return
        except Exception as e:      # on ne bloque jamais un geste pour un son
            print(f"  (son {tag} impossible : {e})", flush=True)
            return
        self.bec_t0, self.bec_fin = time.monotonic(), time.monotonic() + self.BEC_S.get(tag, 0.4)
        self.t_dernier_son = time.monotonic()            # le mode garde ne doit pas l'entendre lui-meme
        recents = (getattr(self, "extras", None) or {}).get("sons_recents")
        if recents is not None:
            recents.append((round(time.time(), 3), tag))  # canard jumeau : le casque joue ses sons a sa place
        voix = (getattr(self, "extras", None) or {}).get("voix")
        if voix is not None:
            voix.parle(tag)                     # le micro ne s'ecoute pas lui-meme (audio.VoixPropre)

    def bec(self):
        """A chaque trame : bec qui bat pendant le son (~8 Hz), puis refermé une fois. robot.mouth est une consigne
        continue (la derniere valeur reste) : on ne l'envoie que pendant le son et a la fermeture."""
        fin = getattr(self, "bec_fin", None)
        if fin is None:
            return
        now = time.monotonic()
        if now >= fin:
            self.client.notify("robot.mouth", {"open": 0.0})
            self.bec_fin = None
            return
        self.client.notify("robot.mouth", {"open": 0.45 + 0.35 * math.cos(2 * math.pi * 8.0 * (now - self.bec_t0))})

    def bouche(self, ouverture):
        """Ouvre le bec sans son (robot.mouth, consigne continue) - pour un baillement."""
        self.bec_fin = None
        self.client.notify("robot.mouth", {"open": float(ouverture)})

    def calme(self):
        self.head((0.0, 0.0, 0.0, 0.0))
        self.move()
        self.pose(None)

class Etat:
    nom = "?"

    def duree(self, brain):
        return 4.0

    def entre(self, brain):
        pass

    def pas(self, brain, t):
        """Appele a chaque trame avec t = secondes depuis l'entree dans l'etat."""
        brain.ctx.calme()

    def sort(self, brain):
        brain.ctx.calme()

class Chill(Etat):
    nom = "chill"
    P_AUX_AGUETS = 0.35          # un repos sur trois : il se fige, aux aguets (la veille du coup d'oeil peut tourner)
    aux_aguets = False

    def entre(self, brain):
        self.aux_aguets = getattr(brain, "_rng_vie", brain.rng).random() < self.P_AUX_AGUETS

    def pas(self, brain, t):
        """Au repos il respire et son regard bouge un peu (vivant.py) - sauf aux aguets : immobile, il guette."""
        brain.ctx.move()
        brain.ctx.pose(None)
        if self.aux_aguets:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
        else:
            from vivant import vie_au_repos
            brain.ctx.head(vie_au_repos(brain, t))

    def duree(self, brain):
        # initiative rare : plus l'eveil est haut, moins on reste longtemps au calme
        base = brain.rng.uniform(6.0, 12.0)
        return base * (1.0 - 0.5 * brain.humeur.eveil)

class LookAround(Etat):
    nom = "look"

    def duree(self, brain):
        return 6.0

    def pas(self, brain, t):
        f = fatigue(brain)                                        # fatigue progressive : plus lent, plus discret
        yaw = 0.6 * f * math.sin(2 * math.pi * t / (6.0 / f))
        brain.ctx.head((0.0, 0.1 * f * math.sin(2 * math.pi * t / (3.0 / f)), yaw, 0.0))

# Vitesses AU-DESSUS de la zone morte de la politique de marche (ZONE_MORTE.md) : en dessous, les jambes restent figees.
V_PROMENADE, V_ROTATION = 0.4, 1.5

LIBRE_MIN = 0.45                 # on n'avance pas si le ToF voit un obstacle (ou un vide) a moins de 45 cm devant

TETE_PROMENADE = 0.3             # inclinaison de tete en marchant (rad) : voir le sol, donc les marches, assez tot

class TurnInPlace(Etat):
    """Tourne sur place ; du cote le plus degage si le ToF le dit (ou si Wander vient de buter), sinon au hasard."""
    nom = "turn"

    def entre(self, brain):
        virage = getattr(brain, "virage_cible", None)        # demande par l'exploration : un angle precis
        prefere = getattr(brain, "cote_degage", None)
        if virage:
            self.signe = math.copysign(1.0, virage)
            self.duree_s = min(2.0, max(0.6, abs(math.degrees(virage)) / 50.0))   # ~50 deg/s a vyaw = 1,5
            brain.virage_cible = None
            brain.suivant_force = "wander"                   # puis on part dans la direction choisie
            brain.cap_choisi = True
        else:
            self.signe = prefere if prefere else brain.rng.choice((-1.0, 1.0))
            self.duree_s = brain.rng.uniform(1.0, 1.8)      # ~50 a 90 deg
        brain.cote_degage = None

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))                 # tete neutre : tete baissee, la rotation est morte
        brain.ctx.move(vyaw=V_ROTATION * self.signe)

class Wander(Etat):
    """Promenade en ligne droite, SEULEMENT si le capteur de distance voit de la place devant. Sans ToF frais : on ne
    bouge pas (prudence). Obstacle a moins de LIBRE_MIN : on s'arrete, on note le cote le plus degage, et on passe a
    `turn`."""
    nom = "wander"

    GAFFE_M = 0.3                # obstacle vu a moins de 30 cm (surgi au dernier moment) : il « bute » (gaffe)
    SEUIL_PASSAGE_ETROIT = 0.5   # m, de chaque cote : en dessous des deux, pause avant de s'y engager

    def entre(self, brain):
        self.duree_s = brain.rng.uniform(2.5, 6.0)
        self.arrets = 0
        self.virage = None
        self.pause_faite = False     # une seule pause par traversee, pas a chaque trame dans le passage
        self.pause_jusqua = None
        # Exploration : avant de partir, regarder si une direction mene vers des zones moins visitees (sauf si on vient
        # justement de tourner pour ca).
        o = brain.ctx.state.get("odom") if brain.ctx.state is not None else None
        if brain.explo_actif and o is not None and not getattr(brain, "cap_choisi", False):
            ecart = brain.exploration.meilleur_ecart(o["position"][0], o["position"][1], o["yaw"], brain.t_global)
            if abs(ecart) >= math.radians(30):
                self.virage = ecart
        brain.cap_choisi = False

    def duree(self, brain):
        return self.duree_s

    def pas(self, brain, t):
        # Tete un peu baissee : le canard regarde ou il met les pattes. Tete au neutre, les rayons du ToF touchent le sol
        # trop loin et le bord d'une estrade n'est vu qu'une fois passe (essai_vide.py : 0/3 au neutre, 3/3 a 0,3 rad).
        brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
        if t < 0.4:
            brain.ctx.move()                                 # on laisse la tete se placer avant de juger le sol
            return
        if self.virage is not None:                          # d'abord tourner vers la zone la plus nouvelle
            brain.virage_cible, self.virage = self.virage, None
            brain.fin_etat = brain.t_etat
            brain.suivant_force = "turn"
            brain.ctx.move()
            return
        if self.pause_jusqua is not None:
            brain.ctx.move()                                 # immobile : on "jauge" le passage avant de s'y engager
            if t >= self.pause_jusqua:
                self.pause_jusqua = None
            return
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(brain.ctx.state) if tof is not None and brain.ctx.state is not None else None
        if lib is None:
            brain.ctx.move()                                 # aveugle : on reste sur place
            return
        if lib["devant"] < 9.0 and brain.ctx.state.get("odom"):    # obstacle vu devant : on le note dans la grille
            o = brain.ctx.state["odom"]
            if brain.exploration.obstacle(o["position"][0] + lib["devant"] * math.cos(o["yaw"]),
                                          o["position"][1] + lib["devant"] * math.sin(o["yaw"]), brain.t_global) \
                    and lib["devant"] <= 1.5:
                brain.objet_nouveau = lib["devant"]                   # tiens, ce n'etait pas la avant
                mur = brain.diagnostic.mur if hasattr(brain, "diagnostic") else time.time
                brain.objets_au_sol = (brain.objets_au_sol + [(mur(),
                                       round(o["position"][0] + lib["devant"] * math.cos(o["yaw"]), 2),
                                       round(o["position"][1] + lib["devant"] * math.sin(o["yaw"]), 2))])[-20:]
                brain.evenement("objet_nouveau")
        # Passage etroit (ROADMAP "chantier actif") : une pause VISIBLE avant de s'y engager, comme un animal qui
        # jauge un couloir serre - pas un evitement (on continue ensuite), distinct de l'arret sur obstacle ci-dessous.
        if (not self.pause_faite and lib["devant"] >= LIBRE_MIN
                and lib["gauche"] < self.SEUIL_PASSAGE_ETROIT and lib["droite"] < self.SEUIL_PASSAGE_ETROIT):
            self.pause_faite = True
            self.pause_jusqua = t + 0.6
            brain.ctx.move()
            return
        if lib["devant"] < LIBRE_MIN:
            brain.ctx.move()
            brain.cote_degage = 1.0 if lib["gauche"] >= lib["droite"] else -1.0
            brain.obstacle_vu = brain.obstacle_vu + 1 if hasattr(brain, "obstacle_vu") else 1
            brain.fin_etat = brain.t_etat                    # fin de la promenade : on va tourner
            brain.suivant_force = "turn"
            # Gaffe (personnage.py) : l'obstacle a surgi TOUT pres (il ne l'a vu qu'au dernier moment) -> il bute, se
            # vexe et contourne en exagerant ; rare, et seulement si l'etat existe (essais minimaux sans lui)
            rng = getattr(brain, "_rng_vie", None)
            if (lib["devant"] < self.GAFFE_M and rng is not None and "gaffe" in getattr(brain, "etats", {})
                    and brain.t_global - brain.derniere_fois.get("gaffe", -1e9) >= 600.0 and rng.random() < 0.35):
                brain.derniere_fois["gaffe"] = brain.t_global
                brain.suivant_force = "gaffe"
            return
        brain.ctx.move(vx=V_PROMENADE)

class Geste(Etat):
    """Etat qui joue un geste de gestures.py (tete) avec recul optionnel."""

    def __init__(self, nom_etat, geste, recul=False, son=None):
        self.nom = nom_etat
        self.geste = geste
        self.recul = recul
        self.son = son              # etiquette de robot.sound jouee a l'entree (la voix du canard)
        self._duree, self._fn = gestures.GESTES[geste]

    def entre(self, brain):
        if self.son:
            brain.ctx.sound(self.son)

    def duree(self, brain):
        return self._duree + 0.5

    def pas(self, brain, t):
        brain.ctx.head(self._fn(min(t, self._duree)) if t < self._duree else (0, 0, 0, 0))
        corps = gestures.GESTES_CORPS.get(self.geste)
        if corps is not None:
            brain.ctx.pose(corps(t) if t < self._duree else None)
        if self.recul and t <= 0.5:
            brain.ctx.move(vx=-0.1)

class Nap(Etat):
    """Affaissement de tete, assis, repos qui recharge l'energie, puis on se leve."""
    nom = "nap"

    def entre(self, brain):
        self.assis = brain.ctx.sitting           # deja assis (sieste prolongee en mode calme) : on ne se rassoit pas
        self.leve = False
        f = brain.facteur_sieste() if hasattr(brain, "facteur_sieste") else 1.0
        self.total = 2.0 + 4.0 + brain.rng.uniform(8.0, 14.0) * f + 4.0
        # "Reves" pendant le sommeil profond (ROADMAP "chantier actif", 2026-10-05) : 0 a 2 petits tressaillements
        # de tete, jamais pendant l'endormissement (< 2s) ni le reveil (derniers 4s) - juste de quoi distinguer une
        # sieste "vivante" d'une simple pause, sans RL ni capteur supplementaire.
        profond = self.total - 2.0 - 4.0
        # ses reves rejouent sa journee (personnage.REVES) : le theme est tire de ce qu'il a vecu aujourd'hui
        import personnage
        self.theme = personnage.theme_de_reve(getattr(brain, "du_jour", None), getattr(brain, "_rng_vie", brain.rng))
        self.reves = []
        if profond >= 3.0:
            for _ in range(brain.rng.randint(0, 2)):
                t0 = 2.0 + brain.rng.uniform(0.5, profond - 1.5)
                self.reves.append([t0, brain.rng.uniform(0.6, 1.2), brain.rng.choice((-1, 1)), False])

    def duree(self, brain):
        return self.total

    def pas(self, brain, t):
        ctx = brain.ctx
        if t < 2.0 and not self.assis:
            ctx.head(gestures.fatigue(t))
        elif not self.assis:
            ctx.toggle_sit()
            self.assis = True
        elif t >= self.total - 4.0 and not self.leve and not brain.reste_assis():
            ctx.toggle_sit()
            self.leve = True
            ctx.head((0, 0, 0, 0))
        elif self.assis and not self.leve and getattr(brain, "surchauffe", False):
            # il a chaud : il halete, bec entrouvert en rythme (comme un canard au soleil), sans rever
            ctx.bouche(0.25 + 0.15 * math.sin(2 * math.pi * 1.5 * t))
        elif self.assis and not self.leve:
            for reve in self.reves:
                t0, duree, signe, joue = reve
                if t0 <= t < t0 + duree:
                    k = math.sin(math.pi * (t - t0) / duree)      # monte puis redescend a 0 : jamais de saut brusque
                    if self.theme is not None:
                        import personnage
                        _, son, (cou, tete, lacet, roulis) = personnage.REVES[self.theme]
                        if not joue:
                            if son:
                                ctx.sound(son)
                            reve[3] = True
                        balance = math.sin(4 * math.pi * (t - t0) / duree) if self.theme == "danse" else signe
                        ctx.head((cou * k, 0.7 + (tete - 0.7) * k, lacet * signe * k, roulis * balance * k))
                        break
                    if not joue:
                        ctx.sound("chirp")        # murmure sonore occasionnel (ROADMAP) ; silencieux en mode calme
                        reve[3] = True
                    ctx.head((0.0, 0.7 + 0.05 * signe * k, 0.08 * signe * k, 0.0))
                    break

    def sort(self, brain):
        if getattr(brain, "surchauffe", False):
            brain.ctx.bouche(0.0)               # fin de halètement
        if brain.ctx.sitting and not brain.reste_assis():
            brain.ctx.toggle_sit()
        brain.ctx.calme()

class Ecoute(Etat):
    """Une conversation vocale est en cours (quacksat, satellite Assist de HA) : le cerveau se tait et ne commande PLUS
    RIEN (robotd : le dernier ecrit gagne ; quacksat balance la tete en reflechissant et peut faire marcher le canard a la
    demande). Une seule consigne a l'entree : arreter la promenade en cours. Sortie sur ecoute_off, ou au bout de
    DUREE_MAX si le signal de fin se perd (satellite devenu indisponible)."""
    nom = "ecoute"
    DUREE_MAX = 90.0

    def entre(self, brain):
        brain.ctx.move()
        brain.ctx.pose(None)

    def duree(self, brain):
        return self.DUREE_MAX

    def pas(self, brain, t):
        pass

    def sort(self, brain):
        pass                                    # pas de consigne de tete au milieu d'une reponse de quacksat

def _regarder(brain, x, y, z, defaut):
    """robot.look vers (x, y, z) du repere du tronc -> angles de tete renvoyes par robotd, sinon `defaut`."""
    r = brain.ctx.client.request("robot.look", {"x": float(x), "y": float(y), "z": float(z)})
    h = (r.get("result") or {}).get("head") if isinstance(r, dict) else None
    return (h["neck_pitch"], h["head_pitch"], h["head_yaw"], h["head_roll"]) if h else defaut

class Sequence(Etat):
    """Suite de gestes de gestures.py, chacun avec son son (robot.sound), joues l'un apres l'autre - la meme mecanique
    que `Accueil`, pour les routines qui n'ont pas besoin de sa logique de familiarite."""

    def __init__(self, nom_etat, etapes):
        self.nom = nom_etat
        self.etapes_def = list(etapes)          # [(geste, son ou None)]

    def etapes_pour(self, brain):
        return self.etapes_def

    def entre(self, brain):
        self.etapes, t = [], 0.0
        for geste, son in self.etapes_pour(brain):
            d, fn = gestures.GESTES[geste]
            self.etapes.append((t, d, fn, son, gestures.GESTES_CORPS.get(geste)))
            t += d + 0.3
        self.total = t
        self.joues = set()

    def duree(self, brain):
        return self.total + 0.3

    def pas(self, brain, t):
        tete, corps = (0, 0, 0, 0), None
        for i, (t0, d, fn, son, fn_corps) in enumerate(self.etapes):
            if t0 <= t < t0 + d:
                if i not in self.joues:
                    self.joues.add(i)
                    if son:
                        brain.ctx.sound(son)
                tete = fn(t - t0)
                corps = fn_corps(t - t0) if fn_corps else None
        brain.ctx.head(tete)
        brain.ctx.pose(corps)
