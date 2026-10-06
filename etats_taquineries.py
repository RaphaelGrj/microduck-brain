#!/usr/bin/env python3
"""Taquineries (ROADMAP "Chantier suivant : taquiner l'humain"), lots A a D. Le budget, le signal stop et la
memoire des blagues sont dans taquineries.py ; chaque etat ici porte `taquinerie = True`.
"""
import math

import gestures
from etats_base import (Etat, LIBRE_MIN, TETE_PROMENADE, V_PROMENADE, V_ROTATION, _regarder)


class FeinteBec(Etat):
    """Feinte affectueuse : il regarde la main tendue, avance lentement le bec vers elle... et devie au dernier moment
    en reculant d'un petit bond (0,5 s de marche arriere, ~5 cm), avec un chirp : "je t'aurai pas"."""
    nom = "feinte_bec"
    taquinerie = True

    def entre(self, brain):
        m = brain.detecteur_main.main
        h = (brain.ctx.state or {}).get("odom", {}).get("position", [0, 0, 0.1])[2]
        self.vise = _regarder(brain, m[1], m[2], m[3] - h, (0.0, 0.25, 0.0, 0.0)) if m else (0.0, 0.25, 0.0, 0.0)
        self.cote = 1.0 if brain.rng.random() < 0.5 else -1.0

    def duree(self, brain):
        return 3.2

    def pas(self, brain, t):
        n, p, y, r = self.vise
        if t < 1.4:                              # le bec s'approche, de plus en plus
            k = gestures._smooth(t, 0.2, 1.4)
            brain.ctx.head((n, p + 0.3 * k, y, r))
            brain.ctx.move()
            return
        brain.son_une_fois("ecart", "chirp")
        k = 1.0 - gestures._smooth(t, 2.4, 3.1)  # ecart brusque, tenu, puis retour
        brain.ctx.head((0.0, -0.2 * k, 0.6 * self.cote * k, -0.2 * self.cote * k))
        brain.ctx.move(vx=-0.4 if t < 1.9 else 0.0)

class Esquive(Etat):
    """Se faire desirer : la premiere main qui approche est esquivee (tete detournee, petit son interrogatif) ; la
    suivante, dans la minute, est acceptee avec un roucoulement (Brain.ESQUIVE_S)."""
    nom = "esquive"
    taquinerie = True

    def entre(self, brain):
        brain.ctx.sound("inquire")
        self.cote = 1.0 if brain.rng.random() < 0.5 else -1.0
        brain.t_esquive = brain.t_global

    def duree(self, brain):
        return 2.4

    def pas(self, brain, t):
        k = gestures._smooth(t, 0.0, 0.25) * (1.0 - gestures._smooth(t, 1.6, 2.2))
        brain.ctx.head((0.0, -0.15 * k, 0.7 * self.cote * k, 0.25 * self.cote * k))
        brain.ctx.move()

class FauxEndormi(Etat):
    """Appele (deux claquements de mains), il fait mine de dormir : tete qui tombe, immobile... puis se "reveille" d'un
    coup, tout content de sa blague."""
    nom = "faux_endormi"
    taquinerie = True

    def entre(self, brain):
        self.reveil = brain.rng.uniform(4.0, 7.0)

    def duree(self, brain):
        return self.reveil + gestures.GESTES["surpris"][0] + 0.8

    def pas(self, brain, t):
        if t < self.reveil:
            brain.ctx.head(gestures.fatigue(min(t, 2.0)))
        else:
            brain.son_une_fois("reveil", "wheee")
            d, fn = gestures.GESTES["surpris"]
            brain.ctx.head(fn(t - self.reveil) if t - self.reveil < d else (0, 0, 0, 0))
        brain.ctx.move()

class SourdeOreille(Etat):
    """Appele, il fait mine de ne pas entendre : regarde ostensiblement ailleurs, puis double-prise exageree (la tete
    revient d'un coup) et repond enfin."""
    nom = "sourde_oreille"
    taquinerie = True

    def entre(self, brain):
        self.cote = 1.0 if brain.rng.random() < 0.5 else -1.0

    def duree(self, brain):
        return 6.2

    def pas(self, brain, t):
        if t < 3.4:                              # nonchalant : il detourne lentement la tete et le bec en l'air
            k = gestures._smooth(t, 0.0, 1.2)
            brain.ctx.head((0.0, -0.2 * k, 0.75 * self.cote * k, 0.0))
        elif t < 3.6:                            # double-prise : retour brutal
            k = 1.0 - (t - 3.4) / 0.2
            brain.ctx.head((0.0, -0.2 * k, 0.75 * self.cote * k, 0.0))
        else:
            brain.son_une_fois("reponse", "inquire")
            u = t - 3.6
            brain.ctx.head(gestures.surpris(u) if u < 1.2 else gestures.oui(u - 1.2) if u < 2.4 else (0, 0, 0, 0))
        brain.ctx.move()

class RegardMystere(Etat):
    """Regard mysterieux vers un point vide : il fixe intensement un coin de la piece, immobile, penche un peu la tete...
    puis rien. Gag pur, sans aucune alerte derriere (pas de son d'alarme, pas d'evenement HA)."""
    nom = "regard_mystere"
    taquinerie = True

    def entre(self, brain):
        cote = brain.rng.choice((-1.0, 1.0))
        self.vise = _regarder(brain, 1.2, 0.7 * cote, 0.6, (0.0, -0.35, 0.5 * cote, 0.0))

    def duree(self, brain):
        return 7.0

    def pas(self, brain, t):
        n, p, y, r = self.vise
        k = gestures._smooth(t, 0.0, 0.8) * (1.0 - gestures._smooth(t, 6.2, 7.0))
        penche = 0.15 * gestures._smooth(t, 3.0, 3.6)
        brain.ctx.head((n * k, p * k, y * k, (r + penche) * k))
        brain.ctx.move()

class Baillement(Etat):
    """Faux baillement d'ennui pendant une discussion qui s'eternise (audio.py : discussion_longue) - exagere, bec grand
    ouvert, tete en arriere, soupir. Commentaire ironique sur la longueur, rien de plus."""
    nom = "baillement"
    taquinerie = True

    def duree(self, brain):
        return gestures.GESTES["baillement"][0] + 0.4

    def pas(self, brain, t):
        brain.ctx.head(gestures.baillement(t))
        if t >= 0.4:
            brain.son_une_fois("soupir", "coo")
        if 0.7 <= t < 2.2:
            brain.ctx.bouche(0.9 * math.sin(math.pi * (t - 0.7) / 1.5))
        elif 2.2 <= t < 2.25:
            brain.ctx.bouche(0.0)
        brain.ctx.move()

    def sort(self, brain):
        brain.ctx.bouche(0.0)
        brain.ctx.calme()

class DernierMot(Etat):
    """Il a toujours le dernier mot : dans un silence de la conversation (audio.py : silence_conversation), un petit son
    de canard et un hochement, comme s'il participait - sans jamais rien dire d'utile."""
    nom = "dernier_mot"
    taquinerie = True

    def entre(self, brain):
        brain.ctx.sound(brain.rng.choice(("peck", "chirp", "inquire")))

    def duree(self, brain):
        return 1.0

    def pas(self, brain, t):
        brain.ctx.head(gestures.oui(t) if t < 0.6 else (0, 0, 0, 0))
        brain.ctx.move()

class PousseBalle(Etat):
    """Quelqu'un tend la main vers la balle posee devant le canard : il la pousse du pied juste hors de portee (une
    rafale de marche de 0,6 s - "le pied pousse la balle au dernier pas", constat de la Phase 2), puis releve la tete,
    tout content. Deux fois par 10 min au plus (Malice.LIMITES). Jamais s'il y a un vide devant."""
    nom = "pousse_balle"
    taquinerie = True

    def entre(self, brain):
        brain.ctx.sound("chirp")
        self.annule = False

    def duree(self, brain):
        return 3.2

    def pas(self, brain, t):
        if self.annule:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            brain.ctx.move()
            return
        if t < 1.4:
            # tete baissee comme en promenade : le ToF voit le sol et les bords ; verification du vide A CHAQUE trame
            brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
            tof = brain.ctx.extras.get("tof")
            lib = tof.libre(brain.ctx.state) if tof is not None and brain.ctx.state is not None else None
            if t >= 0.4 and (lib is None or lib.get("vide", math.inf) < 0.35):
                self.annule = True               # un vide (ou un capteur muet) : on ne pousse pas
                brain.ctx.move()
                brain.fin_etat = min(brain.fin_etat, t + 0.5)
                return
            brain.ctx.move(vx=0.4 if 0.7 <= t < 1.3 else 0.0)
            return
        brain.son_une_fois("content", "wheee")
        k = gestures._smooth(t, 1.4, 1.8) * (1.0 - gestures._smooth(t, 2.6, 3.2))
        brain.ctx.head((0.0, -0.3 * k, 0.0, 0.15 * k * math.sin(2 * math.pi * t / 0.8)))
        brain.ctx.move()

class MimeVol(Etat):
    """Mime de vol d'un objet au sol : il pique la balle (skill officiel `ground_pick`, pilote par le robot), referme le
    bec, prend un air fier et se detourne avec "son butin". On ne sait pas encore si `ground_pick` attrape vraiment un
    objet : d'ici la, c'est un MIME (a requalifier en vrai vol/planque une fois le skill mesure sur le robot)."""
    nom = "mime_vol"
    taquinerie = True

    def entre(self, brain):
        r = brain.ctx.client.request("robot.do", {"skill": "ground_pick"})
        self.refuse = isinstance(r, dict) and "error" in r
        self.t_fin_pique = None

    def duree(self, brain):
        return 1.0 if self.refuse else 12.0

    def pas(self, brain, t):
        if self.refuse:
            return
        if self.t_fin_pique is None:             # le robot pique : on n'envoie rien (le skill pilote tout le corps)
            pol = (brain.ctx.state or {}).get("policy")
            if (t >= 1.0 and pol != "ground_pick") or t >= 6.0:
                self.t_fin_pique = t
                brain.ctx.bouche(0.0)             # bec ferme : "je l'ai"
                brain.ctx.sound("chirp")
            return
        u = t - self.t_fin_pique
        if u < 1.8:
            brain.ctx.head(gestures.fier(u))
            brain.ctx.move()
        elif u < 3.0:                            # il se detourne avec son butin
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            brain.ctx.move(vyaw=V_ROTATION)
        else:
            brain.son_une_fois("butin", "wheee")
            brain.ctx.head((0.0, -0.2, 0.0, 0.1))
            brain.ctx.move()
            if u >= 4.0:
                brain.fin_etat = t

class Aspirateur(Etat):
    """Le robot aspirateur arrive vers lui. En taquinerie (`taquine`) : il lui barre le chemin un instant, tete baissee
    vers lui avec un petit "peck" provocateur ; puis, dans tous les cas, il s'ecarte - pivot vers le cote le plus
    degage et quelques pas - AVANT que l'aspirateur ne soit a 30 cm (un canard de 800 g ne se fait pas bousculer).
    Jamais de poursuite."""
    nom = "aspirateur"
    TIENT_S = 2.5
    TROP_PRES_M = 0.30

    def __init__(self):
        self.taquine = False

    def entre(self, brain):
        self.taquinerie_jouee = self.taquine
        if self.taquine:
            brain.malice.noter(brain, "barre_aspirateur")
            brain.ctx.sound("peck")
        self.t_ecart = self.TIENT_S if self.taquine else 0.0
        self.signe = brain.cote_degage if getattr(brain, "cote_degage", None) else brain.rng.choice((-1.0, 1.0))
        self.taquine = False

    def duree(self, brain):
        return self.t_ecart + 3.0

    def pas(self, brain, t):
        d = brain.detecteur_approche.distance
        if t < self.t_ecart and (d is None or d > self.TROP_PRES_M):
            brain.ctx.head((0.0, 0.3, 0.0, 0.15))
            brain.ctx.move()
            return
        if t < self.t_ecart:
            self.t_ecart = t                     # trop pres : on s'ecarte tout de suite
        u = t - self.t_ecart
        if u < 1.2:
            brain.ctx.head((0.0, 0.0, 0.0, 0.0))
            brain.ctx.move(vyaw=V_ROTATION * self.signe)
            return
        tof = brain.ctx.extras.get("tof")
        lib = tof.libre(brain.ctx.state) if tof is not None and brain.ctx.state is not None else None
        libre = lib is not None and lib["devant"] >= LIBRE_MIN
        brain.ctx.head((0.0, TETE_PROMENADE, 0.0, 0.0))
        brain.ctx.move(vx=V_PROMENADE if libre and u < 2.6 else 0.0)

class MimeTon(Etat):
    """Il mime l'intonation de qui vient de parler (audio.py : intonation monte / descend), en exagerant : deux sons
    qui "montent" (chirp puis inquire) et la tete qui part vers le haut, ou l'inverse (inquire puis coo, tete qui
    tombe). Effet perroquet ironique, sans un seul mot."""
    nom = "mime_ton"
    taquinerie = True

    def __init__(self):
        self.sens = "monte"

    def entre(self, brain):
        self.sons = ("chirp", "inquire") if self.sens == "monte" else ("inquire", "coo")
        brain.ctx.sound(self.sons[0])

    def duree(self, brain):
        return 2.0

    def pas(self, brain, t):
        if t >= 0.6:
            brain.son_une_fois("ton2", self.sons[1])
        k = gestures._smooth(t, 0.0, 1.2) * (1.0 - gestures._smooth(t, 1.5, 2.0))
        signe = -1.0 if self.sens == "monte" else 1.0          # head_pitch negatif = tete vers le haut
        brain.ctx.head((0.0, signe * 0.4 * k, 0.0, 0.2 * k))
        brain.ctx.move()

class CompteEternuements(Etat):
    """Une serie d'eternuements : au premier, contagion sincere (son propre eternuement, etat `eternuement`) ; a partir
    du deuxieme, il "compte" - un son different a chaque fois et autant de hochements que d'eternuements (4 au plus),
    avec un brin de moquerie."""
    nom = "compte_eternuements"
    taquinerie = True
    SONS = ("peck", "chirp", "inquire", "wheee")

    def __init__(self):
        self.n = 2

    def entre(self, brain):
        brain.ctx.sound(self.SONS[min(self.n, len(self.SONS) + 1) - 2])
        self.hoche = min(self.n, 4)

    def duree(self, brain):
        return 0.5 * self.hoche + 0.6

    def pas(self, brain, t):
        brain.ctx.head(gestures.oui(t % 0.5) if t < 0.5 * self.hoche else (0, 0, 0, 0))
        brain.ctx.move()

class FausseChute(Etat):
    """Fausse chute comique, clairement theatrale : le corps se dandine de plus en plus (robot.pose, roulis 0,25 rad -
    sous les +-0,3 rad mesures sans chute, diag_pose.py), la tete s'affole, "wheee"... et il s'assoit d'un coup
    (sit_toggle), l'air etourdi, puis se releve et prend un petit air fier. AUCUNE perte d'equilibre reelle."""
    nom = "fausse_chute"
    taquinerie = True
    ROULIS = 0.25

    def entre(self, brain):
        self.assis = False
        self.releve = False

    def duree(self, brain):
        return 9.0

    def pas(self, brain, t):
        ctx = brain.ctx
        if t < 1.5:
            k = gestures._smooth(t, 0.0, 1.2)
            ctx.pose((0.0, self.ROULIS * k * math.sin(2 * math.pi * 2.0 * t), 0.0))
            ctx.head((0.0, -0.2 * k, 0.35 * k * math.sin(2 * math.pi * 3.0 * t), -0.3 * k * math.sin(2 * math.pi * 2.0 * t)))
            if t >= 1.2:
                brain.son_une_fois("cascade", "wheee")
        elif not self.assis:
            ctx.pose(None)
            ctx.toggle_sit()                     # "plop"
            self.assis = True
        elif t < 5.0:
            u = t - 1.5                          # etourdi : la tete fait de petits cercles
            ctx.head((0.0, 0.15 * math.cos(2 * math.pi * 0.7 * u), 0.2 * math.sin(2 * math.pi * 0.7 * u), 0.0))
        elif not self.releve:
            ctx.sound("chirp")
            ctx.head((0.0, 0.0, 0.0, 0.0))
            if ctx.sitting:
                ctx.toggle_sit()
            self.releve = True
        else:
            u = t - 6.0
            ctx.head(gestures.fier(u) if 0.0 <= u < 1.8 else (0, 0, 0, 0))
        ctx.move()

    def sort(self, brain):
        brain.ctx.pose(None)
        if brain.ctx.sitting and not brain.reste_assis():
            brain.ctx.toggle_sit()
        brain.ctx.calme()

class FausseNotif(Etat):
    """Parodie sonore d'une notification de telephone : "ding-ding" en deux chirps (un son clairement ludique, jamais une
    imitation d'alarme), il regarde ailleurs d'un air innocent... puis file, tout content de lui."""
    nom = "fausse_notif"
    taquinerie = True

    def entre(self, brain):
        brain.ctx.sound("chirp")
        self.cote = brain.rng.choice((-1.0, 1.0))

    def duree(self, brain):
        return 5.2

    def pas(self, brain, t):
        if t >= 0.3:
            brain.son_une_fois("ding2", "chirp")
        if t < 3.4:
            k = gestures._smooth(t, 0.6, 1.2)
            brain.ctx.head((0.0, -0.25 * k, 0.6 * self.cote * k, 0.0))
            brain.ctx.move()
            return
        brain.son_une_fois("file", "wheee")
        brain.ctx.head((0.0, 0.0, 0.0, 0.0))
        brain.ctx.move(vyaw=V_ROTATION * self.cote if t < 4.6 else 0.0)

class Fier(Etat):
    """Petit air fier apres une blague devenue un running gag ; amplitude = Malice.fierte (trophee de malice)."""
    nom = "fier"

    def __init__(self):
        self.k = 0.5

    def entre(self, brain):
        brain.ctx.sound("chirp")

    def duree(self, brain):
        return gestures.GESTES["fier"][0] + 0.3

    def pas(self, brain, t):
        brain.ctx.head(tuple(self.k * v for v in gestures.fier(t)) if t < gestures.GESTES["fier"][0] else (0, 0, 0, 0))
        brain.ctx.move()
