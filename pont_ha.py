#!/usr/bin/env python3
"""Pont Home Assistant <-> cerveau du canard.

  Maison -> canard : on ecoute les changements d'ETAT des entites listees dans `ha.toml` (imprimantes 3D :
      PrusaLink pour les Prusa, integration Elegoo pour la Saturn 4 Ultra...). Une transition vers un etat
      qui a une reaction (finished, stopped, error...) devient un evenement du cerveau ("impression_finie:MK4S")
      que `brain.py` joue en geste + voix du canard.
  Canard -> maison : l'etat du robot (batterie, chute, politique active, position, etat d'esprit du cerveau)
      est publie comme entites `sensor.microduck_*` (REST `POST /api/states/...`).

Configuration : UN fichier local `ha.toml` a sections (modele : `ha.exemple.toml`) : IP de Home Assistant, jeton,
MQTT, reseau, imprimantes. Il est dans `.gitignore` (comme tout fichier `*token*`) et ne doit JAMAIS etre versionne ;
le jeton n'est jamais affiche ni ecrit dans un journal. Variante : jeton dans HA_TOKEN ou dans `token_file`.
`python pont_ha.py ha.toml --verifier` teste l'URL, le jeton, la joignabilite du broker MQTT et LISTE les entites
d'imprimante trouvees dans HA (pour recopier leurs vrais noms dans la config).

Limite connue : les entites creees par REST n'ont pas d'`unique_id` (pas editables dans l'interface de HA)
et disparaissent au redemarrage de HA jusqu'a la prochaine publication (< 1 min ici). La version "propre"
passe par MQTT discovery (a faire si un broker est disponible).

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


class ErreurAuth(Exception):
    pass


REACTIONS_PAR_TYPE = {       # etats connus par type d'integration ; pour les autres, a ecrire dans la config
    "prusalink": {"finished": "impression_finie", "stopped": "impression_echec", "error": "impression_echec",
                  "attention": "alerte", "printing": "impression_commencee"},
}


def est_vide(v):
    """Vrai pour une valeur non renseignee : absente, vide ou encore le texte "A_REMPLIR..." du modele."""
    return v is None or str(v).strip() == "" or "A_REMPLIR" in str(v)


def lire_config(chemin):
    """Lit `ha.toml` (format a sections, ou l'ancien format plat) et renvoie un dict normalise."""
    with open(chemin, "rb") as f:
        brut = tomllib.load(f)
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
        "ignorees": [],
    }
    for imp in brut.get("imprimante", []):
        if est_vide(imp.get("entite")):
            cfg["ignorees"].append(imp.get("nom", "?"))
            continue
        cfg["surveillance"].append({
            "entite": imp["entite"], "nom": imp.get("nom", imp["entite"]),
            "reactions": imp.get("reactions") or REACTIONS_PAR_TYPE.get(imp.get("type", ""), {})})
    if est_vide(cfg["url"]):
        cfg["url"] = None
    return cfg


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
                            callback(d["entity_id"], ancien, nouveau)
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


class PontHA:
    def __init__(self, cfg, jeton, log=print):
        self.cfg = cfg
        self.log = log
        self.client = HAClient(cfg["url"], jeton, log, cfg.get("url_ws"))
        self.evenements = queue.SimpleQueue()
        self.arret = threading.Event()
        self.surveillance = {s["entite"]: s for s in cfg["surveillance"]}
        self.calme = None if est_vide(cfg.get("interrupteur_calme")) else cfg["interrupteur_calme"]
        if self.calme:                          # regle de vie : interrupteur "calme" (input_boolean dans HA)
            self.surveillance[self.calme] = {"nom": "calme", "reactions": {"on": "calme_on", "off": "calme_off"}}
        self.instantane = {}                    # derniere photo de l'etat du canard, ecrite par le cerveau
        self._derniers = {}                     # entite -> (etat, instant de la derniere publication)
        self._threads = []

    # evenements maison -> cerveau
    def _sur_changement(self, entite, ancien, nouveau):
        if nouveau is None or nouveau.lower() in ETATS_IGNORES or nouveau == ancien:
            return
        s = self.surveillance[entite]
        reaction = {k.lower(): v for k, v in s.get("reactions", {}).items()}.get(nouveau.lower())
        self.log(f"[HA] {entite}: {ancien} -> {nouveau}" + (f"  => {reaction}" if reaction else ""))
        if reaction:
            self.evenements.put(reaction if entite == self.calme else f"{reaction}:{s.get('nom', entite)}")

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
        out = []
        while True:
            try:
                out.append(self.evenements.get_nowait())
            except queue.Empty:
                return out

    # canard -> maison
    def photographier(self, brain, state):
        """A passer a brain.run(a_chaque_tick=...) : memorise l'etat courant (rapide, sans reseau)."""
        self.instantane = {
            "etat": brain.courant.nom, "energie": brain.humeur.energie, "eveil": brain.humeur.eveil,
            "tombe": bool(state.get("safety", {}).get("fallen")), "politique": state.get("policy"),
            "batterie": state.get("battery"), "odom": state.get("odom"),
        }

    def entites_du_canard(self):
        i = self.instantane
        if not i:
            return {}
        ent = {
            "sensor.microduck_etat": (i["etat"], {"friendly_name": "Microduck - etat d'esprit", "icon": "mdi:duck"}),
            "sensor.microduck_energie": (round(i["energie"] * 100), {
                "friendly_name": "Microduck - energie", "unit_of_measurement": "%", "icon": "mdi:flash"}),
            "sensor.microduck_politique": (i["politique"], {"friendly_name": "Microduck - politique active"}),
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
                    self.client.pousser_etat(entite, etat, attrs)
                    self._derniers[entite] = (etat, now)
                except (urllib.error.URLError, OSError) as e:
                    self.log(f"[HA] publication de {entite} impossible : {e}")
                    self._derniers[entite] = (etat, now)   # pas de rafale d'erreurs : on reessaiera a la prochaine periode

    def demarrer(self):
        self.lire_calme_initial()
        entites = set(self.surveillance)
        for cible in (lambda: self.client.ecouter(entites, self._sur_changement, self.arret), self._publier):
            t = threading.Thread(target=cible, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self.arret.set()


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
            log(f"[INFO] {len(res['entites'])} entite(s) qui ressemblent a une imprimante (recopie `entite` dans ha.toml) :")
            for ent, etat, nom in res["entites"][:60]:
                log(f"         {ent}  =  {etat}   ({nom})")
        except Exception as e:
            log(f"[ECHEC] liste des entites : {type(e).__name__}: {e}")
    mq = cfg.get("mqtt") or {}
    if mq.get("actif") and not est_vide(mq.get("hote")):
        try:
            socket.create_connection((mq["hote"], int(mq.get("port", 1883))), timeout=4).close()
            res["mqtt"] = True
            log(f"[OK] MQTT : le broker repond sur {mq['hote']}:{mq.get('port', 1883)} (identifiants non testes)")
        except OSError as e:
            res["mqtt"] = False
            log(f"[ECHEC] MQTT : {mq['hote']}:{mq.get('port', 1883)} injoignable ({e}) : add-on Mosquitto demarre ?")
    for nom in cfg.get("ignorees", []):
        log(f"[A FAIRE] imprimante '{nom}' ignoree : `entite` pas encore renseignee")
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
    # Un petit Raspberry Pi (ou une liaison SSH / Wi-Fi) n'a pas besoin des 50 trames d'etat par seconde ; le deadman de
    # `robot.move` (500 ms) exige seulement >= 10 envois par seconde.
    c.request("robot.subscribe", {"hz": int(hz)} if isinstance(hz, int) and 10 <= hz <= 50 else {})
    pont.demarrer()
    try:
        brain.run(c, duree, source=pont.source, a_chaque_tick=pont.photographier)
    finally:
        pont.stop()


if __name__ == "__main__":
    main()
