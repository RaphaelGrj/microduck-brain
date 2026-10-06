#!/usr/bin/env python3
"""Faux Home Assistant local, pour tester `pont_ha.py` sans installation reelle.

Imite le strict necessaire de l'API de HA : WebSocket `/api/websocket` (auth par jeton, `subscribe_events`
state_changed) et REST `POST /api/states/<entite>`, `POST /api/services/<d>/<s>`. Deux petits serveurs sur deux
ports (le vrai HA n'en a qu'un ; la config du pont accepte donc `url_ws` en plus de `url`).

Cote test : `set_state(entite, etat)` emet un evenement state_changed comme le ferait une imprimante ;
`etats` et `appels` memorisent ce que le canard a publie / demande.

Ce n'est PAS une preuve de compatibilite avec le vrai HA (formats copies de la documentation) : la
validation finale se fera contre ton instance.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from websockets.sync.server import serve


class MockHA:
    def __init__(self, jeton="JETON_DE_TEST"):
        self.jeton = jeton
        self.etats = {}            # entite -> {"state":..., "attributes":...}  (publie par le canard ou set_state)
        self.appels = []           # [(domaine, service, donnees)]
        self.abonnes = set()
        self.verrou = threading.Lock()

        mock = self

        class Rest(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.headers.get("Authorization") != f"Bearer {mock.jeton}":
                    return self._rep(401, {"message": "Unauthorized"})
                if self.path == "/api/config":
                    return self._rep(200, {"version": "2099.1.0-mock", "location_name": "Maison de test"})
                if self.path == "/api/states":
                    with mock.verrou:
                        return self._rep(200, list(mock.etats.values()))
                self._rep(404, {"message": "inconnu"})

            def do_POST(self):
                if self.headers.get("Authorization") != f"Bearer {mock.jeton}":
                    return self._rep(401, {"message": "Unauthorized"})
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    corps = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    corps = {}
                if self.path.startswith("/api/states/"):
                    entite = self.path[len("/api/states/"):]
                    with mock.verrou:
                        mock.etats[entite] = {"entity_id": entite, "state": corps.get("state"),
                                              "attributes": corps.get("attributes", {})}
                        rep = mock.etats[entite]
                    return self._rep(200, rep)
                if self.path.startswith("/api/events/"):
                    with mock.verrou:
                        mock.appels.append(("evenement", self.path[len("/api/events/"):], corps))
                    return self._rep(200, {"message": "Event fired."})
                if self.path.startswith("/api/services/"):
                    domaine, _, service = self.path[len("/api/services/"):].partition("/")
                    with mock.verrou:
                        mock.appels.append((domaine, service, corps))
                    return self._rep(200, [])
                self._rep(404, {"message": "inconnu"})

            def _rep(self, code, objet):
                brut = json.dumps(objet).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(brut)))
                self.end_headers()
                self.wfile.write(brut)

        self.rest = ThreadingHTTPServer(("127.0.0.1", 0), Rest)
        self.ws = serve(self._ws, "127.0.0.1", 0)
        self.url = f"http://127.0.0.1:{self.rest.server_address[1]}"
        self.url_ws = f"ws://127.0.0.1:{self.ws.socket.getsockname()[1]}/api/websocket"
        threading.Thread(target=self.rest.serve_forever, daemon=True).start()
        threading.Thread(target=self.ws.serve_forever, daemon=True).start()

    def arreter(self):
        self.rest.shutdown()
        self.ws.shutdown()

    # --- cote test ---------------------------------------------------------------------------------
    def set_state(self, entite, etat, attributs=None, il_y_a_s=0.0):
        """`il_y_a_s` : date le changement dans le passe (`last_changed`), pour simuler une longue absence."""
        from datetime import datetime, timedelta, timezone
        quand = (datetime.now(timezone.utc) - timedelta(seconds=il_y_a_s)).isoformat()
        with self.verrou:
            ancien = self.etats.get(entite)
            nouveau = {"entity_id": entite, "state": etat, "attributes": attributs or {}, "last_changed": quand}
            self.etats[entite] = nouveau
            abonnes = list(self.abonnes)
        evt = {"id": 1, "type": "event", "event": {"event_type": "state_changed", "data": {
            "entity_id": entite, "old_state": ancien, "new_state": nouveau}}}
        for ws in abonnes:
            try:
                ws.send(json.dumps(evt))
            except Exception:
                with self.verrou:
                    self.abonnes.discard(ws)

    # --- WebSocket ---------------------------------------------------------------------------------
    def _ws(self, ws):
        ws.send(json.dumps({"type": "auth_required", "ha_version": "mock"}))
        msg = json.loads(ws.recv())
        if msg.get("type") != "auth" or msg.get("access_token") != self.jeton:
            ws.send(json.dumps({"type": "auth_invalid", "message": "Invalid access token or password"}))
            return
        ws.send(json.dumps({"type": "auth_ok", "ha_version": "mock"}))
        try:
            for brut in ws:
                m = json.loads(brut)
                if m.get("type") == "subscribe_events":
                    with self.verrou:
                        self.abonnes.add(ws)
                    ws.send(json.dumps({"id": m["id"], "type": "result", "success": True, "result": None}))
        finally:
            with self.verrou:
                self.abonnes.discard(ws)
