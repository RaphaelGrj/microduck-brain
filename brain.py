#!/usr/bin/env python3
"""Squelette du cerveau comportemental (Phase 3) : etats + modele energie/eveil.

Inspire des etats M9 de Pollen (Chill, LookAround, Wander, TurnInPlace, Startle, Nap...),
sans RL : chaque etat ne fait qu'envoyer des intents a robotd (robot.head, robot.move,
robot.do) et le vocabulaire de gestes vient de gestures.py.

Principes (ROADMAP "regles de vie") :
  - initiative rare : longs temps de repos (Chill) entre deux actions ;
  - ne jamais insister : un evenement ignore (Nap, chute) n'est pas rejoue ;
  - securite : si le canard est tombe, le cerveau s'arrete et ne commande plus rien ;
  - a la sortie, tete neutre, arret du mouvement, et on se releve si on dormait.

Usage : python3 brain.py [duree_s] [--energy 0.2] [--events bruit@20,chat@40]
"""
import math
import random
import sys
import threading
import time

from exploration import Exploration
from habitudes import Habitudes
from personnalite import Personnalite
from caresse import DetecteurCaresse
from main_tendue import DetecteurApproche, DetecteurMain
from taquineries import Malice
# Les etats vivent dans etats_*.py ; ils sont reexportes ici pour que `from brain import ...` continue de marcher.
from etats_base import (DT_DEFAUT, SONS_CANARD, FATIGUE_BAS, FATIGUE_MIN, FATIGUE_PLEIN, LIBRE_MIN, TETE_PROMENADE,  # noqa: F401
                        V_PROMENADE, V_ROTATION, Chill, Ctx, Ecoute, Etat, Geste, Humeur, LookAround, Nap, Sequence,
                        TurnInPlace, Wander, _regarder, fatigue)
from etats_jeux import CacheCache, JeuBalle, Soleil
from diagnostic import Diagnostic
from etats_maison import AlarmeFumee, AssisDemande, AutoTestReveil, Toupie
from etats_taquineries import (Aspirateur, Baillement, CompteEternuements, DernierMot, Esquive, FausseChute,
                               FausseNotif, FauxEndormi, FeinteBec, Fier, MimeTon, MimeVol, PousseBalle, RegardMystere,
                               SourdeOreille)
from etats_vie import (Picore, Remarque, Zoomies, Accueil, Bonjour, Caresse, Danse, JeuSolitaire, MainTendue, Porte, RechercheAttention,
                       RegardeChat, VaAuCoin, Timide, CoupOeil, Compagnie, BaillementContagieux)

class Brain:
    SEUIL_SIESTE = 0.25
    # "Va se recharger de sa propre initiative avant d'etre a court" (ROADMAP "chantier actif") : la VRAIE batterie
    # (state["battery"]["percent"], distincte du modele comportemental `Humeur.energie`) force le repos en dessous
    # de ce seuil - anticipation (consommer moins en se posant) plutot qu'attendre l'arret force. Pas encore de
    # retour physique au chargeur : aucune position de chargeur connue dans brain.py (meme limite que `Accueil`).
    BATTERIE_BASSE_PCT = 25.0
    RARES = {"lissage": 0.015, "ebouriffe": 0.01, "etirement": 0.008, "eternuement": 0.005}   # poids face a ~1 pour le reste
    DELAI_RARE = 300.0
    # Occupation autonome / recherche d'attention (ROADMAP "chantier actif", 2026-10-05) : si rien ne s'est passe
    # depuis SEUIL_ENNUI_S, le canard ne reste pas simplement passif en Chill -> jeu solitaire ou recherche
    # d'attention (humain present, sinon chat visible). Jamais plus souvent que DELAI_ENNUI_S (ne jamais insister).
    SEUIL_ENNUI_S = 600.0
    DELAI_ENNUI_S = 300.0
    # "S'ebroue apres une longue immobilite REELLE" (ROADMAP "chantier actif") : reutilise le geste `ebouriffe`
    # existant, mais declenche par l'etat constate (odom qui ne bouge quasi pas) plutot que par l'horloge/le hasard
    # des RARES ci-dessus - les deux partagent le meme garde-fou (`derniere_fois["ebouriffe"]`, DELAI_RARE) pour ne
    # jamais se declencher plus souvent que le geste "rare" habituel, quelle que soit la cause.
    SEUIL_IMMOBILE_S = 1200.0    # 20 min sans bouger de plus de SEUIL_DEPLACEMENT
    SEUIL_DEPLACEMENT = 0.1      # m : en dessous, on considere que le canard n'a pas vraiment bouge
    # Garde-fou "chat agace" (ROADMAP, garde-fous du chat, non negociable) : renverse plusieurs fois de suite -> il
    # s'assoit et passe en veille plutot que de recommencer. Valable quelle que soit la cause (chat, enfant, sol
    # glissant) : tomber en serie n'est jamais une raison de repartir aussitot.
    CHUTES_AGACE = 3
    FENETRE_CHUTES_S = 600.0
    VEILLE_AGACE_S = 900.0
    DELAI_DANSE_S = 300.0       # une danse au plus toutes les 5 min (initiative rare, pas un juke-box)
    TAQUIN_PROBA = 0.2
    P_TAQUINE = 0.35            # quand une taquinerie est permise, elle remplace la reaction normale 1 fois sur 3
    P_REGARD_MYSTERE = 0.04     # par passage par chill, quand c'est permis
    P_SIGNATURE = 0.01          # par passage par chill : son geste signature (une fois par jour au plus)
    P_ATTENTE = 0.05            # quelqu'un tarde a rentrer : un petit moment d'attente inquiete (toutes les 30 min max)
    P_TOILETTE = 0.5            # apres une impression terminee : il se lisse les plumes
    P_OBSERVER = 0.03           # par passage par chill, en journee : rejoindre son coin d'observation
    CHARGE_S, CHARGE_PCT = 120.0, 2.0     # immobile 2 min et +2 % de batterie : il est sur son chargeur
    P_ZOOMIES = 0.1             # tres en forme et tres eveille : petite folle course (M9 Zoomies)
    P_PICORE = 0.01             # picorer le sol par curiosite (M9 GroundPick)
    P_BALLE = 0.15              # balle vue a 0,3-2 m et de l'energie : il va jouer avec
    P_CACHE_CACHE = 0.005       # initiative rare : il lance lui-meme une partie de cache-cache
    P_GAG = 0.02                # gag spontane (fausse chute, fausse notification) par passage par chill, si permis
    P_POUSSE_BALLE = 0.6        # main vers la balle a ses pieds : il la pousse hors de portee
    P_MIME_VOL = 0.3            # balle a ses pieds, un familier present : il fait mine de la voler
    ESQUIVE_S = 60.0          # "non" theatral avant d'accepter de jouer (registre du jeu seulement, jamais la securite)
    # evenement de la maison -> (etat de reaction, hausse d'eveil)
    REACTIONS_MAISON = {
        "impression_finie": ("celebre", 0.4),
        "impression_echec": ("alerte", 0.7),
        "impression_commencee": ("info", 0.1),
        "alerte": ("alerte", 0.7),
        "info": ("info", 0.2),
        # messager de la maison (pont_ha.py, sections [[appareil]])
        "sonnette": ("sonnette", 0.6),
        "toc_porte": ("sonnette", 0.6),         # on frappe a la porte (entendu par audio.py, sans Home Assistant)
        "machine_finie": ("messager", 0.2),
        "machine_echec": ("alerte", 0.7),
    }
    # Notifications qui meritent d'etre REDITES a un habitant absent a ce moment-la (ROADMAP "Messager physique") : le
    # canard les garde et les rappelle a l'accueil du prochain retour (sans navigation : il ne va pas chercher
    # quelqu'un, il transmet quand on rentre). Une sonnette n'a pas de sens apres coup : pas gardee.
    MESSAGES_A_GARDER = ("impression_finie", "impression_echec", "machine_finie", "machine_echec")
    MESSAGES_MAX = 5

    BONJOUR_FENETRE_H = 4       # le bonjour du matin n'est dit que dans les 4 h qui suivent l'heure prevue

    def __init__(self, client, humeur=None, seed=None, extras=None, heures_calmes=None, horloge=time.localtime,
                 bonjour=None, bonjour_weekend=None):
        self.ctx = Ctx(client)
        self.ctx.extras = extras or {}          # perceptions externes partagees (ex. {"chat": VeilleChat})
        # "Heures calmes" (ROADMAP, table Humains : routine "Heure, HA" -> Nap) : optionnel (None = desactive, le
        # comportement par defaut ne change pas) - un tuple (heure_debut, heure_fin) en heure LOCALE, ex. (23, 7)
        # pour 23h-7h (franchit minuit). Reutilise exactement le chemin "calme_on"/"calme_off" de l'interrupteur
        # HA (meme effet : assis, silencieux, prioritaire) plutot que dupliquer sa logique - un vrai toggle HA
        # pendant la nuit reste respecte jusqu'au prochain changement d'heure (evenement non renvoye si deja a
        # l'etat demande). `horloge` injectable pour les tests (sinon l'heure reelle de la machine).
        self.heures_calmes = heures_calmes
        self.horloge = horloge
        self._nuit_actuelle = None
        # Routine du matin : `bonjour` = heure locale (8 ou (7, 30)) a partir de laquelle le canard dit bonjour, une
        # seule fois par jour, des qu'il est au repos (chill/look) et hors mode calme ; rien apres la fenetre de
        # BONJOUR_FENETRE_H (un "bonjour" a 17h n'a pas de sens). None = desactive (opt-in, comme heures_calmes).
        self.bonjour = (bonjour, 0) if isinstance(bonjour, int) else (tuple(bonjour) if bonjour else None)
        # rythme different le week-end (samedi, dimanche) : autre heure de bonjour si configuree
        self.bonjour_weekend = ((bonjour_weekend, 0) if isinstance(bonjour_weekend, int)
                                else (tuple(bonjour_weekend) if bonjour_weekend else None))
        self._jour_bonjour = None
        self.humeur = humeur or Humeur()
        self.rng = random.Random(seed)
        self.etats = {
            "chill": Chill(), "look": LookAround(), "turn": TurnInPlace(),
            "wander": Wander(), "nap": Nap(),
            "startle": Geste("startle", "surpris", recul=True),
            "curious": Geste("curious", "curieux"),
            # reactions aux notifications de la maison (Home Assistant, voir pont_ha.py)
            "celebre": Geste("celebre", "content", son="greet"),   # impression terminee : tremoussement de joie
            "alerte": Geste("alerte", "surpris", son="alarm"),     # impression ratee, alarme
            "info": Geste("info", "curieux", son="inquire"),       # information a signaler
            "regarde_chat": RegardeChat(),                         # le chat vient d'apparaitre
            "accueil": Accueil(),                                  # un habitant rentre (presence HA)
            "rituel_depart": Geste("rituel_depart", "oui", son="chirp"),  # signe discret au depart, symetrique
            "ecoute": Ecoute(),                                    # conversation vocale en cours (quacksat)
            # vocabulaire M9 (gestes de tete scriptes) : initiatives RARES, voir RARES / _choisit_suivant
            "etirement": Geste("etirement", "etirement", son="coo"),
            "ebouriffe": Geste("ebouriffe", "ebouriffe"),
            "lissage": Geste("lissage", "lissage"),
            "eternuement": Geste("eternuement", "eternuement", son="peck"),
            "jeu_solitaire": JeuSolitaire(),                       # occupation autonome, personne de disponible
            "cherche_attention": RechercheAttention(),             # occupation autonome, humain/chat disponible
            "bonjour": Bonjour(),                                  # routine du matin, une fois par jour
            # messager : "on sonne !" (tete qui se redresse + alarme, puis interrogatif) ; "c'est fini" (signe)
            "sonnette": Sequence("sonnette", [("surpris", "alarm"), ("curieux", "inquire")]),
            "messager": Sequence("messager", [("curieux", "inquire"), ("oui", "chirp")]),
            "main_tendue": MainTendue(),                           # une main tendue devant lui (ToF) : il picore
            "caresse": Caresse(),                                  # on le caresse : roucoulement, tete contre la main
            "soleil": Soleil(),                                    # jeu "1-2-3 soleil" (camera + ToF)
            "va_au_coin": VaAuCoin(),                              # fatigue : rejoindre son coin de sieste
            "va_chargeur": VaAuCoin("va_chargeur", "nap", "se recharger la ou il s'est deja recharge"),
            "va_observer": VaAuCoin("va_observer", "look", "dans son coin d'observation"),
            "taquin": Sequence("taquin", [("non", "inquire")]),    # "non..." puis il joue quand meme
            # reflexes sonores (audio.py)
            "appel": Sequence("appel", [("curieux", "inquire"), ("oui", "greet")]),   # deux claquements : "oui ?"
            "bravo": Sequence("bravo", [("content", "wheee")]),                       # applaudissements
            "danse": Danse(),                                                        # musique : hochements en rythme
            # taquineries, lot A (socle : taquineries.py)
            "feinte_bec": FeinteBec(), "esquive": Esquive(), "faux_endormi": FauxEndormi(),
            "sourde_oreille": SourdeOreille(), "regard_mystere": RegardMystere(), "baillement": Baillement(),
            "dernier_mot": DernierMot(), "fier": Fier(),
            "pousse_balle": PousseBalle(), "mime_vol": MimeVol(), "aspirateur": Aspirateur(),
            "mime_ton": MimeTon(), "compte_eternuements": CompteEternuements(),
            "fausse_chute": FausseChute(), "fausse_notif": FausseNotif(),
            # la maison
            "alarme": AlarmeFumee(), "toupie": Toupie(), "assis_demande": AssisDemande(),
            "autotest": AutoTestReveil(),                                         # diagnostic : premier reveil du jour
            "porte": Porte(),                                                     # dans les bras (M9 "Held")
            "son_bref": Sequence("son_bref", [("curieux", None)]),               # robotd a entendu un son bref
            "salut": Sequence("salut", [("oui", "greet"), ("content", "wheee")]),
            # commandes vocales locales (commandes.py) : reponses en sons de canard uniquement
            "attentif": Sequence("attentif", [("curieux", "chirp")]),            # on l'a appele par son nom
            "hesite": Sequence("hesite", [("curieux", "inquire")]),              # il n'a pas compris
            "compliment": Sequence("compliment", [("fier", "coo")]),             # "bravo" : fierte discrete
            "chaud": Sequence("chaud", [("fatigue", "coo")]),                    # servos chauds : il s'affale
            "remarque": Remarque(),
            "cache_cache": CacheCache(),
            "zoomies": Zoomies(), "picore": Picore(),                            # M9 : trop-plein d'energie, picorer
            "balle": JeuBalle(),                                                 # M9 BallPlay : approche + tir avec vision                                         # il se cache, indices sonores
            "silence_curieux": Sequence("silence_curieux", [("curieux", "inquire")]),   # la maison est trop calme                                              # un objet qui n'etait pas la
            # social
            "signature": Sequence("signature", [("curieux", "coo"), ("fier", "wheee")]),
            "gene": Sequence("gene", [("gene", "peck")]),                     # trebuche devant quelqu'un
            "attente": Sequence("attente", [("curieux", "inquire"), ("lissage", None)]),   # quelqu'un tarde
            "meteo_curieux": Sequence("meteo_curieux", [("curieux", "inquire")]),      # tiens, il pleut
            "meteo_neige": Sequence("meteo_neige", [("curieux", "inquire"), ("content", "wheee")]),
            "meteo_orage": Sequence("meteo_orage", [("surpris", "inquire")]),         # inquiet, puis va se blottir
            # vie de la maison (ROADMAP "Pistes supplementaires", "Actions spontanees vers l'humain")
            "jour_special": Sequence("jour_special", [("content", "wheee"), ("oui", "greet")]),   # calendrier HA
            "baillement_contagieux": BaillementContagieux(),                       # on a baille pres de lui
            "timide": Timide(),                                                    # visiteur inconnu
            "apprivoise": Sequence("apprivoise", [("curieux", "inquire")]),        # la timidite s'est dissipee
            "coup_oeil": CoupOeil(),                                               # mouvement a la peripherie
            "va_repas": VaAuCoin("va_repas", "look", "trainer la ou l'on mange, comme chaque jour a cette heure"),
            "va_compagnie": VaAuCoin("va_compagnie", "compagnie", "tenir compagnie la ou l'on s'occupe de lui"),
            "compagnie": Compagnie(),
        }
        self.etats["taquin"].taquinerie = True
        self.malice = Malice(self.ctx.extras.get("memoire"))
        self.detecteur_approche = DetecteurApproche()
        self.aspirateur_actif = False
        self.meteo = None                       # groupe meteo courant (Home Assistant) : soleil, pluie, neige, orage...
        self.chargeur = None                    # (x, y) odom ou la batterie est deja remontee (session en cours)
        self._charge_ref = None                 # (t, pourcentage, position) depuis le dernier deplacement
        mem = self.ctx.extras.get("memoire")
        donnees = mem.donnees.setdefault("ambiance", {}) if mem is not None and hasattr(mem, "donnees") else None
        self.habitudes = Habitudes(donnees, horloge=self.horloge,   # sauvegarde avec la memoire (memoire.py)
                                   sauver=mem.sauver if donnees is not None and hasattr(mem, "sauver") else None)
        perso = mem.donnees.setdefault("personnalite", {}) if donnees is not None else None
        self.perso = Personnalite(perso, rng=random.Random(seed), sauver=mem.sauver if perso is not None else None)
        self._t_ecoute = None                   # premiere trame : debut de l'ecoute des habitudes sonores
        # auto-surveillance (diagnostic.py) : batterie dans la duree, derive des servos, journal des chutes, auto-test
        self.diagnostic = Diagnostic(mem, mur=self.ctx.extras.get("mur", time.time))
        self.derniere_sante = None              # derniere reponse de robot.health
        self._jour_autotest = None
        self.objet_nouveau = None               # distance (m) devant de l'objet nouvellement remarque
        self.objets_au_sol = []                 # (heure murale, x, y odom) des objets nouveaux remarques : vers HA
        self.presence_suivie = False            # presence initiale lue dans HA : "personne a la maison" a un sens
        self.lumiere = None                     # derniere luminosite mesuree la nuit, maison vide (0..1)
        self.lumiere_oubliee = False
        self._t_lumiere = -1e9
        self.surchauffe = False                 # servos trop chauds (robot.health.motors.max_c)
        self.cpu_chaud = False                  # carte trop chaude (robot.health.cpu_temp_c) : camera en pause
        self.temperatures = {}                  # derniere lecture : {"moteurs": max_c, "cpu": c}
        self._t_sante = -1e9
        self._audio_prec = None                 # derniers compteurs robot.state.audio (patch contrib/)
        self.porte = False                      # dans les bras (safety.picked_up)
        self.ignores, self._t_tentative, self._tentative_jugee = 0, None, False   # demandes d'attention ignorees
        self.bruits = []                        # t_global des bruits forts recents (detonations -> refuge)
        self._jour_signature = None             # geste signature : une fois par jour au plus
        self.eternuements = []                  # t_global des eternuements entendus (serie = moins de 60 s d'ecart)
        self.t_esquive = -1e9                   # derniere main esquivee (la suivante, dans la minute, est acceptee)
        self.t_dernier_accueil = -1e9
        self.chutes = []                        # t_global des dernieres chutes (garde-fou "chat agace")
        self.veille_jusqua = -1.0               # repos force apres une serie de chutes
        self.detecteur_caresse = DetecteurCaresse()
        self.detecteur_main = DetecteurMain()
        self._tete_prec, self._t_tete_change = None, 0.0     # derniere consigne de tete vue, et quand elle a change
        self.messages = []                      # notifications a redire au prochain habitant qui rentre
        self.suivant_force = None               # etat impose pour la prochaine bascule (un etat qui enchaine)
        self._sons_etat = set()                 # sons "une fois" deja joues dans l'etat courant (son_une_fois)
        self.derniere_fois = {}                 # etat rare -> t_global de la derniere fois
        self.mode_calme = False                 # interrupteur "calme" de Home Assistant (regle de vie)
        self.exploration = Exploration()        # memoire des zones visitees (novelty grid du M9)
        self.explo_actif = self.ctx.extras.get("exploration", True)
        self._t_explo = -1.0
        self._derniere_position = None          # derniere position odom connue, pour noter une "zone noire" a la chute
        self._pos_ref_immobile = None           # (x, y) de reference pour detecter l'immobilite reelle
        self._t_ref_immobile = 0.0
        self._batterie_pct = None               # vraie batterie (state["battery"]["percent"]), si connue
        self.courant = self.etats["chill"]
        self.t_etat = 0.0
        self.fin_etat = self.courant.duree(self)
        self.evenements = []
        self.differes = []                      # notifications arrivees pendant une conversation : rejouees apres
        self.journal = []  # (t_global, nom_etat, energie, eveil)
        self.t_global = 0.0
        self.tombe = False
        self.presents = set()                   # habitants actuellement a la maison (presence HA, retour/depart)
        self.derniere_interaction = 0.0         # dernier evenement externe notable (hors bascule calme/ecoute)
        self.discret = False                    # quelqu'un telephone (audio.py) : ni son ni initiative bruyante
        self._t_discret = 0.0
        self.visite = None                      # t_global de l'arrivee d'un visiteur inconnu (timidite)
        self._apprivoise = True
        self._t_sonnette = None                 # derniere sonnette sans retour d'habitant : un visiteur ?
        self.jour_special = None                # (jour de l'annee, nom) : evenement du calendrier HA aujourd'hui
        self._jour_special_vu = set()           # habitants deja salues "jour special" aujourd'hui
        self._repas_faits = set()               # (jour, repas) deja rejoints
        self._rng_babil = random.Random(None if seed is None else seed + 7)   # sons gratuits : hasard a part
        self._t_babil = -1e9
        self._peri_arme = False                 # veille mouvement armee pendant chill (mouvement peripherique)
        self._t_peri_arme = 0.0

    # -- evenements externes (plus tard : micro, camera, HA...) --
    def evenement(self, nom):
        self.evenements.append(nom)

    def _traite_evenements(self):
        while self.evenements:
            nom = self.evenements.pop(0)
            base, _, detail = nom.partition(":")     # "impression_echec:MK4S" -> ("impression_echec", "MK4S")
            if base == "alarme_fumee":
                # securite des habitants : avant le mode calme, la conversation vocale, la sieste ou un jeu
                print(f"[{self.t_global:6.1f}s] ALARME fumee / CO", flush=True)
                self.derniere_interaction = self.t_global
                self._bascule("alarme")
                continue
            if base in ("calme_on", "calme_off"):
                # Regle de vie : interrupteur "calme" (veille, silence, sieste forcee). Prioritaire sur tout.
                actif = base == "calme_on"
                if actif != self.mode_calme:
                    self.mode_calme = actif
                    self.ctx.silence = actif or self.discret
                    print(f"[{self.t_global:6.1f}s] mode calme {'ACTIVE' if actif else 'desactive'}", flush=True)
                    self._bascule("nap" if actif else ("etirement" if self.courant.nom == "nap" else "chill"))
                continue
            # Occupation autonome : tout evenement reel (hors bascule "calme") remet le compteur d'ennui a zero,
            # qu'il soit ou non traite immediatement (differe pendant une conversation, ignore pendant la sieste...).
            self.derniere_interaction = self.t_global
            self.ignores = 0                    # quelqu'un s'est manifeste : le decouragement s'efface
            if base in ("telephone", "telephone_fin"):
                self._discretion(base == "telephone")
                continue
            if base in ("visiteur", "visiteur_fin"):
                self._sur_visiteur(base == "visiteur")
                continue
            if base in ("voix", "intonation", "silence_conversation", "discussion_longue"):
                self._apprend_repas()
                if self._t_sonnette is not None and self.t_global - self._t_sonnette <= self.VISITEUR_APRES_SONNETTE_S:
                    self._t_sonnette = None
                    self._sur_visiteur(True)    # on a sonne, on parle, et aucun habitant n'est rentre : un visiteur
            if base == "jour_special":
                self._sur_jour_special(detail)
                continue
            if base == "compagnie_fin" and self.courant.nom == "va_compagnie":
                self.suivant_force = None       # l'activite est deja finie : il ne va pas s'asseoir pour rien
                self.fin_etat = self.t_etat
                continue
            if base in ("compagnie", "compagnie_fin") and self.courant.nom != "compagnie":
                if base == "compagnie":
                    self._sur_compagnie()
                continue
            if base == "baillement_entendu":
                if (self.courant.nom in ("chill", "look", "wander") and not self.mode_calme
                        and self.t_global - self.derniere_fois.get("baillement_contagieux", -1e9) >= 600.0
                        and self.rng.random() < self.P_BAILLEMENT_CONTAGIEUX):
                    self.derniere_fois["baillement_contagieux"] = self.t_global
                    self._bascule("baillement_contagieux")
                continue
            if base in ("ecoute_on", "ecoute_off"):
                # conversation vocale (satellite Assist) : on se tait ; a la fin, on reprend et on rejoue ce qui attendait
                if base == "ecoute_on" and self.courant.nom != "ecoute":
                    print(f"[{self.t_global:6.1f}s] conversation vocale : le cerveau se tait", flush=True)
                    self._bascule("ecoute")
                elif base == "ecoute_off" and self.courant.nom == "ecoute":
                    print(f"[{self.t_global:6.1f}s] fin de conversation ({len(self.differes)} evenement(s) en attente)", flush=True)
                    self._bascule("nap" if self.mode_calme else "chill")
                continue
            if self.courant.nom == "ecoute" and base != "depart":
                self.differes.append(nom)       # ni son ni geste pendant que quelqu'un parle au canard
                continue
            if base == "presence":
                # etat initial lu dans HA au demarrage (pont_ha.lire_presence_initiale) : ni accueil ni rituel
                qui, _, ou = detail.partition("|")
                (self.presents.add if ou == "home" else self.presents.discard)(qui)
                self.presence_suivie = True
                continue
            if base in ("retour", "depart"):
                # presence d'un habitant (person.* dans HA) : "retour:Nom|absence_s", "depart:Nom"
                qui, _, absence = detail.partition("|")
                mem = self.ctx.extras.get("memoire")
                if base == "depart":
                    self.presents.discard(qui)
                    if mem is not None:
                        mem.depart(qui)
                    # Petit rituel de presence, symetrique de l'accueil au retour (ROADMAP "chantier actif") : un
                    # signe discret et reconnaissable, jamais une "fete" - et jamais pendant la sieste, le calme ou
                    # une conversation en cours (ne jamais interrompre pour un simple depart).
                    if not self.mode_calme and self.courant.nom not in ("nap", "ecoute"):
                        self._bascule("rituel_depart")
                    continue
                self.presents.add(qui)
                self._t_sonnette = None             # c'etait un habitant qui rentrait, pas un visiteur
                if self.visite is not None and self.t_global - self.visite <= 300.0:
                    self._sur_visiteur(False)       # (presence HA en retard sur la sonnette et les voix)
                absence = float(absence) if absence else (mem.absence_s(qui) if mem is not None else None)
                longue = absence is not None and absence >= Accueil.ABSENCE_LONGUE_S
                if self.mode_calme or (self.courant.nom == "nap" and not longue):
                    # calme : jamais de reaction ; sieste : seul un retour apres une longue absence le reveille
                    if mem is not None:
                        mem.rencontre(qui)
                    print(f"[{self.t_global:6.1f}s] {qui} rentre (pas de reaction : "
                          f"{'mode calme' if self.mode_calme else 'sieste'})", flush=True)
                    continue
                self.etats["accueil"].qui, self.etats["accueil"].absence_s = qui, absence
                self.humeur.eveil = min(1.0, self.humeur.eveil + (0.6 if longue else 0.3))
                self._bascule("accueil")
                if self._jour_special_aujourdhui() and qui not in self._jour_special_vu:
                    self._jour_special_vu.add(qui)
                    self.suivant_force = "jour_special"     # c'est un jour special : il le lui dit aussi
                continue
            if base == "sonnette":
                self._t_sonnette = self.t_global
            if base in self.REACTIONS_MAISON:
                # une notification que l'habitant a demandee n'est pas un caprice : elle interrompt la sieste
                etat, eveil = self.REACTIONS_MAISON[base]
                self.humeur.eveil = min(1.0, self.humeur.eveil + eveil)
                if base == "impression_finie" and not self.mode_calme and self.rng.random() < self.P_TOILETTE:
                    self.suivant_force = "lissage"   # toilette apres l'atelier "poussiereux" (ROADMAP)
                if base in self.MESSAGES_A_GARDER and not self.presents:
                    self.messages = (self.messages + [nom])[-self.MESSAGES_MAX:]
                print(f"[{self.t_global:6.1f}s] notification maison : {nom}", flush=True)
                self._bascule(etat)
                continue
            if base in ("stop_taquinerie", "non"):
                # signal "stop" (bouton HA, "non" vocal) : la taquinerie en cours s'arrete net, plus aucune pendant un moment
                self.malice.stop(self)
                self.perso.vit("stop")
                print(f"[{self.t_global:6.1f}s] stop : plus de taquinerie pendant {self.malice.stop_jusqua - self.t_global:.0f} s",
                      flush=True)
                if getattr(self.courant, "taquinerie", False) or self.courant.nom == "fier":
                    self.suivant_force = None        # ex. le jeu qui devait suivre le "non" theatral : annule aussi
                    self._bascule("chill")
                continue
            if base in ("tour_salut", "tour_toupie", "tour_assis") and self.courant.nom != "assis_demande":
                # tours sur demande (boutons HA) : une demande explicite reveille la sieste, mais rien en mode calme
                if not self.mode_calme and self.courant.nom != "alarme":
                    self._bascule({"tour_salut": "salut", "tour_toupie": "toupie", "tour_assis": "assis_demande"}[base])
                continue
            if base == "commande":
                self._sur_commande(detail)
                continue
            if base in ("meteo", "orage"):
                self._sur_meteo("orage" if base == "orage" else detail)
                continue
            sur_evt = getattr(self.courant, "sur_evenement", None)
            if sur_evt is not None and sur_evt(self, base):
                continue                        # l'etat en cours (un jeu) a pris l'evenement pour lui
            if base == "jeu_balle":
                if (not self.mode_calme and self.ctx.extras.get("tof") is not None and not self.surchauffe
                        and self.ctx.extras.get("balle") is not None          # camera locale branchee (canard.py)
                        and self.courant.nom not in ("balle", "nap", "alarme", "porte")):
                    self._bascule("balle")
                continue
            if base == "jeu_cache":
                if not self.mode_calme and self.courant.nom not in ("cache_cache", "nap", "soleil", "alarme", "porte") \
                        and self.ctx.extras.get("tof") is not None:
                    self._lance_cache_cache()
                continue
            if base == "jeu_soleil":
                if self.mode_calme or self.courant.nom in ("soleil", "nap"):
                    continue                    # pas de jeu en mode calme ; pas pendant la sieste (ne pas reveiller)
                if self.ctx.extras.get("mouvement") is None:
                    print(f"[{self.t_global:6.1f}s] 1-2-3 soleil impossible : pas de camera (veille mouvement)", flush=True)
                    continue
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.4)
                if self.rng.random() < self.TAQUIN_PROBA and self.malice.permise(self, "taquin", humain=True):
                    self.suivant_force = "soleil"    # taquinerie : "non..." de la tete, puis il joue quand meme
                    self._bascule("taquin")
                else:
                    self._bascule("soleil")
                continue
            if base in ("caresse", "main") and self._derniere_position is not None:
                # la ou l'on s'occupe de lui : la que l'on viendra tenir compagnie (Compagnie)
                self.exploration.preference(*self._derniere_position, "social", 10.0, self.t_global)
            if base == "caresse":
                if self.courant.nom == "nap" or self.mode_calme:
                    self.ctx.sound("coo")       # caresse pendant le sommeil : un roucoulement, sans se reveiller
                elif self.courant.nom != "caresse":
                    self._bascule("caresse")
                continue
            if self.courant.nom == "nap":
                continue  # ne jamais insister : on dort, l'evenement est perdu
            if nom == "bruit":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.5)
                self.bruits = [t for t in self.bruits if self.t_global - t <= 60.0] + [self.t_global]
                if len(self.bruits) >= 3:        # detonations en serie (petards, orage) : il va se mettre a l'abri
                    coin = self._coin_atteignable()
                    if coin is not None:
                        self.etats["va_au_coin"].cible = coin
                    self.suivant_force = "va_au_coin" if coin is not None else "nap"
                    self.bruits = []
                self._bascule("startle")
            elif nom == "chat":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("regarde_chat" if "chat" in self.ctx.extras else "curious")
            elif base == "appel":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule(self._taquinerie(("faux_endormi", "sourde_oreille"), humain=True) or "appel")
            elif base in ("aspirateur_on", "aspirateur_off"):
                avant, self.aspirateur_actif = self.aspirateur_actif, base == "aspirateur_on"
                if self.aspirateur_actif and not avant and self.courant.nom in ("chill", "look"):
                    self._bascule("curious")             # tiens, le voila : un regard curieux, un peu mefiant
            elif base == "objet_approche":
                asp = self.etats["aspirateur"]
                asp.taquine = bool(self._taquinerie(("barre_aspirateur",), humain=True, proba=0.5))
                self._bascule("aspirateur")
            elif base == "intonation" and detail in ("monte", "descend"):
                if self._taquinerie(("mime_ton",), humain=True):
                    self.etats["mime_ton"].sens = detail
                    self._bascule("mime_ton")
            elif base == "eternuement":
                self.eternuements = [t for t in self.eternuements if self.t_global - t <= 60.0] + [self.t_global]
                n = len(self.eternuements)
                if n == 1:
                    self._bascule("eternuement")         # contagion sincere : il eternue a son tour
                elif self._taquinerie(("compte_eternuements",), humain=True, proba=1.0):
                    self.etats["compte_eternuements"].n = n
                    self._bascule("compte_eternuements")
            elif base == "discussion_longue":
                choix = self._taquinerie(("baillement",), humain=True, proba=1.0)
                if choix:
                    self._bascule(choix)
            elif base == "silence_conversation":
                choix = self._taquinerie(("dernier_mot",), humain=True, proba=0.5)
                if choix and not getattr(self.courant, "taquinerie", False):
                    self._bascule(choix)
            elif base == "objet_nouveau":
                self.ctx.move()
                self._bascule("remarque")
            elif base == "son_bref":
                if self.courant.nom in ("chill", "look"):
                    self._bascule("son_bref")            # un claquement, une porte : il tourne la tete, curieux
            elif base == "voix":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.1)   # on parle : il s'eveille un peu
                self.habitudes.voix(self.t_global)
            elif base == "applaudissements":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("bravo")
            elif base == "musique" and self.t_global - self.derniere_fois.get("danse", -1e9) >= self.DELAI_DANSE_S:
                self.derniere_fois["danse"] = self.t_global
                self.etats["danse"].bpm = int(detail) if detail.isdigit() else 100
                self._bascule("danse")
            elif nom == "main":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.2)
                if self.t_global - self.t_esquive < self.ESQUIVE_S:
                    self.t_esquive = -1e9
                    self.etats["main_tendue"].son_entree = "coo"     # esquivee la fois d'avant : cette fois il accepte
                    self._bascule("main_tendue")
                else:
                    vers_balle = self._main_vers_balle()
                    choix = self._taquinerie(("pousse_balle",), humain=True, proba=self.P_POUSSE_BALLE) if vers_balle else None
                    self._bascule(choix or self._taquinerie(("feinte_bec", "esquive"), humain=True) or "main_tendue")
            elif nom == "personne":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("curious")

    def reste_assis(self):
        """Pendant le mode calme, la veille apres des chutes ou une surchauffe des servos, on ne se releve pas entre
        deux siestes (se relever puis se rasseoir solliciterait justement les servos)."""
        return self.mode_calme or self.t_global < self.veille_jusqua or self.surchauffe

    COIN_DISTANCE = (0.5, 4.0)               # m : plus pres, inutile de bouger ; plus loin, l'odometrie a trop derive

    def _atteignable(self, point, distances):
        """Point (odom) a une distance dans `distances`, capteur de distance branche (on ne marche jamais a l'aveugle)."""
        if self.ctx.extras.get("tof") is None or not (self.ctx.state or {}).get("odom"):
            return False
        p = self.ctx.state["odom"]["position"]
        return distances[0] <= math.hypot(point[0] - p[0], point[1] - p[1]) <= distances[1]

    def _quelqu_un_tarde(self):
        """Un habitant parti depuis plus de 2 h et pas rentre plus d'une heure apres son heure de retour habituelle
        (memoire.py : heure ou on le rencontre le plus souvent)."""
        mem = self.ctx.extras.get("memoire")
        if mem is None or not hasattr(mem, "donnees"):
            return False
        heure = self.horloge().tm_hour
        for qui in mem.donnees.get("etres", {}):
            if qui == "chat" or qui in self.presents:
                continue
            absence, habituelle = mem.absence_s(qui), mem.heure_habituelle(qui)
            if absence is not None and absence > 7200 and habituelle is not None and 1 <= (heure - habituelle) % 24 <= 3:
                return True
        return False

    def _coin_atteignable(self):
        """Coin de sieste appris (exploration.py), s'il est a une distance raisonnable et que le capteur de distance
        est la (on ne marche jamais a l'aveugle)."""
        if self.ctx.extras.get("tof") is None or not (self.ctx.state or {}).get("odom"):
            return None
        coin = self.exploration.coin_favori("nap", self.t_global)
        if coin is None:
            return None
        p = self.ctx.state["odom"]["position"]
        d = math.hypot(coin[0] - p[0], coin[1] - p[1])
        return coin if self.COIN_DISTANCE[0] <= d <= self.COIN_DISTANCE[1] else None

    def _main_vers_balle(self):
        """La main tendue vise-t-elle la balle posee devant le canard ? (main a moins de 15 cm de la balle, balle a
        portee de pied : 6 a 25 cm devant)."""
        veille, m = self.ctx.extras.get("balle"), self.detecteur_main.main
        b = veille.position() if veille is not None else None
        if b is None or m is None:
            return False
        return 0.06 <= b[0] <= 0.25 and abs(b[1]) <= 0.10 and math.hypot(m[1] - b[0], m[2] - b[1]) <= 0.15

    def _sur_commande(self, quoi):
        """Commande vocale reconnue SUR le canard (commandes.py). Il ne repond jamais en mots : sons de canard et gestes.
        Rien en mode calme sauf "reveille-toi" ; la sieste n'est interrompue que par "reveille-toi"."""
        if quoi == "reveil":
            if self.mode_calme:
                self.evenements.insert(0, "calme_off")
            elif self.courant.nom == "nap":
                self._bascule("etirement")
            return
        if self.mode_calme or self.courant.nom in ("nap", "alarme", "porte"):
            return
        if self.courant.nom == "cache_cache" and quoi in ("trouve", "stop", "ecoute"):
            jeu = self.etats["cache_cache"]
            if jeu.phase == "cache":
                jeu._trouve(self, self.t_etat)   # "trouve !" (ou son nom, ou stop) : la partie est finie
            return
        if quoi == "stop":
            self.evenements[0:0] = ["non", "fin_jeu"]      # coupe une taquinerie, termine un jeu
            if self.courant.nom == "assis_demande":
                self.fin_etat = self.t_etat
        elif quoi == "assis" and not self.ctx.sitting:
            self._bascule("assis_demande")
        elif quoi == "debout" and self.courant.nom == "assis_demande":
            self.fin_etat = self.t_etat
        elif quoi == "bravo":
            self.humeur.eveil = min(1.0, self.humeur.eveil + 0.1)
            self._bascule("compliment")
        elif quoi == "danse":
            self.etats["danse"].bpm = 100
            self._bascule("danse")
        elif quoi == "ecoute" and self.courant.nom in ("chill", "look", "jeu_solitaire"):
            self._bascule("attentif")
        elif quoi == "pas_compris":
            self._bascule("hesite")

    METEO = {"lightning": "orage", "lightning-rainy": "orage", "hail": "orage", "exceptional": "orage",
             "rainy": "pluie", "pouring": "pluie", "snowy-rainy": "pluie", "snowy": "neige",
             "sunny": "soleil", "clear-night": "clair", "partlycloudy": "nuageux", "cloudy": "nuageux",
             "fog": "nuageux", "windy": "nuageux", "windy-variant": "nuageux", "orage": "orage"}
    MARCHE_PAR_METEO = {"orage": 0.3, "pluie": 0.6, "neige": 0.8, "soleil": 1.3}   # envie de se promener

    def _sur_meteo(self, etat):
        """Ne reagit qu'au CHANGEMENT (le debut de la pluie, pas chaque instant ou elle tombe)."""
        groupe = self.METEO.get(etat)
        if groupe is None or groupe == self.meteo:
            return
        self.meteo = groupe
        if self.mode_calme or self.courant.nom in ("nap", "ecoute", "alarme"):
            return
        if groupe == "orage":
            # inquiet, puis il va se blottir dans son coin de sieste s'il le connait (sinon sieste sur place)
            coin = self._coin_atteignable()
            if coin is not None:
                self.etats["va_au_coin"].cible = coin
                self.suivant_force = "va_au_coin"
            else:
                self.suivant_force = "nap"
            self._bascule("meteo_orage")
        elif groupe == "neige":
            self._bascule("meteo_neige")
        elif groupe == "pluie":
            self._bascule("meteo_curieux")

    # etat dans lequel il entre -> experience qui faconne sa personnalite (personnalite.py)
    EXPERIENCES_PAR_ETAT = {"caresse": "caresse", "accueil": "accueil", "remarque": "remarque", "wander": "promenade",
                            "startle": "sursaut", "soleil": "jeu"}

    def _prepare_cache_cache(self):
        """Ou se cacher : un coin appris (sieste ou observation) a 1-4 m, sinon droit devant."""
        coin = None
        for activite in ("nap", "chill"):
            c = self.exploration.coin_favori(activite, self.t_global)
            if c is not None and self._atteignable(c, (1.0, 4.0)):
                coin = c
                break
        self.etats["cache_cache"].cible = coin

    def _lance_cache_cache(self):
        self._prepare_cache_cache()
        self._bascule("cache_cache")

    def son_une_fois(self, cle, tag):
        """Joue `tag` au plus UNE fois par entree dans l'etat courant (cle libre) : les etats l'appellent des qu'un
        instant est depasse, quelle que soit la cadence des trames (10 a 50 Hz), au lieu d'une fenetre de temps qui
        sonnait 2-3 fois a 50 Hz et jamais a 10 Hz."""
        if cle not in self._sons_etat:
            self._sons_etat.add(cle)
            self.ctx.sound(tag)

    def _taquinerie(self, noms, humain=False, proba=None):
        """Une taquinerie a la place de la reaction normale ? -> son nom, ou None (budget, familiarite, stop, hasard)."""
        p = (self.P_TAQUINE if proba is None else proba) * self.perso.envie_taquiner()
        if self.rng.random() >= min(1.0, p):
            return None
        permises = [n for n in noms if self.malice.permise(self, n, humain=humain)]
        return self.rng.choice(permises) if permises else None

    def _choisit_suivant(self):
        force = getattr(self, "suivant_force", None)
        if force:
            self.suivant_force = None
            return force
        if self.surchauffe:
            return "nap"                        # servos trop chauds : repos assis, jamais de marche, jusqu'a refroidir
        if self.mode_calme or self.t_global < self.veille_jusqua:
            return "nap"                        # sieste prolongee, assis : interrupteur calme, ou veille apres des chutes
        h = self.humeur
        batterie_basse = self._batterie_pct is not None and self._batterie_pct < self.BATTERIE_BASSE_PCT
        if h.energie < self.SEUIL_SIESTE or batterie_basse:
            # fatigue "jouee" OU vraie batterie basse : meme reponse (repos) - dans son coin favori s'il est connu et
            # pas trop loin (sauf batterie basse : on ne gaspille pas les derniers pourcents a marcher)
            if self.courant.nom not in ("nap", "va_au_coin", "va_chargeur"):
                if batterie_basse:
                    # batterie basse : seulement vers le chargeur appris, jamais pour un simple coin prefere
                    if self.chargeur is not None and self._atteignable(self.chargeur, (0.3, 4.0)):
                        self.etats["va_chargeur"].cible = self.chargeur
                        return "va_chargeur"
                else:
                    coin = self._coin_atteignable()
                    if coin is not None:
                        self.etats["va_au_coin"].cible = coin
                        return "va_au_coin"
            return "nap"
        if self.discret:
            return self.rng.choice(("chill", "chill", "look"))   # quelqu'un telephone : il reste tranquille, sans bruit
        if self.courant.nom == "nap":
            self.derniere_fois["etirement"] = self.t_global
            return "etirement"                  # on s'etire en se reveillant
        if getattr(self.courant, "taquinerie", False):
            k = self.malice.fierte(self.courant.nom)
            if k > 0.0:
                self.etats["fier"].k = k             # running gag : petit air fier, qui grandit avec l'historique
                return "fier"
        if self.courant.nom != "chill":
            return "chill"
        # Occupation autonome / recherche d'attention : rien ne s'est passe depuis longtemps -> le canard ne reste
        # pas simplement passif. Priorite sur les initiatives habituelles (look/turn/wander/RARES), mais seulement
        # si le delai minimal est passe (ne jamais insister).
        sans_interaction = self.t_global - self.derniere_interaction
        depuis_ennui = self.t_global - self.derniere_fois.get("ennui", -1e9)
        if (self._t_tentative is not None and not self._tentative_jugee
                and self.t_global - self._t_tentative >= 60.0            # on lui a laisse une minute pour repondre
                and self.derniere_interaction < self._t_tentative):
            self.ignores += 1                   # sa derniere demande d'attention est restee sans reponse
            self.perso.vit("ignore")
            self._tentative_jugee = True
        delai = self.DELAI_ENNUI_S * 2 ** min(self.ignores, 3)      # decouragement progressif : il demande moins
        if sans_interaction >= self.SEUIL_ENNUI_S * self.perso.patience_seul() and depuis_ennui >= delai:
            self.derniere_fois["ennui"] = self.t_global
            chat = self.ctx.extras.get("chat")
            chat_visible = chat is not None and getattr(chat.suivi, "visible", False)
            if (self.presents or chat_visible) and self.ignores < 2:
                self.etats["cherche_attention"].cible = "humain" if self.presents else "chat"
                self._t_tentative, self._tentative_jugee = self.t_global, False
                return "cherche_attention"
            return "jeu_solitaire"              # personne, ou ignore deux fois de suite : il s'occupe seul
        if self.rng.random() < self.P_REGARD_MYSTERE and self.malice.permise(self, "regard_mystere"):
            return "regard_mystere"
        h_loc = self.horloge()
        if (self.presents and getattr(h_loc, "tm_yday", None) != self._jour_signature
                and 9 <= h_loc.tm_hour < 21 and self.rng.random() < self.P_SIGNATURE):
            self._jour_signature = getattr(h_loc, "tm_yday", None)
            return "signature"                  # son geste a lui, rare : une fois par jour au plus
        if self._t_ecoute is not None and self.presents and self.ctx.extras.get("tof") is not None \
                and self.t_global - self.derniere_fois.get("silence", -1e9) >= 7200.0 \
                and self.habitudes.silence_inhabituel(self.t_global, self._t_ecoute):
            self.derniere_fois["silence"] = self.t_global
            self.suivant_force = "wander"       # que se passe-t-il ? un petit tour pour aller voir
            return "silence_curieux"
        timide = self.timidite()
        if timide > 0.0:
            # visiteur inconnu : timide de moins en moins souvent au fil de la visite ; sinon il reste en retrait (ni
            # promenade, ni jeu, ni coin d'observation devant quelqu'un qu'il ne connait pas)
            return "timide" if self.rng.random() < 0.7 * timide else self.rng.choice(("chill", "look"))
        if self.visite is not None and timide == 0.0 and not self._apprivoise:
            self._apprivoise = True
            return "apprivoise"                 # la timidite s'est dissipee : un "inquire" curieux
        repas = self._repas_maintenant()
        if repas is not None:
            return repas
        if self.rng.random() < self.P_ATTENTE and self.t_global - self.derniere_fois.get("attente", -1e9) >= 1800.0:
            if self._quelqu_un_tarde():
                self.derniere_fois["attente"] = self.t_global
                return "attente"
        if self.rng.random() < self.P_OBSERVER and h.energie > 0.4 and 9 <= self.horloge().tm_hour < 21:
            coin = self.exploration.coin_favori("chill", self.t_global)
            if coin is not None and self._atteignable(coin, (1.0, 4.0)):
                self.etats["va_observer"].cible = coin       # en journee : il va regarder la piece depuis son coin
                return "va_observer"
        if (self.presents and self.ctx.extras.get("tof") is not None and h.energie > 0.5
                and 9 <= self.horloge().tm_hour < 21 and self.rng.random() < self.P_CACHE_CACHE * self.perso.envie_taquiner()
                and self.malice.permise(self, "cache_cache")):
            self.malice.noter(self, "cache_cache")      # initiative de jeu : comptee dans le budget de malice
            self._prepare_cache_cache()
            return "cache_cache"
        chat = self.ctx.extras.get("chat")
        chat_la = chat is not None and getattr(getattr(chat, "suivi", None), "visible", False)
        if (h.energie > 0.85 and h.eveil > 0.5 and not chat_la and not self.surchauffe and timide == 0.0
                and self.ctx.extras.get("tof") is not None and self.horloge().tm_hour in range(8, 22)
                and self.rng.random() < self.P_ZOOMIES * (1.5 - self.perso.trait("prudence")) * self.vivacite()):
            return "zoomies"                    # trop-plein d'energie
        if self.rng.random() < self.P_PICORE:
            return "picore"
        veille_balle = self.ctx.extras.get("balle")
        vue = veille_balle.position() if veille_balle is not None else None
        if (vue is not None and 0.3 <= math.hypot(*vue) <= 2.0 and h.energie > 0.5 and not self.surchauffe
                and self.ctx.extras.get("tof") is not None and self.rng.random() < self.P_BALLE * self.perso.envie_promenade()):
            return "balle"                      # il voit sa balle, en forme : il va jouer avec (seul ou pas)
        if self.rng.random() < self.P_GAG * self.perso.envie_taquiner():
            chat = self.ctx.extras.get("chat")
            gags = [g for g in ("fausse_chute", "fausse_notif") if self.malice.permise(self, g)
                    and not (g == "fausse_chute" and (h.energie < 0.5
                             or (chat is not None and getattr(chat.suivi, "visible", False))))]
            if gags:
                return self.rng.choice(gags)
        veille_balle = self.ctx.extras.get("balle")
        b = veille_balle.position() if veille_balle is not None else None
        if (b is not None and 0.06 <= b[0] <= 0.25 and abs(b[1]) <= 0.10 and self.rng.random() < self.P_MIME_VOL
                and self.malice.permise(self, "mime_vol")):
            return "mime_vol"
        poids = {"look": 0.4, "turn": 0.2 + 0.3 * h.energie,
                 "wander": ((0.15 + 0.4 * h.energie * (0.5 + h.eveil)) * self.MARCHE_PAR_METEO.get(self.meteo, 1.0)
                            * self.perso.envie_promenade())}
        # Initiative rare et surprenante (principe Pollen : un duo surprise est un plaisir, un juke-box non) :
        # faible probabilite, et jamais deux fois le meme geste en moins de DELAI_RARE secondes.
        for nom, p in self.RARES.items():
            if self.t_global - self.derniere_fois.get(nom, -1e9) >= self.DELAI_RARE:
                poids[nom] = p
        noms = list(poids)
        return self.rng.choices(noms, weights=[poids[n] for n in noms])[0]

    def _bascule(self, nom):
        if self.courant.nom == "ecoute" and nom != "ecoute" and self.differes:
            self.evenements.extend(self.differes)      # fin de conversation (ou delai depasse) : on rejoue ce qui attendait
            self.differes = []
        if nom in self.RARES:
            self.derniere_fois[nom] = self.t_global
        self.courant.sort(self)
        self._desarme_peripherie()              # avant l'entree : un jeu peut armer la veille mouvement pour lui
        if nom == "accueil":
            self.t_dernier_accueil = self.t_global
        if getattr(self.etats[nom], "taquinerie", False):
            self.malice.noter(self, nom)
            self.perso.vit("taquinerie")
        experience = self.EXPERIENCES_PAR_ETAT.get(nom)
        if experience:
            self.perso.vit(experience)
        self.courant = self.etats[nom]
        self._sons_etat = set()
        self.courant.entre(self)
        self.t_etat = 0.0
        self.fin_etat = self.courant.duree(self)
        self.journal.append((round(self.t_global, 1), nom,
                             round(self.humeur.energie, 2), round(self.humeur.eveil, 2)))
        print(f"[{self.t_global:6.1f}s] -> {nom:8s} energie={self.humeur.energie:.2f} "
              f"eveil={self.humeur.eveil:.2f}", flush=True)

    REPOS_MAIN = ("chill", "main_tendue")    # canard immobile, tete au repos : une main peut lui etre tendue
    TETE_STABLE_S = 1.0                      # la tete doit etre immobile depuis 1 s (sinon un meuble "apparait")

    def _surveille_main(self, state):
        """Main tendue (main_tendue.py) : seulement quand le canard est immobile - en marchant, tout ce dont il
        s'approche "apparait" devant lui. Jamais si le chat est la (une patte n'est pas une main, et pas de geste vif
        pres du chat : garde-fou de la ROADMAP)."""
        tof = self.ctx.extras.get("tof")
        if tof is None or not hasattr(tof, "points"):
            return
        if self.courant.nom == "aspirateur":
            self.detecteur_approche.mise_a_jour(tof.points(state), self.t_global)   # distance suivie, sans evenement
            return
        tete = getattr(self.ctx, "tete_cmd", None)
        if tete != getattr(self, "_tete_prec", None):
            self._tete_prec, self._t_tete_change = tete, self.t_global
        en_suivi = self.courant.nom == "main_tendue"     # la tete suit la main : on continue de la localiser
        if (self.courant.nom not in self.REPOS_MAIN or self.mode_calme
                or (not en_suivi and self.t_global - self._t_tete_change < self.TETE_STABLE_S)):
            self.detecteur_main.reinitialiser()
            self.detecteur_approche.reinitialiser()
            return
        points = tof.points(state)
        if self.aspirateur_actif and not en_suivi:
            for e in self.detecteur_approche.mise_a_jour(points, self.t_global):
                self.evenement(e)
        evts = self.detecteur_main.mise_a_jour(points, self.t_global)
        chat = self.ctx.extras.get("chat")
        if chat is not None and getattr(getattr(chat, "suivi", None), "visible", False):
            return
        if self.courant.nom != "main_tendue":
            for e in evts:
                self.evenement(e)

    SANTE_S = 30.0                      # robot.health toutes les 30 s
    MOTEURS_CHAUD_C, MOTEURS_OK_C = 60.0, 50.0   # XL330 : coupure vers 70 degres ; hysteresis pour ne pas osciller
    CPU_CHAUD_C, CPU_OK_C = 85.0, 75.0

    def _verifie_sante(self):
        """Auto-preservation thermique (ROADMAP) : servos chauds -> repos assis (et il halete) ; carte chaude -> la veille
        camera de la balle se met en pause. Lu dans robot.health (robotd), toutes les SANTE_S."""
        if self.t_global - self._t_sante < self.SANTE_S:
            return
        self._t_sante = self.t_global
        sante = self.lit_sante()
        if sante is None:
            return
        self.diagnostic.servos.note_plus_chaud((sante.get("motors") or {}).get("hottest"))
        moteurs = (sante.get("motors") or {}).get("max_c")
        cpu = sante.get("cpu_temp_c")
        self.temperatures = {"moteurs": moteurs, "cpu": cpu}
        if moteurs is not None:
            if not self.surchauffe and moteurs >= self.MOTEURS_CHAUD_C:
                self.surchauffe = True
                print(f"[{self.t_global:6.1f}s] servos chauds ({moteurs:.0f} C, {sante['motors'].get('hottest')}) : "
                      "repos jusqu'a refroidir", flush=True)
                if self.courant.nom not in ("nap", "alarme", "porte"):
                    self.suivant_force = "nap"
                    self._bascule("chaud")
            elif self.surchauffe and moteurs <= self.MOTEURS_OK_C:
                self.surchauffe = False
                print(f"[{self.t_global:6.1f}s] servos refroidis ({moteurs:.0f} C)", flush=True)
        if cpu is not None:
            if not self.cpu_chaud and cpu >= self.CPU_CHAUD_C:
                self.cpu_chaud = True
            elif self.cpu_chaud and cpu <= self.CPU_OK_C:
                self.cpu_chaud = False
            veille = self.ctx.extras.get("balle")
            if veille is not None:
                veille.pause = self.cpu_chaud

    P_BAILLEMENT_CONTAGIEUX = 0.6
    VISITEUR_APRES_SONNETTE_S = 180.0
    TIMIDE_S = 1200.0                   # la timidite se dissipe en 20 min de visite
    DISCRET_MAX_S = 3600.0              # garde-fou : un "telephone_fin" perdu ne le rend pas muet pour toujours
    BABIL_MOYEN_S = 900.0               # un petit son gratuit toutes les ~15 min au repos
    PERI_DELAI_S = 300.0
    REPAS_AVANT_MIN, REPAS_APRES_MIN = 10, 30

    def _discretion(self, on):
        """Quelqu'un telephone (audio.py) : il se tait et ne lance rien de bruyant ; fin au "telephone_fin"."""
        if on == self.discret:
            return
        self.discret, self._t_discret = on, self.t_global
        if self.courant.nom != "alarme":        # l'alarme incendie parle quoi qu'il arrive (AlarmeFumee.sort recale)
            self.ctx.silence = on or self.mode_calme
        print(f"[{self.t_global:6.1f}s] {'quelqu un telephone : discret' if on else 'fin de l appel'}", flush=True)
        if on and self.courant.nom not in ("chill", "look", "nap", "alarme", "porte", "compagnie"):
            self._bascule("chill")

    def _sur_visiteur(self, arrive):
        if arrive and (self.visite is None or self.t_global - self.visite > self.TIMIDE_S):
            self.visite, self._apprivoise = self.t_global, False
            print(f"[{self.t_global:6.1f}s] un visiteur inconnu : timide", flush=True)
        elif not arrive:
            self.visite, self._apprivoise = None, True

    def timidite(self):
        """1 a l'arrivee d'un visiteur inconnu, 0 au bout de TIMIDE_S."""
        if self.visite is None:
            return 0.0
        return max(0.0, 1.0 - (self.t_global - self.visite) / self.TIMIDE_S)

    def _jour_special_aujourdhui(self):
        return self.jour_special is not None and self.jour_special[0] == getattr(self.horloge(), "tm_yday", None)

    def _sur_jour_special(self, nom):
        """Calendrier HA du foyer (pont_ha, type "calendrier") : un signe reconnaissable, une fois par jour, puis a
        chaque habitant qui rentre ce jour-la. Pas de fete scriptee lourde."""
        jour = getattr(self.horloge(), "tm_yday", None)
        if self.jour_special is not None and self.jour_special[0] == jour:
            return
        self.jour_special, self._jour_special_vu = (jour, nom), set()
        print(f"[{self.t_global:6.1f}s] jour special : {nom}", flush=True)
        self._jour_special_a_dire = True        # dit au premier moment de repos, pas avant 8 h (evenement a 00:00)

    def _verifie_jour_special(self):
        if (not getattr(self, "_jour_special_a_dire", False) or not self._jour_special_aujourdhui()
                or self.horloge().tm_hour < 8 or self.mode_calme or self.discret
                or self.courant.nom not in ("chill", "look")):
            return
        self._jour_special_a_dire = False
        self._jour_special_vu |= set(self.presents)
        self._bascule("jour_special")

    def _sur_compagnie(self):
        """Quelqu'un est pris par une longue activite immobile (declencheur HA, ex. "bureau occupe depuis 1 h") : il
        va se poser la ou l'on s'occupe le plus de lui, s'il le connait et peut y aller."""
        batterie_basse = self._batterie_pct is not None and self._batterie_pct < self.BATTERIE_BASSE_PCT
        if (self.mode_calme or self.discret or self.reste_assis() or batterie_basse
                or self.humeur.energie < self.SEUIL_SIESTE
                or self.courant.nom not in ("chill", "look", "wander", "jeu_solitaire", "cherche_attention")):
            return                              # seulement depuis le repos ou une occupation libre : jamais un detour
        coin = self.exploration.coin_favori("social", self.t_global)
        if coin is None or self.ctx.extras.get("tof") is None:
            return
        if self._atteignable(coin, (0.0, 0.5)):
            self._bascule("compagnie")
        elif self._atteignable(coin, (0.5, 4.0)):
            self.etats["va_compagnie"].cible = coin
            self._bascule("va_compagnie")

    def _repas_horaires(self):
        return [(r, 0) if isinstance(r, int) else tuple(r) for r in (self.ctx.extras.get("repas") or ())]

    def _proche_repas(self, avant, apres):
        h = self.horloge()
        m = h.tm_hour * 60 + getattr(h, "tm_min", 0)
        for r in self._repas_horaires():
            if -avant <= m - (r[0] * 60 + r[1]) <= apres:
                return r
        return None

    def _apprend_repas(self):
        """Autour des repas (+-45 min), on parle : il note ou il se trouve. A la longue, la case la plus "repas" est la
        piece ou l'on mange - une routine apprise par habitude, pas un point programme."""
        if self._derniere_position is not None and self._proche_repas(45, 45) is not None:
            self.exploration.preference(*self._derniere_position, "repas", 5.0, self.t_global)

    def _repas_maintenant(self):
        r = self._proche_repas(self.REPAS_AVANT_MIN, self.REPAS_APRES_MIN)
        cle = (getattr(self.horloge(), "tm_yday", None), r)
        if (r is None or cle in self._repas_faits or not self.presents or self.humeur.energie < 0.3
                or self.ctx.extras.get("tof") is None):
            return None
        self._repas_faits = {c for c in self._repas_faits if c[0] == cle[0]} | {cle}   # aujourd'hui seulement
        coin = self.exploration.coin_favori("repas", self.t_global)
        if coin is None or not self._atteignable(coin, (0.5, 4.0)):
            return None
        self.etats["va_repas"].cible = coin
        return "va_repas"

    def _babille(self, dt):
        """Vocalisations gratuites (ROADMAP) : de temps en temps, au repos, un petit son sans raison."""
        if (self.courant.nom not in ("chill", "look", "wander") or getattr(self.ctx, "silence", False) or self.discret
                or self.timidite() > 0.0 or self.t_global - self._t_babil < 180.0):
            return
        if self._rng_babil.random() < dt * self.vivacite() / self.BABIL_MOYEN_S:
            self._t_babil = self.t_global
            self.ctx.sound(self._rng_babil.choice(("coo", "chirp", "chirp", "peck")))

    def _surveille_peripherie(self):
        """Pendant chill (tete immobile), la veille mouvement tourne doucement ; un mouvement AU BORD de l'image (petite
        tache : pas son propre mouvement, qui fait bouger toute l'image) -> un coup d'oeil de ce cote."""
        veille = self.ctx.extras.get("mouvement")
        if veille is None or not hasattr(veille, "dernier_centre"):
            return
        if (self.courant.nom != "chill" or self.t_etat < 1.5 or self.mode_calme or self.discret or self.cpu_chaud
                or self.t_global - self.derniere_fois.get("coup_oeil", -1e9) < self.PERI_DELAI_S):
            self._desarme_peripherie()
            return
        if not self._peri_arme:
            veille.armer(periode_s=0.3)
            self._peri_arme, self._t_peri_arme = True, self.t_global
            return
        c = veille.dernier_centre
        if c is None or self.t_global - self._t_peri_arme < 1.0:
            return
        _, x, fraction = c
        if (x < 0.2 or x > 0.8) and fraction < 0.05:
            self._desarme_peripherie()
            self.derniere_fois["coup_oeil"] = self.t_global
            self.etats["coup_oeil"].lacet = 0.5 if x < 0.5 else -0.5   # image : gauche = sa gauche (lacet positif)
            self._bascule("coup_oeil")

    def _desarme_peripherie(self):
        if self._peri_arme:
            self._peri_arme = False
            veille = self.ctx.extras.get("mouvement")
            if veille is not None:
                veille.desarmer()

    LUMIERE_PERIODE_S = 600.0
    LUMIERE_SEUIL = 0.25                # luminosite moyenne au-dessus : piece eclairee (camera, a etalonner)
    NUIT = (21, 7)                      # heures ou une piece eclairee sans personne est une lumiere oubliee

    def _verifie_lumiere(self):
        """Lumiere oubliee (ROADMAP "Capteurs d'etat par vision") : la nuit, maison vide d'apres HA, la piece ou il se
        trouve est-elle eclairee ? Mesure dans un fil (requete HTTP de la camera locale), toutes les 10 min, publiee
        dans HA (binary_sensor.microduck_lumiere_oubliee) - a HA de decider quoi en faire. Rien ne quitte le canard
        qu'un oui/non et un nombre."""
        mesure = self.ctx.extras.get("luminosite")
        if mesure is None or self.t_global - self._t_lumiere < self.LUMIERE_PERIODE_S:
            return
        self._t_lumiere = self.t_global
        h = self.horloge().tm_hour
        nuit = h >= self.NUIT[0] or h < self.NUIT[1]
        if not (nuit and self.presence_suivie and not self.presents):
            self.lumiere_oubliee = False
            return

        def lire():
            try:
                self.lumiere = float(mesure())
            except Exception:
                return
            oubliee = self.lumiere >= self.LUMIERE_SEUIL
            if oubliee and not self.lumiere_oubliee:
                print(f"[{self.t_global:6.1f}s] lumiere allumee, personne a la maison ({self.lumiere:.2f})", flush=True)
            self.lumiere_oubliee = oubliee
        if self.ctx.extras.get("luminosite_synchrone"):
            lire()                              # tests
        else:
            threading.Thread(target=lire, daemon=True).start()

    # Rythme circadien reel (ROADMAP "Pistes supplementaires") : vivacite selon l'heure LOCALE - endormi la nuit, creux
    # apres le dejeuner, plus vif en fin d'apres-midi, qui se calme seul le soir sans mode calme. Opt-in
    # (extras["circadien"], active par canard.py) : sans lui, vivacite = 1 et rien ne change.
    CIRCADIEN = ((0, 0.55), (6, 0.6), (8, 0.9), (12, 1.0), (14, 0.9), (17, 1.15), (20, 1.0), (22, 0.7), (24, 0.55))

    def vivacite(self):
        if not self.ctx.extras.get("circadien"):
            return 1.0
        h = self.horloge()
        x = h.tm_hour + getattr(h, "tm_min", 0) / 60.0
        for (h0, v0), (h1, v1) in zip(self.CIRCADIEN, self.CIRCADIEN[1:]):
            if h0 <= x <= h1:
                return v0 + (v1 - v0) * (x - h0) / (h1 - h0)
        return 1.0

    def lit_sante(self):
        """robot.health (robotd) -> dict, ou None si pas de reponse."""
        try:
            r = self.ctx.client.request("robot.health", {})
        except Exception:
            return None
        sante = (r or {}).get("result") if isinstance(r, dict) else None
        self.derniere_sante = sante if isinstance(sante, dict) else None
        return self.derniere_sante

    def _note_diagnostic(self, state, pct):
        if pct is not None:
            self.diagnostic.batterie.note(self.diagnostic.mur(), pct)
        # servos au repos debout : chill (ni marche ni geste de tete), politique stand, apres 2 s de stabilisation
        if self.courant.nom == "chill" and self.t_etat >= 2.0 and state.get("policy") == "stand" and not self.ctx.sitting:
            h = self.horloge()
            jour = f"{getattr(h, 'tm_year', 0)}-{getattr(h, 'tm_yday', 0):03d}"
            self.diagnostic.servos.note_repos(jour, state.get("joints"), state.get("targets"), state.get("currents_ma"))

    def _verifie_autotest(self):
        """Une fois par jour, au premier moment de repos apres le demarrage (opt-in : extras["autotest"], canard.py)."""
        jour = getattr(self.horloge(), "tm_yday", None)
        if (jour == self._jour_autotest or self.t_global < 20.0 or self.mode_calme
                or self.horloge().tm_hour < 6 or self.courant.nom not in ("chill", "look")):
            return
        self._jour_autotest = jour
        self._bascule("autotest")

    def _surveille_robotd(self, state):
        """Ce que robotd sait deja : la tete entendue par son micro (robot.state.audio : compteurs, voir
        contrib/robotd-audio-state.patch) et le canard pris dans les bras (safety.picked_up)."""
        a = state.get("audio")
        if a:
            prec, self._audio_prec = self._audio_prec, a
            if prec is not None:
                if a.get("pettings", 0) > prec.get("pettings", 0):
                    self.evenement("caresse")
                if a.get("noises", 0) > prec.get("noises", 0):
                    self.evenement("son_bref")
                if a.get("voices", 0) > prec.get("voices", 0):
                    self.evenement("voix")
        porte = bool((state.get("safety") or {}).get("picked_up"))
        if porte != self.porte:
            self.porte = porte
            if porte:
                print(f"[{self.t_global:6.1f}s] pris dans les bras", flush=True)
                self._bascule("porte")
            elif self.courant.nom == "porte":
                print(f"[{self.t_global:6.1f}s] repose", flush=True)
                self._bascule("ebouriffe" if not self.mode_calme else "nap")

    def _traite_evenements_porte(self):
        """Dans les bras : seules l'alarme et une caresse (un roucoulement) comptent ; le reste attend."""
        garde = []
        for nom in self.evenements:
            if nom.startswith("alarme_fumee"):
                self.ctx.silence = False
                self.ctx.sound("alarm")
                self.ctx.silence = self.mode_calme or self.discret
            elif nom == "caresse":
                self.ctx.sound("coo")
                self.derniere_interaction = self.t_global
            else:
                garde.append(nom)
        self.evenements = garde

    def _surveille_caresse(self, state):
        joints = state.get("joints")
        if not joints or len(joints) < 9:
            return
        immobile = self.courant.nom == "chill" or (     # sieste : pas pendant qu'il s'assoit ni qu'il se releve
            self.courant.nom == "nap" and 6.0 <= self.t_etat < self.fin_etat - 4.0)
        courants = state.get("currents_ma")
        courants = courants[5:9] if courants and len(courants) >= 9 else None
        for e in self.detecteur_caresse.mise_a_jour(self.t_global, getattr(self.ctx, "tete_cmd", None),
                                                    joints[5:9], immobile, courants):
            self.evenement(e)

    def _apprend_chargeur(self, pct, position):
        """La batterie remonte alors qu'il ne bouge pas : il est sur son chargeur -> il retient cet endroit (repere de
        l'odometrie de la session) pour y retourner sur batterie basse."""
        pos = (position[0], position[1])
        ref = self._charge_ref
        if ref is None or math.hypot(pos[0] - ref[2][0], pos[1] - ref[2][1]) > 0.1 or pct < ref[1] - 0.5:
            self._charge_ref = (self.t_global, pct, pos)
            return
        if self.t_global - ref[0] >= self.CHARGE_S and pct - ref[1] >= self.CHARGE_PCT:
            if self.chargeur is None or math.hypot(pos[0] - self.chargeur[0], pos[1] - self.chargeur[1]) > 0.2:
                print(f"[{self.t_global:6.1f}s] chargeur appris en ({pos[0]:.2f}, {pos[1]:.2f})", flush=True)
            self.chargeur = pos
            self._charge_ref = (self.t_global, pct, pos)

    def _verifie_bonjour(self):
        h = self.horloge()
        jour = getattr(h, "tm_yday", None)
        if jour == self._jour_bonjour:
            return
        minutes = h.tm_hour * 60 + getattr(h, "tm_min", 0)
        heure = self.bonjour_weekend if (self.bonjour_weekend and getattr(h, "tm_wday", 0) >= 5) else self.bonjour
        debut = heure[0] * 60 + heure[1]
        if not (0 <= minutes - debut < self.BONJOUR_FENETRE_H * 60):
            return
        if self.mode_calme or self.tombe or self.courant.nom not in ("chill", "look"):
            return                              # on attend un moment de repos (ne jamais interrompre une activite)
        self._jour_bonjour = jour
        print(f"[{self.t_global:6.1f}s] routine du matin : bonjour", flush=True)
        self._bascule("bonjour")

    def tick(self, state, dt):
        """Un pas du cerveau, a appeler une fois par trame robot.state."""
        if self.ctx.state is None and state.get("policy") == "sit":
            self.ctx.sitting = True             # demarrage sur un canard deja assis (cerveau precedent arrete en sieste)
        self.ctx.state = state
        self.ctx.bec()
        if self.ctx.extras.get("tof") is not None:
            self.ctx.extras["tof"].noter_etat(state)     # pose de tete datee, pour placer chaque trame ToF a son instant
        self.t_global += dt
        if self.heures_calmes is not None:
            debut, fin = self.heures_calmes
            h = self.horloge().tm_hour
            nuit = (h >= debut or h < fin) if debut > fin else (debut <= h < fin)
            if nuit != self._nuit_actuelle:
                self._nuit_actuelle = nuit
                self.evenement("calme_on" if nuit else "calme_off")
        if state.get("odom"):
            self._derniere_position = (state["odom"]["position"][0], state["odom"]["position"][1])
        pct = state.get("battery", {}).get("percent")
        if pct is not None:
            self._batterie_pct = pct
            if state.get("odom"):
                self._apprend_chargeur(pct, state["odom"]["position"])
        if state.get("safety", {}).get("fallen"):
            if not self.tombe:
                print(f"[{self.t_global:6.1f}s] CHUTE : cerveau en pause (robotd se charge du relevement)", flush=True)
                if self._derniere_position is not None:
                    self.exploration.chute(*self._derniere_position, self.t_global)   # "zone noire" apprise
                self.diagnostic.chutes.note(self.diagnostic.mur(), self.courant.nom, self._derniere_position,
                                            self.diagnostic.session, getattr(self.horloge(), "tm_hour", None))
                self.chutes = [t for t in self.chutes if self.t_global - t <= self.FENETRE_CHUTES_S] + [self.t_global]
                self.perso.vit("chute")
                if len(self.chutes) >= self.CHUTES_AGACE:
                    self.veille_jusqua = self.t_global + self.VEILLE_AGACE_S
                    chat = self.ctx.extras.get("chat")
                    qui = "le chat" if chat is not None and getattr(chat.suivi, "visible", False) else "quelque chose"
                    print(f"[{self.t_global:6.1f}s] {len(self.chutes)} chutes en {self.FENETRE_CHUTES_S / 60:.0f} min "
                          f"({qui}) : veille {self.VEILLE_AGACE_S / 60:.0f} min, assis", flush=True)
            self.tombe = True
            self.ctx.calme()
            return
        if self.tombe and state.get("policy") == "stand":
            # De nouveau debout (la sequence limp_fall de robotd l'a releve) : il s'ebroue, comme un canard qui se
            # remet d'une glissade, puis reprend sa vie. Pas en mode calme (silence et immobilite d'abord).
            self.tombe = False
            self.ctx.sitting = False             # robotd l'a remis DEBOUT (policy stand) : on se recale dessus
            print(f"[{self.t_global:6.1f}s] releve apres la chute", flush=True)
            if self.t_global < self.veille_jusqua:
                self._bascule("nap")             # serie de chutes : il s'assoit et ne recommence pas
            elif not self.mode_calme and self.presents:
                self.suivant_force = "ebouriffe" # devant quelqu'un : un peu gene d'abord, puis il s'ebroue
                self._bascule("gene")
            elif not self.mode_calme:
                self._bascule("ebouriffe")
            else:
                self._bascule("nap")             # mode calme : il retourne a sa sieste, assis
        if self.tombe:
            return                              # pas encore la politique 'stand' : on attend sans rien commander
        if state.get("odom") and self.t_global - self._t_explo >= 0.5:
            self._t_explo = self.t_global
            self.exploration.noter(state["odom"]["position"][0], state["odom"]["position"][1], self.t_global)
        if state.get("odom") and self.courant.nom in ("chill", "nap"):
            # "Deux coins favoris distincts selon l'activite" (ROADMAP "chantier actif") : on accumule le temps
            # passe par activite, par case - a chaque trame (pas throttle comme `noter` ci-dessus : c'est une duree
            # cumulee, pas un compteur de passages). La navigation vers le coin appris n'est pas encore cablee (pas
            # de position fiable connue d'avance, meme limite que Accueil).
            o = state["odom"]
            self.exploration.preference(o["position"][0], o["position"][1], self.courant.nom, dt, self.t_global)
        if state.get("odom"):
            # "S'ebroue apres une longue immobilite REELLE" (ROADMAP "chantier actif") : l'odom ne bouge quasi pas
            # depuis SEUIL_IMMOBILE_S -> `ebouriffe`, uniquement depuis un etat de repos (chill/look), pas en
            # interrompant autre chose (wander, accueil, ecoute...). Meme garde-fou que le tirage RARES habituel.
            pos = (state["odom"]["position"][0], state["odom"]["position"][1])
            if self._pos_ref_immobile is None or math.hypot(pos[0] - self._pos_ref_immobile[0],
                                                              pos[1] - self._pos_ref_immobile[1]) > self.SEUIL_DEPLACEMENT:
                self._pos_ref_immobile, self._t_ref_immobile = pos, self.t_global
            elif (self.t_global - self._t_ref_immobile >= self.SEUIL_IMMOBILE_S
                  and self.t_global - self.derniere_fois.get("ebouriffe", -1e9) >= self.DELAI_RARE
                  and not self.mode_calme and self.courant.nom in ("chill", "look")):
                self.derniere_fois["ebouriffe"] = self.t_global
                self._t_ref_immobile = self.t_global     # redemarre la fenetre : pas de declenchement en boucle
                self._bascule("ebouriffe")

        self._surveille_robotd(state)
        self._verifie_sante()
        self._note_diagnostic(state, pct)
        if self._t_ecoute is None:
            self._t_ecoute = self.t_global
        if int(self.t_global / 60.0) != int((self.t_global - dt) / 60.0):
            self.habitudes.avance()             # une fois par minute : changement d'heure
            self.perso.avance(self.t_global)    # retour lent vers son temperament de base
        if self.courant.nom == "porte":
            self._traite_evenements_porte()
            self.t_etat += dt
            self.courant.pas(self, self.t_etat)
            return                              # dans les bras : rien d'autre ne compte
        self._surveille_main(state)
        self._surveille_caresse(state)
        self._traite_evenements()
        if self.bonjour is not None:
            self._verifie_bonjour()                 # apres les evenements : un "calme_on" en attente passe d'abord
        if self.ctx.extras.get("autotest"):
            self._verifie_autotest()
        self._verifie_jour_special()
        self.humeur.avance(dt, self.courant.nom, self.vivacite())
        if self.discret and self.t_global - self._t_discret > self.DISCRET_MAX_S:
            self._discretion(False)
        self._babille(dt)
        self._surveille_peripherie()
        self._verifie_lumiere()
        self.t_etat += dt
        self.courant.pas(self, self.t_etat)
        if self.t_etat >= self.fin_etat:
            self._bascule(self._choisit_suivant())

    def arret(self):
        """Sortie propre : on se leve si on dormait (meme en mode calme : le prochain cerveau doit trouver le canard
        debout, comme il le suppose), tete neutre, mouvement arrete."""
        self.courant.sort(self)
        if self.ctx.sitting:
            self.ctx.toggle_sit()
        self.ctx.calme()

def run(client, duree, humeur=None, evenements=None, seed=None, source=None, a_chaque_tick=None, extras=None,
        **options):
    """`source()` : appelee a chaque trame, renvoie les noms d'evenements arrives depuis l'exterieur (pont
    Home Assistant...). `a_chaque_tick(brain, state)` : crochet facultatif (publication d'etat...). `options` :
    reglages optionnels de Brain (heures_calmes, bonjour...)."""
    brain = Brain(client, humeur=humeur, seed=seed, extras=extras, **options)
    evenements = sorted(evenements or [])
    last_t = None
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < duree:
            state = client.read_state_frame()
            t = state.get("t")
            dt = (t - last_t) if (t is not None and last_t is not None and 0 < t - last_t < 0.5) else DT_DEFAUT
            last_t = t
            while evenements and evenements[0][0] <= time.monotonic() - t0:
                brain.evenement(evenements.pop(0)[1])
            if source:
                for nom in source():
                    brain.evenement(nom)
            brain.tick(state, dt)
            if a_chaque_tick:
                a_chaque_tick(brain, state)
    finally:
        brain.arret()
    return brain

def _parse_args(argv):
    duree, energie, events = 60.0, 0.8, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--energy":
            energie = float(argv[i + 1]); i += 2
        elif a == "--events":
            for item in argv[i + 1].split(","):
                nom, _, t = item.partition("@")
                events.append((float(t), nom))
            i += 2
        else:
            duree = float(a); i += 1
    return duree, energie, events


if __name__ == "__main__":
    from poc_robotd_client import RobotdClient, SOCK_PATH
    duree, energie, events = _parse_args(sys.argv[1:])
    c = RobotdClient(SOCK_PATH)
    c.request("robot.subscribe", {})
    print(f"Cerveau actif {duree:.0f}s, energie initiale {energie}", flush=True)
    b = run(c, duree, Humeur(energie=energie), events)
    print(f"Fin. {len(b.journal)} transitions.", flush=True)
