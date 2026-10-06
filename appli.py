#!/usr/bin/env python3
"""Application Microduck : l'interface telephone du canard, SERVIE PAR LE CANARD (ROADMAP "Application Microduck").

Un petit serveur HTTP (bibliotheque standard, aucune dependance) sur le reseau local : il sert l'interface (`interface/`,
HTML + JS sans framework) et une API JSON. Sur le telephone : ouvrir http://<ip-du-canard>:8090 puis "Ajouter a l'ecran
d'accueil".

Regles du projet respectees :
  - le telephone AFFICHE des etats et ENVOIE des commandes ; aucune image, aucun son ne lui est envoye ;
  - acces protege par un code d'appairage (`[appli] code` dans ha.toml), et seulement depuis le reseau local ;
  - le cerveau garde la main : les commandes sont des EVENEMENTS mis en file (comme ceux de Home Assistant), traites
    par le cerveau dans sa boucle avec ses garde-fous (jamais de marche sans capteur de distance ni vers un vide...).

API :
  GET  /api/etat            instantane complet (JSON)
  GET  /api/flux?code=...   le meme, en continu (Server-Sent Events, 1 par seconde)
  POST /api/commande        {"commande": "<nom>"} parmi COMMANDES
  GET  /api/carte           carte des zones parcourues depuis le demarrage (repere de l'odometrie)
  GET  /api/sante           test de vie, sans code (pour savoir si le canard repond)
Le code se passe dans l'en-tete `X-Microduck-Code` (ou `?code=` pour le flux).
"""
import hmac
import ipaddress
import json
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
    "oublier_carte": "oublier_carte",
    "avance": "guide:avance", "gauche": "guide:gauche", "droite": "guide:droite",
    "regard_gauche": "regard:gauche", "regard_droite": "regard:droite", "regard_haut": "regard:haut",
    "regard_bas": "regard:bas", "regard_centre": "regard:centre",
}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".webmanifest": "application/manifest+json", ".json": "application/json"}


def adresse_locale(ip):
    """Reseau local seulement (192.168.x, 10.x, 172.16-31.x, boucle locale, IPv6 locale)."""
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_private or a.is_loopback or a.is_link_local


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
                  "timidite": round(brain.timidite(), 2) if hasattr(brain, "timidite") else 0.0,
                  "taquineries_coupees": brain.t_global < getattr(getattr(brain, "malice", None), "stop_jusqua", -1)},
        "presents": sorted(getattr(brain, "presents", ())),
        "du_jour": dict(getattr(brain, "du_jour", {}) or {}),
        "journal": [{"t": round(e[0]), "etat": e[1]} for e in list(brain.journal)[-40:]],
        "temperatures": dict(getattr(brain, "temperatures", {}) or {}),
        "maintenance": {
            "diagnostic": {"ok": at.ok() if at else None, "le": dg.get("autotest_le"),
                           "detail": dg.get("autotest_detail") or {}, "demande": bool(getattr(brain, "diag_demande", False))},
            "batterie": {"autonomie_h": dg.get("autonomie_h"), "sante_pct": dg.get("sante_batterie"),
                         "a_remplacer": dg.get("batterie_a_remplacer"), "cycles": dg.get("cycles")},
            "servos": {"derives": dg.get("servos_derive") or [], "plus_chaud_habituel": dg.get("servo_chaud_habituel"),
                       "jours_mesures": len((servos.d.get("jours") or {})) if servos else 0},
            "chutes": {"sept_jours": dg.get("chutes_7j"), "activite_risquee": dg.get("activite_risquee"),
                       "lieux_a_risque": dg.get("lieux_a_risque"),
                       "dernieres": list((chutes.d.get("chutes") or [])[-5:]) if chutes else []},
        },
        "caractere": {
            "traits": {k: round(v, 2) for k, v in (perso.d.get("traits") or {}).items()} if perso else {},
            "sons": {k: round(v, 2) for k, v in (perso.d.get("sons") or {}).items()} if perso else {},
            "blagues": brain.malice.compte() if hasattr(brain, "malice") else None,
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
    }


class Appli:
    def __init__(self, code, port=PORT_DEFAUT, log=print, version=None, hote="0.0.0.0"):
        if not code or len(str(code)) < 6:
            raise ValueError("[appli] code : au moins 6 caracteres (c'est la cle de ton canard sur le reseau)")
        self.code, self.port, self.hote, self.log, self.version = str(code), port, hote, log, version
        self.evenements = queue.Queue()
        self.etat = {}
        self.carte = {}
        self._t_photo = self._t_carte = -1e9
        self._echecs = {}                       # ip -> instant du dernier code faux (freine les essais)
        self.serveur = None

    # -- cote cerveau (boucle a 50 Hz) --------------------------------------------------------------------------
    def photographier(self, brain, state):
        """Crochet a_chaque_tick : un instantane toutes les PERIODE_INSTANTANE_S, jamais de reseau ici."""
        now = time.monotonic()
        if now - self._t_photo < PERIODE_INSTANTANE_S:
            return
        self._t_photo = now
        self.etat = instantane(brain, state, self.version)
        if now - self._t_carte >= PERIODE_CARTE_S:
            self._t_carte = now
            self.carte = carte(brain, state)

    def source(self):
        """Evenements envoyes par l'appli depuis la derniere trame (brain.run(source=...))."""
        out = []
        while True:
            try:
                out.append(self.evenements.get_nowait())
            except queue.Empty:
                return out

    # -- cote reseau --------------------------------------------------------------------------------------------
    def code_valide(self, essai, ip):
        if self._echecs.get(ip, -1e9) > time.monotonic() - 1.0:
            return False                        # au plus un essai par seconde apres un code faux
        ok = isinstance(essai, str) and hmac.compare_digest(essai.encode(), self.code.encode())
        if not ok:
            self._echecs[ip] = time.monotonic()
        return ok

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
                if not appli.code_valide(code if code is not None else self.headers.get("X-Microduck-Code"),
                                         self.client_address[0]):
                    self._json(401, {"erreur": "code d'appairage"})
                    return False
                return True

            def do_GET(self):
                url = urlparse(self.path)
                if not adresse_locale(self.client_address[0]):
                    return self._json(403, {"erreur": "reseau local seulement"})
                if url.path == "/api/sante":
                    return self._json(200, {"ok": True, "appli": "microduck", "version": appli.version})
                if url.path == "/api/etat":
                    if self._autorise():
                        self._json(200, appli.etat)
                    return
                if url.path == "/api/carte":
                    if self._autorise():
                        self._json(200, appli.carte)
                    return
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
                if urlparse(self.path).path != "/api/commande" or not self._autorise():
                    if urlparse(self.path).path != "/api/commande":
                        self._json(404, {"erreur": "inconnu"})
                    return
                try:
                    n = min(int(self.headers.get("Content-Length", "0")), 4096)
                    nom = json.loads(self.rfile.read(n) or b"{}").get("commande")
                except (ValueError, AttributeError):
                    return self._json(400, {"erreur": "JSON attendu"})
                if not appli.commande(nom):
                    return self._json(400, {"erreur": f"commande inconnue : {nom}"})
                self._json(200, {"ok": True, "commande": nom})

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
