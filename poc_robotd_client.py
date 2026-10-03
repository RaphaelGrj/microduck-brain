#!/usr/bin/env python3
"""Premier client externe de robotd — parle au socket JSON-RPC/NDJSON directement,
sans passer par robotctl. Brique de base du futur cerveau (Phase 3) : se connecte,
s'abonne a l'etat, lit quelques trames, envoie une commande de vitesse, s'arrete.

Usage : python3 poc_robotd_client.py [chemin_du_socket]
Defaut : ~/.cache/duck-sim/duck-a.sock (duck-sim en cours d'execution requis)
"""
import json
import os
import socket
import sys
import time
from pathlib import Path

# duck-sim par defaut ; `ROBOTD_SOCK=/run/robotd.sock` (robot) ou le socket d'un tunnel SSH pour un cerveau distant.
SOCK_PATH = Path(os.environ.get("ROBOTD_SOCK") or Path.home() / ".cache/duck-sim/duck-a.sock")


class RobotdClient:
    def __init__(self, sock_path: Path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(sock_path))
        self.buf = b""
        self._next_id = 1

    def _read_line(self) -> dict:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("robotd a ferme la connexion")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def notify(self, method: str, params: dict | None = None):
        """Intent continu : pas d'id, pas de reponse (robot.move, robot.head, ...)."""
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.sock.sendall((json.dumps(msg) + "\n").encode())

    def request(self, method: str, params: dict | None = None, timeout_s: float = 5.0) -> dict:
        """Requete discrete : attend la reponse qui porte le meme id (ignore les
        trames d'etat qui peuvent arriver entre-temps sur un flux deja abonne —
        a 50 Hz un budget en NOMBRE de trames se fait vite manger par le flux)."""
        req_id = self._next_id
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        self.sock.sendall((json.dumps(msg) + "\n").encode())
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            frame = self._read_line()
            if frame.get("id") == req_id:
                return frame
        raise TimeoutError(f"pas de reponse a {method} apres {timeout_s}s")

    def read_state_frame(self) -> dict:
        """Lit la prochaine trame robot.state (saute tout le reste)."""
        while True:
            frame = self._read_line()
            if frame.get("method") == "robot.state":
                return frame["params"]


def main():
    sock = Path(sys.argv[1]) if len(sys.argv) > 1 else SOCK_PATH
    print(f"Connexion a {sock} ...")
    client = RobotdClient(sock)
    print("Connecte.\n")

    print("-- robot.subscribe --")
    result = client.request("robot.subscribe", {})
    print(json.dumps(result, indent=2), "\n")

    print("-- 3 trames robot.state --")
    for i in range(3):
        state = client.read_state_frame()
        policy = state.get("policy")
        battery = state.get("battery", {})
        safety = state.get("safety", {})
        print(f"  [{i}] policy={policy}  battery={battery.get('percent')}%  "
              f"fallen={safety.get('fallen')}  hz={state.get('loop', {}).get('hz')}")
    print()

    print("-- robot.move (avance tout droit 2s) --")
    client.notify("robot.move", {"vx": 0.15, "vy": 0.0, "vyaw": 0.0})
    time.sleep(2)

    print("-- robot.stop --")
    result = client.request("robot.stop")
    print(json.dumps(result, indent=2), "\n")

    print("-- robot.do (roulade) --")
    result = client.request("robot.do", {"skill": "roulade"})
    print(json.dumps(result, indent=2))

    print("\nOK — connexion directe au socket robotd validee.")


if __name__ == "__main__":
    main()
