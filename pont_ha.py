#!/usr/bin/env python3
"""Pont Home Assistant <-> cerveau du canard.

  Maison -> canard : on ecoute les changements d'ETAT des entites listees dans `ha.toml` (imprimantes 3D :
      PrusaLink pour les Prusa, integration Elegoo pour la Saturn 4 Ultra...). Une transition vers un etat
      qui a une reaction (finished, stopped, error...) devient un evenement du cerveau ("impression_finie:MK4S")
      que `brain.py` joue en geste + voix du canard.
  Canard -> maison : l'etat du robot (batterie, chute, politique active, position, etat d'esprit du cerveau)
      est publie comme entites `sensor.microduck_*` (REST `POST /api/states/...`).

Securite : le jeton d'acces longue duree de Home Assistant n'est JAMAIS dans `ha.toml` ni dans le depot ;
il est lu dans le fichier `token_file` (chmod 600) ou la variable d'environnement HA_TOKEN, et jamais affiche.

Limite connue : les entites creees par REST n'ont pas d'`unique_id` (pas editables dans l'interface de HA)
et disparaissent au redemarrage de HA jusqu'a la prochaine publication (< 1 min ici). La version "propre"
passe par MQTT discovery (a faire si un broker est disponible).

Usage : bash ~/run-brain.sh pont_ha.py [ha.toml] [duree_s]
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


def lire_config(chemin):
    with open(chemin, "rb") as f:
        cfg = tomllib.load(f)
    cfg.setdefault("publier_toutes_les_s", 30)
    cfg.setdefault("surveillance", [])
    return cfg


def lire_jeton(cfg):
    jeton = os.environ.get("HA_TOKEN", "").strip()
    if not jeton and cfg.get("token_file"):
        chemin = Path(os.path.expanduser(cfg["token_file"]))
        if chemin.exists():
            jeton = chemin.read_text().strip()
    if not jeton:
        raise SystemExit("Jeton Home Assistant introuvable : cree un jeton d'acces longue duree (profil HA -> "
                         "Securite) et mets-le dans le fichier indique par `token_file` (chmod 600), ou dans HA_TOKEN.")
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
            self.evenements.put(f"{reaction}:{s.get('nom', entite)}")

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
        entites = set(self.surveillance)
        for cible in (lambda: self.client.ecouter(entites, self._sur_changement, self.arret), self._publier):
            t = threading.Thread(target=cible, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self.arret.set()


def main():
    chemin = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "ha.toml")
    duree = float(sys.argv[2]) if len(sys.argv) > 2 else 3600.0
    if not Path(chemin).exists():
        raise SystemExit(f"config absente : {chemin} (copie ha.exemple.toml en ha.toml et adapte-le)")
    cfg = lire_config(chemin)
    pont = PontHA(cfg, lire_jeton(cfg), log=lambda m: print(m, flush=True))
    import brain
    from poc_robotd_client import RobotdClient, SOCK_PATH
    c = RobotdClient(SOCK_PATH)
    c.request("robot.subscribe", {})
    pont.demarrer()
    try:
        brain.run(c, duree, source=pont.source, a_chaque_tick=pont.photographier)
    finally:
        pont.stop()


if __name__ == "__main__":
    main()
