#!/usr/bin/env python3
"""Pont Home Assistant <-> cerveau du canard.

  Maison -> canard : on ecoute les changements d'ETAT des entites listees dans `ha.toml` (imprimantes 3D :
      PrusaLink pour les Prusa, integration Elegoo pour la Saturn 4 Ultra...). Une transition vers un etat
      qui a une reaction (finished, stopped, error...) devient un evenement du cerveau ("impression_finie:MK4S")
      que `brain.py` joue en geste + voix du canard. Presence des habitants (`person.*`) : "retour:Nom|absence_s" et
      "depart:Nom" -> accueil au retour, plus chaleureux avec la familiarite et apres une longue absence.
  Canard -> maison : l'etat du robot (batterie, chute, politique active, position, etat d'esprit du cerveau)
      est publie comme entites `sensor.microduck_*` (REST `POST /api/states/...`).

Configuration : UN fichier local `ha.toml` a sections (modele : `ha.exemple.toml`) : IP de Home Assistant, jeton,
MQTT, reseau, imprimantes. Il est dans `.gitignore` (comme tout fichier `*token*`) et ne doit JAMAIS etre versionne ;
le jeton n'est jamais affiche ni ecrit dans un journal. Variante : jeton dans HA_TOKEN ou dans `token_file`.
`python pont_ha.py ha.toml --verifier` teste l'URL, le jeton, la joignabilite du broker MQTT et LISTE les entites
d'imprimante trouvees dans HA (pour recopier leurs vrais noms dans la config).

Deux facons de publier l'etat du canard :
  - REST (par defaut, rien a installer) : entites sans `unique_id` (pas editables dans l'interface de HA), qui
    disparaissent au redemarrage de HA jusqu'a la prochaine publication (< 1 min ici) ;
  - MQTT discovery (`[mqtt] actif = true`, add-on Mosquitto) : appareil "Microduck" cree automatiquement, entites
    editables et persistantes, "indisponible" si le cerveau s'arrete, interrupteur calme fourni (`switch.microduck_calme`).

Usage : bash ~/run-brain.sh pont_ha.py [ha.toml] [duree_s]
        bash ~/run-brain.sh pont_ha.py ha.toml --verifier
"""
import json
import os
import queue
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

ETATS_IGNORES = {"unavailable", "unknown", "", "none"}
ETATS_CONVERSATION = {"listening", "processing", "responding"}    # assist_satellite.* ; "idle" = fin de conversation


class ErreurAuth(Exception):
    pass


REACTIONS_PAR_TYPE = {       # etats connus par type d'integration ; pour les autres, a ecrire dans la config
    "prusalink": {"finished": "impression_finie", "stopped": "impression_echec", "error": "impression_echec",
                  "attention": "alerte", "printing": "impression_commencee"},
    # Messager de la maison (ROADMAP, table Humains "Messager physique", prochaine etape n°3) : "*" = tout nouvel
    # etat (une entite event.* de sonnette change d'etat - son horodatage - a chaque appui).
    "sonnette": {"on": "sonnette"},                 # binary_sensor de sonnette
    "sonnette_event": {"*": "sonnette"},            # event.* (sonnettes recentes : Ring, Reolink, Aqara...)
    "fumee": {"on": "alarme_fumee"},                # binary_sensor de detecteur de fumee / CO (device_class smoke)
    "aspirateur": {"cleaning": "aspirateur_on", "docked": "aspirateur_off", "idle": "aspirateur_off",   # vacuum.*
                   "returning": "aspirateur_off", "paused": "aspirateur_off", "error": "aspirateur_off"},
    "calendrier": {"on": "jour_special"},           # calendar.* : un evenement du calendrier du foyer commence
    "machine": {"finished": "machine_finie", "end": "machine_finie", "complete": "machine_finie",   # Home Connect,
                "completed": "machine_finie", "error": "machine_echec", "failure": "machine_echec"},  # ThinQ, SmartThings...
}

# Lave-linge "bete" sur une prise connectee : on suit la PUISSANCE (W). En marche au-dessus du seuil ; finie quand
# elle reste sous le seuil assez longtemps (un lave-linge s'arrete quelques minutes pendant le trempage) et seulement
# apres un vrai cycle (une prise qu'on allume 10 s n'est pas une lessive).
PUISSANCE_DEFAUTS = {"seuil_w": 5.0, "fin_apres_s": 180.0, "marche_min_s": 300.0}


def duree_etat(ancien, nouveau):
    """Combien de temps l'ancien etat a dure (s), d'apres les `last_changed` de HA ; None si inconnu."""
    from datetime import datetime
    try:
        return (datetime.fromisoformat(nouveau["last_changed"]) - datetime.fromisoformat(ancien["last_changed"])).total_seconds()
    except (TypeError, KeyError, ValueError):
        return None


def est_vide(v):
    """Vrai pour une valeur non renseignee : absente, vide ou encore le texte "A_REMPLIR..." du modele."""
    return v is None or str(v).strip() == "" or "A_REMPLIR" in str(v)


def lire_config(chemin):
    """Lit `ha.toml` (format a sections, ou l'ancien format plat) et renvoie un dict normalise."""
    with open(chemin, "rb") as f:
        return normaliser(tomllib.load(f))


def normaliser(brut):
    """Configuration brute (ha.toml, eventuellement completee par l'application : configuration.py) -> dict normalise."""
    ha = brut.get("home_assistant", {})
    cfg = {
        "url": ha.get("url") or brut.get("url"),
        "url_ws": ha.get("url_ws") or brut.get("url_ws"),
        "token": ha.get("token"),
        "token_file": ha.get("token_file") or brut.get("token_file"),
        "publier_toutes_les_s": ha.get("publier_toutes_les_s", brut.get("publier_toutes_les_s", 30)),
        "mqtt": brut.get("mqtt", {}),
        "reseau": brut.get("reseau", {}),
        "surveillance": list(brut.get("surveillance", [])),
        "interrupteur_calme": ha.get("interrupteur_calme"),
        "satellite_vocal": ha.get("satellite_vocal"),
        "cerveau": brut.get("cerveau", {}),
        "appli": brut.get("appli", {}),
        "ignorees": [],
    }
    for hab in brut.get("habitant", []):        # presence HA (person.*) -> accueil au retour
        if est_vide(hab.get("entite")) or est_vide(hab.get("nom")):
            cfg["ignorees"].append(hab.get("nom", "?"))
            continue
        cfg["surveillance"].append({"entite": hab["entite"], "nom": hab["nom"], "habitant": True})
    for imp in brut.get("imprimante", []):
        if est_vide(imp.get("entite")):
            cfg["ignorees"].append(imp.get("nom", "?"))
            continue
        cfg["surveillance"].append({
            "entite": imp["entite"], "nom": imp.get("nom", imp["entite"]),
            "reactions": imp.get("reactions") or REACTIONS_PAR_TYPE.get(imp.get("type", ""), {})})
    for dec in brut.get("declencheur", []):     # n'importe quelle entite HA -> un evenement du cerveau (jeu...)
        if est_vide(dec.get("entite")) or est_vide(dec.get("evenement")):
            cfg["ignorees"].append(dec.get("evenement", "?"))
            continue
        meme = next((s for s in cfg["surveillance"] if s["entite"] == dec["entite"] and "reactions" in s), None)
        if meme is not None:
            # plusieurs declencheurs sur la MEME entite (visiteur sur "on", visiteur_fin sur "off") : on fusionne,
            # sinon le dernier ecraserait les autres (la surveillance est indexee par entite)
            meme["reactions"][str(dec.get("etat", "*"))] = dec["evenement"]
            continue
        entree = {"entite": dec["entite"], "nom": dec.get("nom", dec["entite"]),
                  "reactions": {str(dec.get("etat", "*")): dec["evenement"]}}
        if est_vide(dec.get("nom")) and str(dec["evenement"]).startswith("visiteur"):
            entree["sans_detail"] = True        # visiteur sans prenom : un INCONNU, pas "visiteur:binary_sensor.x"
        cfg["surveillance"].append(entree)
    for app in brut.get("appareil", []):        # messager : sonnette, lave-linge, lave-vaisselle...
        if est_vide(app.get("entite")):
            cfg["ignorees"].append(app.get("nom", "?"))
            continue
        s = {"entite": app["entite"], "nom": app.get("nom", app["entite"])}
        if app.get("type") == "puissance":
            s["puissance"] = {k: float(app.get(k, v)) for k, v in PUISSANCE_DEFAUTS.items()}
        elif app.get("type") == "meteo":
            s["meteo"] = True                   # weather.* : chaque nouvel etat -> "meteo:<etat>"
        elif app.get("type") == "temperature":
            s["temperature"] = True             # sensor de temperature exterieure -> "temperature_ext:<C>" (saison)
        else:
            s["reactions"] = app.get("reactions") or REACTIONS_PAR_TYPE.get(app.get("type", ""), {})
        cfg["surveillance"].append(s)
    cfg["actions"] = []
    from commandes import VOCABULAIRE
    nom_canard = str((brut.get("cerveau") or {}).get("nom", "canard")).lower()
    interdites = set(VOCABULAIRE) | {nom_canard}
    for act in brut.get("action", []):          # canard -> maison : scenes et services HA declenches par le canard
        a = lire_action(act, interdites)
        if a is None:
            cfg["ignorees"].append(act.get("nom") or act.get("quand") or act.get("voix") or "action")
        else:
            cfg["actions"].append(a)
    if est_vide(cfg["url"]):
        cfg["url"] = None
    return cfg


def tester(url, jeton, delai=6.0):
    """Page Connexions de l'application : Home Assistant repond-il a cette adresse avec ce jeton ? -> (ok, message)."""
    import urllib.error
    import urllib.request
    if est_vide(url) or not str(url).startswith(("http://", "https://")):
        return False, "adresse attendue : http://homeassistant.local:8123"
    req = urllib.request.Request(str(url).rstrip("/") + "/api/", headers={"Authorization": f"Bearer {jeton}"})
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            return (r.status == 200), "Home Assistant répond"
    except urllib.error.HTTPError as e:
        return False, "jeton refusé" if e.code == 401 else f"erreur HTTP {e.code}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"injoignable ({getattr(e, 'reason', e)})"


def slug(texte):
    """"Allume l'entrée" -> "allume_l_entree" (identifiant d'evenement)."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().lower()
    return "_".join("".join(c if c.isalnum() else " " for c in t).split())


SANS_CIBLE = {"notify", "script", "persistent_notification", "shell_command", "rest_command"}
CLES_CIBLE = ("entity_id", "area_id", "device_id", "label_id")


def lire_heures(h):
    """[22, 6] ou "22-6" -> (22, 6) ; None si absent ; False si mal ecrit (l'action est alors ignoree, jamais "toute
    la journee" par erreur)."""
    if h is None:
        return None
    if isinstance(h, str) and "-" in h:
        h = h.split("-", 1)
    if (isinstance(h, (list, tuple)) and len(h) == 2
            and all(str(x).strip().isdigit() and 0 <= int(x) < 24 for x in h) and int(h[0]) != int(h[1])):
        return int(h[0]), int(h[1])
    return False


def lire_action(act, interdites=()):
    """[[action]] de ha.toml -> dict, ou None si incomplete ou dangereuse.
    `quand` : un etat du canard ("accueil", "nap", "bonjour"...), ou "evenement:<nom>" pour un evenement ("sonnette",
    "petarades"...) ; `voix` : phrase dite apres son nom ("canard, lumiere du salon"), reconnue SUR le canard
    (commandes.py) -> evenement "maison:<id>" ; `service` : "domaine.service" de HA ; `entite` ou une cible dans
    `donnees` : OBLIGATOIRE (sauf notify, script...) - light.turn_on sans cible allumerait toute la maison ;
    `heures` : [debut, fin] ; `delai_min_s` : 60 s par defaut, 2 s pour une phrase vocale (on peut la redire).
    `interdites` : phrases deja prises par les commandes du canard (et son nom)."""
    service = act.get("service")
    voix = None if est_vide(act.get("voix")) else " ".join(str(act["voix"]).lower().replace("'", " ").split())
    quand = None if est_vide(act.get("quand")) else str(act["quand"])
    if est_vide(service) or "." not in str(service) or (quand is None and voix is None):
        return None
    if voix is not None and voix in interdites:
        return None     # "danse", "silence", son nom... : la commande du canard gagnerait, l'action ne partirait jamais
    domaine, _, nom_service = str(service).partition(".")
    if "entite" in act and est_vide(act["entite"]):
        return None
    donnees = dict(act.get("donnees") or {})
    if not est_vide(act.get("entite")):
        donnees.setdefault("entity_id", act["entite"])
    if any(k in donnees and est_vide(donnees[k]) for k in CLES_CIBLE):
        return None
    if domaine not in SANS_CIBLE and not any(k in donnees for k in CLES_CIBLE):
        return None     # pas de cible : jamais d'appel "a toute la maison"
    heures = lire_heures(act.get("heures"))
    try:
        delai = float(act.get("delai_min_s", 2.0 if voix else 60.0))
    except (TypeError, ValueError):
        return None
    if heures is False or delai < 0:
        return None
    return {"quand": quand, "voix": voix, "voix_evt": f"maison:{slug(voix)}" if voix else None, "domaine": domaine,
            "service": nom_service, "donnees": donnees, "heures": heures, "delai_min_s": delai}


def action_concernee(action, evenement, etats=None):
    """L'evenement du canard ("etat:accueil", "sonnette:Entree", "maison:lumiere") declenche-t-il cette action ?
    `quand` simple = un ETAT du canard s'il en existe un de ce nom (`etats`), sinon un evenement ; "evenement:x" =
    l'evenement x seulement ; "etat:x" = l'etat x seulement. Une phrase vocale a son propre evenement."""
    if action.get("voix_evt") and evenement == action["voix_evt"]:
        return True
    q = action["quand"]
    if q is None:
        return False
    if q.startswith("evenement:"):
        q = q[len("evenement:"):]
        return not evenement.startswith("etat:") and (evenement == q or evenement.partition(":")[0] == q)
    if q.startswith("etat:"):
        return evenement == q
    if etats is not None and q in etats:
        return evenement == f"etat:{q}"
    if evenement.startswith("etat:"):
        return evenement[5:] == q
    return q == evenement or (":" not in q and evenement.partition(":")[0] == q)


def options_cerveau(cfg):
    """Section [cerveau] de ha.toml -> options de brain.Brain (routines a heure fixe). Tout est optionnel."""
    c = cfg.get("cerveau") or {}
    options = {}
    hc = c.get("heures_calmes")
    if isinstance(hc, str) and "-" in hc:          # "23-7" aussi accepte, en plus de [23, 7]
        debut, _, fin = hc.partition("-")
        hc = [int(debut), int(fin)] if debut.strip().isdigit() and fin.strip().isdigit() else None
    if isinstance(hc, (list, tuple)) and len(hc) == 2 and all(isinstance(h, int) and 0 <= h < 24 for h in hc):
        options["heures_calmes"] = (hc[0], hc[1])
    for cle in ("bonjour", "bonjour_weekend"):
        bj = c.get(cle)
        if isinstance(bj, int) and 0 <= bj < 24:
            options[cle] = bj
        elif isinstance(bj, str) and ":" in bj:
            h, _, m = bj.partition(":")
            if h.strip().isdigit() and m.strip().isdigit() and 0 <= int(h) < 24 and 0 <= int(m) < 60:
                options[cle] = (int(h), int(m))
    return options


def lire_jeton(cfg):
    jeton = "" if est_vide(cfg.get("token")) else str(cfg["token"]).strip()
    if not jeton:
        jeton = os.environ.get("HA_TOKEN", "").strip()
    if not jeton and cfg.get("token_file"):
        chemin = Path(os.path.expanduser(cfg["token_file"]))
        if chemin.exists():
            jeton = chemin.read_text().strip()
    if not jeton:
        raise SystemExit("Jeton Home Assistant introuvable : cree un jeton d'acces longue duree (profil HA -> "
                         "Securite) et colle-le dans la section [home_assistant] de ha.toml (champ `token`), ou dans "
                         "HA_TOKEN, ou dans le fichier indique par `token_file`.")
    return jeton


class HAClient:
    def __init__(self, url, jeton, log=print, url_ws=None):
        self.url = url.rstrip("/")
        self.jeton = jeton
        self.log = log
        self._url_ws = url_ws        # seulement pour les tests (faux HA sur deux ports) ; le vrai HA n'en a pas besoin

    @property
    def url_ws(self):
        if self._url_ws:
            return self._url_ws
        return ("wss" if self.url.startswith("https") else "ws") + self.url[self.url.index("://"):] + "/api/websocket"

    # --- maison -> canard : flux d'evenements ------------------------------------------------------
    def ecouter(self, entites, callback, arret):
        """Boucle de reconnexion : appelle callback(entite, ancien_etat, nouvel_etat) a chaque changement d'etat
        d'une entite surveillee. Ne leve jamais ; s'arrete quand `arret` (threading.Event) est positionne."""
        attente = 1.0
        while not arret.is_set():
            try:
                with connect(self.url_ws, open_timeout=10, max_size=2 ** 22) as ws:
                    json.loads(ws.recv())                                   # auth_required
                    ws.send(json.dumps({"type": "auth", "access_token": self.jeton}))
                    rep = json.loads(ws.recv())
                    if rep.get("type") != "auth_ok":
                        raise ErreurAuth(rep.get("message", rep.get("type")))
                    ws.send(json.dumps({"id": 1, "type": "subscribe_events", "event_type": "state_changed"}))
                    self.log(f"[HA] connecte a {self.url}, {len(entites)} entite(s) surveillee(s)")
                    attente = 1.0
                    while not arret.is_set():
                        try:
                            brut = ws.recv(timeout=1.0)
                        except TimeoutError:
                            continue
                        msg = json.loads(brut)
                        if msg.get("type") != "event":
                            continue
                        d = msg["event"]["data"]
                        if d["entity_id"] in entites:
                            ancien = (d.get("old_state") or {}).get("state")
                            nouveau = (d.get("new_state") or {}).get("state")
                            callback(d["entity_id"], ancien, nouveau, duree_etat(d.get("old_state"), d.get("new_state")))
            except ErreurAuth as e:
                self.log(f"[HA] jeton refuse ({e}) : verifie le fichier de jeton ; nouvel essai dans 60 s")
                attente = 60.0
            except Exception as e:
                self.log(f"[HA] connexion perdue ({type(e).__name__}: {e}) ; nouvel essai dans {attente:.0f} s")
            arret.wait(attente)
            attente = min(attente * 2, 30.0)

    # --- canard -> maison : REST -------------------------------------------------------------------
    def _get(self, chemin):
        req = urllib.request.Request(self.url + chemin, headers={"Authorization": f"Bearer {self.jeton}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())

    def _post(self, chemin, corps):
        req = urllib.request.Request(
            self.url + chemin, data=json.dumps(corps).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.jeton}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status

    def pousser_etat(self, entite, etat, attributs=None):
        return self._post(f"/api/states/{entite}", {"state": str(etat), "attributes": attributs or {}})

    def appeler_service(self, domaine, service, donnees=None):
        """Le canard declenche une scene / un service de la maison : appeler_service("scene", "turn_on",
        {"entity_id": "scene.salon_film"})."""
        return self._post(f"/api/services/{domaine}/{service}", donnees or {})


class PublieurMQTT:
    """Entites du canard par MQTT discovery (add-on Mosquitto de HA) : creees automatiquement sous un appareil
    "Microduck", editables dans l'interface (unique_id), conservees au redemarrage de HA (messages retenus), et
    "indisponibles" si le cerveau s'arrete ou perd le reseau (testament MQTT). Expose aussi l'interrupteur calme
    (`switch.microduck_calme`) : plus besoin de creer l'input_boolean a la main."""
    PREFIXE = "microduck"
    DECOUVERTE = "homeassistant"
    APPAREIL = {"identifiers": ["microduck"], "name": "Microduck", "manufacturer": "Pollen Robotics", "model": "Microduck"}
    CLES_CONFIG = ("unit_of_measurement", "device_class", "icon")
    # (objet, nom dans HA, icone, charge MQTT = evenement du cerveau) ; seules ces charges sont acceptees
    BOUTONS = (("jouer_soleil", "jouer a 1-2-3 soleil", "mdi:weather-sunny", "jeu_soleil"),
               ("fin_jeu", "fin du jeu", "mdi:stop-circle-outline", "fin_jeu"),
               ("jouer_cache", "jouer a cache-cache", "mdi:eye-off-outline", "jeu_cache"),
               ("jouer_balle", "jouer a la balle", "mdi:soccer", "jeu_balle"),
               ("stop_taquinerie", "arrete de me taquiner", "mdi:hand-back-left", "stop_taquinerie"),
               ("tour_salut", "tour : salut", "mdi:hand-wave", "tour_salut"),
               ("tour_toupie", "tour : toupie", "mdi:rotate-360", "tour_toupie"),
               ("tour_assis", "tour : assis / debout", "mdi:seat", "tour_assis"),
               ("diagnostic", "lancer le diagnostic", "mdi:stethoscope", "diagnostic"),
               ("ou_es_tu", "ou es-tu ?", "mdi:map-marker-question", "ou_es_tu"),
               ("signal_stop", "arrete le signal (minuteur, reveil)", "mdi:bell-off", "signal_stop"),
               ("suis_moi", "suis-moi", "mdi:shoe-print", "suis_moi"),
               ("je_te_suis", "montre-moi le chemin", "mdi:walk", "je_te_suis"))

    def __init__(self, mq, log=print, sur_evenement=None):
        import paho.mqtt.client as mqtt
        self.log = log
        self.sur_evenement = sur_evenement      # callback(nom) : "calme_on" / "calme_off" vers le cerveau
        self.annonces = set()
        self.connecte = False
        self.calme_lu = False
        self.dispo = f"{self.PREFIXE}/disponible"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="microduck-cerveau")
        if not est_vide(mq.get("utilisateur")):
            self.client.username_pw_set(mq["utilisateur"], None if est_vide(mq.get("mot_de_passe")) else mq["mot_de_passe"])
        self.client.will_set(self.dispo, "offline", retain=True)
        self.client.on_connect = self._sur_connexion
        self.client.on_disconnect = self._sur_deconnexion
        self.client.on_message = self._sur_message
        self.client.reconnect_delay_set(1, 30)
        self.hote, self.port = mq["hote"], int(mq.get("port", 1883))
        self.client.connect_async(self.hote, self.port, keepalive=30)
        self.client.loop_start()

    def _sur_connexion(self, client, userdata, flags, code, proprietes=None):
        if code.is_failure:
            self.log(f"[MQTT] connexion refusee par {self.hote}:{self.port} ({code}) : verifie utilisateur / mot de passe")
            return
        self.connecte = True
        self.annonces.clear()                   # on re-annonce tout apres une reconnexion (broker redemarre sans persistance)
        client.publish(self.dispo, "online", retain=True)
        self._annoncer("switch", "calme", {
            "name": "calme", "icon": "mdi:sleep", "command_topic": f"{self.PREFIXE}/calme/set",
            "state_topic": f"{self.PREFIXE}/calme/etat"})
        for objet, nom, icone, charge in self.BOUTONS:          # jeux et commandes : un bouton dans HA -> un evenement
            self._annoncer("button", objet, {"name": nom, "icon": icone, "command_topic": f"{self.PREFIXE}/commande",
                                             "payload_press": charge})
        client.subscribe([(f"{self.PREFIXE}/calme/set", 1), (f"{self.PREFIXE}/calme/etat", 1),
                          (f"{self.PREFIXE}/commande", 1)])
        self.log(f"[MQTT] connecte a {self.hote}:{self.port} (decouverte Home Assistant)")

    def _sur_deconnexion(self, client, userdata, drapeaux, code, proprietes=None):
        if self.connecte:
            self.log(f"[MQTT] deconnecte ({code}) ; reconnexion automatique")
        self.connecte = False

    def _sur_message(self, client, userdata, msg):
        if msg.topic == f"{self.PREFIXE}/commande":
            commande = msg.payload.decode(errors="replace").strip()
            if commande in {b[3] for b in self.BOUTONS} and self.sur_evenement:
                self.sur_evenement(commande)
            return
        charge = msg.payload.decode(errors="replace").strip().upper()
        if charge not in ("ON", "OFF"):
            return
        if msg.topic.endswith("/calme/set"):
            client.publish(f"{self.PREFIXE}/calme/etat", charge, retain=True)
        elif self.calme_lu:
            return                              # notre propre etat qui revient : deja traite
        self.calme_lu = True                    # au demarrage, l'etat retenu restaure le mode calme d'avant
        if self.sur_evenement:
            self.sur_evenement("calme_on" if charge == "ON" else "calme_off")

    def _annoncer(self, composant, objet, config):
        config = {**config, "unique_id": f"microduck_{objet}", "object_id": f"microduck_{objet}",
                  "availability_topic": self.dispo, "device": self.APPAREIL}
        self.client.publish(f"{self.DECOUVERTE}/{composant}/{self.PREFIXE}/{objet}/config", json.dumps(config), retain=True)
        self.annonces.add(f"{composant}.{objet}")

    def publier(self, entite, etat, attributs):
        """entite "sensor.microduck_batterie" -> topics microduck/batterie/... ; False si le broker n'est pas joignable."""
        if not self.connecte:
            return False
        composant, objet = entite.split(".", 1)
        objet = objet.removeprefix("microduck_")
        base = f"{self.PREFIXE}/{objet}"
        if f"{composant}.{objet}" not in self.annonces:
            config = {"name": attributs.get("friendly_name", objet).removeprefix("Microduck - "),
                      "state_topic": f"{base}/etat", "json_attributes_topic": f"{base}/attributs"}
            config.update({k: attributs[k] for k in self.CLES_CONFIG if k in attributs})
            if composant == "binary_sensor":
                config.update({"payload_on": "on", "payload_off": "off"})
            self._annoncer(composant, objet, config)
        autres = {k: v for k, v in attributs.items() if k not in self.CLES_CONFIG and k != "friendly_name"}
        self.client.publish(f"{base}/etat", str(etat), retain=True)
        self.client.publish(f"{base}/attributs", json.dumps(autres), retain=True)
        return True

    def arreter(self):
        if self.connecte:
            self.client.publish(self.dispo, "offline", retain=True).wait_for_publish(2)
        self.client.disconnect()
        self.client.loop_stop()


class PontHA:
    def __init__(self, cfg, jeton, log=print, horloge=time.monotonic):
        self.cfg = cfg
        self.horloge = horloge
        self._verrou_puissances = threading.Lock()   # _sur_puissance (fil WebSocket) / _verifie_puissances (cerveau)
        self._puissances = {}                   # entite -> {"debut": instant de mise en marche, "sous_seuil": instant}
        self.log = log
        self.client = HAClient(cfg["url"], jeton, log, cfg.get("url_ws"))
        self.evenements = queue.SimpleQueue()
        self.arret = threading.Event()
        self.surveillance = {s["entite"]: s for s in cfg["surveillance"]}
        self.calme = None if est_vide(cfg.get("interrupteur_calme")) else cfg["interrupteur_calme"]
        if self.calme:                          # regle de vie : interrupteur "calme" (input_boolean dans HA)
            self.surveillance[self.calme] = {"nom": "calme", "reactions": {"on": "calme_on", "off": "calme_off"}}
        # Satellite vocal (quacksat en mode wyoming = entite assist_satellite.* dans HA) : pendant une conversation, le
        # cerveau se tait et ne commande plus rien (quacksat pilote la tete et peut faire marcher le canard).
        self.satellite = None if est_vide(cfg.get("satellite_vocal")) else cfg["satellite_vocal"]
        self._ecoute = False
        if self.satellite:
            self.surveillance[self.satellite] = {"nom": "satellite", "satellite": True}
        self.instantane = {}                    # derniere photo de l'etat du canard, ecrite par le cerveau
        self._derniers = {}                     # entite -> (etat, instant de la derniere publication)
        self._threads = []
        self.mqtt = None                        # PublieurMQTT si [mqtt] actif = true (sinon publication REST)
        self._derniere_vue_chat = None           # time.time() de la derniere fois ou la veille camera l'a vu
        self._actions = queue.Queue()            # actions domotiques a executer (fil _executer_actions)
        self._derniere_action = {}               # index de l'action -> instant du dernier declenchement

    # evenements maison -> cerveau
    def _sur_changement(self, entite, ancien, nouveau, duree_ancien=None):
        if nouveau is None or nouveau.lower() in ETATS_IGNORES or nouveau == ancien:
            return
        s = self.surveillance[entite]
        if s.get("satellite"):
            actif = nouveau.lower() in ETATS_CONVERSATION
            if actif != self._ecoute:
                self._ecoute = actif
                self.log(f"[HA] satellite vocal : {nouveau} -> conversation {'en cours' if actif else 'terminee'}")
                self.evenements.put("ecoute_on" if actif else "ecoute_off")
            return
        if s.get("habitant"):
            # person.* : "home", "not_home" ou le nom d'une zone ("Travail"...). Un passage par unavailable (redemarrage
            # de HA) ou la premiere apparition ne sont ni un retour ni un depart.
            if ancien is None or ancien.lower() in ETATS_IGNORES:
                return
            if nouveau.lower() == "home":
                absence = f"|{int(duree_ancien)}" if duree_ancien is not None and duree_ancien >= 0 else ""
                self.log(f"[HA] {s['nom']} rentre a la maison" + (f" ({int(duree_ancien) // 60} min d'absence)" if absence else ""))
                self.evenements.put(f"retour:{s['nom']}{absence}")
            elif ancien.lower() == "home":
                self.log(f"[HA] {s['nom']} quitte la maison")
                self.evenements.put(f"depart:{s['nom']}")
            return
        if s.get("puissance"):
            self._sur_puissance(entite, s, nouveau)
            return
        if s.get("temperature"):
            try:
                c = float(nouveau)
            except ValueError:
                return
            derniers = self.__dict__.setdefault("_dernieres_temperatures", {})     # par capteur
            dernier = derniers.get(entite)
            if dernier is None or abs(c - dernier) >= 1.0:      # au degre pres : pas un evenement par dixieme
                derniers[entite] = c
                self.evenements.put(f"temperature_ext:{c:.1f}")
            return
        if s.get("meteo"):
            self.log(f"[HA] meteo : {ancien} -> {nouveau}")
            self.evenements.put(f"meteo:{nouveau.lower()}")
            return
        reactions = {k.lower(): v for k, v in s.get("reactions", {}).items()}
        reaction = reactions.get(nouveau.lower())
        if reaction is None and "*" in reactions and ancien is not None and ancien.lower() not in ETATS_IGNORES:
            # "tout nouvel etat" (sonnette event.*, input_button) : jamais au retour d'un "unavailable" (redemarrage de
            # HA, reconnexion) ni a la premiere apparition - sinon fausse sonnette / jeu lance a chaque redemarrage
            reaction = reactions["*"]
        self.log(f"[HA] {entite}: {ancien} -> {nouveau}" + (f"  => {reaction}" if reaction else ""))
        if reaction:
            self.evenements.put(reaction if entite == self.calme or s.get("sans_detail")
                                else f"{reaction}:{s.get('nom', entite)}")

    def _sur_puissance(self, entite, s, valeur):
        try:
            w = float(valeur)
        except ValueError:
            return
        p, now = s["puissance"], self.horloge()
        with self._verrou_puissances:
            self._maj_puissance(entite, s, p, w, now)

    def _maj_puissance(self, entite, s, p, w, now):
        suivi = self._puissances.setdefault(entite, {"debut": None, "sous_seuil": None})
        if w > p["seuil_w"]:
            if suivi["debut"] is None:
                suivi["debut"] = now
                self.log(f"[HA] {s['nom']} : en marche ({w:.0f} W)")
            suivi["sous_seuil"] = None
        elif suivi["debut"] is not None and suivi["sous_seuil"] is None:
            suivi["sous_seuil"] = now           # peut-etre la fin, peut-etre une pause : verdict dans _verifie_puissances

    def _verifie_puissances(self):
        now = self.horloge()
        with self._verrou_puissances:            # le fil WebSocket peut ajouter une prise pendant qu'on parcourt
            for entite, suivi in self._puissances.items():
                if suivi["debut"] is None or suivi["sous_seuil"] is None:
                    continue
                p, nom = self.surveillance[entite]["puissance"], self.surveillance[entite]["nom"]
                if now - suivi["sous_seuil"] < p["fin_apres_s"]:
                    continue
                duree = suivi["sous_seuil"] - suivi["debut"]
                suivi["debut"] = suivi["sous_seuil"] = None
                if duree >= p["marche_min_s"]:
                    self.log(f"[HA] {nom} : cycle termine ({duree / 60:.0f} min)")
                    self.evenements.put(f"machine_finie:{nom}")

    # canard -> maison : actions (scenes, services) ------------------------------------------------------------------
    def _sur_canard(self, evenement):
        """Ecouteur du cerveau (Brain.ecouteurs) : appele dans le fil du tick, il ne fait que mettre en file."""
        if evenement.startswith("garde:"):
            # mode garde : un evenement HA "microduck_garde" {type: voix|choc|bruit|porte} - a tes automatisations
            # d'en faire une notification ; aucun son ne quitte le canard
            self._actions.put(("@evenement", "microduck_garde", {"type": evenement[6:]}, evenement))
            return
        now = self.horloge()
        heure = time.localtime().tm_hour
        etats = getattr(self, "_etats_canard", None)
        partie = False
        for i, a in enumerate(self.cfg.get("actions") or ()):
            if not action_concernee(a, evenement, etats):
                continue
            if a["heures"] is not None:
                debut, fin = a["heures"]
                if not ((heure >= debut or heure < fin) if debut > fin else (debut <= heure < fin)):
                    continue
            if now - self._derniere_action.get(i, -1e9) < a["delai_min_s"]:
                continue
            self._derniere_action[i] = now
            self._actions.put((a["domaine"], a["service"], a["donnees"], evenement))
            partie = True
        if evenement.startswith("maison:") and getattr(self, "_cerveau", None) is not None:
            # accuse de reception HONNETE : "oui" seulement si la commande part vraiment (plage horaire, delai...)
            self._cerveau.evenement("maison_ok" if partie else "maison_refus")

    def _ecoute_le_canard(self):
        cfg = getattr(self, "cfg", None) or {}
        return bool(cfg.get("actions") or (cfg.get("cerveau") or {}).get("garde"))

    def _executer_actions(self):
        while not self.arret.is_set():
            try:
                domaine, service, donnees, pourquoi = self._actions.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                if domaine == "@evenement":
                    self.client._post(f"/api/events/{service}", donnees)
                    self.log(f"[HA] evenement {service} {donnees}")
                    continue
                self.client.appeler_service(domaine, service, donnees)
                self.log(f"[HA] {pourquoi} -> {domaine}.{service} {donnees.get('entity_id', '')}")
            except Exception as e:                  # HA injoignable : le canard continue sa vie
                self.log(f"[HA] {domaine}.{service} impossible ({type(e).__name__})")

    def lire_presence_initiale(self):
        """Au demarrage, qui est DEJA a la maison (person.*) : "presence:Nom|home" ou "presence:Nom|absent", sans
        accueil ni rituel. Sans cela, "personne a la maison" (lumiere oubliee...) n'aurait pas de sens."""
        for entite, s in self.surveillance.items():
            if not s.get("habitant"):
                continue
            try:
                etat = (self.client._get(f"/api/states/{entite}").get("state") or "").lower()
            except Exception as e:
                self.log(f"[HA] presence de {s['nom']} illisible : {type(e).__name__}")
                self.evenements.put(f"presence:{s['nom']}|inconnu")
                continue
            # inconnu (HA ne sait pas, ou ne repond pas pour lui) : la maison ne sera pas tenue pour "vide"
            self.evenements.put(f"presence:{s['nom']}|"
                                f"{'inconnu' if not etat or etat in ETATS_IGNORES else 'home' if etat == 'home' else 'absent'}")

    def lire_calme_initial(self):
        """Au demarrage, applique l'etat ACTUEL de l'interrupteur calme (sinon un canard relance la nuit ferait du bruit)."""
        if not self.calme:
            return
        try:
            etat = self.client._get(f"/api/states/{self.calme}").get("state")
            if etat in ("on", "off"):
                self.evenements.put("calme_on" if etat == "on" else "calme_off")
        except urllib.error.HTTPError as e:
            self.log(f"[HA] interrupteur {self.calme} introuvable ({e.code}) : cree-le dans HA (Parametres -> Appareils et "
                     "services -> Entrees -> Interrupteur)" if e.code == 404 else f"[HA] interrupteur calme : HTTP {e.code}")
        except Exception as e:
            self.log(f"[HA] interrupteur calme illisible : {type(e).__name__}")

    def source(self):
        """A passer a brain.run(source=...) : evenements arrives depuis la derniere trame."""
        self._verifie_puissances()
        out = []
        while True:
            try:
                out.append(self.evenements.get_nowait())
            except queue.Empty:
                return out

    # canard -> maison
    def photographier(self, brain, state):
        """A passer a brain.run(a_chaque_tick=...) : memorise l'etat courant (rapide, sans reseau)."""
        if self._ecoute_le_canard() and self._sur_canard not in getattr(brain, "ecouteurs", [self._sur_canard]):
            self._cerveau, self._etats_canard = brain, set(getattr(brain, "etats", {}))
            brain.ecouteurs.append(self._sur_canard)        # a la premiere trame : actions domotiques du canard
        # veille camera du chat (chat.py, extras du cerveau) : optionnelle, absente dans les tests qui n'en ont pas besoin.
        chat = (getattr(brain, "ctx", None) and (brain.ctx.extras or {}).get("chat"))
        chat_visible = bool(chat is not None and getattr(getattr(chat, "suivi", None), "visible", False))
        if chat_visible:
            self._derniere_vue_chat = time.time()
        self.instantane = {
            "etat": brain.courant.nom, "energie": brain.humeur.energie, "eveil": brain.humeur.eveil,
            "tombe": bool((state.get("safety") or {}).get("fallen")), "politique": state.get("policy"),
            "batterie": state.get("battery"), "odom": state.get("odom"), "chat_visible": chat_visible,
            "presents": sorted(getattr(brain, "presents", None) or []),
            "messages": list(getattr(brain, "messages", None) or []),
            "veille": getattr(brain, "t_global", 0.0) < getattr(brain, "veille_jusqua", -1.0),
            "temperatures": dict(getattr(brain, "temperatures", None) or {}),
            "traits": dict(brain.perso.d["traits"]) if hasattr(brain, "perso") else None,
            "blagues": brain.malice.compte() if hasattr(brain, "malice") else None,
            "diagnostic": self._resume_diagnostic(brain),
            "objets_au_sol": list(getattr(brain, "objets_au_sol", None) or []),
            "du_jour": dict(getattr(brain, "du_jour", None) or {}),
            "lumiere_oubliee": getattr(brain, "lumiere_oubliee", False), "lumiere": getattr(brain, "lumiere", None),
            "derniere_blague": (brain.malice.historique[-1][1] if getattr(getattr(brain, "malice", None), "historique", None)
                                else None),
        }

    def _resume_diagnostic(self, brain):
        """diagnostic.resume() au plus une fois toutes les 10 s : photographier() tourne a chaque trame (50 Hz) et le
        resume parcourt l'historique (chutes, jours de mesures des servos) - jamais dans le budget d'une trame."""
        if not hasattr(brain, "diagnostic"):
            return None
        now = time.monotonic()
        cache = getattr(self, "_cache_diag", None)
        if cache is None or now - cache[0] >= 10.0:
            self._cache_diag = cache = (now, brain.diagnostic.resume())
        return cache[1]

    def entites_du_canard(self):
        i = self.instantane
        if not i:
            return {}
        ent = {
            "sensor.microduck_etat": (i["etat"], {"friendly_name": "Microduck - etat d'esprit", "icon": "mdi:duck"}),
            "sensor.microduck_energie": (round(i["energie"] * 100), {
                "friendly_name": "Microduck - energie", "unit_of_measurement": "%", "icon": "mdi:flash"}),
            "sensor.microduck_eveil": (round(i["eveil"] * 100), {
                "friendly_name": "Microduck - eveil", "unit_of_measurement": "%", "icon": "mdi:eye"}),
            "sensor.microduck_politique": (i["politique"], {"friendly_name": "Microduck - politique active"}),
            "sensor.microduck_habitants_presents": (len(i["presents"]), {
                "friendly_name": "Microduck - habitants presents (connus de lui)", "icon": "mdi:account-group",
                "noms": ", ".join(i["presents"]) or None}),
            "binary_sensor.microduck_tombe": ("on" if i["tombe"] else "off", {
                "friendly_name": "Microduck - tombe", "device_class": "problem"}),
        }
        if i.get("batterie"):
            b = i["batterie"]
            ent["sensor.microduck_batterie"] = (round(b.get("percent", 0)), {
                "friendly_name": "Microduck - batterie", "unit_of_measurement": "%", "device_class": "battery",
                "volts": b.get("volts")})
        if i.get("odom"):
            p = i["odom"]["position"]
            ent["sensor.microduck_position"] = (f"{p[0]:.2f},{p[1]:.2f}", {
                "friendly_name": "Microduck - position (odometrie)", "x": round(p[0], 3), "y": round(p[1], 3),
                "cap_deg": round(i["odom"]["yaw"] * 57.2958, 1)})
        msgs = i.get("messages") or []
        ent["sensor.microduck_messages"] = (len(msgs), {
            "friendly_name": "Microduck - messages a transmettre", "icon": "mdi:email-outline",
            "messages": ", ".join(msgs) or None})
        if i.get("traits"):
            dominant = max(i["traits"], key=i["traits"].get)
            ent["sensor.microduck_personnalite"] = (dominant, {
                "friendly_name": "Microduck - trait dominant", "icon": "mdi:emoticon-outline",
                **{k: round(v * 100) for k, v in i["traits"].items()}})
        t_moteurs = (i.get("temperatures") or {}).get("moteurs")
        if t_moteurs is not None:
            ent["sensor.microduck_temperature_servos"] = (round(t_moteurs), {
                "friendly_name": "Microduck - servo le plus chaud", "unit_of_measurement": "°C",
                "device_class": "temperature"})
        ent["binary_sensor.microduck_veille"] = ("on" if i.get("veille") else "off", {
            "friendly_name": "Microduck - en veille apres des chutes", "icon": "mdi:sleep"})
        if i.get("blagues") is not None:
            ent["sensor.microduck_blagues"] = (i["blagues"], {
                "friendly_name": "Microduck - taquineries (total)", "icon": "mdi:emoticon-wink-outline",
                "derniere": i.get("derniere_blague")})
        dg = i.get("diagnostic")
        if dg:
            # auto-surveillance (diagnostic.py) : ce qui derive chez le canard lui-meme, avant la panne
            if dg["autonomie_h"] is not None:
                ent["sensor.microduck_autonomie"] = (dg["autonomie_h"], {
                    "friendly_name": "Microduck - autonomie estimee", "unit_of_measurement": "h", "icon": "mdi:timer",
                    "cycles": dg["cycles"]})
            if dg["sante_batterie"] is not None:
                ent["sensor.microduck_sante_batterie"] = (dg["sante_batterie"], {
                    "friendly_name": "Microduck - sante de la batterie", "unit_of_measurement": "%",
                    "icon": "mdi:battery-heart-variant", "a_remplacer": dg["batterie_a_remplacer"]})
            ent["binary_sensor.microduck_servos_derive"] = ("on" if dg["servos_derive"] else "off", {
                "friendly_name": "Microduck - servo a surveiller", "device_class": "problem",
                "servos": ", ".join(dg["servos_derive"]) or None, "plus_chaud_habituel": dg["servo_chaud_habituel"]})
            ent["sensor.microduck_chutes_7j"] = (dg["chutes_7j"], {
                "friendly_name": "Microduck - chutes (7 jours)", "icon": "mdi:human-fall",
                "activite_risquee": dg["activite_risquee"], "lieux_a_risque": dg["lieux_a_risque"]})
            if dg["autotest_ok"] is not None:
                ent["binary_sensor.microduck_autotest"] = ("off" if dg["autotest_ok"] else "on", {
                    "friendly_name": "Microduck - diagnostic", "device_class": "problem",
                    "echecs": ", ".join(dg["autotest_echecs"]) or None,
                    "le": dg.get("autotest_le"), **(dg.get("autotest_detail") or {})})
        dj = i.get("du_jour") or {}
        ent["sensor.microduck_journal"] = (sum(dj.values()), {
            "friendly_name": "Microduck - journal de bord du jour", "icon": "mdi:notebook-outline",
            **{k: dj.get(k, 0) for k in ("promenades", "siestes", "jeux", "danses", "caresses", "accueils",
                                         "folles_courses", "blagues")}})
        objets = [o for o in (i.get("objets_au_sol") or []) if time.time() - o[0] <= 86400]
        ent["sensor.microduck_objets_au_sol"] = (len(objets), {
            "friendly_name": "Microduck - objets nouveaux au sol (24 h)", "icon": "mdi:shoe-sneaker",
            "dernier_il_y_a_min": round((time.time() - objets[-1][0]) / 60) if objets else None,
            "dernier_position_odom": f"{objets[-1][1]:.2f},{objets[-1][2]:.2f}" if objets else None})
        ent["binary_sensor.microduck_lumiere_oubliee"] = ("on" if i.get("lumiere_oubliee") else "off", {
            "friendly_name": "Microduck - lumiere allumee sans personne", "icon": "mdi:lightbulb-alert",
            "luminosite": round(i["lumiere"], 2) if i.get("lumiere") is not None else None})
        attrs_chat = {"friendly_name": "Microduck - chat vu", "icon": "mdi:cat"}
        if self._derniere_vue_chat is not None:
            attrs_chat["derniere_vue_il_y_a_s"] = round(time.time() - self._derniere_vue_chat, 1)
        ent["binary_sensor.microduck_chat_vu"] = ("on" if i.get("chat_visible") else "off", attrs_chat)
        return ent

    def _publier(self):
        periode = self.cfg["publier_toutes_les_s"]
        while not self.arret.wait(1.0):
            now = time.monotonic()
            for entite, (etat, attrs) in self.entites_du_canard().items():
                avant = self._derniers.get(entite)
                if avant and avant[0] == etat and now - avant[1] < periode:
                    continue                    # inchange et publie recemment : on ne spamme pas HA
                try:
                    if self.mqtt is not None:
                        if self.mqtt.publier(entite, etat, attrs):
                            self._derniers[entite] = (etat, now)
                        continue                # broker injoignable : paho se reconnecte seul, on republiera
                    self.client.pousser_etat(entite, etat, attrs)
                    self._derniers[entite] = (etat, now)
                except (urllib.error.URLError, OSError) as e:
                    self.log(f"[HA] publication de {entite} impossible : {e}")
                    self._derniers[entite] = (etat, now)   # pas de rafale d'erreurs : on reessaiera a la prochaine periode

    def demarrer(self):
        mq = self.cfg.get("mqtt") or {}
        if mq.get("actif") and not est_vide(mq.get("hote")):
            self.mqtt = PublieurMQTT(mq, self.log, sur_evenement=self.evenements.put)
        self.lire_calme_initial()
        self.lire_presence_initiale()
        if self._ecoute_le_canard():
            threading.Thread(target=self._executer_actions, daemon=True).start()
        entites = set(self.surveillance)
        for cible in (lambda: self.client.ecouter(entites, self._sur_changement, self.arret), self._publier):
            t = threading.Thread(target=cible, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self.arret.set()
        if self.mqtt is not None:
            self.mqtt.arreter()


def tester_identifiants_mqtt(mq, delai=6.0):
    """Vraie connexion MQTT (sans rien publier) : True si le broker accepte l'utilisateur / mot de passe."""
    import paho.mqtt.client as mqtt
    fini, ok = threading.Event(), []
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="microduck-verifier")
    if not est_vide(mq.get("utilisateur")):
        cli.username_pw_set(mq["utilisateur"], None if est_vide(mq.get("mot_de_passe")) else mq["mot_de_passe"])
    cli.on_connect = lambda c, u, f, code, p=None: (ok.append(not code.is_failure), fini.set())
    try:
        cli.connect(mq["hote"], int(mq.get("port", 1883)), keepalive=10)
        cli.loop_start()
        fini.wait(delai)
        cli.disconnect()
        cli.loop_stop()
    except OSError:
        return False
    return bool(ok and ok[0])


MOTS_IMPRIMANTE = ("prusa", "elegoo", "saturn", "printer", "imprim", "mk3", "mk4", "resin", "print")


def verifier(cfg, jeton, log=print):
    """Teste la config SANS rien modifier : URL, jeton (REST puis WebSocket), broker MQTT, et liste les entites qui
    ressemblent a une imprimante. Renvoie un dict de resultats (utilise par les tests)."""
    import socket
    res = {"rest": False, "ws": False, "mqtt": None, "entites": []}
    cli = HAClient(cfg["url"], jeton, log, cfg.get("url_ws"))
    try:
        info = cli._get("/api/config")
        res["rest"], res["version"] = True, info.get("version")
        log(f"[OK] REST : Home Assistant {info.get('version')} repond et accepte le jeton")
    except urllib.error.HTTPError as e:
        log("[ECHEC] REST : jeton refuse (401), recree un jeton d'acces longue duree" if e.code == 401
            else f"[ECHEC] REST : HTTP {e.code}")
    except Exception as e:
        log(f"[ECHEC] REST : {cfg['url']} injoignable ({type(e).__name__}) : bonne IP ? meme reseau ? port 8123 ?")
    if res["rest"]:
        try:
            with connect(cli.url_ws, open_timeout=8) as ws:
                json.loads(ws.recv())
                ws.send(json.dumps({"type": "auth", "access_token": jeton}))
                res["ws"] = json.loads(ws.recv()).get("type") == "auth_ok"
            log("[OK] WebSocket : authentification acceptee" if res["ws"] else "[ECHEC] WebSocket : jeton refuse")
        except Exception as e:
            log(f"[ECHEC] WebSocket : {type(e).__name__}: {e}")
        try:
            for e in cli._get("/api/states"):
                nom = (e.get("attributes") or {}).get("friendly_name", "")
                if e["entity_id"].split(".")[0] in ("sensor", "binary_sensor", "select", "update") and any(
                        m in (e["entity_id"] + " " + nom).lower() for m in MOTS_IMPRIMANTE):
                    res["entites"].append((e["entity_id"], e["state"], nom))
                if e["entity_id"].startswith("person."):
                    res.setdefault("personnes", []).append((e["entity_id"], e["state"], nom))
                if e["entity_id"].startswith("assist_satellite."):
                    res.setdefault("satellites", []).append((e["entity_id"], e["state"], nom))
            log(f"[INFO] {len(res['entites'])} entite(s) qui ressemblent a une imprimante (recopie `entite` dans ha.toml) :")
            for ent, etat, nom in res["entites"][:60]:
                log(f"         {ent}  =  {etat}   ({nom})")
            log(f"[INFO] {len(res.get('personnes', []))} personne(s) (section [[habitant]] de ha.toml) :")
            for ent, etat, nom in res.get("personnes", []):
                log(f"         {ent}  =  {etat}   ({nom})")
            for ent, etat, nom in res.get("satellites", []):
                log(f"[INFO] satellite vocal : {ent} = {etat} ({nom}) -> `satellite_vocal` dans [home_assistant]")
        except Exception as e:
            log(f"[ECHEC] liste des entites : {type(e).__name__}: {e}")
    mq = cfg.get("mqtt") or {}
    if mq.get("actif") and not est_vide(mq.get("hote")):
        try:
            socket.create_connection((mq["hote"], int(mq.get("port", 1883))), timeout=4).close()
            res["mqtt"] = True
        except OSError as e:
            res["mqtt"] = False
            log(f"[ECHEC] MQTT : {mq['hote']}:{mq.get('port', 1883)} injoignable ({e}) : add-on Mosquitto demarre ?")
        if res["mqtt"]:
            res["mqtt_auth"] = tester_identifiants_mqtt(mq)
            log(f"[OK] MQTT : {mq['hote']}:{mq.get('port', 1883)} accepte les identifiants du canard" if res["mqtt_auth"]
                else "[ECHEC] MQTT : le broker repond mais refuse les identifiants (utilisateur / mot de passe dans [mqtt])")
    for nom in cfg.get("ignorees", []):
        log(f"[A FAIRE] '{nom}' ignore(e) : `entite` pas encore renseignee")
    return res


def avertir_si_non_ignore(chemin):
    """Le fichier de config contient un jeton : on previent si git ne l'ignore PAS (risque de fuite sur GitHub)."""
    import subprocess
    try:
        r = subprocess.run(["git", "check-ignore", "-q", str(chemin)], cwd=Path(chemin).resolve().parent,
                           capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return
    if r.returncode == 1:       # 0 = ignore, 1 = dans un depot mais NON ignore, 128 = pas un depot
        print(f"!!! ATTENTION : {chemin} n'est PAS ignore par git alors qu'il contient un jeton : "
              "ajoute-le a .gitignore avant tout commit.", flush=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    chemin = args[0] if args else str(Path(__file__).parent / "ha.toml")
    duree = float(args[1]) if len(args) > 1 else 3600.0
    if not Path(chemin).exists():
        raise SystemExit(f"config absente : {chemin} (copie ha.exemple.toml en ha.toml et remplis-le)")
    avertir_si_non_ignore(chemin)
    cfg = lire_config(chemin)
    if cfg["url"] is None:
        raise SystemExit("ha.toml : renseigne `url` dans la section [home_assistant] (ex. http://192.168.1.50:8123)")
    if "--verifier" in sys.argv:
        verifier(cfg, lire_jeton(cfg))
        return
    if not cfg["surveillance"]:
        print("(aucune imprimante renseignee : le pont publiera seulement l'etat du canard)", flush=True)
    pont = PontHA(cfg, lire_jeton(cfg), log=lambda m: print(m, flush=True))
    import brain
    from poc_robotd_client import RobotdClient, SOCK_PATH
    c = RobotdClient(SOCK_PATH)
    hz = (cfg.get("reseau") or {}).get("etat_hz")
    # Le cerveau n'a pas besoin des 50 trames d'etat par seconde ; le deadman de
    # `robot.move` (500 ms) exige seulement >= 10 envois par seconde.
    c.request("robot.subscribe", {"hz": int(hz)} if isinstance(hz, int) and 10 <= hz <= 50 else {})
    pont.demarrer()
    try:
        brain.run(c, duree, source=pont.source, a_chaque_tick=pont.photographier, **options_cerveau(cfg))
    finally:
        pont.stop()


if __name__ == "__main__":
    main()
