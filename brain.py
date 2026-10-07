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

from choregraphies import Choregraphie
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
from etats_appli import Parcours, PosePhoto, Signal
import vivant
from vivant import AttendPorte, Boude, Habituation, JeTeSuis, Reponse, SuisMoi
import personnage
from etats_plan import Accoste, Guide, Ronde, Tresor, VaSurPlan, point_approche
import plan_vie
from personnage import (BainSoleil, Doudou, Gaffe, Gouts, Hoquet, Inspecte, Nid, Nomme, ObservateurChat, Petit,
                         Rythme, Solitude, Succes)
from diagnostic import Diagnostic
from etats_maison import AlarmeFumee, AssisDemande, AutoTestReveil, Toupie
from etats_taquineries import (Aspirateur, Baillement, CompteEternuements, DernierMot, Esquive, FausseChute,
                               FausseNotif, FauxEndormi, FeinteBec, Fier, MimeTon, MimeVol, PousseBalle, RegardMystere,
                               SourdeOreille)
from etats_vie import (Picore, Remarque, Zoomies, Accueil, Bonjour, Caresse, Danse, JeuSolitaire, MainTendue, Porte, RechercheAttention,
                       RegardeChat, VaAuCoin, Timide, CoupOeil, Compagnie, BaillementContagieux, PasGuide,
                       RegardGuide)

class Brain:
    SEUIL_SIESTE = 0.25
    # "Va se recharger de sa propre initiative avant d'etre a court" (ROADMAP "chantier actif") : la VRAIE batterie
    # (state["battery"]["percent"], distincte du modele comportemental `Humeur.energie`) force le repos en dessous
    # de ce seuil - anticipation (consommer moins en se posant) plutot qu'attendre l'arret force. Pas encore de
    # retour physique au chargeur : aucune position de chargeur connue dans brain.py (meme limite que `Accueil`).
    BATTERIE_BASSE_PCT = 25.0
    BATTERIE_FAIBLE_PCT = 40.0  # entre 25 et 40 % : il passe d'abord voir quelqu'un, une fois, avant le chargeur
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
    P_HOQUET = 0.004            # par passage par chill (x5 dans les 10 min apres un repas) ; une fois par 3 h au plus
    P_DOUDOU = 0.03             # par passage par chill, sa balle vue : il va retrouver son doudou
    P_NID = 0.7                 # avant une sieste de fatigue : deux tours sur lui-meme (une fois par heure au plus)
    SOLLICITATIONS_MAX = 30     # sollicitations en 30 min (x sociabilite) avant d'avoir besoin d'etre un peu seul
    SOLEIL_PERIODE_S = 600.0    # en journee, au repos : y a-t-il une tache de soleil au sol ? (camera)
    SPECTACLE = ("danse", "zoomies", "signature", "rythme", "hoquet", "gaffe", "fausse_chute", "fausse_notif",
                 "lissage", "ebouriffe", "etirement", "eternuement", "cabotine")   # cabotinage : ses « numeros »
    P_SOUVENIR = 0.02           # par passage par chill : flaner la ou il s'est passe quelque chose de bien
    CONVERSATION_S = 45.0       # apres un appel, une caresse... : il « repond » a ce qu'on lui dit pendant 45 s
    BONS = {"caresse": 30.0, "bravo": 20.0, "accueil": 20.0, "cajole": 20.0, "compagnie": 10.0, "compliment": 20.0,
            "reconcilie": 10.0, "signature": 5.0}                     # souvenirs de lieux : ce qui fait du bien...
    MAUVAIS = {"startle": 30.0, "mefiant": 15.0, "retrait": 15.0, "gene": 10.0}   # ... et ce qui fait peur
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
            # « Ou es-tu ? » de l'application : trois petits chirp pour qu'on le retrouve (sous un meuble...)
            "choregraphie": Choregraphie(),                # studio de choregraphies de l'application
            "ou_es_tu": Sequence("ou_es_tu", [("curieux", "chirp"), ("oui", "chirp"), ("curieux", "chirp")]),
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
            "coup_oeil": CoupOeil(),
            "compris": Sequence("compris", [("oui", "chirp")]),                 # commande domotique transmise
            "pas_guide": PasGuide(), "regard_guide": RegardGuide(),             # telecommande (application)
            "penaud": Sequence("penaud", [("gene", None), ("fatigue", None)]),   # gronde : tete basse, sans un son
            "cajole": Sequence("cajole", [("content", "coo")]),                   # appele tendrement
            "mefiant": Sequence("mefiant", [("surpris", "inquire"), ("gene", None)]),   # l'aspirateur, les 1res fois
            "bips": Sequence("bips", [("curieux", "inquire")]),                    # bips d'un appareil
            "retrait": Sequence("retrait", [("gene", None)]),                      # trop de bruit : il s'en va                                               # mouvement a la peripherie
            "va_repas": VaAuCoin("va_repas", "look", "trainer la ou l'on mange, comme chaque jour a cette heure"),
            "va_compagnie": VaAuCoin("va_compagnie", "compagnie", "tenir compagnie la ou l'on s'occupe de lui"),
            "compagnie": Compagnie(),
            # lances depuis l'application : parcours d'obstacles, balle guidee, pose pour une photo
            "parcours": Parcours(), "pose_photo": PosePhoto(),
            "signal": Signal(),                                   # minuteur, rappel, reveil doux (application)
            # vivant.py : bouderie, attente a la porte, suis-moi / je te suis, tour de parole, et leurs petites suites
            "boude": Boude(), "attend_porte": AttendPorte(), "suis_moi": SuisMoi(), "mene": JeTeSuis(), "repond": Reponse(),
            "reconcilie": Sequence("reconcilie", [("content", "coo"), ("oui", "chirp")]),
            "jaloux": Sequence("jaloux", [("curieux", "inquire"), ("non", "peck"), ("content", "chirp")]),
            "va_porte": VaAuCoin("va_porte", "attend_porte", "attendre a la porte"),
            "va_souvenir": VaAuCoin("va_souvenir", "souvenir", "flaner la ou il s'est passe quelque chose de bien"),
            "souvenir": Sequence("souvenir", [("content", "coo")]),
            "mefiant_lieu": Sequence("mefiant_lieu", [("curieux", None), ("gene", None)]),
            "excite": Sequence("excite", [("oui", "chirp"), ("oui", "chirp"), ("content", "wheee")]),
            "va_social": VaAuCoin("va_social", "cherche_attention", "voir quelqu'un avant d'aller se recharger"),
            # personnage.py : hoquet, gaffes, nid, rythme, nom sonore, ambiance, doudou, objet nouveau, bain de soleil
            "hoquet": Hoquet(), "gueri": Sequence("gueri", [("surpris", None), ("content", "coo")]),
            "gaffe": Gaffe(), "nid": Nid(), "inspecte": Inspecte(), "rythme": Rythme(), "nomme": Nomme(),
            "petit": Petit(), "bain_soleil": BainSoleil(), "doudou": Doudou(),
            "va_doudou": VaAuCoin("va_doudou", "doudou", "retrouver son doudou"),
            "rit": Sequence("rit", [("content", "chirp")]),
            "cabotine": Sequence("cabotine", [("fier", "chirp")]),
            "reclame": Sequence("reclame", [("curieux", "coo")]),
            # vivant III : solitude, anniversaire, le chat comme modele
            "solitude": Solitude(), "va_solitude": VaAuCoin("va_solitude", "solitude", "etre un peu seul"),
            "anniversaire": Sequence("anniversaire", [("content", "wheee"), ("fier", "chirp"), ("content", "wheee")]),
            "chat_joue": Sequence("chat_joue", [("curieux", "chirp"), ("content", "wheee")]),
            "va_chat": VaAuCoin("va_chat", "nap", "faire la sieste pres du chat"),
            # sur le plan de la maison (position.py) : station de charge, ronde du soir, piece ou l'on est, point demande
            "va_station": VaSurPlan("va_station", "accoste", "rentrer a sa station", si_echec="nap"),
            "accoste": Accoste(), "ronde": Ronde(),
            "va_piece": VaSurPlan("va_piece", "cherche_attention", "voir dans la piece ou l'on est"),
            "va_point": VaSurPlan("va_point", "chill", "la ou on l'envoie"),
            # plan II : tresor, guide, balle retrouvee, porte d'entree, imprimante, habitudes, soleil, decor change
            "tresor": Tresor(), "guide": Guide(),
            "va_balle": VaSurPlan("va_balle", "balle", "retrouver sa balle", proche_ok=0.6),
            "va_entree": VaSurPlan("va_entree", "attend_porte", "t'attendre a la porte"),
            "va_imprimante": VaSurPlan("va_imprimante", "regarde_impression", "voir l'impression", proche_ok=0.8),
            "regarde_impression": Sequence("regarde_impression", [("curieux", "inquire"), ("content", "chirp")]),
            "va_habitude": VaSurPlan("va_habitude", "chill", "a sa place de ce moment de la journee"),
            "va_soleil": VaSurPlan("va_soleil", "au_soleil", "la ou il y a du soleil a cette heure"),
            "au_soleil": Sequence("au_soleil", [("etirement", "coo")]),
            "va_changement": VaSurPlan("va_changement", "inspecte", "voir ce qui a change", proche_ok=0.7),
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
        self._vieillit()                        # timidite de jeunesse, assurance des blagues (vivant.py)
        self._t_ecoute = None                   # premiere trame : debut de l'ecoute des habitudes sonores
        # auto-surveillance (diagnostic.py) : batterie dans la duree, derive des servos, journal des chutes, auto-test
        self.diagnostic = Diagnostic(mem, mur=self.ctx.extras.get("mur", time.time))
        self.derniere_sante = None              # derniere reponse de robot.health
        self._jour_autotest = None
        self.diag_demande = False               # diagnostic demande a la main (Home Assistant, interface)
        self.objet_nouveau = None               # distance (m) devant de l'objet nouvellement remarque
        self.objets_au_sol = []                 # (heure murale, x, y odom) des objets nouveaux remarques : vers HA
        self.presence_suivie = False            # presence initiale lue dans HA : "personne a la maison" a un sens
        self.presence_inconnue = set()          # habitants dont HA ne sait pas l'etat : la maison n'est pas "vide"
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
        self.messages_perso = []                # (id, destinataire) : messages laisses dans l'application
        self.vus = {}                           # "chat"/"balle"/"objet" -> (heure murale, x, y) : ou il l'a vu
        self._t_vu_balle = -1e9
        self.vacances = False                   # mode vacances de l'application : calme + garde
        self.habituation = Habituation()        # vivant.py : il s'habitue aux stimuli qui reviennent
        donnees_mem = getattr(self.ctx.extras.get("memoire"), "donnees", None)
        self.succes = Succes(donnees_mem if isinstance(donnees_mem, dict) else None)   # cabotinage (personnage.py)
        self._t_motif = None                    # un rythme tape vient d'etre rejoue : pas aussi un appel / une porte
        self._t_soleil = -1e9
        self._soleil_vu = None                  # (x relatif, fraction) : tache de soleil vue par la camera
        self._rituels_faits = set()             # (jour, qui) : rituel deja reclame aujourd'hui
        self.sollicitations = []                # t_global des sollicitations recentes (besoin de solitude)
        self.pieces_occupees = {}               # piece -> t_global : presence par piece (capteurs HA, [[piece]])
        self.lieux_heure = plan_vie.LieuxHeure(donnees_mem if isinstance(donnees_mem, dict) else None)
        self.recharge_jusqua = -1e9             # recharge anticipee : sieste sur la station jusque-la
        self.balle_plan = None                  # (lieu, x, y, heure murale) : ou il a vu sa balle, sur le plan
        self._t_lieu_note = -1e9
        self.dernier_releve_ronde = None
        self._jour_ronde = None
        self.observateur_chat = ObservateurChat()
        self._t_chat_note = -1e9
        self.anniversaire = 0                   # aujourd'hui : son anniversaire (nombre d'annees), 0 sinon
        self.humeur_jour = "normal"
        self.gouts = None                       # gouts musicaux : seulement avec une memoire (graine = sa naissance)
        if isinstance(donnees_mem, dict) and getattr(self.perso, "sauver", None) is not None:
            self.gouts = Gouts(donnees_mem, self.perso.d.get("naissance", 0))
        self._maj_humeur_jour()
        self._rng_vie = random.Random(None if seed is None else seed + 11)   # respiration, saccades : hasard a part
        self.conversation_jusqua = -1e9         # tour de parole : on vient de s'adresser a lui (appel, caresse...)
        self.entree = None                      # (x, y) odom : la ou il accueille d'habitude (porte d'entree)
        self._attentes_faites = set()           # (jour, qui) : deja alle attendre a la porte aujourd'hui
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
        # Qui veut savoir ce que vit le canard (pont_ha : actions domotiques) : f("etat:<nom>") a chaque entree dans un
        # etat, f(<evenement>) a chaque evenement recu. Doit rendre la main tout de suite (le tick ne bloque jamais).
        self.ecouteurs = []
        self.discret = False                    # quelqu'un telephone (audio.py) : ni son ni initiative bruyante
        self.vacarme = False                    # ambiance tres bruyante (audio.py) : il reste a l'ecart, assis
        self._t_vacarme = 0.0
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
        if not isinstance(nom, str) or not nom:
            return
        self.evenements.append(nom)
        self._previent(nom)

    def _previent(self, quoi):
        """Ecouteurs (pont_ha...) : une erreur chez eux ne doit jamais arreter le canard."""
        for f in self.ecouteurs:
            try:
                f(quoi)
            except Exception as e:
                print(f"  (ecouteur {getattr(f, '__name__', f)} : {type(e).__name__}: {e})", flush=True)

    def _traite_evenements(self):
        while self.evenements:
            nom = self.evenements.pop(0)
            base, _, detail = nom.partition(":")     # "impression_echec:MK4S" -> ("impression_echec", "MK4S")
            if base in self.VUS_EVENEMENTS:
                self._note_vu(self.VUS_EVENEMENTS[base])
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
            self._veille_garde(base)
            if base in ("garde_on", "garde_off"):
                self.ctx.extras["garde"] = base == "garde_on"      # depuis l'application
                continue
            if base in ("vacances_on", "vacances_off"):
                # application : la maison est vide pour longtemps. Calme (sieste, silence) + garde ; au retour, tout
                # reprend. Un vrai interrupteur calme ou garde reste ensuite libre.
                self.vacances = base == "vacances_on"
                self.evenements[0:0] = ["calme_on", "garde_on"] if self.vacances else ["calme_off", "garde_off"]
                print(f"[{self.t_global:6.1f}s] vacances {'ON' if self.vacances else 'off'}", flush=True)
                continue
            if base == "message":
                # application : un message laisse pour quelqu'un. Le canard ne dit pas de mots : il le signale (sons
                # de canard) quand la personne est la, et l'appli affiche le texte.
                ident, _, pour = (detail or "").partition("|")
                if ident and pour:
                    self.messages_perso = (self.messages_perso + [(ident, pour)])[-self.MESSAGES_PERSO_MAX:]
                    if pour in self.presents:
                        self._transmet_messages(pour, maintenant=True)
                continue
            if base in ("parcours", "va_balle"):
                # application : des points poses sur sa carte (ou « la balle est par la »). Debout, au calme, avec le
                # capteur de distance (on ne marche jamais sans), et des etapes courtes (odometrie).
                points = Parcours.lire_points(detail.replace("|", ";"), self._derniere_position)
                libre = (not self.mode_calme and not self.tombe and not self.porte and not self.ctx.sitting
                         and self.courant.nom not in ("alarme", "porte", "nap", "ecoute"))
                if points and libre and self.ctx.extras.get("tof") is not None:
                    self.derniere_interaction = self.t_global
                    self.etats["parcours"].charger(points[:1] if base == "va_balle" else points,
                                                   "balle" if base == "va_balle" else "parcours")
                    self._bascule("parcours")
                else:
                    self._previent(f"parcours_fini:{'balle' if base == 'va_balle' else 'parcours'}|refuse|0|0/0")
                continue
            if base == "pose_photo":
                if (detail in PosePhoto.POSES and not self.mode_calme and not self.tombe
                        and self.courant.nom not in ("alarme", "porte", "ecoute")):
                    self.etats["pose_photo"].geste = detail
                    self._bascule("pose_photo")
                continue
            if base == "signal":
                # application : minuteur fini, rappel, reveil doux. Demande expresse : meme en mode calme ou en sieste,
                # mais jamais a terre, dans les bras ni pendant l'alarme (alors : l'appli a deja notifie le telephone).
                genre, _, ident = (detail or "").partition("|")
                if genre in Signal.SEQUENCES and not self.tombe and not self.porte \
                        and self.courant.nom not in ("alarme", "porte"):
                    self.etats["signal"].genre, self.etats["signal"].ident = genre, ident
                    self._bascule("signal")
                continue
            if base == "signal_stop":
                if self.courant.nom == "signal":
                    self.etats["signal"].arreter(self, "arrete")
                continue
            if base == "enonce":
                self._sur_enonce(detail)
                continue
            if base in ("suis_moi", "je_te_suis"):
                # application, voix ou bouton HA : jouer a se suivre. Capteur de distance obligatoire, debout, au calme.
                if (self.ctx.extras.get("tof") is not None and not self.mode_calme and not self.tombe and not self.porte
                        and not self.ctx.sitting and not self.surchauffe
                        and self.courant.nom not in ("alarme", "porte", "nap", "ecoute", "signal")):
                    self.derniere_interaction = self.t_global
                    self._bascule("suis_moi" if base == "suis_moi" else "mene")
                continue
            if base == "message_annule":
                self.messages_perso = [m for m in self.messages_perso if m[0] != detail]
                continue
            if base == "arrivee":
                # application : le telephone de quelqu'un vient de rejoindre le Wi-Fi de la maison. S'il est deja
                # compte present (Home Assistant), rien ; sinon c'est un retour, avec l'accueil.
                qui = (detail or "").partition("|")[0]
                if qui and qui not in self.presents:
                    self.evenements.insert(0, f"retour:{qui}")
                continue
            if base in ("guide", "regard"):
                self._sur_telecommande(base, detail)
                continue
            if base == "oublier_carte":
                # depuis l'application (meubles bouges, autre piece) : il repart d'une carte vierge, coins et chargeur
                # compris (ils sont dans le meme repere). Rien d'autre n'est oublie.
                self.exploration = Exploration()
                self.chargeur = None
                print(f"[{self.t_global:6.1f}s] carte effacee", flush=True)
                continue
            if base == "ou_es_tu":
                # depuis l'application : il se signale. Pas en mode calme (silence promis), ni a terre ou dans les bras.
                if not self.mode_calme and not self.tombe and self.courant.nom not in ("alarme", "porte"):
                    self._bascule("ou_es_tu")
                continue
            if base == "choregraphie":
                # depuis l'application (ou une routine) : une choregraphie du studio, par son nom
                etapes = (self.ctx.extras.get("choregraphies") or {}).get(detail)
                if etapes and not self.mode_calme and not self.tombe and self.courant.nom not in ("alarme", "porte"):
                    self.etats["choregraphie"].charger(detail, etapes)
                    self._bascule("choregraphie")
                continue
            if base == "skill_essai":
                # application, page Comportements : essayer une politique installee (robot.do), debout et au calme
                if (detail and not self.mode_calme and not self.tombe and not self.ctx.sitting
                        and self.courant.nom in ("chill", "look", "regard_guide")):
                    try:
                        self.ctx.client.request("robot.do", {"skill": detail})
                    except Exception as e:
                        print(f"  (essai de {detail} impossible : {e})", flush=True)
                continue
            if base == "routine_compagnie":
                # routine programmee dans l'application (« a 18 h, il vient me voir ») : comme son envie de compagnie
                if not self.mode_calme and not self.tombe and self.courant.nom not in ("alarme", "porte"):
                    self._bascule("cherche_attention")
                continue
            if base in ("servo_remplace", "batterie_remplacee"):
                # carnet d'entretien de l'application : une piece changee repart d'une mesure neuve
                if base == "servo_remplace":
                    self.diagnostic.servos.remplace(detail)
                else:
                    self.diagnostic.batterie.remplacee(detail)
                continue
            if base == "batterie_mise":
                # depuis l'application : quelle batterie du pack est dans le canard (statistiques par batterie)
                if hasattr(self, "diagnostic"):
                    self.diagnostic.batterie.mettre(detail)
                continue
            if base == "lieu":
                # lieux.py : il a change d'endroit (autre reseau Wi-Fi, ou choix dans l'application). La carte de la
                # session ne vaut plus rien ici : il en recommence une. Un lieu inconnu le rend curieux ; un retour,
                # il s'etire (le trajet).
                genre, _, lieu = (detail or "").partition("|")
                self.exploration = Exploration()
                self.chargeur = None
                self.ctx.extras["lieu"] = lieu or None
                print(f"[{self.t_global:6.1f}s] lieu : {lieu} ({genre})", flush=True)
                if not self.mode_calme and not self.tombe and self.courant.nom not in ("alarme", "porte", "nap"):
                    if genre == "nouveau":
                        self._bascule("curious")
                    elif genre == "retour":
                        self._bascule("etirement")
                continue
            if base == "diagnostic":
                self.diag_demande = True        # une demande de maintenance, pas une interaction : avant l'ennui
                print(f"[{self.t_global:6.1f}s] diagnostic demande : au prochain moment de repos", flush=True)
                continue
            if base in ("temperature_ext", "presence"):
                # informations de la maison, pas une manifestation humaine : traitees AVANT la remise a zero de l'ennui
                self._sur_info_maison(base, detail)
                continue
            # Occupation autonome : tout evenement reel (hors bascule "calme") remet le compteur d'ennui a zero,
            # qu'il soit ou non traite immediatement (differe pendant une conversation, ignore pendant la sieste...).
            self.derniere_interaction = self.t_global
            self.ignores = 0                    # quelqu'un s'est manifeste : le decouragement s'efface
            if base in ("caresse", "main", "appel", "applaudissements", "commande", "rire", "enonce", "motif"):
                self.sollicitations = [t for t in self.sollicitations if self.t_global - t <= 1800.0] + [self.t_global]
                if self.courant.nom == "danse" and base in ("caresse", "main", "rire", "applaudissements") \
                        and self.gouts is not None:
                    self.gouts.noter_bon(self.etats["danse"].bpm)   # un bon moment sur cette musique
            if base in ("caresse", "main", "appel", "commande", "applaudissements"):
                self._reponse_au_babil()        # (pas "voix" : la tele ou une conversation ne lui repondent pas)
            if base in ("telephone", "telephone_fin"):
                self._discretion(base == "telephone")
                continue
            if base in ("visiteur", "visiteur_fin"):
                self._sur_visiteur(base == "visiteur", detail or None)
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
            if base in ("vacarme", "vacarme_fin"):
                self._sur_vacarme(base == "vacarme")   # meme pendant la sieste : la fin du vacarme doit etre vue
                continue
            if base in ("maison", "maison_ok", "maison_refus"):
                # commande domotique dite a la voix (commandes.py) : pont_ha appelle le service HA et repond
                # maison_ok / maison_refus ; le canard accuse reception en son de canard, jamais en mots
                if base != "maison" and not self.mode_calme and self.courant.nom in ("chill", "look", "wander",
                                                                                      "jeu_solitaire"):
                    self._bascule("compris" if base == "maison_ok" else "hesite")
                continue
            if base == "ton":
                # Le ton sur lequel on dit son nom (commandes.py), sans comprendre les mots : grondé -> penaud, tete
                # basse, plus de blague un moment ; cajole -> content, il roucoule. Jamais en mode calme ni la nuit.
                if self.mode_calme or self.courant.nom in ("nap", "alarme", "porte", "ecoute"):
                    continue
                if detail == "gronde":
                    self.perso.vit("gronde")
                    self.malice.stop(self)
                    if getattr(self.courant, "taquinerie", False):
                        self.suivant_force = None   # la blague qui devait suivre ; pas un abri ou une sieste decides
                    if self.rng.random() < 0.3 + 0.4 * self.perso.trait("espieglerie"):
                        self.suivant_force = "boude"    # penaud... puis vexe, un petit moment
                    self._bascule("penaud")
                elif detail == "calin":
                    self.perso.vit("calin")
                    self._bascule("cajole")
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
            if base in ("retour", "depart"):
                self.presence_inconnue.discard(detail.partition("|")[0])
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
                if mem is not None and hasattr(mem, "donnees"):
                    vivant.noter_retour(mem.donnees, qui, self.horloge())     # pour l'attendre a la porte
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
                self._transmet_messages(qui)
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
                if base == "impression_finie":
                    imp = self._point_imprimante(detail)
                    if imp is not None:
                        self.etats["va_imprimante"].cible = imp
                        self.suivant_force = "va_imprimante"   # il va voir la piece terminee
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
            if base == "emmene":
                # « emmene-moi a la cuisine » (voix) : un point nomme ou une piece du plan
                pos = self.ctx.extras.get("position")
                cible = plan_vie.resoudre(pos.plan, detail) if pos is not None and pos.plan is not None else None
                if cible is None or pos.pose() is None or self.mode_calme or self.ctx.sitting or self.tombe:
                    self._bascule("hesite")             # « ou ca ? »
                else:
                    self.etats["guide"].cible, self.etats["guide"].nom_cible = cible, detail
                    self._bascule("guide")
                continue
            if base == "arrivee_proche":
                # HA : quelqu'un approche de la maison (son telephone) -> il va l'attendre a la vraie porte d'entree
                pos = self.ctx.extras.get("position")
                entree = (pos.plan.reperes.get("entree") if pos is not None and pos.plan is not None else None)
                if (entree and pos.pose() is not None and detail not in self.presents and not self.mode_calme
                        and not self.tombe and self.courant.nom in ("chill", "look", "wander", "nap", "jeu_solitaire")):
                    self.etats["attend_porte"].qui = detail or None
                    self.etats["va_entree"].cible = (entree[0], entree[1])
                    self._bascule("va_entree")
                continue
            if base == "presence_piece":
                piece, _, etat = detail.partition("|")
                if etat == "on":
                    self.pieces_occupees[piece] = self.t_global
                else:
                    self.pieces_occupees.pop(piece, None)
                continue
            if base == "aller":
                # « va la » (appli, casque) : un point du plan, s'il sait ou il est et qu'un chemin existe
                try:
                    x, y = (float(v) for v in detail.split("|")[:2])
                except ValueError:
                    continue
                pos = self.ctx.extras.get("position")
                if (pos is not None and pos.pose() is not None and not self.mode_calme and not self.tombe
                        and not self.ctx.sitting and self.courant.nom not in ("alarme", "porte", "nap", "signal")):
                    self.etats["va_point"].cible = (x, y)
                    self._bascule("va_point")
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
            if base in ("caresse", "main") and self.courant.nom == "boude":
                self.perso.vit("calin")
                self._bascule("reconcilie")             # une caresse, et il ne boude plus
                continue
            if base == "motif":
                # on tape un rythme (audio.py) : s'il joue avec quelqu'un, il le rejoue en coups de bec
                if (self.t_global < self.conversation_jusqua and not self.mode_calme and not self.discret
                        and self.courant.nom in self.REPOS_REPONSE + ("rythme",)):
                    try:
                        self.etats["rythme"].ecarts = [int(x) / 1000.0 for x in detail.split(",") if x]
                    except ValueError:
                        continue
                    self._t_motif = self.t_global
                    self.conversation_jusqua = self.t_global + self.CONVERSATION_S
                    self._bascule("rythme")
                continue
            if base in ("appel", "toc_porte") and self._t_motif == self.t_global:
                continue                                # c'etait le rythme qu'il vient de rejouer
            if base == "rire":
                self._sur_rire()
                continue
            if base == "ambiance":
                if (detail == "tendue" and not self.mode_calme and self.courant.nom in ("chill", "look", "wander",
                                                                                          "compagnie", "attentif")):
                    self.malice.stop_jusqua = max(self.malice.stop_jusqua, self.t_global + 600.0)   # pas de blague
                    self._bascule("petit")              # des voix qui montent : il se fait tout petit
                continue
            if base in ("caresse", "appel") and self.courant.nom == "solitude":
                self.ctx.sound("coo")                   # « oui, oui... » : il reste dans son coin un moment
                continue
            if base in ("caresse", "main") and self.courant.nom == "hoquet":
                self._bascule("gueri")                  # une caresse, et le hoquet passe
                continue
            if base == "caresse" and len(self.presents) == 1:
                self._note_rituel(next(iter(self.presents)))
            if base == "appel" and self.courant.nom == "boude":
                self.etats["boude"].regarde(self)       # un regard en coin, et il se detourne
                continue
            if base in ("caresse", "main", "appel", "applaudissements"):
                self.conversation_jusqua = self.t_global + self.CONVERSATION_S
            if base == "applaudissements" and self.succes.reaction(self.t_global) is not None:
                self.perso.vit("taquinerie")            # son numero a plu : un peu plus espiegle
            if base in ("caresse", "main") and self.courant.nom == "signal":
                self.etats["signal"].arreter(self, "caresse")   # « c'est bon, j'ai compris »
                continue
            if base == "caresse":
                if self.courant.nom == "nap" or self.mode_calme:
                    self.ctx.sound("coo")       # caresse pendant le sommeil : un roucoulement, sans se reveiller
                elif self.courant.nom != "caresse":
                    self._bascule("caresse")
                continue
            if self.courant.nom == "nap":
                continue  # ne jamais insister : on dort, l'evenement est perdu
            if base == "petarades":
                # Petards, feux d'artifice (audio.py) : plus que le sursaut du tonnerre - il va se mettre a l'abri dans son
                # coin et y reste 10 min, assis ; un peu plus prudent ensuite (personnalite).
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.6)
                if self.t_global - self.derniere_fois.get("petarades", -1e9) > 3600.0:
                    for _ in range(3):
                        self.perso.vit("sursaut")   # une fois par soiree de feux d'artifice, pas a chaque salve
                self.derniere_fois["petarades"] = self.t_global
                self.veille_jusqua = max(self.veille_jusqua, self.t_global + self.ABRI_PETARDS_S)
                coin = self._coin_atteignable()
                if coin is not None:
                    self.etats["va_au_coin"].cible = coin
                self.suivant_force = "va_au_coin" if coin is not None else "nap"
                self._bascule("startle")
            elif nom == "bruit":
                self.bruits = [t for t in self.bruits if self.t_global - t <= 60.0] + [self.t_global]
                force = self.habituation.noter("bruit", self.t_global)
                if len(self.bruits) == 1 and force < 0.6:
                    # habituation : un bruit isole qui revient au fil des heures, il sursaute de moins en moins (un
                    # regard, puis plus rien) ; une SERIE de detonations, elle, fait toujours peur (abri ci-dessous)
                    if force >= 0.25 and self.courant.nom in ("chill", "look"):
                        self.humeur.eveil = min(1.0, self.humeur.eveil + 0.2)
                        self._bascule("son_bref")
                    continue
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.5)
                if len(self.bruits) >= 3:        # detonations en serie (petards, orage) : il va se mettre a l'abri
                    coin = self._coin_atteignable()
                    if coin is not None:
                        self.etats["va_au_coin"].cible = coin
                    self.suivant_force = "va_au_coin" if coin is not None else "nap"
                    self.bruits = []
                self._bascule("startle")
            elif base == "chat_caresse":
                # on caresse le chat devant lui : il vient reclamer sa part (en gardant ses distances avec le chat)
                if (self.courant.nom in ("chill", "look", "regarde_chat", "wander") and not self.discret
                        and self.t_global - self.derniere_fois.get("jaloux", -1e9) >= 1200.0):
                    self.derniere_fois["jaloux"] = self.t_global
                    if self.presents or self.ctx.extras.get("tof") is not None:
                        self.etats["cherche_attention"].cible = "humain"
                        self.suivant_force = "cherche_attention"
                    self._bascule("jaloux")
            elif nom == "chat":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("regarde_chat" if "chat" in self.ctx.extras else "curious")
            elif base == "appel":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                choix = self._taquinerie(("faux_endormi", "sourde_oreille"), humain=True)
                if choix is None and self._nommable() and self._rng_vie.random() < 0.5:
                    self.etats["nomme"].qui = next(iter(self.presents))
                    self.suivant_force = "nomme"        # « oui ? » ... puis ton nom, a sa facon
                self._bascule(choix or "appel")
            elif base in ("aspirateur_on", "aspirateur_off"):
                avant, self.aspirateur_actif = self.aspirateur_actif, base == "aspirateur_on"
                if self.aspirateur_actif and not avant:
                    # Relation avec l'aspirateur (ROADMAP "Interaction avec le reste de la maison") : mefiant les
                    # premieres fois (comme avec un visiteur), curieux ensuite, puis il l'ignore une fois familier.
                    mem = self.ctx.extras.get("memoire")
                    fam = mem.familiarite("aspirateur") if mem is not None and hasattr(mem, "familiarite") else None
                    if mem is not None and hasattr(mem, "rencontre"):
                        mem.rencontre("aspirateur")
                    if self.courant.nom in ("chill", "look"):
                        if fam is not None and fam < self.ASPI_MEFIANT:
                            self._bascule("mefiant")
                        elif fam is None or fam < self.ASPI_FAMILIER:
                            self._bascule("curious")     # tiens, le voila : un regard curieux
            elif base == "bips_appareil":
                if (self.courant.nom in ("chill", "look", "wander") and not self.discret
                        and self.habituation.noter("bips", self.t_global) >= 0.3
                        and self.t_global - self.derniere_fois.get("bips", -1e9) >= 300.0):
                    self.derniere_fois["bips"] = self.t_global
                    self._bascule("bips")                # le four, le micro-ondes : "c'est quoi ?"
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
                if self.habituation.noter("objet_nouveau", self.t_global) < 0.3:
                    continue                            # tant de nouveautes aujourd'hui : il n'y fait plus attention
                if (self.ctx.extras.get("tof") is not None and (self.objet_nouveau or 9.0) <= 1.2
                        and self._rng_vie.random() < 0.5 * self.perso.envie_promenade()):
                    self.suivant_force = "inspecte"     # il va voir de plus pres, et le picore
                self._bascule("remarque")
            elif base == "son_bref":
                if self.courant.nom in ("chill", "look") and self.habituation.noter("son_bref", self.t_global) >= 0.3:
                    self._bascule("son_bref")            # un claquement, une porte : il tourne la tete, curieux
            elif base == "voix":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.1)   # on parle : il s'eveille un peu
                self.habitudes.voix(self.t_global)
            elif base == "applaudissements":
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
                self._bascule("bravo")
            elif base == "musique" and self._envie_de_danser(int(detail) if detail.isdigit() else 100):
                self.derniere_fois["danse"] = self.t_global
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

    VUS_EVENEMENTS = {"chat": "chat", "objet_nouveau": "objet"}
    MESSAGES_PERSO_MAX = 10

    def _case(self, p):
        import exploration as xp
        return (math.floor(p[0] / xp.CASE), math.floor(p[1] / xp.CASE))

    REPOS_REPONSE = ("chill", "look", "attentif", "appel", "compagnie", "cajole", "regard_guide", "repond", "main_tendue")

    def _sur_enonce(self, detail):
        """Tour de parole (audio.py, « enonce:<duree>|<sens> » a la fin d'une phrase) : si l'on vient de s'adresser a
        lui, il « repond » d'un son de canard choisi d'apres la phrase - jamais en coupant la parole (l'enonce est fini)."""
        try:
            duree_s, _, sens = detail.partition("|")
            duree = float(duree_s)
        except ValueError:
            return
        if (self.t_global >= self.conversation_jusqua or self.mode_calme or self.discret or self.timidite() > 0.0
                or self.courant.nom not in self.REPOS_REPONSE
                or self.t_global - self.derniere_fois.get("repond", -1e9) < 4.0
                or self.rng.random() >= min(1.0, 0.85 * self.perso.bavardage())):
            return
        self.derniere_fois["repond"] = self.t_global
        self.conversation_jusqua = self.t_global + 30.0
        self.etats["repond"].son, self.etats["repond"].geste = Reponse.choisir(duree, sens or None)
        self._bascule("repond")

    def _attente_porte(self):
        """Dix minutes avant l'heure habituelle de retour d'un habitant absent : il va l'attendre a l'entree."""
        mem = self.ctx.extras.get("memoire")
        if mem is None or not hasattr(mem, "donnees"):
            return None
        h = self.horloge()
        maintenant = getattr(h, "tm_hour", 0) * 60 + getattr(h, "tm_min", 0)
        weekend = getattr(h, "tm_wday", 0) >= 5
        for qui in (mem.donnees.get("retours") or {}):
            cle = (getattr(h, "tm_yday", None), qui)
            if qui in self.presents or cle in self._attentes_faites:
                continue
            prevu = vivant.retour_prevu(mem.donnees, qui, weekend)
            if prevu is None or not 5 <= prevu - maintenant <= 12:
                continue
            self._attentes_faites.add(cle)
            self.etats["attend_porte"].qui = qui
            if self.entree is not None and self._atteignable(self.entree, (0.5, 4.0)):
                self.etats["va_porte"].cible = self.entree
                return "va_porte"
            return "attend_porte"
        return None

    def _note_vu(self, quoi):
        """« Ou l'a-t-il vu ? » (application) : la ou IL etait quand il l'a vu (repere de l'odometrie). Honnete : sa
        position a lui, pas celle de la chose (la balle, elle, est situee par la camera : voir tick)."""
        if self._derniere_position is not None:
            mur = self.ctx.extras.get("mur", time.time)
            self.vus[quoi] = (round(mur()), round(self._derniere_position[0], 2), round(self._derniere_position[1], 2))

    def _transmet_messages(self, qui, maintenant=False):
        """Messages laisses pour `qui` : signales a son accueil (brain.messages -> sons « il y a du nouveau »), ou tout
        de suite s'il est deja la et que le canard est disponible. L'application est prevenue (message_transmis)."""
        pour_lui = [m for m in self.messages_perso if m[1] == qui]
        if not pour_lui:
            return
        if maintenant and (self.mode_calme or self.tombe or self.courant.nom in ("alarme", "porte", "nap", "ecoute")):
            return                              # il le lui dira a son prochain retour
        self.messages_perso = [m for m in self.messages_perso if m[1] != qui]
        for ident, _ in pour_lui:
            self._previent(f"message_transmis:{ident}")
        if maintenant:
            self._bascule("messager")
        else:
            self.messages = (self.messages + ["message_perso"])[-self.MESSAGES_MAX:]

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
            if self.courant.nom in ("assis_demande", "suis_moi", "mene", "va_porte", "va_souvenir", "va_station",
                                    "accoste", "ronde", "va_piece", "va_point", "tresor", "guide", "va_balle",
                                    "va_entree", "va_imprimante", "va_habitude", "va_soleil", "va_changement"):
                self.suivant_force = None
                self.fin_etat = self.t_etat
        elif quoi == "station":
            cible = self._station_cible()
            if cible is not None and not self.tombe:
                self.etats["va_station"].cible = cible
                self._bascule("va_station")             # « va te coucher » / bouton : il rentre a sa station
        elif quoi == "ronde":
            if self._ronde_possible():
                self._bascule("ronde")
        elif quoi == "tresor":
            if self._ronde_possible():
                self._bascule("tresor")                 # chasse au tresor : il fouille piece par piece
        elif quoi == "cherche_balle":
            cible = self._balle_sur_plan()
            if cible is not None:
                self.etats["va_balle"].cible = cible
                self._bascule("va_balle")
        elif quoi == "assis" and not self.ctx.sitting:
            self._bascule("assis_demande")
        elif quoi == "debout" and self.courant.nom == "assis_demande":
            self.fin_etat = self.t_etat
        elif quoi == "bravo":
            self.humeur.eveil = min(1.0, self.humeur.eveil + 0.1)
            self._bascule("compliment")
        elif quoi == "danse":
            self.etats["danse"].bpm, self.etats["danse"].entrain, self.etats["danse"].son = 100, 1.0, "chirp"
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
        """Ou se cacher : sur le plan, une vraie cachette (derriere un meuble, invisible d'ici) ; sinon un coin appris
        (sieste ou observation) a 1-4 m ; sinon droit devant."""
        self.etats["cache_cache"].cible_plan = None
        pos = self.ctx.extras.get("position")
        p = pos.pose() if pos is not None else None
        if p is not None and pos.plan is not None:
            import numpy as np
            cachette = plan_vie.cachette(pos.plan, p[:2], np.random.default_rng(self._rng_vie.randrange(1 << 30)))
            if cachette is not None:
                self.etats["cache_cache"].cible_plan = cachette
                self.etats["cache_cache"].cible = None
                return
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
        if not permises:
            return None
        poids = [self.succes.poids(n) for n in permises]
        if any(abs(w - 1.0) > 1e-9 for w in poids):
            return self.rng.choices(permises, weights=poids)[0]      # cabotinage : ce qui fait rire revient
        return self.rng.choice(permises)

    def _choisit_suivant(self):
        force = getattr(self, "suivant_force", None)
        if force:
            self.suivant_force = None
            if (self.discret or self.timidite() > 0.0) and (
                    force in self.INITIATIVES_BRUYANTES or getattr(self.etats[force], "taquinerie", False)):
                force = None                    # un appel en cours, un visiteur : pas de jeu ni de blague enchaines
            else:
                return force
        if self.surchauffe:
            return "nap"                        # servos trop chauds : repos assis, jamais de marche, jusqu'a refroidir
        if self.t_global < self.recharge_jusqua and self.courant.nom in ("nap", "accoste", "etirement"):
            if self._batterie_pct is None or self._batterie_pct < 90:
                return "nap"                    # recharge anticipee, sur sa station
            self.recharge_jusqua = -1e9
        if self.mode_calme or self.t_global < self.veille_jusqua:
            return "nap"                        # sieste prolongee, assis : interrupteur calme, ou veille apres des chutes
        h = self.humeur
        batterie_basse = self._batterie_pct is not None and self._batterie_pct < self.BATTERIE_BASSE_PCT
        if self.vacarme and self.courant.nom != "va_au_coin":
            return "nap"                        # tant que dure le vacarme, il reste assis a l'ecart
        if h.energie < self.SEUIL_SIESTE or batterie_basse:
            # fatigue "jouee" OU vraie batterie basse : meme reponse (repos) - dans son coin favori s'il est connu et
            # pas trop loin (sauf batterie basse : on ne gaspille pas les derniers pourcents a marcher)
            if self.courant.nom not in ("nap", "va_au_coin", "va_chargeur"):
                if batterie_basse:
                    # batterie basse : sa station sur le plan s'il sait ou il est ; sinon le chargeur appris
                    station = self._station_cible()
                    if station is not None and self.courant.nom not in ("va_station", "accoste"):
                        self.etats["va_station"].cible = station
                        return "va_station"
                    if self.chargeur is not None and self._atteignable(self.chargeur, (0.3, 4.0)):
                        self.etats["va_chargeur"].cible = self.chargeur
                        return "va_chargeur"
                else:
                    coin = self._coin_atteignable()
                    if coin is not None:
                        self.etats["va_au_coin"].cible = coin
                        return "va_au_coin"
            if self._nid_possible(batterie_basse):
                self.derniere_fois["nid"] = self.t_global
                return "nid"                    # deux tours sur lui-meme, puis la sieste
            return "nap"
        if self.discret:
            return self.rng.choice(("chill", "chill", "look"))   # quelqu'un telephone : il reste tranquille, sans bruit
        social = self._presence_avant_la_prise()
        if social is not None:
            return social
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
        seul = self._besoin_de_solitude()
        if seul is not None:
            return seul
        if self._heure_de_la_ronde():
            return "ronde"
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
                piece = self._piece_a_rejoindre() if self.presents else None
                if piece is not None:
                    self.etats["va_piece"].cible = piece
                    return "va_piece"                   # d'abord la piece ou quelqu'un est (capteurs HA)
                return "cherche_attention"
            if (self.ignores >= 2 and self.presents and self.timidite() == 0.0
                    and self.t_global - self.derniere_fois.get("boude", -1e9) >= 7200.0 and self.rng.random() < 0.5):
                self.derniere_fois["boude"] = self.t_global
                return "boude"                  # ignore deux fois : il boude (une caresse le reconcilie)
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
        porte = self._attente_porte()
        if porte is not None:
            return porte
        rituel = self._rituel_du_moment()
        if rituel is not None:
            return rituel
        if self._hoquet_possible():
            self.derniere_fois["hoquet"] = self.t_global
            return "hoquet"
        doudou = self._va_doudou()
        if doudou is not None:
            return doudou
        soleil = self._bain_de_soleil()
        if soleil is not None:
            return soleil
        avant = self._recharge_avant()
        if avant is not None:
            return avant
        habitude = self._habitude_du_moment()
        if habitude is not None:
            return habitude
        repas = self._repas_maintenant()
        if repas is not None:
            return repas
        if self.rng.random() < self.P_SOUVENIR and h.energie > 0.4 and self.ctx.extras.get("tof") is not None:
            lieu = self.exploration.coin_favori("bon", self.t_global)
            if (lieu is not None and self._atteignable(lieu, (0.8, 4.0))
                    and self.exploration._poids_activite(self._case(lieu), "mauvais", self.t_global) < 1.0):
                self.etats["va_souvenir"].cible = lieu
                return "va_souvenir"
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
                poids = [self.succes.poids(g) for g in gags]
                if any(abs(w - 1.0) > 1e-9 for w in poids):
                    return self.rng.choices(gags, weights=poids)[0]
                return self.rng.choice(gags)
        veille_balle = self.ctx.extras.get("balle")
        b = veille_balle.position() if veille_balle is not None else None
        if (b is not None and 0.06 <= b[0] <= 0.25 and abs(b[1]) <= 0.10 and self.rng.random() < self.P_MIME_VOL
                and self.malice.permise(self, "mime_vol")):
            return "mime_vol"
        poids = {"look": 0.4, "turn": 0.2 + 0.3 * h.energie,
                 "wander": ((0.15 + 0.4 * h.energie * (0.5 + h.eveil)) * self.MARCHE_PAR_METEO.get(self.meteo, 1.0)
                            * self.perso.envie_promenade() * (0.8 if self.saison() == "hiver" else 1.0))}
        # Initiative rare et surprenante (principe Pollen : un duo surprise est un plaisir, un juke-box non) :
        # faible probabilite, et jamais deux fois le meme geste en moins de DELAI_RARE secondes.
        for nom, p in self.RARES.items():
            if self.t_global - self.derniere_fois.get(nom, -1e9) >= self.DELAI_RARE:
                poids[nom] = p * self.succes.poids(nom)
        noms = list(poids)
        return self.rng.choices(noms, weights=[poids[n] for n in noms])[0]

    def _bascule(self, nom):
        if self.courant.nom == "ecoute" and nom != "ecoute" and self.differes:
            self.evenements.extend(self.differes)      # fin de conversation (ou delai depasse) : on rejoue ce qui attendait
            self.differes = []
        if nom in self.RARES:
            self.derniere_fois[nom] = self.t_global
        if self.courant.nom == "hoquet" and nom in ("startle", "son_bref", "surpris", "petarades"):
            self.suivant_force = "gueri"        # une bonne surprise fait passer le hoquet
        if (nom in self.SPECTACLE or getattr(self.etats.get(nom), "taquinerie", False)) and self.presents:
            self.succes.joue(nom, self.t_global)   # un « numero » devant quelqu'un : on guette les rires
        self.courant.sort(self)
        self._desarme_peripherie()              # avant l'entree : un jeu peut armer la veille mouvement pour lui
        if nom == "accueil":
            self.t_dernier_accueil = self.t_global
            if self._derniere_position is not None:   # la ou l'on accueille : l'entree (moyenne glissante)
                x, y = self._derniere_position
                self.entree = (x, y) if self.entree is None else (0.7 * self.entree[0] + 0.3 * x, 0.7 * self.entree[1] + 0.3 * y)
        if self._derniere_position is not None and (nom in self.BONS or nom in self.MAUVAIS):
            sorte, poids = ("bon", self.BONS[nom]) if nom in self.BONS else ("mauvais", self.MAUVAIS[nom])
            self.exploration.preference(*self._derniere_position, sorte, poids, self.t_global)
        if getattr(self.etats[nom], "taquinerie", False):
            self.malice.noter(self, nom)
            self.perso.vit("taquinerie")
        experience = self.EXPERIENCES_PAR_ETAT.get(nom)
        if experience:
            self.perso.vit(experience)
        self.courant = self.etats[nom]
        self._previent(f"etat:{nom}")
        self._sons_etat = set()
        self.courant.entre(self)
        self.t_etat = 0.0
        self.fin_etat = self.courant.duree(self)
        self.journal.append((round(self.t_global, 1), nom,
                             round(self.humeur.energie, 2), round(self.humeur.eveil, 2)))
        if len(self.journal) > self.JOURNAL_MAX:
            del self.journal[:self.JOURNAL_MAX // 2]    # des mois de vie : la memoire du canard n'est pas infinie
        self._compte_du_jour(nom)
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
        prec = getattr(self, "_tete_prec", None)
        # « tete immobile » a la respiration pres (vivant.vie_au_repos : quelques centiemes de radian, lents)
        if (tete is None) != (prec is None) or (tete is not None and max(abs(a - b) for a, b in zip(tete, prec)) > 0.06):
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
        h = self.horloge()                      # (meme cle de jour que note_repos)
        self.diagnostic.servos.note_chaleur(f"{getattr(h, 'tm_year', 0)}-{getattr(h, 'tm_yday', 0):03d}", moteurs)
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
    INITIATIVES_BRUYANTES = {"wander", "zoomies", "balle", "soleil", "cache_cache", "danse", "jour_special", "fier",
                             "salut", "bravo", "cherche_attention", "va_observer", "picore"}
    JOURNAL_MAX = 20000
    # Journal de bord du jour (Home Assistant : sensor.microduck_journal) : ce qu'il a fait depuis minuit
    CATEGORIES_JOUR = {"wander": "promenades", "va_au_coin": "promenades", "nap": "siestes",
                       "balle": "jeux", "soleil": "jeux", "cache_cache": "jeux", "jeu_solitaire": "jeux",
                       "danse": "danses", "caresse": "caresses", "accueil": "accueils", "zoomies": "folles_courses"}

    # Mode garde (opt-in : [cerveau] garde = true) : maison VIDE d'apres HA, il entend une voix, un choc, on frappe ->
    # "garde:<type>" pour pont_ha, qui envoie l'evenement HA "microduck_garde". Rien que le TYPE de son, jamais le son.
    SONS_GARDE = {"voix": "voix", "intonation": "voix", "discussion_longue": "voix", "silence_conversation": "voix",
                  "bruit": "choc", "petarades": "choc", "son_bref": "bruit", "toc_porte": "porte"}
    GARDE_DELAI_S = 600.0
    REPOS_GARDE = ("chill", "look", "nap")

    def _veille_garde(self, base):
        type_son = self.SONS_GARDE.get(base)
        if (type_son is None or not self.ctx.extras.get("garde") or not self.presence_suivie or self.presents
                or self.presence_inconnue
                or self.t_global - self.derniere_fois.get(f"garde:{type_son}", -1e9) < self.GARDE_DELAI_S):
            return
        if (self.tombe or self.courant.nom not in self.REPOS_GARDE
                or time.monotonic() - getattr(self.ctx, "t_dernier_son", -1e9) < 5.0):
            return                              # ses propres sons, ses pas, une chute : ce n'est pas un intrus
        self.derniere_fois[f"garde:{type_son}"] = self.t_global
        print(f"[{self.t_global:6.1f}s] garde : {type_son} entendu, personne a la maison", flush=True)
        self._previent(f"garde:{type_son}")

    def _change_de_jour(self):
        """Le journal du jour repart de zero a minuit (meme s'il dort) ; il est garde dans la memoire du canard."""
        h = self.horloge()
        jour = getattr(h, "tm_yday", None)
        mem = self.ctx.extras.get("memoire")
        d = mem.donnees.setdefault("journal_jour", {}) if mem is not None and hasattr(mem, "donnees") else None
        if d and d.get("jour") is not None and d.get("jour") != jour and d.get("compte"):
            # le jour d'avant part dans l'historique (bilan de la semaine dans l'application), 60 jours au plus
            hist = mem.donnees.setdefault("historique_jours", [])
            hist.append({"date": d.get("date"), "compte": dict(d["compte"])})
            del hist[:-self.HISTORIQUE_JOURS]
            d["compte"] = {}
        if getattr(self, "_jour_compte", None) is None and d and d.get("jour") == jour:
            self.du_jour = dict(d.get("compte", {}))      # redemarrage dans la journee : on reprend la matinee
        elif getattr(self, "_jour_compte", None) != jour:
            self.du_jour = {}
        self._jour_compte = jour
        if d is not None:
            d["jour"], d["compte"] = jour, self.du_jour
            try:
                d["date"] = time.strftime("%Y-%m-%d", h)
            except (TypeError, ValueError):
                d["date"] = None

    HISTORIQUE_JOURS = 60

    def semaine(self):
        """Les 6 jours precedents gardes en memoire, puis aujourd'hui : [{"date", "compte"}] (bilan de l'application)."""
        mem = self.ctx.extras.get("memoire")
        hist = list((mem.donnees.get("historique_jours") or [])[-6:]) if mem is not None and hasattr(mem, "donnees") else []
        d = (mem.donnees.get("journal_jour") or {}) if mem is not None and hasattr(mem, "donnees") else {}
        return hist + [{"date": d.get("date"), "compte": dict(getattr(self, "du_jour", {}) or {})}]

    def _compte_du_jour(self, nom):
        self._change_de_jour()
        cat = self.CATEGORIES_JOUR.get(nom) or ("blagues" if getattr(self.etats[nom], "taquinerie", False) else None)
        if cat:
            self.du_jour[cat] = self.du_jour.get(cat, 0) + 1
    ABRI_PETARDS_S = 600.0
    ASPI_MEFIANT, ASPI_FAMILIER = 0.3, 0.7     # familiarite (memoire.py) avec l'aspirateur

    def _presence_avant_la_prise(self):
        """ROADMAP "Cherche la presence humaine plutot que la prise" : batterie faible mais pas critique, quelqu'un a la
        maison -> il va d'abord la ou l'on s'occupe de lui (coin "social" appris), une fois par decharge ; le chargeur
        ne vient qu'en dessous de BATTERIE_BASSE_PCT."""
        pct = self._batterie_pct
        if pct is None or pct >= self.BATTERIE_FAIBLE_PCT:
            if pct is None or pct >= self.BATTERIE_FAIBLE_PCT + 10.0:
                self._social_fait = False       # vraiment rechargee (hysteresis : la tension oscille sous charge)
            return None
        if (getattr(self, "_social_fait", False) or pct < self.BATTERIE_BASSE_PCT or not self.presents
                or self.ctx.extras.get("tof") is None or self.surchauffe):
            return None
        self._social_fait = True
        coin = self.exploration.coin_favori("social", self.t_global)
        if coin is None or not self._atteignable(coin, (0.5, 3.0)):
            return None
        self.etats["va_social"].cible = coin
        self.etats["cherche_attention"].cible = "humain"    # a l'arrivee : chercher l'attention de quelqu'un
        return "va_social"

    def _sur_info_maison(self, base, detail):
        if base == "temperature_ext":
            try:
                self.temperature_ext = float(detail)     # temperature exterieure (HA) : la saison ressentie
            except ValueError:
                pass
        elif base == "presence":
            # etat initial lu dans HA au demarrage (pont_ha.lire_presence_initiale) : ni accueil ni rituel
            qui, _, ou = detail.partition("|")
            (self.presents.add if ou == "home" else self.presents.discard)(qui)
            (self.presence_inconnue.add if ou == "inconnu" else self.presence_inconnue.discard)(qui)
            self.presence_suivie = True

    def _sur_telecommande(self, base, detail):
        """Application Microduck : petit pas ou regard guides. Jamais en mode calme, a terre, dans les bras ou pendant
        l'alarme ; un pas en avant exige le capteur de distance (PasGuide verifie ensuite chaque trame)."""
        if self.mode_calme or self.tombe or self.porte or self.courant.nom == "alarme":
            return
        if base == "regard":
            rg = self.etats["regard_guide"]
            if self.courant.nom != "regard_guide":
                rg.lacet = rg.tangage = 0.0
            rg.oriente(detail)
            if self.courant.nom == "regard_guide":
                self.fin_etat = self.t_etat + rg.duree(self)      # chaque cran prolonge la pose
            else:
                self._bascule("regard_guide")
            return
        if detail not in ("avance", "gauche", "droite"):
            return
        if detail == "avance" and self.ctx.extras.get("tof") is None:
            return
        if self.ctx.sitting:
            self.ctx.toggle_sit()               # on le releve d'abord
        self.suivant_force = None
        self.etats["pas_guide"].mouvement = detail
        self._bascule("pas_guide")

    def _sur_vacarme(self, fort):
        """Ambiance tres bruyante et prolongee (fete, dispute, travaux ; audio.py) : il se retire dans son coin de sieste
        s'il le connait, sinon il s'assoit sur place, et y reste tant que dure le vacarme - ses propres limites."""
        if fort == self.vacarme:
            return
        self.vacarme, self._t_vacarme = fort, self.t_global
        print(f"[{self.t_global:6.1f}s] {'trop de bruit : il se retire' if fort else 'le calme revient'}", flush=True)
        if not fort or self.mode_calme or self.courant.nom in ("nap", "alarme", "porte", "ecoute", "va_au_coin"):
            return
        coin = self._coin_atteignable()
        if coin is not None:
            self.etats["va_au_coin"].cible = coin
        self.suivant_force = "va_au_coin" if coin is not None else "nap"
        self._bascule("retrait")
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

    def _sur_visiteur(self, arrive, qui=None):
        """Un visiteur : inconnu (sonnette puis voix, sans nom) -> pleinement timide ; nomme par HA (declencheur
        "visiteur", ex. la personne qui fait le menage, un grand-parent) -> sa familiarite (memoire.py) grandit a chaque
        visite et la timidite de depart baisse d'autant : ni inconnu, ni habitant (ROADMAP "Visiteur recurrent")."""
        if not arrive:
            self.visite, self._apprivoise = None, True
            return
        if self.visite is not None and self.t_global - self.visite <= self.TIMIDE_S:
            return
        mem = self.ctx.extras.get("memoire")
        fam = 0.0
        if qui and mem is not None and hasattr(mem, "familiarite"):
            fam = mem.familiarite(qui)
            if hasattr(mem, "rencontre"):
                mem.rencontre(qui)
        # tout jeune, il est plus timide (vivant.timidite_jeunesse) : la timidite dure jusqu'a 1,5 fois plus longtemps
        self.timidite_depart = max(0.0, 1.0 - fam) * (1.0 + 0.5 * self.perso.jeunesse)
        if self.timidite_depart < 0.15:
            print(f"[{self.t_global:6.1f}s] {qui} : un visiteur bien connu, pas de timidite", flush=True)
            return
        self.visite, self._apprivoise = self.t_global, self.timidite_depart < 0.4
        print(f"[{self.t_global:6.1f}s] visiteur {qui or 'inconnu'} : timide ({self.timidite_depart:.1f})", flush=True)

    def timidite(self):
        """timidite_depart (1 pour un inconnu) a l'arrivee du visiteur, 0 au bout de TIMIDE_S."""
        if self.visite is None:
            return 0.0
        return max(0.0, getattr(self, "timidite_depart", 1.0) - (self.t_global - self.visite) / self.TIMIDE_S)

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
        if self._rng_babil.random() < dt * self.vivacite() * self.perso.bavardage() / self.BABIL_MOYEN_S:
            self._t_babil = self.t_global
            self._dernier_babil = self.perso.choisit_son(self._rng_babil)
            self.ctx.sound(self._dernier_babil)

    REPONSE_BABIL_S = 30.0

    def _reponse_au_babil(self):
        """Quelqu'un reagit (caresse, main, appel, voix...) peu apres un petit son gratuit : ce son-la plait ici."""
        tag = getattr(self, "_dernier_babil", None)
        if tag is not None and self.t_global - self._t_babil <= self.REPONSE_BABIL_S:
            self.perso.renforce_son(tag)
            self._dernier_babil = None

    def _surveille_peripherie(self):
        """Pendant chill (tete immobile), la veille mouvement tourne doucement ; un mouvement AU BORD de l'image (petite
        tache : pas son propre mouvement, qui fait bouger toute l'image) -> un coup d'oeil de ce cote."""
        veille = self.ctx.extras.get("mouvement")
        if veille is None or not hasattr(veille, "dernier_centre"):
            return
        if (self.courant.nom != "chill" or not getattr(self.courant, "aux_aguets", True) or self.t_etat < 1.5
                or self.mode_calme or self.discret or self.cpu_chaud
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
            if self.habituation.noter("mouvement", self.t_global) < 0.3:
                return                          # ca bouge encore la-bas : il s'y est habitue
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
        v = 1.0
        for (h0, v0), (h1, v1) in zip(self.CIRCADIEN, self.CIRCADIEN[1:]):
            if h0 <= x <= h1:
                v = v0 + (v1 - v0) * (x - h0) / (h1 - h0)
                break
        saison = self.saison()
        if saison == "ete":                     # matinal avant la chaleur, ramolli l'apres-midi
            v *= 1.15 if 7 <= x < 11 else 0.8 if 13 <= x < 17 else 1.0
        elif saison == "hiver":
            v *= 0.9                            # cocooning
        return v

    # Personnalite un peu saisonniere (ROADMAP "Ambiance du foyer") : d'apres la temperature exterieure de HA si on
    # l'a (appareil de type "temperature"), sinon d'apres le mois. Opt-in avec le circadien (extras["circadien"]).
    HIVER_C, ETE_C = 8.0, 24.0

    def saison(self):
        if not self.ctx.extras.get("circadien"):
            return "mi_saison"
        t = getattr(self, "temperature_ext", None)
        if t is not None:
            return "hiver" if t < self.HIVER_C else "ete" if t > self.ETE_C else "mi_saison"
        mois = getattr(self.horloge(), "tm_mon", None)
        return "hiver" if mois in (12, 1, 2) else "ete" if mois in (6, 7, 8) else "mi_saison"

    def facteur_sieste(self):
        """L'hiver, les siestes s'allongent (cocooning) ; un jour paresseux aussi."""
        return (1.3 if self.saison() == "hiver" else 1.0) * personnage.HUMEURS_JOUR[self.humeur_jour][3]

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
        """Une fois par jour, au premier moment de repos apres le demarrage (opt-in : extras["autotest"], canard.py) ;
        ou A LA DEMANDE (bouton HA "lancer le diagnostic", evenement "diagnostic"), meme si c'est deja fait aujourd'hui."""
        jour = getattr(self.horloge(), "tm_yday", None)
        if self.diag_demande:
            if self.mode_calme or self.tombe or self.courant.nom not in ("chill", "look", "jeu_solitaire"):
                return                          # au prochain moment de repos (jamais en plein jeu ni assis en calme)
            self.diag_demande = False
            self._jour_autotest = jour
            self._bascule("autotest")
            return
        if not self.ctx.extras.get("autotest"):
            return
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
            elif nom.startswith("ton:"):
                pass                            # le ton d'un instant : rejoue plus tard, il serait hors contexte
            else:
                garde.append(nom)
        self.evenements = garde

    def _surveille_caresse(self, state):
        joints = state.get("joints")
        if not joints or len(joints) < 9:
            return
        immobile = self.courant.nom == "chill" or (     # sieste : pas pendant qu'il s'assoit ni qu'il se releve
            self.courant.nom == "nap" and 6.0 <= self.t_etat < self.fin_etat - 4.0) or (
            self.courant.nom == "signal" and self.etats["signal"].au_repos(self.t_etat))   # entre deux cycles
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

    routines = ()                               # [(heure, minute, jours (0 = lundi), evenement)] : reglages.py

    def _verifie_routines(self):
        """Routines programmees dans l'application : a l'heure dite, les jours dits, l'evenement part une fois."""
        h = self.horloge()
        cle = (getattr(h, "tm_yday", None), getattr(h, "tm_hour", None), getattr(h, "tm_min", None))
        if cle == getattr(self, "_minute_routines", None):
            return
        self._minute_routines = cle
        for heure, minute, jours, evt in self.routines:
            if heure == cle[1] and minute == cle[2] and getattr(h, "tm_wday", 0) in jours:
                print(f"[{self.t_global:6.1f}s] routine {heure:02d}:{minute:02d} : {evt}", flush=True)
                self.evenement(evt)

    HUMEUR_PAS_S = 15 * 60
    HUMEUR_POINTS = 7 * 24 * 4                  # une semaine, un point par quart d'heure

    # -- personnage.py ----------------------------------------------------------------------------------------------
    def _nommable(self):
        """Une seule personne, familiere : il peut « dire son nom » (sa suite de sons a lui)."""
        mem = self.ctx.extras.get("memoire")
        if len(self.presents) != 1 or mem is None or not hasattr(mem, "familiarite") or self.mode_calme or self.discret:
            return False
        return mem.familiarite(next(iter(self.presents))) >= 0.6

    def _sur_rire(self):
        """On rit (audio.py) : si c'est de son numero, il cabotine (et le refera) ; sinon le rire le gagne."""
        self.humeur.eveil = min(1.0, self.humeur.eveil + 0.2)
        auteur = self.succes.reaction(self.t_global)
        if self.mode_calme or self.discret or self.courant.nom not in ("chill", "look", "compagnie", "attentif",
                                                                       "wander", "repond") + self.SPECTACLE:
            return
        if self.courant.nom in self.SPECTACLE:
            if auteur is not None:
                self.suivant_force = "cabotine"     # il finit son numero, puis prend un air fier
            return
        if auteur is not None:
            self.derniere_fois["cabotine"] = self.t_global
            self._bascule("cabotine")           # « c'est moi qui ai fait ca ! »
        elif self.t_global - self.derniere_fois.get("rit", -1e9) >= 300.0:
            self.derniere_fois["rit"] = self.t_global
            self._bascule("rit")                # le rire est contagieux

    def _jour(self):
        return int(self.ctx.extras.get("mur", time.time)() // 86400)

    def _note_rituel(self, qui):
        mem = self.ctx.extras.get("memoire")
        if mem is not None and isinstance(getattr(mem, "donnees", None), dict):
            personnage.noter_rituel(mem.donnees, qui, self.horloge().tm_hour, self._jour())

    def _rituel_du_moment(self):
        """Une habitude avec quelqu'un a cette heure-ci (une caresse le soir...) : il vient la reclamer."""
        mem = self.ctx.extras.get("memoire")
        if (mem is None or not isinstance(getattr(mem, "donnees", None), dict) or not self.presents
                or self.timidite() > 0.0 or self.humeur.energie < 0.3):
            return None
        jour, heure = self._jour(), self.horloge().tm_hour
        for qui in sorted(self.presents):
            if (jour, qui) in self._rituels_faits or not personnage.rituel_maintenant(mem.donnees, qui, heure, jour):
                continue
            self._rituels_faits.add((jour, qui))
            print(f"[{self.t_global:6.1f}s] c'est l'heure du calin avec {qui}", flush=True)
            self.etats["cherche_attention"].cible = "humain"
            self.suivant_force = "cherche_attention"
            if self._nommable():
                self.etats["nomme"].qui, self.etats["nomme"].ensuite = qui, "cherche_attention"
                return "nomme"                  # il t'appelle par « ton nom », puis vient te voir
            return "reclame"
        return None

    def _hoquet_possible(self):
        if self.mode_calme or self.discret or self.t_global - self.derniere_fois.get("hoquet", -1e9) < 3 * 3600.0:
            return False
        p = self.P_HOQUET * (5.0 if self.t_global - self.derniere_fois.get("repas", -1e9) < 600.0 else 1.0)
        return self._rng_vie.random() < p

    def _doudou(self):
        """Sa balle devient son doudou une fois qu'il y a joue quelques parties (memoire)."""
        mem = self.ctx.extras.get("memoire")
        st = (getattr(mem, "donnees", None) or {}).get("balle") if mem is not None else None
        return isinstance(st, dict) and st.get("parties", 0) >= personnage.DOUDOU_PARTIES

    def _va_doudou(self):
        vb = self.ctx.extras.get("balle")
        if (vb is None or not hasattr(vb, "position") or self.ctx.extras.get("tof") is None or not self._doudou()
                or self.t_global - self.derniere_fois.get("doudou", -1e9) < 1800.0
                or self._rng_vie.random() >= self.P_DOUDOU):
            return None
        b = vb.position()
        o = (self.ctx.state or {}).get("odom")
        if b is None or o is None or not 0.4 <= math.hypot(*b) <= 2.5:
            return None
        d = math.hypot(*b)
        k = max(0.0, d - 0.25) / d               # il s'arrete a 25 cm de sa balle
        cap = o.get("yaw") or 0.0
        x0, y0 = o["position"][0], o["position"][1]
        bx, by = b[0] * k, b[1] * k
        self.derniere_fois["doudou"] = self.t_global
        self.etats["va_doudou"].cible = (x0 + bx * math.cos(cap) - by * math.sin(cap),
                                         y0 + bx * math.sin(cap) + by * math.cos(cap))
        return "va_doudou"

    def _nid_possible(self, batterie_basse):
        if (batterie_basse or self.ctx.sitting or self.ctx.extras.get("tof") is None or self.courant.nom == "nid"
                or self.t_global - self.derniere_fois.get("nid", -1e9) < 3600.0):
            return False
        return self._rng_vie.random() < self.P_NID

    def _verifie_soleil(self):
        """Bain de soleil : en journee, au repos, toutes les 10 min, une image : une tache de soleil au sol ? Mesure
        dans un fil (camera locale) ; le resultat sert au prochain passage par chill."""
        mesure = self.ctx.extras.get("soleil")
        if mesure is None or self.t_global - self._t_soleil < self.SOLEIL_PERIODE_S:
            return
        h = self.horloge().tm_hour
        if not 9 <= h < 19 or self.courant.nom != "chill" or self.mode_calme or self.tombe:
            return
        self._t_soleil = self.t_global

        def lire():
            try:
                self._soleil_vu = mesure()
            except Exception:
                self._soleil_vu = None
        if self.ctx.extras.get("soleil_synchrone"):
            lire()
        else:
            threading.Thread(target=lire, daemon=True).start()

    def _bain_de_soleil(self):
        vu, self._soleil_vu = self._soleil_vu, None
        if (self.ctx.extras.get("tof") is None or self.surchauffe
                or self.t_global - self.derniere_fois.get("bain_soleil", -1e9) < 7200.0):
            return None
        pos = self.ctx.extras.get("position")
        p = pos.pose() if pos is not None else None
        mem = self.ctx.extras.get("memoire")
        donnees = getattr(mem, "donnees", None) if mem is not None else None
        h = self.horloge()
        minute = h.tm_hour * 60 + h.tm_min
        if vu is not None:
            self.derniere_fois["bain_soleil"] = self.t_global
            self.etats["bain_soleil"].x_rel = vu[0]
            if p is not None and isinstance(donnees, dict):     # il retient quelle fenetre donne du soleil, et quand
                plan_vie.noter_soleil(donnees, (pos._cle or [None])[0], pos.plan, p[0], p[1], minute)
            return "bain_soleil"
        if p is None or not isinstance(donnees, dict) or not 9 <= h.tm_hour < 19 or self._rng_vie.random() >= 0.3:
            return None
        f = plan_vie.fenetre_au_soleil(donnees, (pos._cle or [None])[0], pos.plan, minute)
        cible = plan_vie.devant_la_fenetre(pos.plan, f) if f is not None else None
        if cible is None or math.hypot(cible[0] - p[0], cible[1] - p[1]) < 0.8:
            return None
        self.derniere_fois["bain_soleil"] = self.t_global
        self.etats["va_soleil"].cible = cible
        return "va_soleil"                      # sans voir la tache : il sait qu'a cette heure, le soleil est la

    # -- le plan de la maison (position.py, etats_plan.py) ----------------------------------------------------------------
    def _balle_sur_plan(self):
        """Ou il a vu sa balle en dernier (sur le plan du lieu actuel) -> un point 40 cm avant elle, ou None."""
        pos = self.ctx.extras.get("position")
        p = pos.pose() if pos is not None else None
        b = self.balle_plan
        if b is None:
            mem = self.ctx.extras.get("memoire")
            b = ((getattr(mem, "donnees", None) or {}).get("balle_plan") if mem is not None else None)
        if p is None or not b or b[0] != (pos._cle or [None])[0]:
            return None
        return plan_vie.avant(p[:2], (b[1], b[2]), 0.4)

    def _point_imprimante(self, nom_imprimante):
        """Le point du plan « imprimante » (ou « imprimante <nom> », ou le nom de l'imprimante) -> devant, ou None."""
        pos = self.ctx.extras.get("position")
        p = pos.pose() if pos is not None else None
        if p is None or pos.plan is None or self.mode_calme or self.tombe:
            return None
        nom = str(nom_imprimante or "").lower()
        candidats = [(k, v) for k, v in pos.plan.points.items()
                     if k.lower() in (nom, f"imprimante {nom}") or (k.lower().startswith("imprimante") and not nom)]
        if not candidats:
            candidats = [(k, v) for k, v in pos.plan.points.items() if k.lower().startswith("imprimante")]
        if not candidats:
            return None
        return float(candidats[0][1][0]), float(candidats[0][1][1])

    def _recharge_avant(self):
        """Il passe a sa station AVANT un grand moment (un retour habituel dans 15-45 min, la ronde dans l'heure) si sa
        batterie est a moins de 50 % : en forme pour l'accueil."""
        if (self._batterie_pct is None or self._batterie_pct >= 50 or self._station_cible() is None
                or self.t_global - self.derniere_fois.get("recharge_avant", -1e9) < 7200.0):
            return None
        h = self.horloge()
        maintenant = h.tm_hour * 60 + h.tm_min
        bientot = False
        mem = self.ctx.extras.get("memoire")
        if mem is not None and isinstance(getattr(mem, "donnees", None), dict):
            for qui in (mem.donnees.get("retours") or {}):
                prevu = vivant.retour_prevu(mem.donnees, qui, getattr(h, "tm_wday", 0) >= 5)
                if qui not in self.presents and prevu is not None and 15 <= prevu - maintenant <= 45:
                    bientot = True
        ronde = self.ctx.extras.get("ronde")
        if ronde and self.ctx.extras.get("garde") and 0 <= ronde[0] * 60 + ronde[1] - maintenant <= 60:
            bientot = True
        if not bientot:
            return None
        self.derniere_fois["recharge_avant"] = self.t_global
        self.recharge_jusqua = self.t_global + 1800.0
        self.etats["va_station"].cible = self._station_cible()
        print(f"[{self.t_global:6.1f}s] il passe a sa station avant ({self._batterie_pct:.0f} %)", flush=True)
        return "va_station"

    def _habitude_du_moment(self):
        """Sa place a ce moment de la journee (appris : la ou il se repose le plus a cette heure), parfois."""
        pos = self.ctx.extras.get("position")
        p = pos.pose() if pos is not None else None
        if p is None or self._rng_vie.random() >= 0.05 or self.humeur.energie < 0.35:
            return None
        lieu = (pos._cle or [None])[0]
        f = self.lieux_heure.favori(lieu, self.horloge().tm_hour)
        if f is None or math.hypot(f[0] - p[0], f[1] - p[1]) < 1.2 or pos.plan.dans_zone_interdite(*f):
            return None
        self.etats["va_habitude"].cible = f
        return "va_habitude"

    def _plan_vie_tick(self, state):
        """Une fois par seconde : ce qu'il apprend du plan (sa place selon l'heure, sa balle) et les changements du decor."""
        pos = self.ctx.extras.get("position")
        if pos is None or self.t_global - self._t_lieu_note < 1.0:
            return
        dt, self._t_lieu_note = min(5.0, self.t_global - self._t_lieu_note), self.t_global
        p = pos.pose()
        if p is None:
            return
        lieu = (pos._cle or [None])[0]
        if self.courant.nom in ("chill", "look", "nap", "compagnie", "au_soleil", "solitude"):
            self.lieux_heure.noter(lieu, self.horloge().tm_hour, p[0], p[1], dt)
        b = self.vus.get("balle")
        if b is not None and (self.balle_plan is None or b[0] > self.balle_plan[3]):
            bp = pos.vers_plan(b[1], b[2])
            if bp is not None:
                self.balle_plan = (lieu, round(bp[0], 2), round(bp[1], 2), b[0])
                mem = self.ctx.extras.get("memoire")
                if mem is not None and isinstance(getattr(mem, "donnees", None), dict):
                    mem.donnees["balle_plan"] = list(self.balle_plan)
        while getattr(pos, "a_signaler", None):
            x, y = pos.a_signaler.pop(0)
            self._previent(f"changement:{x:.2f}|{y:.2f}")
            if (self.courant.nom in ("chill", "look", "wander") and not self.mode_calme and not self.discret
                    and self.t_global - self.derniere_fois.get("va_changement", -1e9) >= 600.0):
                self.derniere_fois["va_changement"] = self.t_global
                self.etats["va_changement"].cible = plan_vie.avant(p[:2], (x, y), 0.4)
                self.objet_nouveau = 0.4
                self._bascule("va_changement")  # tiens, ce n'etait pas la : il va voir

    def _station_cible(self):
        """Point d'approche de sa station sur le plan, s'il sait ou il est ; sinon None."""
        pos = self.ctx.extras.get("position")
        if pos is None or pos.pose() is None or pos.plan is None or not pos.plan.reperes.get("chargeur"):
            return None
        return point_approche(pos.plan.reperes["chargeur"])

    def _ronde_possible(self):
        pos = self.ctx.extras.get("position")
        batterie_ok = self._batterie_pct is None or self._batterie_pct >= self.BATTERIE_BASSE_PCT + 15
        return (pos is not None and pos.pose() is not None and pos.plan is not None and bool(pos.plan.pieces)
                and batterie_ok and not self.tombe and not self.ctx.sitting and self.ctx.extras.get("tof") is not None)

    def _heure_de_la_ronde(self):
        """Ronde du soir : mode garde actif, a l'heure reglee ([cerveau] ronde = "22:30"), une fois par jour."""
        heure = self.ctx.extras.get("ronde")
        if not heure or not self.ctx.extras.get("garde"):
            return False
        h = self.horloge()
        maintenant = h.tm_hour * 60 + h.tm_min
        jour = getattr(h, "tm_yday", None)
        if jour == self._jour_ronde or not 0 <= maintenant - (heure[0] * 60 + heure[1]) <= 30:
            return False
        if not self._ronde_possible():
            return False
        self._jour_ronde = jour
        return True

    def _piece_a_rejoindre(self):
        """Centre de la piece ou un capteur HA a vu quelqu'un recemment (10 min), si ce n'est pas la sienne."""
        pos = self.ctx.extras.get("position")
        if pos is None or pos.pose() is None or pos.plan is None or not self.pieces_occupees:
            return None
        recentes = [(t, n) for n, t in self.pieces_occupees.items() if self.t_global - t <= 600.0]
        if not recentes:
            return None
        nom = max(recentes)[1]
        if nom == pos.piece():
            return None
        from etats_plan import centre
        p = next((q for q in pos.plan.pieces if q.get("nom") == nom and len(q.get("contour") or []) >= 3), None)
        return centre(p["contour"]) if p else None

    # -- vivant III ---------------------------------------------------------------------------------------------------
    def _maj_humeur_jour(self):
        """L'humeur du jour (personnage.humeur_du_jour), tiree une fois par jour ; sans memoire (essais) : normale."""
        if getattr(self.perso, "sauver", None) is None:
            return
        jour = int(self.ctx.extras.get("mur", time.time)() // 86400)
        nom = personnage.humeur_du_jour(self.perso.d.get("naissance", 0), jour)
        if nom != getattr(self, "humeur_jour", None):
            print(f"[{getattr(self, 't_global', 0.0):6.1f}s] humeur du jour : {nom}", flush=True)
        self.humeur_jour = nom
        self.perso.jour = personnage.HUMEURS_JOUR[nom]

    def _envie_de_danser(self, bpm):
        """Ses gouts : une musique qui ne lui plait pas le laisse froid ; celle qu'il aime, il danse avec entrain ; « sa
        chanson », il y va meme s'il vient de danser."""
        danse = self.etats["danse"]
        danse.bpm, danse.entrain, danse.son = bpm, 1.0, "chirp"
        delai = self.DELAI_DANSE_S
        if self.gouts is not None:
            g, chanson = self.gouts.gout(bpm), self.gouts.chanson(bpm)
            if chanson:
                danse.entrain, danse.son, delai = 1.4, "wheee", self.DELAI_DANSE_S / 3
                print(f"[{self.t_global:6.1f}s] sa chanson ! ({bpm} BPM)", flush=True)
            elif g <= -0.5:
                return False                    # ca ne lui plait pas : il ne danse pas
            elif g >= 0.5:
                danse.entrain, danse.son = 1.25, "wheee"
        return self.t_global - self.derniere_fois.get("danse", -1e9) >= delai

    def _besoin_de_solitude(self):
        recentes = [t for t in self.sollicitations if self.t_global - t <= 1800.0]
        seuil = self.SOLLICITATIONS_MAX * (0.5 + self.perso.trait("sociabilite"))
        if (len(recentes) < seuil or self.mode_calme or self.discret
                or self.t_global - self.derniere_fois.get("solitude", -1e9) < 3600.0):
            return None
        self.sollicitations = []
        self.derniere_fois["solitude"] = self.t_global
        print(f"[{self.t_global:6.1f}s] beaucoup de monde autour de lui : il a besoin d'etre un peu seul", flush=True)
        coin = self.exploration.coin_favori("nap", self.t_global)
        if coin is not None and self.ctx.extras.get("tof") is not None and self._atteignable(coin, (0.5, 4.0)):
            self.etats["va_solitude"].cible = coin
            return "va_solitude"
        return "solitude"

    def _verifie_anniversaire(self):
        naissance = self.perso.d.get("naissance") if getattr(self.perso, "sauver", None) is not None else None
        if naissance is None:
            return
        mur = self.ctx.extras.get("mur", time.time)()
        ans = personnage.est_anniversaire(naissance, mur)
        self.anniversaire = ans
        if (not ans or self.perso.d.get("anniversaire_fete") == time.localtime(mur).tm_year
                or self.horloge().tm_hour < 9 or self.mode_calme or self.discret
                or self.courant.nom not in ("chill", "look")):
            return
        self.perso.d["anniversaire_fete"] = time.localtime(mur).tm_year
        print(f"[{self.t_global:6.1f}s] c'est son anniversaire : {ans} an(s) !", flush=True)
        if self.ctx.extras.get("tof") is not None and self.humeur.energie > 0.5:
            self.suivant_force = "zoomies"      # une folle course pour feter ca
        self._bascule("anniversaire")

    def _regarde_le_chat(self, state):
        """Le chat comme modele : il dort -> sieste non loin ; il joue -> ca l'anime."""
        chat = self.ctx.extras.get("chat")
        o = (state or {}).get("odom")
        if chat is None or o is None or self.t_global - self._t_chat_note < 1.0:
            return
        self._t_chat_note = self.t_global
        e = getattr(chat, "estimation", None)
        if not getattr(getattr(chat, "suivi", None), "visible", False) or e is None:
            if self.observateur_chat.points and self.t_global - self.observateur_chat.points[-1][0] > 30.0:
                self.observateur_chat.oublier()
            return
        cap = o.get("yaw") or 0.0
        x0, y0 = o["position"][0], o["position"][1]
        self.observateur_chat.noter(self.t_global, x0 + e[1] * math.cos(cap) - e[2] * math.sin(cap),
                                    y0 + e[1] * math.sin(cap) + e[2] * math.cos(cap))
        etat = self.observateur_chat.etat(self.t_global)
        if etat is None or self.courant.nom not in ("chill", "look") or self.mode_calme or self.discret:
            return
        genre, (cx, cy) = etat
        if (genre == "dort" and self.humeur.energie < 0.75
                and self.t_global - self.derniere_fois.get("sieste_chat", -1e9) >= 7200.0):
            self.derniere_fois["sieste_chat"] = self.t_global
            d = math.hypot(cx - x0, cy - y0)
            if d > 0.9 and self.ctx.extras.get("tof") is not None:
                k = (d - 0.6) / d                       # il s'arrete a 60 cm du chat : pas trop pres
                self.etats["va_chat"].cible = (x0 + (cx - x0) * k, y0 + (cy - y0) * k)
                if self._atteignable(self.etats["va_chat"].cible, (0.3, 4.0)):
                    self._bascule("va_chat")
                    return
            self._bascule("nap")                        # le chat dort : lui aussi
        elif (genre == "joue" and self.humeur.energie > 0.5
              and self.t_global - self.derniere_fois.get("chat_joue", -1e9) >= 1200.0):
            self.derniere_fois["chat_joue"] = self.t_global
            self.humeur.eveil = min(1.0, self.humeur.eveil + 0.3)
            self._bascule("chat_joue")

    def age(self):
        """Jours vecus depuis sa premiere mise en route (vivant.age_jours ; inf sans memoire : adulte)."""
        return vivant.age_jours(self.perso, self.ctx.extras.get("mur", time.time)())

    def _vieillit(self):
        a = self.age()
        self.perso.assurance, self.perso.jeunesse = vivant.assurance_blagues(a), vivant.timidite_jeunesse(a)
        self._maj_humeur_jour()

    def _note_humeur(self):
        """Graphique d'humeur de l'application : energie et eveil, un point par quart d'heure, une semaine (memoire)."""
        mur = self.ctx.extras.get("mur", time.time)()
        if mur - getattr(self, "_t_age", -1e12) >= 600.0:
            self._t_age = mur
            self._vieillit()
        mem = self.ctx.extras.get("memoire")
        if mem is None or not hasattr(mem, "donnees"):
            return
        h = mem.donnees.setdefault("humeur", [])
        if h and mur - h[-1][0] < self.HUMEUR_PAS_S:
            return
        h.append([round(mur), round(self.humeur.energie, 2), round(self.humeur.eveil, 2)])
        del h[:-self.HUMEUR_POINTS]

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
            vb = self.ctx.extras.get("balle")
            if (vb is not None and hasattr(vb, "levee") and vb.levee() and self.courant.nom in ("chill", "look")
                    and not self.mode_calme and self.humeur.energie > 0.3
                    and self.t_global - self.derniere_fois.get("excite", -1e9) >= 120.0):
                self.derniere_fois["excite"] = self.t_global
                self.humeur.eveil = min(1.0, self.humeur.eveil + 0.4)
                self._bascule("excite")         # on tient sa balle en l'air : il trepigne de la tete, va-t-on la lancer ?
            if (self.courant.nom == "wander" and self.t_global - self.derniere_fois.get("mefiant_lieu", -1e9) >= 600.0
                    and self.exploration._poids_activite(self._case(self._derniere_position), "mauvais", self.t_global) >= 2.0):
                self.derniere_fois["mefiant_lieu"] = self.t_global
                self._bascule("mefiant_lieu")   # ici, il a eu peur : il ralentit, mefiant
            if vb is not None and hasattr(vb, "position") and self.t_global - self._t_vu_balle >= 2.0:
                self._t_vu_balle = self.t_global
                b = vb.position()               # (x, y) dans le repere du tronc : -> repere de l'odometrie
                if b is not None:
                    cap = state["odom"].get("yaw") or 0.0
                    x0, y0 = self._derniere_position
                    mur = self.ctx.extras.get("mur", time.time)
                    self.vus["balle"] = (round(mur()), round(x0 + b[0] * math.cos(cap) - b[1] * math.sin(cap), 2),
                                         round(y0 + b[0] * math.sin(cap) + b[1] * math.cos(cap), 2))
        pct = (state.get("battery") or {}).get("percent")      # "battery": null tant que le bus n'a pas repondu
        if pct is not None:
            self._batterie_pct = pct
            if state.get("odom"):
                self._apprend_chargeur(pct, state["odom"]["position"])
        if (state.get("safety") or {}).get("fallen"):
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
            self._change_de_jour()
            self.perso.avance(self.t_global)    # retour lent vers son temperament de base
            jour = getattr(self.horloge(), "tm_yday", None)
            if jour != self.perso.d.get("jour_sons"):     # persistant : un redemarrage ne fait pas deriver
                self.perso.d["jour_sons"] = jour
                self.perso.derive_sons(self._rng_babil)   # sa voix change doucement, jour apres jour
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
        if self.routines:
            self._verifie_routines()
        self._note_humeur()
        self._verifie_autotest()
        self._verifie_jour_special()
        self._verifie_anniversaire()
        self.humeur.avance(dt, self.courant.nom, self.vivacite())
        if self.discret and self.t_global - self._t_discret > self.DISCRET_MAX_S:
            self._discretion(False)
        if self.vacarme and self.t_global - self._t_vacarme > self.DISCRET_MAX_S:
            self._sur_vacarme(False)            # garde-fou : un "vacarme_fin" perdu ne le cloue pas au sol
        self._babille(dt)
        self._surveille_peripherie()
        self._verifie_lumiere()
        self._verifie_soleil()
        self._regarde_le_chat(state)
        self._plan_vie_tick(state)
        flop = self.succes.juge(self.t_global, bool(self.presents))
        if flop is not None:
            print(f"[{self.t_global:6.1f}s] {flop} : tombe a plat", flush=True)
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
