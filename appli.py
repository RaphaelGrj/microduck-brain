#!/usr/bin/env python3
"""Application Microduck : l'interface telephone du canard, SERVIE PAR LE CANARD (ROADMAP "Application Microduck").

Un petit serveur HTTP (bibliotheque standard, aucune dependance) sur le reseau local : il sert l'interface (`interface/`,
HTML + JS sans framework) et une API JSON. Sur le telephone : ouvrir http://<ip-du-canard>:8090 puis "Ajouter a l'ecran
d'accueil".

Regles du projet respectees :
  - le telephone AFFICHE des etats et ENVOIE des commandes ; aucun son ne lui est envoye, et une image seulement si on
    l'a voulu (journal photo : reglage « photos », desactive par defaut ; mode photo) - gardee SUR le canard, montree
    au seul code parent, jamais envoyee ailleurs (ni Home Assistant, ni Internet) ;
  - acces protege par un code d'appairage (`[appli] code` dans ha.toml), et seulement depuis le reseau local ;
  - le cerveau garde la main : les commandes sont des EVENEMENTS mis en file (comme ceux de Home Assistant), traites
    par le cerveau dans sa boucle avec ses garde-fous (jamais de marche sans capteur de distance ni vers un vide...).

API :
  GET  /api/etat            instantane complet (JSON)
  GET  /api/flux?code=...   le meme, en continu (Server-Sent Events, 1 par seconde)
  POST /api/commande        {"commande": "<nom>"} parmi COMMANDES
  GET  /api/carte           carte des zones parcourues depuis le demarrage (repere de l'odometrie)
  GET  /api/lieux           les lieux (lieux.py) ; GET /api/lieu-carte?id=... la carte gardee d'un lieu
  POST /api/lieu            {"action": ..., "id": ..., "nom": ...} (basculer, renommer, archiver, restaurer, ...)
  GET  /api/plan?id=...     le plan definitif d'un lieu (scan du Quest, plan.py) ; POST /api/plan {"id", "nom",
                            "contenu": export Quest ou plan sauvegarde} l'importe (converti sur le canard) ;
                            POST /api/plan-supprimer {"id"} le retire ; POST /api/plan-annoter {"id", "zones",
                            "points"} : zones interdites et points nommes (casque, appli)
  GET  /api/xr              casque : position sur le plan, nuage d'hypotheses, capteur, trajet (position.py)
  POST /api/verite          casque : {"x", "y", "cap", "recaler"} position mesuree -> erreur (et recalage)
  POST /api/aller           {"x", "y"} : « va la » (point du plan)
  GET  /api/jumeau?depuis=T canard jumeau (Quest) : poses des pieces du canard SIMULE (duck-sim), balles, derniers sons ;
                            POST /api/jumeau-balle {"pos", "vel"} la lance ; POST /api/jumeau-caresse le caresse. 404
                            sans simulateur (rien de cela n'existe sur le vrai robot) - jumeau.py
  GET  /api/casque          le casque Quest : connecte ?, son mode, simulateur et scene, adresses a taper pour
                            l'appairer ; POST {"action": "balle" | "chargeur" | "scene", "scene"} (canard jumeau)
  POST /api/casque-demande  (sans code, reseau local) un casque demande l'acces -> {"id"} ; GET ?id=... : "attente",
                            "refuse" ou "accepte" + le code, UNE fois, apres accord d'un parent dans l'appli
                            (POST /api/casque {"action": "accepter" | "refuser", "id"})
  POST /api/design-apercu   {"couleurs": {...}} : couleurs du design space vues tout de suite dans le casque, sans les
                            enregistrer ({} : fin de l'apercu)
  GET  /api/vue             une image de sa camera (casque, « etre le canard ») - seulement si les photos sont permises
  GET  /api/design          schemas de couleurs et filaments du design space ; POST /api/design pour les garder
  GET  /api/alertes?depuis=T les alertes (chute, batterie, garde, incendie, impressions...) apres l'instant T (s)
  GET  /api/reglages        heures calmes, bonjour, repas... ; POST /api/reglages pour les changer (reglages.py)
  POST /api/presence        {"nom": ...} : le telephone de quelqu'un vient d'arriver sur le Wi-Fi de la maison
  GET  /api/sauvegarde      sa memoire (apprentissages, lieux, design, reglages ; jamais ha.toml ni jeton)
  POST /api/restauration    une sauvegarde, appliquee au prochain demarrage du canard
  GET  /api/choregraphies   le studio ; POST {"liste": [...]} pour les garder, {"jouer": nom} pour en jouer une
  GET  /api/comportements   politiques installees (robotd) ; POST /api/comportement chercher / installer / essayer
  POST /api/regard          {"lacet", "tangage"} : regard a une position (pave tactile), borne par le cerveau
  POST /api/mise-a-jour     {"action": "installer", "branche": ...} ou {"action": "revenir"} : au prochain demarrage
  GET  /api/rapport         rapport de diagnostic a partager (versions, sante, alertes) ; aucune donnee personnelle
  GET  /api/photos          le journal photo (photos.py) ; GET /api/photo?id=... une image ; POST /api/photo
                            {"action": "prendre" | "supprimer" (id) | "tout_supprimer"}
  GET  /api/messages        messages laisses au canard (messages.py) ; POST /api/message {"pour", "texte", "de"} ou
                            {"action": "annuler", "id"}
  GET  /api/parcours        parcours d'obstacles : records et dernieres courses ; POST {"points": [[x, y]...],
                            "genre": "parcours" | "balle"} (points de sa carte, repere de l'odometrie)
  GET  /api/usure           courbes d'usure des servos et autonomie de chaque batterie, jour par jour
  GET  /api/carnet          carnet d'entretien (carnet.py) ; POST {"action": "ajouter", ...} ou {"action": "supprimer", "id"}
  POST /api/imprimer        un G-code (corps brut) pour une imprimante Prusa du reseau local ; en-tetes X-Imprimante
                            (son nom), X-Fichier (nom .bgcode/.gcode), X-Lancer (1 : imprimer tout de suite). Le
                            telephone le telecharge (catalogue) : le canard ne sort jamais sur Internet.
  GET  /api/invites         codes invites ; POST {"heures": 24, "nom": ...} pour en creer un, {"action": "revoquer", "code"}
  GET  /api/planning        minuteurs et rappels (planning.py) ; POST /api/minuteur {"secondes", "nom"},
                            POST /api/rappel {"texte", "heure": "HH:MM", "pour", "quotidien"} ; {"action": "annuler", "id"}
  GET  /api/stats           bilan du mois et graphique d'humeur : 60 jours d'activites, humeur d'une semaine, balle
  GET  /api/sante           test de vie, sans code (pour savoir si le canard repond)
Le code se passe dans l'en-tete `X-Microduck-Code` (ou `?code=` pour le flux).
"""
import collections
import hmac
import os
import re
import ipaddress
import json
import math
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DOSSIER = Path(__file__).parent / "interface"
PORT_DEFAUT = 8090
PERIODE_INSTANTANE_S = 0.5
PERIODE_CARTE_S = 3.0
CARTE_MAX_CASES = 2500
COINS = ("nap", "chill", "social", "repas")

# commande de l'appli -> evenement du cerveau (liste FERMEE : l'appli ne peut rien declencher d'autre)
COMMANDES = {
    "jouer_balle": "jeu_balle", "jouer_cache": "jeu_cache", "jouer_soleil": "jeu_soleil", "fin_jeu": "fin_jeu",
    "salut": "tour_salut", "toupie": "tour_toupie", "assis": "tour_assis", "danse": "commande:danse",
    "stop": "commande:stop", "stop_taquinerie": "stop_taquinerie", "diagnostic": "diagnostic",
    "calme_on": "calme_on", "calme_off": "calme_off", "garde_on": "garde_on", "garde_off": "garde_off",
    "oublier_carte": "oublier_carte", "ou_es_tu": "ou_es_tu", "signal_stop": "signal_stop",
    "suis_moi": "suis_moi", "je_te_suis": "je_te_suis", "station": "commande:station", "ronde": "commande:ronde",
    "tresor": "commande:tresor", "cherche_balle": "commande:cherche_balle",
    "batterie_1": "batterie_mise:1", "batterie_2": "batterie_mise:2", "batterie_3": "batterie_mise:3",
    "avance": "guide:avance", "gauche": "guide:gauche", "droite": "guide:droite",
    "regard_gauche": "regard:gauche", "regard_droite": "regard:droite", "regard_haut": "regard:haut",
    "regard_bas": "regard:bas", "regard_centre": "regard:centre",
}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".webmanifest": "application/manifest+json", ".json": "application/json",
         ".bin": "application/octet-stream", ".txt": "text/plain; charset=utf-8"}


def adresse_locale(ip):
    """Reseau local seulement (192.168.x, 10.x, 172.16-31.x, boucle locale, IPv6 locale)."""
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_private or a.is_loopback or a.is_link_local


def _position_courte(pos):
    """Ou il est sur le plan du lieu (position.py) : x, y, cap, sur, piece ; None sans plan."""
    if pos is None or getattr(pos, "plan", None) is None:
        return None
    e = pos.estimation()
    if e is None:
        return None
    return {"x": round(e[0], 2), "y": round(e[1], 2), "cap": round(e[2], 2), "ecart": round(e[3], 2),
            "sur": e[3] <= 0.2, "piece": pos.piece(), "lieu": (pos._cle or [None])[0],
            "changements": list(getattr(pos, "changements", []) or [])}


def instantane(brain, state, version=None):
    """Ce que voit l'appli : construit dans la boucle du cerveau (rapide, aucun reseau), lu ensuite par les fils HTTP."""
    dg = brain.diagnostic.resume() if hasattr(brain, "diagnostic") else {}
    at = getattr(getattr(brain, "diagnostic", None), "autotest", None)
    batt = (state or {}).get("battery") or {}
    mem = brain.ctx.extras.get("memoire")
    etres = []
    if mem is not None and hasattr(mem, "donnees") and hasattr(mem, "familiarite"):
        for nom in list((mem.donnees.get("etres") or {}).keys())[:30]:
            etres.append({"nom": nom, "familiarite": round(mem.familiarite(nom), 2),
                          "rencontres": mem.donnees["etres"][nom].get("rencontres", 0)})
    perso = getattr(brain, "perso", None)
    servos = getattr(getattr(brain, "diagnostic", None), "servos", None)
    chutes = getattr(getattr(brain, "diagnostic", None), "chutes", None)
    jb = getattr(getattr(brain, "diagnostic", None), "batterie", None)
    return {
        "t": time.time(), "version": version,
        "etat": brain.courant.nom, "energie": round(brain.humeur.energie, 2), "eveil": round(brain.humeur.eveil, 2),
        "batterie": {"pourcent": batt.get("percent"), "volts": batt.get("volts")},
        "tombe": bool(getattr(brain, "tombe", False)), "porte": bool(getattr(brain, "porte", False)),
        "assis": bool(getattr(brain.ctx, "sitting", False)),
        # derniere consigne de tete (cou, tangage, lacet, roulis, rad) : le canard dessine de l'appli la reprend
        "tete": [round(float(x), 2) for x in (getattr(brain.ctx, "tete_cmd", None) or (0.0, 0.0, 0.0, 0.0))][:4],
        "modes": {"calme": bool(brain.mode_calme), "garde": bool(brain.ctx.extras.get("garde")),
                  "discret": bool(getattr(brain, "discret", False)), "vacarme": bool(getattr(brain, "vacarme", False)),
                  "vacances": bool(getattr(brain, "vacances", False)),
                  "timidite": round(brain.timidite(), 2) if hasattr(brain, "timidite") else 0.0,
                  "taquineries_coupees": brain.t_global < getattr(getattr(brain, "malice", None), "stop_jusqua", -1)},
        "presents": sorted(getattr(brain, "presents", ())),
        "position": _position_courte(brain.ctx.extras.get("position")),
        "du_jour": dict(getattr(brain, "du_jour", {}) or {}),
        "semaine": brain.semaine() if hasattr(brain, "semaine") else [],
        "journal": [{"t": round(e[0]), "etat": e[1]} for e in list(brain.journal)[-40:]],
        "temperatures": dict(getattr(brain, "temperatures", {}) or {}),
        "maintenance": {
            "diagnostic": {"ok": at.ok() if at else None, "le": dg.get("autotest_le"),
                           "detail": dg.get("autotest_detail") or {}, "demande": bool(getattr(brain, "diag_demande", False))},
            "batterie": {"autonomie_h": dg.get("autonomie_h"), "sante_pct": dg.get("sante_batterie"),
                         "a_remplacer": dg.get("batterie_a_remplacer"), "cycles": dg.get("cycles"),
                         **({"actuelle": jb.d.get("actuelle"), "a_nommer": bool(jb.d.get("a_nommer")),
                             "batteries": jb.par_batterie()} if jb is not None and hasattr(jb, "par_batterie") else {})},
            "servos": {"derives": dg.get("servos_derive") or [], "plus_chaud_habituel": dg.get("servo_chaud_habituel"),
                       "jours_mesures": len((servos.d.get("jours") or {})) if servos else 0},
            "chutes": {"sept_jours": dg.get("chutes_7j"), "activite_risquee": dg.get("activite_risquee"),
                       "lieux_a_risque": dg.get("lieux_a_risque"),
                       "dernieres": list((chutes.d.get("chutes") or [])[-5:]) if chutes else []},
        },
        "balle": dict((mem.donnees.get("balle") or {})) if mem is not None and hasattr(mem, "donnees") else {},
        "caractere": {
            "traits": {k: round(v, 2) for k, v in (perso.d.get("traits") or {}).items()} if perso else {},
            "sons": {k: round(v, 2) for k, v in (perso.d.get("sons") or {}).items()} if perso else {},
            "blagues": brain.malice.compte() if hasattr(brain, "malice") else None,
            "age_jours": (lambda a: None if a == float("inf") else int(a))(brain.age()) if hasattr(brain, "age") else None,
            "humeur_jour": getattr(brain, "humeur_jour", None), "anniversaire": getattr(brain, "anniversaire", 0),
            "etres": etres,
        },
    }


def carte(brain, state):
    """Ce qu'il sait de la maison depuis son demarrage (exploration.py) : cases traversees (fraicheur 0..1), obstacles
    et chutes encore retenus, coins favoris, chargeur, objets remarques, et lui. Repere de l'odometrie, en metres."""
    ex = getattr(brain, "exploration", None)
    if ex is None:
        return {}
    import exploration as xp
    t = brain.t_global
    passages = sorted(ex.passages.items(), key=lambda kv: kv[1], reverse=True)[:CARTE_MAX_CASES]
    odom = (state or {}).get("odom") or {}
    pos = odom.get("position") or getattr(brain, "_derniere_position", None)
    coins = {}
    for activite in COINS:
        c = ex.coin_favori(activite, t)
        if c is not None:
            coins[activite] = [round(c[0], 2), round(c[1], 2)]
    return {
        "case": xp.CASE,
        "canard": None if not pos else {"x": round(pos[0], 2), "y": round(pos[1], 2), "cap": round(odom.get("yaw") or 0.0, 2)},
        "cases": [[i, j, round(max(0.0, 1.0 - (t - tp) / xp.MEMOIRE_PASSAGES_S), 3)] for (i, j), tp in passages],
        "obstacles": [[i, j] for (i, j) in list(ex.obstacles) if ex._bloque((i, j), t)][:CARTE_MAX_CASES],
        "chutes": [[i, j] for (i, j) in list(ex.chutes)][:200],
        "coins": coins,
        "chargeur": None if getattr(brain, "chargeur", None) is None else [round(brain.chargeur[0], 2), round(brain.chargeur[1], 2)],
        "objets": [[round(o[1], 2), round(o[2], 2)] for o in list(getattr(brain, "objets_au_sol", []))[-20:]],
        # « ou l'a-t-il vu ? » : SA position quand il a vu le chat, la balle, un objet (heure murale)
        "vus": {k: {"t": v[0], "x": v[1], "y": v[2]} for k, v in dict(getattr(brain, "vus", {}) or {}).items()},
    }


# Alertes pour les notifications du telephone : evenements du cerveau (ecouteur) -> (titre, texte, importante)
ALERTES_EVENEMENTS = {
    "alarme_fumee": ("Alarme incendie !", "Le détecteur de fumée sonne.", True),
    "impression_finie": ("Impression finie", "{detail}", False),
    "impression_echec": ("Impression ratée", "{detail}", True),
    "machine_finie": ("Machine terminée", "{detail}", False),
    "machine_echec": ("Machine en panne", "{detail}", True),
}
GARDE = {"voix": "une voix", "choc": "un choc", "porte": "des coups à la porte", "bruit": "un bruit"}
BATTERIE_FAIBLE_PCT, BATTERIE_REMONTEE_PCT = 20.0, 30.0


INSTALLATION_S = 30 * 60             # sans code : l'installation reste ouverte 30 min apres le demarrage
# profil enfant (code enfant) : regarder, jouer, le retrouver ; ni reglages, ni telecommande des pas, ni sauvegarde
ENFANT_LECTURE = {"/api/role", "/api/etat", "/api/flux", "/api/carte", "/api/alertes", "/api/design", "/api/lieux", "/api/lieu-carte",
                  "/api/imprimantes", "/api/choregraphies", "/api/comportements", "/api/messages", "/api/parcours", "/api/planning", "/api/stats"}
ENFANT_ECRITURE = {"/api/commande", "/api/message", "/api/parcours", "/api/minuteur"}
COMMANDES_ENFANT = {"signal_stop", "suis_moi", "je_te_suis", "tresor", "cherche_balle", "jouer_balle", "jouer_cache", "jouer_soleil", "fin_jeu", "salut", "toupie", "danse", "stop",
                    "stop_taquinerie", "ou_es_tu", "regard_gauche", "regard_droite", "regard_haut", "regard_bas",
                    "regard_centre"}
SECTIONS_A_REDEMARRER = {"home_assistant", "habitant", "imprimante_directe", "appareil", "cerveau"}


COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")
DESIGN_VIDE = {"filaments": [], "couleurs": [], "schemas": [], "actif": None}


def valider_design(d):
    """Schemas et filaments envoyes par le telephone -> version propre (noms courts, couleurs #rrggbb), ou None."""
    if not isinstance(d, dict):
        return None
    def nom(v):
        v = "".join(c for c in v if c.isprintable()).strip()[:40] if isinstance(v, str) else ""
        return v or None
    filaments = [{"nom": nom(f.get("nom")), "couleur": f.get("couleur")} for f in (d.get("filaments") or [])[:50]
                 if isinstance(f, dict) and nom(f.get("nom")) and COULEUR.match(str(f.get("couleur")))]
    couleurs_perso = [{"nom": nom(f.get("nom")) or f.get("couleur"), "couleur": f.get("couleur").lower()}
                      for f in (d.get("couleurs") or [])[:50] if isinstance(f, dict) and COULEUR.match(str(f.get("couleur")))]
    schemas = []
    for sc in (d.get("schemas") or [])[:50]:
        if not isinstance(sc, dict) or not nom(sc.get("nom")) or not isinstance(sc.get("couleurs"), dict):
            continue
        couleurs = {str(k)[:40]: v for k, v in list(sc["couleurs"].items())[:60] if COULEUR.match(str(v))}
        schemas.append({"nom": nom(sc["nom"]), "couleurs": couleurs})
    actif = nom(d.get("actif"))
    return {"filaments": filaments, "couleurs": couleurs_perso, "schemas": schemas,
            "actif": actif if any(sc["nom"] == actif for sc in schemas) else None}


def fichiers_sauvegardes(appli):
    """Ce qu'une sauvegarde contient : nom -> chemin. Jamais ha.toml (jeton Home Assistant)."""
    import carnet
    import lieux
    import memoire
    import reglages
    return {"memoire.json": memoire.CHEMIN_DEFAUT, "lieux.json": lieux.CHEMIN_DEFAUT,
            "design.json": appli.fichier_design, "reglages.json": appli.fichier_reglages or reglages.CHEMIN_DEFAUT,
            "carnet.json": carnet.chemin_defaut(), "jeux.json": appli.fichier_jeux(),
            "planning.json": __import__("planning").chemin_defaut()}


def appliquer_restaurations(chemins, log=print):
    """Au demarrage (canard.py), avant de lire la memoire : les fichiers « .restaurer » remplacent les actuels."""
    for chemin in chemins:
        attente = Path(str(chemin) + ".restaurer")
        if attente.exists():
            try:
                os.replace(attente, chemin)
                log(f"sauvegarde restauree : {chemin.name}")
            except OSError as e:
                log(f"restauration impossible ({chemin.name}) : {e}")


class Appli:
    def __init__(self, code, port=PORT_DEFAUT, log=print, version=None, hote="0.0.0.0", code_enfant=None):
        """`code` None : mode INSTALLATION (INSTALLATION_S, reseau local) pour le choisir depuis le telephone."""
        if code is not None and len(str(code)) < 6:
            raise ValueError("[appli] code : au moins 6 caracteres (c'est la cle de ton canard sur le reseau)")
        self.code, self.port, self.hote, self.log, self.version = (str(code) if code else None), port, hote, log, version
        self.code_enfant = str(code_enfant) if code_enfant and len(str(code_enfant)) >= 6 else None
        self.fichier_invites = Path(os.environ.get("MICRODUCK_INVITES", Path.home() / ".local/share/microduck/invites.json"))
        self.invites = self._lire_invites()     # code -> {"nom", "jusqua"} : droits « enfant », pour un temps
        self.installation_jusqua = time.monotonic() + INSTALLATION_S if self.code is None else None
        self.brut = {}                          # configuration (ha.toml + configuration.json), page Connexions
        self.imprimantes = None
        self.redemarrage_demande = False
        self.fichier_mise_a_jour = Path.home() / ".local/share/microduck/mise_a_jour"
        self.t_demarrage = time.time()
        self.choregraphies = {}                 # nom -> etapes, partage avec le cerveau (extras["choregraphies"])
        self.robotd = None                      # fabrique d'un client robotd a part (page Comportements)
        self.evenements = queue.Queue()
        self.etat = {}
        self.carte = {}
        self.alertes = collections.deque(maxlen=60)    # {"t", "type", "titre", "texte", "importante"}
        self._verrou_alertes = threading.Lock()
        self._avant = None                      # instantane precedent : on alerte sur les changements
        self._ecoute = None
        self.fichier_design = self.fichier_design_defaut()
        self.cerveau = None                     # section [cerveau] fusionnee (canard.py) : reglages modifiables
        self.fichier_reglages = None
        self._reglages_a_appliquer = None
        self.lieux = None                       # lieux.Lieux, branche par canard.py (sinon : pas de section Lieux)
        self.photos = None                      # photos.Photos (journal photo, mode photo), branche par canard.py
        self.position = None                    # position.PositionPlan (plan du lieu), branche par canard.py
        self.casque = {}                        # dernier contact du casque Quest : {"t", "mode", "ip"}
        self.demandes_casque = {}               # id -> {"t", "ip", "etat"} : un casque demande l'acces (appairage)
        self.apercu_design = None               # {"couleurs", "t"} : design space vu dans le casque, non enregistre
        self.sons_recents = collections.deque(maxlen=20)   # (instant, son) : ses derniers sons (canard jumeau)
        self.grab = None                        # image camera (vue en direct du casque, opt-in photos), canard.py
        self.usure = {}                         # courbes d'usure (servos, batteries), photographiees toutes les 30 s
        self.stats = {}                         # bilan du mois, graphique d'humeur (toutes les 30 s)
        self._t_stats = -1e9
        import planning as planning_mod
        self.planning = planning_mod.Planning()
        self._t_usure = -1e9
        import messages as messages_mod
        self.messages = messages_mod.Messages()
        self._messages_rejoues = False
        self._jour_resume = None                # vacances : resume du jour deja envoye ce jour-la
        self.horloge = time.localtime
        self._t_photo = self._t_carte = -1e9
        self._echecs = {}                       # ip -> instant du dernier code faux (freine les essais)
        self.serveur = None

    @staticmethod
    def fichier_design_defaut():
        return Path(os.environ.get("MICRODUCK_DESIGN", Path.home() / ".local/share/microduck/design.json"))

    # -- cote cerveau (boucle a 50 Hz) --------------------------------------------------------------------------
    def photographier(self, brain, state):
        """Crochet a_chaque_tick : un instantane toutes les PERIODE_INSTANTANE_S, jamais de reseau ici."""
        now = time.monotonic()
        if now - self._t_photo < PERIODE_INSTANTANE_S:
            return
        self._t_photo = now
        self.etat = instantane(brain, state, self.version)
        if self._ecoute is not brain and hasattr(brain, "ecouteurs"):
            self._ecoute = brain
            brain.ecouteurs.append(self.sur_evenement)
            if self.photos is not None:
                brain.ecouteurs.append(self.photos.sur_evenement)
        if not self._messages_rejoues:          # (re)demarrage : les messages en attente sont redonnes au cerveau
            self._messages_rejoues = True
            for m in self.messages.en_attente():
                self.evenements.put(f"message:{m['id']}|{m['pour']}")
        if self.photos is not None:
            self.photos.actif = bool((self.cerveau or {}).get("photos"))
        self._resume_vacances(self.etat)
        self._surveiller(self.etat)
        nouveaux, self._reglages_a_appliquer = self._reglages_a_appliquer, None
        if nouveaux is not None:
            import reglages
            reglages.appliquer(brain, nouveaux)
        dg = getattr(brain, "diagnostic", None)
        if dg is not None and now - self._t_usure >= 30.0:
            self._t_usure = now
            self.usure = {"servos": dg.servos.courbes(), "batteries": dg.batterie.courbes()}
        if now - self._t_stats >= 30.0:
            self._t_stats = now
            mem = brain.ctx.extras.get("memoire") if hasattr(brain, "ctx") else None
            dm = getattr(mem, "donnees", None) or {}
            self.stats = {"jours": list(dm.get("historique_jours") or [])[-60:] + (brain.semaine()[-1:] if hasattr(brain, "semaine") else []),
                          "humeur": list(dm.get("humeur") or []), "balle": dict(dm.get("balle") or {})}
        self._verifier_planning()
        if now - self._t_carte >= PERIODE_CARTE_S:
            self._t_carte = now
            self.carte = carte(brain, state)

    # -- alertes (notifications du telephone) -----------------------------------------------------------------------
    def alerter(self, type_, titre, texte="", importante=False):
        with self._verrou_alertes:
            # instants strictement croissants : le telephone lit « depuis T », deux alertes de la meme milliseconde
            # ne doivent pas se confondre
            t = round(max(time.time(), (self.alertes[-1]["t"] + 0.001) if self.alertes else 0.0), 3)
            self.alertes.append({"t": t, "type": type_, "titre": titre, "texte": texte,
                                 "importante": bool(importante)})

    def sur_evenement(self, quoi):
        """Ecouteur du cerveau (evenements recus et « garde:<type> ») : rien de lent ici."""
        base, _, detail = str(quoi).partition(":")
        if base == "garde":
            self.alerter("garde", "Alerte de garde", f"Il a entendu {GARDE.get(detail, 'quelque chose')}, "
                         "alors que personne n'est à la maison.", True)
        elif base in ALERTES_EVENEMENTS:
            titre, texte, importante = ALERTES_EVENEMENTS[base]
            self.alerter(base, titre, texte.format(detail=detail).strip(), importante)
        elif base == "parcours_fini":
            self._fin_parcours(detail)
        elif base == "message_transmis":
            m = self.messages.transmis(detail)
            if m is not None:
                self.alerter("message", "Message transmis", f"{m['pour']} est là : il le lui a signalé.", False)

    def fichier_jeux(self):
        return Path(os.environ.get("MICRODUCK_JEUX", Path.home() / ".local/share/microduck/jeux.json"))

    def jeux(self):
        try:
            d = json.loads(self.fichier_jeux().read_text())
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _fin_parcours(self, detail):
        """« genre|issue|duree|atteints/total » : historique, record par nombre de points, notification."""
        try:
            genre, issue, duree, score = detail.split("|")
            atteints, total = (int(v) for v in score.split("/"))
            duree = float(duree)
        except ValueError:
            return
        if genre == "balle":
            if issue == "refuse":
                self.alerter("parcours", "Il ne peut pas y aller", "Debout, au calme, et pas trop loin (4 m).", False)
            return                              # la suite, c'est le jeu de balle (ses statistiques)
        d = self.jeux()
        record = False
        if issue == "reussi":
            records = d.setdefault("records", {})
            if str(total) not in records or duree < records[str(total)]:
                records[str(total)], record = round(duree, 1), True
        d["historique"] = (d.get("historique", []) + [{"t": round(time.time()), "issue": issue, "duree": round(duree, 1),
                                                         "atteints": atteints, "total": total}])[-20:]
        try:
            self.fichier_jeux().parent.mkdir(parents=True, exist_ok=True)
            self.fichier_jeux().write_text(json.dumps(d))
        except OSError:
            pass
        titres = {"reussi": "Parcours réussi", "bloque": "Parcours : bloqué", "trop_long": "Parcours : trop long",
                  "interrompu": "Parcours interrompu", "refuse": "Il ne peut pas faire ce parcours"}
        texte = (f"{duree:.1f} s".replace(".", ",") + (" : record !" if record else "") if issue == "reussi"
                 else f"{atteints} point(s) sur {total}" if issue != "refuse"
                 else "Debout, au calme, avec des étapes de 4 m au plus.")
        self.alerter("parcours", titres.get(issue, "Parcours"), texte, False)

    def _verifier_planning(self):
        """Minuteurs finis, rappels arrives : notification du telephone, et le canard le signale (sons de canard)."""
        finis, arrives = self.planning.echus()
        for m in finis:
            self.alerter("minuteur", f"Minuteur : {m['nom']}", "C'est l'heure !", True)
            self.evenements.put(f"signal:minuteur|{m['id']}")
        for r in arrives:
            if r.get("pour"):
                msg = self.messages.ajouter(r["pour"], r["texte"], "Rappel")
                if msg is not None:                      # il le dira a la personne (ou a son retour)
                    self.evenements.put(f"message:{msg['id']}|{msg['pour']}")
                self.alerter("rappel", f"Rappel pour {r['pour']}", r["texte"], False)
            else:
                self.alerter("rappel", "Rappel", r["texte"], True)
                self.evenements.put(f"signal:rappel|{r['id']}")

    RESUME_VACANCES_H = 20
    POSE_ATTENTE_S = 1.6

    def _resume_vacances(self, e):
        """Mode vacances : un resume par jour (20 h), en notification : batterie, alertes de garde, chutes."""
        if not e.get("modes", {}).get("vacances"):
            return
        h = self.horloge()
        jour = (h.tm_year, h.tm_yday)
        if h.tm_hour < self.RESUME_VACANCES_H or self._jour_resume == jour:
            return
        self._jour_resume = jour
        depuis = time.time() - 86400
        with self._verrou_alertes:
            garde = sum(1 for a in self.alertes if a["type"] == "garde" and a["t"] > depuis)
            chutes = sum(1 for a in self.alertes if a["type"] == "chute" and a["t"] > depuis)
        p = (e.get("batterie") or {}).get("pourcent")
        morceaux = [f"batterie {round(p)} %" if p is not None else None,
                    "rien d'anormal entendu" if not garde else f"{garde} alerte(s) de garde",
                    f"{chutes} chute(s)" if chutes else None]
        debut = "À voir : " if garde or chutes else "Tout va bien : "
        self.alerter("vacances", "Nouvelles du canard", debut + ", ".join(m for m in morceaux if m) + ".",
                     bool(garde or chutes))

    def _surveiller(self, e):
        """Changements d'etat qui meritent une notification : chute, batterie faible, diagnostic, batterie a nommer."""
        avant, self._avant = self._avant, e
        if avant is None:
            return
        if e["tombe"] and not avant["tombe"]:
            self.alerter("chute", "Il est tombé", "Il essaie de se relever tout seul.", True)
        p, p0 = e["batterie"].get("pourcent"), avant["batterie"].get("pourcent")
        if p is not None and p0 is not None:
            if p < BATTERIE_FAIBLE_PCT <= p0 and not self._batterie_signalee:
                self._batterie_signalee = True
                self.alerter("batterie", "Batterie faible", f"Plus que {round(p)} % : il va vouloir se reposer.", True)
            elif p >= BATTERIE_REMONTEE_PCT:
                self._batterie_signalee = False
        diag, diag0 = e["maintenance"]["diagnostic"], avant["maintenance"]["diagnostic"]
        if diag.get("ok") is False and diag.get("le") != diag0.get("le"):
            self.alerter("diagnostic", "Diagnostic : problème détecté", "Détails dans Santé.", True)
        nouveaux = set(e["maintenance"]["servos"].get("derives") or []) - set(avant["maintenance"]["servos"].get("derives") or [])
        if nouveaux:
            self.alerter("servo", "Servo à surveiller", ", ".join(sorted(nouveaux)) + " : détails dans Santé.", True)
        if e["maintenance"]["batterie"].get("a_nommer") and not avant["maintenance"]["batterie"].get("a_nommer"):
            self.alerter("batterie_echange", "Batterie changée", "Laquelle as-tu mise ? Réponds dans Santé.", False)

    _batterie_signalee = False

    def comportements(self, action, texte=""):
        """Page Comportements : le catalogue des politiques, par robotd (sa propre connexion, jamais celle du cerveau).
        Les noms exacts des requetes (robot.policies, policy.search, policy.install) sont ceux de la doc officielle,
        A VALIDER sur le robot."""
        if self.robotd is None:
            return {"ok": False, "message": "robotd injoignable ici"}
        try:
            c = self.robotd()
        except Exception as e:
            return {"ok": False, "message": f"robotd injoignable ({e})"}
        try:
            if action == "liste":
                pol, sk = c.request("robot.policies"), c.request("robot.skills")
                return {"ok": True, "politiques": pol.get("result", pol.get("error")), "skills": sk.get("result", sk.get("error"))}
            if action == "chercher":
                r = c.request("policy.search", {"query": texte}, timeout_s=20.0)
            else:
                r = c.request("policy.install", {"repo": texte}, timeout_s=120.0)
            return {"ok": "error" not in r, "resultat": r.get("result", r.get("error"))}
        except Exception as e:
            return {"ok": False, "message": str(e)[:160]}
        finally:
            try:
                c.sock.close()
            except Exception:
                pass

    def rapport(self):
        """Pour demander de l'aide (Pollen, communaute) : l'etat technique du canard, SANS donnee personnelle (ni noms,
        ni lieux, ni reseaux, ni journal de la maison, ni texte des alertes)."""
        e = dict(self.etat or {})
        m = e.get("maintenance") or {}
        bt = dict(m.get("batterie") or {})
        brut = self.brut or {}
        with self._verrou_alertes:
            alertes = [{"t": a["t"], "type": a["type"]} for a in self.alertes]
        return {
            "format": "microduck-rapport", "version": 1, "date": time.time(), "cerveau": self.version,
            "demarre_depuis_s": round(time.time() - self.t_demarrage), "etat": e.get("etat"),
            "tombe": e.get("tombe"), "assis": e.get("assis"), "batterie": e.get("batterie"),
            "temperatures": e.get("temperatures"), "diagnostic": m.get("diagnostic"),
            "batteries": {k: v for k, v in bt.items() if k != "actuelle"},
            "servos": m.get("servos"), "chutes": {k: v for k, v in (m.get("chutes") or {}).items() if k != "dernieres"},
            "modes": {k: e.get("modes", {}).get(k) for k in ("calme", "garde", "discret", "vacarme")},
            "configuration": {"home_assistant": bool((brut.get("home_assistant") or {}).get("url") or brut.get("url")),
                              "habitants": len(brut.get("habitant") or []),
                              "imprimantes": sorted({i.get("type") for i in brut.get("imprimante_directe") or []}),
                              "appareils": sorted({a.get("type") for a in brut.get("appareil") or []}),
                              "code_enfant": bool(self.code_enfant)},
            "imprimantes": [{"type": i.get("type"), "etat": i.get("etat"), "joignable": i.get("joignable")}
                            for i in (self.imprimantes.etat() if self.imprimantes is not None else [])],
            "alertes": alertes,
        }

    def alertes_depuis(self, t):
        with self._verrou_alertes:
            return [a for a in self.alertes if a["t"] > t]

    def source(self):
        """Evenements envoyes par l'appli depuis la derniere trame (brain.run(source=...))."""
        out = []
        while True:
            try:
                out.append(self.evenements.get_nowait())
            except queue.Empty:
                return out

    # -- appairage du casque : il demande, un parent accepte dans l'appli, le code lui est remis une fois -----------
    DEMANDE_S = 5 * 60

    def nettoyer_demandes(self):
        for k in [k for k, v in self.demandes_casque.items() if time.time() - v["t"] > self.DEMANDE_S]:
            del self.demandes_casque[k]
        return self.demandes_casque

    def demander_casque(self, ip):
        """-> (code HTTP, reponse). Une demande en attente par adresse, trois au plus en tout."""
        import secrets
        if self.code is None:
            return 409, {"erreur": "canard pas encore installe (choisir son code depuis le telephone)"}
        self.nettoyer_demandes()
        for k, v in self.demandes_casque.items():
            if v["ip"] == ip and v["etat"] == "attente":
                return 200, {"id": k}
        if sum(1 for v in self.demandes_casque.values() if v["etat"] == "attente") >= 3:
            return 429, {"erreur": "trop de demandes en attente"}
        k = secrets.token_urlsafe(12)
        self.demandes_casque[k] = {"t": time.time(), "ip": ip, "etat": "attente"}
        self.alerter("casque", "Un casque demande l'accès", f"Depuis {ip} : à accepter dans Réglages → Casque.", True)
        return 200, {"id": k}

    # -- cote reseau --------------------------------------------------------------------------------------------
    def code_valide(self, essai, ip):
        """-> "parent" (code de l'appli), "enfant" (code enfant : jeux et regard seulement) ou None."""
        if self._echecs.get(ip, -1e9) > time.monotonic() - 1.0:
            return None                         # au plus un essai par seconde apres un code faux
        role = None
        if isinstance(essai, str) and self.code and hmac.compare_digest(essai.encode(), self.code.encode()):
            role = "parent"
        elif isinstance(essai, str) and self.code_enfant and hmac.compare_digest(essai.encode(), self.code_enfant.encode()):
            role = "enfant"
        elif isinstance(essai, str) and essai in self.invites and self.invites[essai]["jusqua"] > time.time():
            role = "invite"
        if role is None:
            self._echecs[ip] = time.monotonic()
        return role

    # -- codes invites (un ami, les grands-parents...) : droits du profil enfant, pour quelques heures -----------------
    INVITE_MAX_H = 24 * 7

    def _lire_invites(self):
        try:
            d = json.loads(self.fichier_invites.read_text())
            return {k: v for k, v in d.items() if isinstance(v, dict) and v.get("jusqua", 0) > time.time()}
        except (OSError, ValueError, AttributeError):
            return {}

    def _ecrire_invites(self):
        try:
            self.fichier_invites.parent.mkdir(parents=True, exist_ok=True)
            self.fichier_invites.write_text(json.dumps(self.invites, ensure_ascii=False))
            os.chmod(self.fichier_invites, 0o600)
        except OSError:
            pass

    def creer_invite(self, heures, nom=""):
        import secrets
        heures = max(1, min(self.INVITE_MAX_H, int(heures)))
        code = "-".join("".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(4)) for _ in range(2))
        nom = "".join(c for c in str(nom or "") if c.isprintable()).strip()[:30] or "Invité"
        self.invites = {k: v for k, v in self.invites.items() if v["jusqua"] > time.time()}
        self.invites[code] = {"nom": nom, "jusqua": round(time.time() + heures * 3600)}
        self._ecrire_invites()
        return code

    def revoquer_invite(self, code):
        if self.invites.pop(str(code), None) is None:
            return False
        self._ecrire_invites()
        return True

    def en_installation(self):
        return self.code is None and self.installation_jusqua is not None and time.monotonic() < self.installation_jusqua

    def commande(self, nom):
        evt = COMMANDES.get(nom)
        if evt is None:
            return False
        self.evenements.put(evt)
        return True

    def demarrer(self):
        appli = self

        class Requete(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, objet):
                corps = json.dumps(objet, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def _autorise(self, code=None):
                if not adresse_locale(self.client_address[0]):
                    self._json(403, {"erreur": "reseau local seulement"})
                    return False
                self.role = appli.code_valide(code if code is not None else self.headers.get("X-Microduck-Code"),
                                              self.client_address[0])
                if self.role is None:
                    self._json(401, {"erreur": "code d'appairage"})
                    return False
                casque = self.headers.get("X-Microduck-Casque")
                if casque:                              # l'appli du Quest se presente (Reglages -> Casque)
                    appli.casque = {"t": time.time(), "mode": str(casque)[:30], "ip": self.client_address[0]}
                chemin = urlparse(self.path).path
                if self.role in ("enfant", "invite") and chemin not in (ENFANT_LECTURE if self.command == "GET" else ENFANT_ECRITURE):
                    self._json(403, {"erreur": "reserve aux parents"})
                    return False
                return True

            def do_GET(self):
                url = urlparse(self.path)
                if not adresse_locale(self.client_address[0]):
                    return self._json(403, {"erreur": "reseau local seulement"})
                if url.path == "/api/sante":
                    return self._json(200, {"ok": True, "appli": "microduck", "version": appli.version,
                                            "installation": appli.en_installation(),
                                            "nom": ((appli.brut.get("cerveau") or {}).get("nom") or "Microduck")})
                if url.path == "/api/casque-demande":
                    # le casque attend l'accord d'un parent ; le code ne part qu'une fois, vers l'adresse qui a demande
                    appli.nettoyer_demandes()
                    d = appli.demandes_casque.get(parse_qs(url.query).get("id", [""])[0])
                    if d is None or d["ip"] != self.client_address[0]:
                        return self._json(404, {"etat": "inconnue"})
                    if d["etat"] == "accepte":
                        appli.demandes_casque.pop(parse_qs(url.query)["id"][0], None)
                        return self._json(200, {"etat": "accepte", "code": appli.code})
                    return self._json(200, {"etat": d["etat"]})
                if url.path == "/api/etat":
                    if self._autorise():
                        self._json(200, appli.etat)
                    return
                if url.path == "/api/carte":
                    if self._autorise():
                        self._json(200, appli.carte)
                    return
                if url.path == "/api/role":
                    if self._autorise():
                        self._json(200, {"role": self.role})
                    return
                if url.path == "/api/configuration":
                    if self._autorise():
                        import configuration
                        self._json(200, configuration.pour_appli(appli.brut))
                    return
                if url.path == "/api/choregraphies":
                    if self._autorise():
                        import choregraphies
                        self._json(200, {"liste": [{"nom": n, "etapes": e} for n, e in appli.choregraphies.items()],
                                         "gestes": choregraphies.GESTES, "bornes": choregraphies.BORNES})
                    return
                if url.path == "/api/comportements":
                    if self._autorise():
                        self._json(200, appli.comportements("liste"))
                    return
                if url.path == "/api/imprimantes":
                    if self._autorise():
                        self._json(200, appli.imprimantes.etat() if appli.imprimantes is not None else [])
                    return
                if url.path == "/api/alertes":
                    if self._autorise():
                        try:
                            depuis = float(parse_qs(url.query).get("depuis", ["0"])[0])
                        except ValueError:
                            depuis = 0.0
                        self._json(200, {"maintenant": time.time(), "alertes": appli.alertes_depuis(depuis)})
                    return
                if url.path == "/api/invites":
                    if self._autorise():
                        self._json(200, {"liste": [{"code": k, **v} for k, v in appli.invites.items()
                                                   if v["jusqua"] > time.time()]})
                    return
                if url.path == "/api/planning":
                    if self._autorise():
                        self._json(200, appli.planning.etat())
                    return
                if url.path == "/api/xr":
                    # casque (appli Quest, mode atelier) : position, nuage d'hypotheses, capteur, trajet - des nombres
                    if self._autorise():
                        self._json(200, appli.position.resume() if appli.position is not None else {"plan": False})
                    return
                if url.path == "/api/casque":
                    if self._autorise():
                        import jumeau
                        gt = jumeau.lire_verite()
                        c = appli.casque
                        self._json(200, {
                            "connecte": bool(c) and time.time() - c["t"] < 8, "dernier": c.get("t"),
                            "mode": c.get("mode"), "ip": c.get("ip"),
                            "simulateur": gt is not None, "scene": (gt or {}).get("scene"),
                            "scenes": list(jumeau.SCENES), "changer_scene": os.environ.get("MICRODUCK_JUMEAU") == "1",
                            "adresses": [f"http://{ip}:{appli.port}" for ip in jumeau.adresses_locales()],
                            "apercu": appli.apercu_design is not None,
                            "demandes": [{"id": k, "ip": v["ip"], "age": round(time.time() - v["t"])}
                                         for k, v in appli.nettoyer_demandes().items() if v["etat"] == "attente"]})
                    return
                if url.path == "/api/jumeau":
                    if self._autorise():
                        import jumeau
                        try:
                            depuis = float(parse_qs(url.query).get("depuis", ["0"])[0])
                        except ValueError:
                            depuis = 0.0
                        e = jumeau.etat(list(appli.sons_recents), depuis)
                        self._json(200, e) if e is not None else self._json(404, {"erreur": "pas de simulateur (duck-sim)"})
                    return
                if url.path == "/api/vue":
                    # « etre le canard » (casque) : une image de sa camera, SEULEMENT si les photos sont permises
                    # (Reglages, opt-in, code parent) - comme le journal photo
                    if not self._autorise():
                        return
                    if appli.photos is None or not appli.photos.actif or appli.grab is None:
                        return self._json(403, {"erreur": "photos désactivées (Réglages : photos)"})
                    try:
                        import cv2
                        ok, jpg = cv2.imencode(".jpg", appli.grab(), [cv2.IMWRITE_JPEG_QUALITY, 70])
                        assert ok
                    except Exception:
                        return self._json(503, {"erreur": "camera indisponible"})
                    corps = jpg.tobytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(corps)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(corps)
                    return
                if url.path == "/api/stats":
                    if self._autorise():
                        self._json(200, appli.stats)
                    return
                if url.path == "/api/usure":
                    if self._autorise():
                        self._json(200, appli.usure)
                    return
                if url.path == "/api/carnet":
                    if self._autorise():
                        import carnet
                        self._json(200, {"liste": carnet.Carnet().lire(), "types": carnet.TYPES})
                    return
                if url.path == "/api/parcours":
                    if self._autorise():
                        self._json(200, appli.jeux())
                    return
                if url.path == "/api/messages":
                    if self._autorise():
                        self._json(200, {"liste": list(reversed(appli.messages.liste))})
                    return
                if url.path in ("/api/photos", "/api/photo"):
                    if not self._autorise():
                        return
                    if appli.photos is None:
                        return self._json(404, {"erreur": "camera absente"})
                    if url.path == "/api/photos":
                        return self._json(200, {"actif": appli.photos.actif, "liste": appli.photos.liste()})
                    lu = appli.photos.lire_photo(parse_qs(url.query).get("id", [""])[0])
                    if lu is None:
                        return self._json(404, {"erreur": "photo inconnue"})
                    self.send_response(200)
                    self.send_header("Content-Type", lu[1])
                    self.send_header("Cache-Control", "private, max-age=86400")
                    self.send_header("Content-Length", str(len(lu[0])))
                    self.end_headers()
                    self.wfile.write(lu[0])
                    return
                if url.path == "/api/rapport":
                    if self._autorise():
                        self._json(200, appli.rapport())
                    return
                if url.path == "/api/sauvegarde":
                    if self._autorise():
                        fichiers = {}
                        for nom, chemin in fichiers_sauvegardes(appli).items():
                            try:
                                fichiers[nom] = json.loads(Path(chemin).read_text())
                            except (OSError, ValueError):
                                pass
                        self._json(200, {"format": "microduck-sauvegarde", "version": 1, "date": time.time(),
                                         "cerveau": appli.version, "fichiers": fichiers})
                    return
                if url.path == "/api/reglages":
                    if self._autorise():
                        if appli.cerveau is None:
                            return self._json(404, {"erreur": "reglages non geres"})
                        import reglages
                        self._json(200, reglages.pour_appli(appli.cerveau))
                    return
                if url.path == "/api/design":
                    if self._autorise():
                        try:
                            d = valider_design(json.loads(appli.fichier_design.read_text())) or dict(DESIGN_VIDE)
                        except (OSError, ValueError):
                            d = dict(DESIGN_VIDE)
                        a = appli.apercu_design
                        import jumeau
                        if a is not None and time.time() - a["t"] < jumeau.APERCU_S:
                            d["apercu"] = a["couleurs"]          # vu dans le casque, pas enregistre
                        self._json(200, d)
                    return
                if url.path == "/api/plan":
                    if not self._autorise():
                        return
                    if appli.lieux is None:
                        return self._json(404, {"erreur": "lieux non geres"})
                    p = appli.lieux.plan(parse_qs(url.query).get("id", [None])[0] or None)
                    return self._json(200, p) if p is not None else self._json(404, {"erreur": "pas de plan"})
                if url.path in ("/api/lieux", "/api/lieu-carte"):
                    if not self._autorise():
                        return
                    if appli.lieux is None:
                        return self._json(404, {"erreur": "lieux non geres"})
                    if url.path == "/api/lieux":
                        return self._json(200, appli.lieux.resume())
                    return self._json(200, appli.lieux.carte(parse_qs(url.query).get("id", [""])[0]))
                if url.path == "/api/flux":
                    if not self._autorise(parse_qs(url.query).get("code", [None])[0]):
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    try:
                        while appli.serveur is not None:
                            self.wfile.write(f"data: {json.dumps(appli.etat, ensure_ascii=False)}\n\n".encode())
                            self.wfile.flush()
                            time.sleep(1.0)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    return
                self._fichier(url.path)

            def do_POST(self):
                chemin = urlparse(self.path).path
                if not adresse_locale(self.client_address[0]):
                    return self._json(403, {"erreur": "reseau local seulement"})
                if chemin not in ("/api/commande", "/api/lieu", "/api/design", "/api/reglages", "/api/presence",
                                  "/api/restauration", "/api/installation", "/api/configuration", "/api/tester-ha",
                                  "/api/tester-imprimante", "/api/redemarrer", "/api/choregraphies", "/api/comportement",
                                  "/api/regard", "/api/mise-a-jour", "/api/photo", "/api/message", "/api/parcours", "/api/carnet",
                                  "/api/imprimer", "/api/invites", "/api/minuteur", "/api/rappel", "/api/plan",
                                  "/api/plan-supprimer", "/api/plan-annoter", "/api/verite", "/api/aller",
                                  "/api/jumeau-balle", "/api/jumeau-caresse", "/api/casque", "/api/design-apercu",
                                  "/api/casque-demande"):
                    return self._json(404, {"erreur": "inconnu"})
                if chemin == "/api/installation":
                    return self._installation()
                if chemin == "/api/casque-demande":
                    return self._json(*appli.demander_casque(self.client_address[0]))
                if not self._autorise():
                    return
                if chemin == "/api/imprimer":
                    return self._imprimer()
                try:
                    n = min(int(self.headers.get("Content-Length", "0")),
                            {"/api/design": 65536, "/api/restauration": 8 * 1024 * 1024,
                             "/api/plan": 16 * 1024 * 1024, "/api/plan-annoter": 65536}.get(chemin, 4096))
                    corps = json.loads(self.rfile.read(n) or b"{}")
                    if not isinstance(corps, dict):
                        raise ValueError
                except (ValueError, AttributeError):
                    return self._json(400, {"erreur": "JSON attendu"})
                if chemin == "/api/casque":
                    import jumeau
                    action = corps.get("action")
                    if action == "balle":
                        return self._json(*jumeau.balle_devant())
                    if action == "chargeur":
                        code, rep = jumeau.au_chargeur()
                        if code == 200 and appli.position is not None:
                            appli.position.recaler(0.0, 0.0, 0.0)  # il SAIT qu'il est au chargeur (repere du plan)
                        return self._json(code, rep)
                    if action in ("accepter", "refuser"):
                        d = appli.nettoyer_demandes().get(str(corps.get("id")))
                        if d is None or d["etat"] != "attente":
                            return self._json(404, {"erreur": "demande inconnue ou expiree"})
                        d["etat"] = "accepte" if action == "accepter" else "refuse"
                        return self._json(200, {"ok": True})
                    if action == "scene":
                        code, rep = jumeau.demander_scene(corps.get("scene"))
                        if code == 200:
                            appli.redemarrage_demande = True    # le cerveau sort ; jumeau.sh relance tout sur la scene
                        return self._json(code, rep)
                    return self._json(400, {"erreur": "action inconnue"})
                if chemin == "/api/design-apercu":
                    import jumeau
                    c = jumeau.valider_apercu(corps)
                    appli.apercu_design = {"couleurs": c, "t": time.time()} if c else None
                    return self._json(200, {"ok": True})
                if chemin == "/api/jumeau-balle":
                    import jumeau
                    return self._json(*jumeau.lancer(corps))
                if chemin == "/api/jumeau-caresse":
                    import jumeau
                    if jumeau.lire_verite() is None:
                        return self._json(404, {"erreur": "pas de simulateur (duck-sim)"})
                    appli.evenements.put("caresse:jumeau")      # la main dans le casque, sur sa tete
                    return self._json(200, {"ok": True})
                if chemin == "/api/configuration":
                    import configuration
                    section = corps.get("section")
                    try:
                        propre = configuration.ecrire(section, corps.get("valeur"))
                    except OSError:
                        return self._json(500, {"erreur": "enregistrement impossible"})
                    if propre is None:
                        return self._json(400, {"erreur": f"section {section} invalide"})
                    appli.brut = configuration.fusion(appli.brut, {section: propre})
                    if section == "appli":                      # nouveaux codes : tout de suite
                        appli.code, appli.code_enfant = propre["code"], propre.get("code_enfant")
                    return self._json(200, {"ok": True, "redemarrer": section in SECTIONS_A_REDEMARRER,
                                            "configuration": configuration.pour_appli(appli.brut)})
                if chemin == "/api/tester-ha":
                    import configuration
                    import pont_ha
                    jeton = corps.get("token")
                    if jeton in (None, "", configuration.SECRET):
                        jeton = (appli.brut.get("home_assistant") or {}).get("token") or ""
                    ok, message = pont_ha.tester(corps.get("url"), jeton)
                    return self._json(200, {"ok": ok, "message": message})
                if chemin == "/api/tester-imprimante":
                    import configuration
                    import imprimantes
                    if corps.get("type") not in configuration.TYPES_IMPRIMANTE or not configuration.adresse_locale(corps.get("adresse")):
                        return self._json(400, {"erreur": "imprimante du reseau local attendue"})
                    cle = corps.get("cle_api")
                    if cle in (None, "", configuration.SECRET):
                        cle = next((i.get("cle_api") for i in appli.brut.get("imprimante_directe", [])
                                    if i.get("adresse") == corps.get("adresse")), None)
                    try:
                        lu = (imprimantes.lire_prusalink(corps["adresse"], cle) if corps["type"] == "prusalink"
                              else imprimantes.lire_sdcp(corps["adresse"]))
                        return self._json(200, {"ok": True, "etat": lu["etat"], "progression": lu.get("progression")})
                    except Exception as e:
                        return self._json(200, {"ok": False, "message": str(e)[:120]})
                if chemin == "/api/choregraphies":
                    import choregraphies
                    if isinstance(corps.get("jouer"), str):
                        if corps["jouer"] not in appli.choregraphies:
                            return self._json(404, {"erreur": "choregraphie inconnue"})
                        appli.evenements.put(f"choregraphie:{corps['jouer']}")
                        return self._json(200, {"ok": True})
                    try:
                        propre = choregraphies.ecrire(corps.get("liste"))
                    except OSError:
                        return self._json(500, {"erreur": "enregistrement impossible"})
                    appli.choregraphies.clear()
                    appli.choregraphies.update({c["nom"]: c["etapes"] for c in propre})
                    return self._json(200, {"ok": True, "liste": propre})
                if chemin == "/api/comportement":
                    action = corps.get("action")
                    if action == "essayer" and isinstance(corps.get("nom"), str) and 0 < len(corps["nom"]) <= 60:
                        appli.evenements.put(f"skill_essai:{corps['nom']}")      # le cerveau decide si c'est le moment
                        return self._json(200, {"ok": True})
                    if action in ("chercher", "installer"):
                        return self._json(200, appli.comportements(action, str(corps.get("texte") or "")[:120]))
                    return self._json(400, {"erreur": "action inconnue"})
                if chemin == "/api/regard":
                    try:
                        lacet, tangage = float(corps.get("lacet")), float(corps.get("tangage"))
                    except (TypeError, ValueError):
                        return self._json(400, {"erreur": "lacet et tangage attendus"})
                    if lacet != lacet or tangage != tangage:
                        return self._json(400, {"erreur": "nombres attendus"})
                    appli.evenements.put(f"regard:abs|{lacet:.3f}|{tangage:.3f}")
                    return self._json(200, {"ok": True})
                if chemin == "/api/mise-a-jour":
                    action, branche = corps.get("action"), str(corps.get("branche") or "main")
                    if action not in ("installer", "revenir") or not re.fullmatch(r"[A-Za-z0-9._/-]{1,80}", branche):
                        return self._json(400, {"erreur": "action ou branche invalide"})
                    try:
                        appli.fichier_mise_a_jour.parent.mkdir(parents=True, exist_ok=True)
                        appli.fichier_mise_a_jour.write_text(f"{action} {branche}\n")
                    except OSError:
                        return self._json(500, {"erreur": "enregistrement impossible"})
                    appli.redemarrage_demande = True            # systemd lance mettre_a_jour.sh puis le cerveau
                    return self._json(200, {"ok": True})
                if chemin == "/api/photo":
                    if appli.photos is None:
                        return self._json(404, {"erreur": "camera absente"})
                    action = corps.get("action")
                    if action == "prendre":
                        import etats_appli
                        pose = corps.get("pose")
                        if pose in etats_appli.PosePhoto.POSES:          # mode photo : il prend la pose, puis clic
                            appli.evenements.put(f"pose_photo:{pose}")
                            time.sleep(appli.POSE_ATTENTE_S)
                        ident = appli.photos.prendre("pose" if pose else "photo", attendre=True)
                        return self._json(200 if ident else 503, {"ok": bool(ident), "id": ident})
                    if action in ("supprimer", "tout_supprimer"):
                        appli.photos.supprimer(corps.get("id") if action == "supprimer" else None)
                        return self._json(200, {"ok": True})
                    return self._json(400, {"erreur": "action inconnue"})
                if chemin in ("/api/minuteur", "/api/rappel"):
                    if corps.get("action") == "annuler":
                        ok = appli.planning.annuler(str(corps.get("id")))
                        return self._json(200 if ok else 404, {"ok": ok})
                    if chemin == "/api/minuteur":
                        m = appli.planning.minuteur(corps.get("secondes"), corps.get("nom"))
                    else:
                        m = appli.planning.rappel(corps.get("texte"), corps.get("heure"), corps.get("pour") or "",
                                                  bool(corps.get("quotidien")))
                    if m is None:
                        return self._json(400, {"erreur": "duree (5 s a 24 h) ou texte et heure HH:MM attendus"})
                    return self._json(200, {"ok": True, "element": m})
                if chemin == "/api/invites":
                    if corps.get("action") == "revoquer":
                        return self._json(200 if appli.revoquer_invite(corps.get("code")) else 404, {"ok": True})
                    try:
                        code = appli.creer_invite(corps.get("heures", 24), corps.get("nom"))
                    except (TypeError, ValueError):
                        return self._json(400, {"erreur": "duree en heures attendue"})
                    return self._json(200, {"ok": True, "code": code, **appli.invites[code]})
                if chemin == "/api/carnet":
                    import carnet
                    c = carnet.Carnet()
                    try:
                        if corps.get("action") == "supprimer":
                            return self._json(200 if c.supprimer(str(corps.get("id"))) else 404, {"ok": True})
                        e = c.ajouter(corps)
                    except OSError:
                        return self._json(500, {"erreur": "enregistrement impossible"})
                    if e is None:
                        return self._json(400, {"erreur": "entree incomplete"})
                    if e["type"] == "servo":
                        appli.evenements.put(f"servo_remplace:{e['servo']}")
                    elif e["type"] == "batterie":
                        appli.evenements.put(f"batterie_remplacee:{e['batterie']}")
                    return self._json(200, {"ok": True, "entree": e})
                if chemin == "/api/parcours":
                    pts = corps.get("points")
                    try:
                        pts = [(float(p[0]), float(p[1])) for p in pts][:6] if isinstance(pts, list) else []
                    except (TypeError, ValueError, IndexError):
                        pts = []
                    if not pts or any(v != v or abs(v) > 100 for p in pts for v in p):
                        return self._json(400, {"erreur": "points de sa carte attendus"})
                    genre = "va_balle" if corps.get("genre") == "balle" else "parcours"
                    appli.evenements.put(f"{genre}:" + ";".join(f"{x:.2f},{y:.2f}" for x, y in pts[:1 if genre == "va_balle" else 6]))
                    return self._json(200, {"ok": True})
                if chemin == "/api/message":
                    if corps.get("action") == "annuler":
                        if self.role != "parent" or not appli.messages.annuler(str(corps.get("id"))):
                            return self._json(400, {"erreur": "message inconnu"})
                        appli.evenements.put(f"message_annule:{corps.get('id')}")
                        return self._json(200, {"ok": True})
                    m = appli.messages.ajouter(corps.get("pour"), corps.get("texte"), corps.get("de"))
                    if m is None:
                        return self._json(400, {"erreur": "destinataire et texte attendus"})
                    appli.evenements.put(f"message:{m['id']}|{m['pour']}")
                    return self._json(200, {"ok": True, "message": m})
                if chemin == "/api/redemarrer":
                    appli.redemarrage_demande = True            # canard.py sort proprement, systemd le relance
                    return self._json(200, {"ok": True})
                if chemin == "/api/presence":
                    nom = corps.get("nom")
                    nom = "".join(c for c in nom if c.isprintable() and c not in "|:").strip()[:40] if isinstance(nom, str) else ""
                    if not nom:
                        return self._json(400, {"erreur": "nom attendu"})
                    appli.evenements.put(f"arrivee:{nom}")      # il arrive : accueil, sauf s'il etait deja compte present
                    return self._json(200, {"ok": True})
                if chemin == "/api/restauration":
                    fichiers = corps.get("fichiers") if corps.get("format") == "microduck-sauvegarde" else None
                    connus = fichiers_sauvegardes(appli)
                    if not isinstance(fichiers, dict) or not fichiers or any(
                            k not in connus or not isinstance(v, (dict, list)) for k, v in fichiers.items()):
                        return self._json(400, {"erreur": "ce n'est pas une sauvegarde de Microduck"})
                    try:
                        for nom, contenu in fichiers.items():
                            cible = Path(str(connus[nom]) + ".restaurer")
                            cible.parent.mkdir(parents=True, exist_ok=True)
                            cible.write_text(json.dumps(contenu, ensure_ascii=False))
                    except OSError:
                        return self._json(500, {"erreur": "enregistrement impossible"})
                    return self._json(200, {"ok": True, "redemarrer": True, "fichiers": sorted(fichiers)})
                if chemin == "/api/reglages":
                    import reglages
                    propre = reglages.valider(corps) if appli.cerveau is not None else None
                    if not propre:
                        return self._json(400, {"erreur": "reglages attendus"})
                    fusion = {**appli.cerveau, **propre}
                    fichier = appli.fichier_reglages or reglages.CHEMIN_DEFAUT
                    try:
                        reglages.ecrire({**reglages.lire(fichier), **propre}, fichier)
                    except OSError:
                        return self._json(500, {"erreur": "enregistrement impossible"})
                    appli.cerveau = fusion
                    appli._reglages_a_appliquer = dict(fusion)
                    return self._json(200, reglages.pour_appli(fusion))
                if chemin == "/api/design":
                    propre = valider_design(corps)
                    if propre is None:
                        return self._json(400, {"erreur": "design attendu"})
                    try:
                        appli.fichier_design.parent.mkdir(parents=True, exist_ok=True)
                        tmp = appli.fichier_design.with_suffix(".tmp")
                        tmp.write_text(json.dumps(propre, ensure_ascii=False))
                        os.replace(tmp, appli.fichier_design)
                    except OSError:
                        return self._json(500, {"erreur": "enregistrement impossible"})
                    return self._json(200, {"ok": True})
                if chemin == "/api/plan-annoter":
                    # zones interdites et points nommes (dessines dans le casque ou l'appli)
                    if appli.lieux is None:
                        return self._json(404, {"erreur": "lieux non geres"})
                    zones, points = corps.get("zones"), corps.get("points")
                    if (zones is not None and not isinstance(zones, list)) or (points is not None and not isinstance(points, dict)):
                        return self._json(400, {"erreur": "zones (liste) et/ou points (objet) attendus"})
                    try:
                        resume = appli.lieux.annoter(corps.get("id") if isinstance(corps.get("id"), str) else None,
                                                     zones, points)
                    except (ValueError, TypeError) as e:
                        return self._json(400, {"erreur": str(e)[:200]})
                    return self._json(200, {"ok": True, "plan": resume})
                if chemin in ("/api/verite", "/api/aller"):
                    try:
                        x, y = float(corps.get("x")), float(corps.get("y"))
                        cap = float(corps["cap"]) if corps.get("cap") is not None else None
                        assert all(math.isfinite(v) for v in (x, y) + ((cap,) if cap is not None else ()))
                    except (TypeError, ValueError, AssertionError):
                        return self._json(400, {"erreur": "x et y (m, repere du plan) attendus"})
                    if chemin == "/api/aller":
                        appli.evenements.put(f"aller:{x:.3f}|{y:.3f}")
                        return self._json(200, {"ok": True})
                    # verite terrain du casque : erreur de sa position ; « recaler » le remet a cet endroit
                    if appli.position is None or appli.position.estimation() is None:
                        return self._json(404, {"erreur": "pas de plan pour ce lieu"})
                    ex, ey, ecap, disp = appli.position.estimation()
                    reponse = {"erreur_m": round(math.hypot(ex - x, ey - y), 3), "estimation": [round(ex, 3), round(ey, 3),
                               round(ecap, 3)], "dispersion": round(disp, 3)}
                    if cap is not None:
                        reponse["erreur_cap_deg"] = round(math.degrees(abs(math.remainder(ecap - cap, 2 * math.pi))), 1)
                    if corps.get("recaler") and cap is not None:
                        reponse["recale"] = appli.position.recaler(x, y, cap)
                    appli.log(f"verite terrain (casque) : erreur {reponse['erreur_m']:.2f} m")
                    return self._json(200, reponse)
                if chemin in ("/api/plan", "/api/plan-supprimer"):
                    if appli.lieux is None:
                        return self._json(404, {"erreur": "lieux non geres"})
                    lid = corps.get("id") if isinstance(corps.get("id"), str) else appli.lieux.d["actuel"]
                    if chemin == "/api/plan-supprimer":
                        ok = appli.lieux.supprimer_plan(lid)
                        return self._json(200 if ok else 404, {"ok": True} if ok else {"erreur": "lieu inconnu"})
                    try:
                        resume, avert = appli.lieux.importer_plan(lid, corps.get("contenu"),
                                                                  corps.get("nom") if isinstance(corps.get("nom"), str) else None)
                    except (ValueError, KeyError, TypeError) as e:
                        return self._json(400, {"erreur": str(e)[:200] or "plan illisible"})
                    return self._json(200, {"ok": True, "plan": resume, "avertissements": avert})
                if chemin == "/api/lieu":
                    if appli.lieux is None:
                        return self._json(404, {"erreur": "lieux non geres"})
                    texte = lambda v: v if isinstance(v, str) else None
                    ok, raison = appli.lieux.action(str(corps.get("action")), texte(corps.get("id")), texte(corps.get("nom")))
                    return self._json(200 if ok else 400, {"ok": True} if ok else {"erreur": raison})
                nom = corps.get("commande")
                if self.role in ("enfant", "invite") and nom not in COMMANDES_ENFANT:
                    return self._json(403, {"erreur": "reserve aux parents"})
                if not appli.commande(nom):
                    return self._json(400, {"erreur": f"commande inconnue : {nom}"})
                self._json(200, {"ok": True, "commande": nom})

            def _imprimer(self):
                """Un G-code vers une Prusa du reseau local (PrusaLink) : la cle API reste sur le canard."""
                import imprimantes
                nom = self.headers.get("X-Imprimante", "")
                cible = next((i for i in appli.brut.get("imprimante_directe") or []
                              if i.get("nom") == nom and i.get("type") == "prusalink"), None)
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    n = 0
                if cible is None:
                    return self._json(404, {"erreur": "imprimante Prusa inconnue (Connexions)"})
                if not 0 < n <= imprimantes.FICHIER_MAX or imprimantes.nom_de_fichier(self.headers.get("X-Fichier")) is None:
                    return self._json(400, {"erreur": "fichier .bgcode ou .gcode attendu (64 Mo au plus)"})
                octets = self.rfile.read(n)
                try:
                    imprimantes.envoyer_prusalink(cible["adresse"], cible.get("cle_api"), self.headers.get("X-Fichier"),
                                                  octets, imprimer=self.headers.get("X-Lancer") == "1")
                except (OSError, ValueError) as e:
                    return self._json(502, {"erreur": str(e)[:160]})
                appli.log(f"application : {self.headers.get('X-Fichier')} envoye a {nom}")
                return self._json(200, {"ok": True})

            def _installation(self):
                """Premier demarrage, sans code : le telephone choisit le code, le nom du canard et les habitants."""
                if not adresse_locale(self.client_address[0]):
                    return self._json(403, {"erreur": "reseau local seulement"})
                if not appli.en_installation():
                    return self._json(403, {"erreur": "installation fermee (redemarre le canard pour la rouvrir)"})
                try:
                    n = min(int(self.headers.get("Content-Length", "0")), 4096)
                    corps = json.loads(self.rfile.read(n) or b"{}")
                except (ValueError, AttributeError):
                    return self._json(400, {"erreur": "JSON attendu"})
                import configuration
                code = corps.get("code") if isinstance(corps, dict) else None
                if not isinstance(code, str) or len(code) < 6:
                    return self._json(400, {"erreur": "code : 6 caracteres au moins"})
                try:
                    configuration.ecrire("appli", {"code": code})
                    cerveau = configuration.ecrire("cerveau", {"nom": corps.get("nom"), "garde": False})
                    habitants = configuration.ecrire("habitant", [{"nom": h} for h in (corps.get("habitants") or [])
                                                                  if isinstance(h, str)])
                except OSError:
                    return self._json(500, {"erreur": "enregistrement impossible"})
                appli.brut = configuration.fusion(appli.brut, {"cerveau": cerveau, "habitant": habitants or []})
                appli.code, appli.installation_jusqua = code, None
                appli.log("application : installation faite depuis le telephone")
                return self._json(200, {"ok": True})

            def _fichier(self, chemin):
                nom = "index.html" if chemin in ("/", "") else chemin.lstrip("/")
                f = (DOSSIER / nom).resolve()
                if DOSSIER.resolve() not in f.parents or not f.is_file():
                    return self._json(404, {"erreur": "inconnu"})
                corps = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", TYPES.get(f.suffix, "application/octet-stream"))
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

        self.serveur = ThreadingHTTPServer((self.hote, self.port), Requete)
        self.serveur.daemon_threads = True
        self.port = self.serveur.server_address[1]          # (port 0 : choisi par le systeme, pour les tests)
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.log(f"application Microduck : http://<ip-du-canard>:{self.port} (reseau local, code d'appairage)")

    def arreter(self):
        s, self.serveur = self.serveur, None
        if s is not None:
            s.shutdown()
            s.server_close()
