#!/usr/bin/env python3
"""Faux broker MQTT 3.1.1 minimal, pour tester la publication MQTT du pont sans Mosquitto.

Gere le strict necessaire : CONNECT (identifiants, message testament), PUBLISH QoS 0/1 et messages retenus,
SUBSCRIBE avec jokers + et #, PINGREQ, DISCONNECT ; une coupure sans DISCONNECT publie le testament (comme Mosquitto).
Cote test : `retenus` (topic -> charge utile) et `messages` (tout ce qui a ete publie), `publier()` pour simuler HA.

Ce n'est PAS une preuve de compatibilite avec Mosquitto / Home Assistant : la validation finale se fera chez toi.
"""
import socket
import socketserver
import struct
import threading


def _lire_longueur(f):
    n, mult = 0, 1
    for _ in range(4):
        b = f.read(1)
        if not b:
            raise EOFError
        n += (b[0] & 0x7F) * mult
        if not b[0] & 0x80:
            return n
        mult *= 128
    raise ValueError("longueur MQTT invalide")


def _longueur(n):
    out = bytearray()
    while True:
        b, n = n % 128, n // 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _chaine(data, i):
    n = struct.unpack_from("!H", data, i)[0]
    return data[i + 2:i + 2 + n], i + 2 + n


def correspond(filtre, topic):
    f, t = filtre.split("/"), topic.split("/")
    for i, niveau in enumerate(f):
        if niveau == "#":
            return True
        if i >= len(t) or (niveau != "+" and niveau != t[i]):
            return False
    return len(f) == len(t)


def paquet_publish(topic, charge, retain=False):
    corps = struct.pack("!H", len(topic.encode())) + topic.encode() + charge
    return bytes([0x30 | (1 if retain else 0)]) + _longueur(len(corps)) + corps


class MockMQTT:
    def __init__(self, utilisateur=None, mot_de_passe=None):
        self.utilisateur, self.mot_de_passe = utilisateur, mot_de_passe
        self.retenus = {}          # topic -> bytes
        self.messages = []         # [(topic, bytes, retain)]
        self.sessions = []         # [(socket, [filtres])]
        self.refus = 0
        self.verrou = threading.Lock()
        broker = self

        class Session(socketserver.StreamRequestHandler):
            def handle(self):
                broker._session(self.request, self.rfile)

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.serveur = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Session)
        self.serveur.daemon_threads = True
        self.port = self.serveur.server_address[1]
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def arreter(self):
        with self.verrou:
            for s, _ in self.sessions:
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self.serveur.shutdown()
        self.serveur.server_close()

    def couper_clients(self):
        """Coupure brutale (sans DISCONNECT) : les testaments sont publies."""
        with self.verrou:
            for s, _ in list(self.sessions):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    # --- distribution ------------------------------------------------------------------------------
    def publier(self, topic, charge, retain=False):
        charge = charge.encode() if isinstance(charge, str) else charge
        with self.verrou:
            self.messages.append((topic, charge, retain))
            if retain:
                if charge:
                    self.retenus[topic] = charge
                else:
                    self.retenus.pop(topic, None)
            cibles = [s for s, filtres in self.sessions if any(correspond(f, topic) for f in filtres)]
        for s in cibles:
            try:
                s.sendall(paquet_publish(topic, charge))
            except OSError:
                pass

    # --- une connexion -----------------------------------------------------------------------------
    def _session(self, sock, f):
        testament, filtres, propre = None, [], False
        try:
            if f.read(1)[0] >> 4 != 1:
                return
            data = f.read(_lire_longueur(f))
            _, i = _chaine(data, 0)
            drapeaux = data[i + 1]
            i += 4
            _, i = _chaine(data, i)                                         # identifiant client
            if drapeaux & 0x04:
                wt, i = _chaine(data, i)
                wm, i = _chaine(data, i)
                testament = (wt.decode(), wm, bool(drapeaux & 0x20))
            user = pwd = None
            if drapeaux & 0x80:
                user, i = _chaine(data, i)
            if drapeaux & 0x40:
                pwd, i = _chaine(data, i)
            if self.utilisateur is not None and (user != self.utilisateur.encode() or pwd != self.mot_de_passe.encode()):
                self.refus += 1
                sock.sendall(b"\x20\x02\x00\x05")                           # non autorise
                return
            sock.sendall(b"\x20\x02\x00\x00")
            with self.verrou:
                self.sessions.append((sock, filtres))
            while True:
                b = f.read(1)
                if not b:
                    break
                typ, fl = b[0] >> 4, b[0] & 0x0F
                data = f.read(_lire_longueur(f))
                if typ == 3:                                                # PUBLISH
                    topic, i = _chaine(data, 0)
                    qos = (fl >> 1) & 3
                    if qos:
                        pid = data[i:i + 2]
                        i += 2
                        sock.sendall(b"\x40\x02" + pid)
                    self.publier(topic.decode(), data[i:], retain=bool(fl & 1))
                elif typ == 8:                                              # SUBSCRIBE
                    pid, i, accordes = data[:2], 2, bytearray()
                    nouveaux = []
                    while i < len(data):
                        t, i = _chaine(data, i)
                        i += 1
                        nouveaux.append(t.decode())
                        accordes.append(0)
                    with self.verrou:
                        filtres.extend(nouveaux)
                        retenus = [(t, c) for t, c in self.retenus.items() if any(correspond(n, t) for n in nouveaux)]
                    sock.sendall(b"\x90" + _longueur(2 + len(accordes)) + pid + bytes(accordes))
                    for t, c in retenus:
                        sock.sendall(paquet_publish(t, c, retain=True))
                elif typ == 12:                                             # PINGREQ
                    sock.sendall(b"\xd0\x00")
                elif typ == 14:                                             # DISCONNECT
                    propre = True
                    break
        except (EOFError, OSError, IndexError, ValueError, struct.error):
            pass
        finally:
            with self.verrou:
                self.sessions = [(s, fl) for s, fl in self.sessions if s is not sock]
            if testament and not propre:
                self.publier(*testament)
