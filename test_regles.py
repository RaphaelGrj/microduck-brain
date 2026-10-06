#!/usr/bin/env python3
"""Les deux regles d'identite du projet, verrouillees :
  1. le canard ne s'exprime QUE par ses sons de canard (banque officielle : alarm, greet, inquire, peck, chirp, coo,
     wheee) - jamais de voix humaine, de synthese vocale ni de mot ;
  2. tout tourne SUR le canard : aucune image ni aucun son ne part vers un autre appareil pour etre analyse ; seul Home
     Assistant recoit des ETATS (nombres, textes courts)."""
import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

import canard
import pont_ha
from brain import SONS_CANARD, Brain, Humeur
from test_brain import FauxClient, simule

RACINE = Path(__file__).parent
MODULES = subprocess.run([sys.executable, str(RACINE / "deploy/robot/modules.py")], capture_output=True, text=True,
                         check=True).stdout.split()
MODULES = [m for m in MODULES if m.endswith(".py")]    # (la liste comprend aussi le dossier interface/ de l'appli)


def test_sons_de_la_banque_officielle_seulement():
    assert SONS_CANARD == {"alarm", "greet", "inquire", "peck", "chirp", "coo", "wheee"}
    trouves = set()
    for nom in MODULES:
        arbre = ast.parse((RACINE / nom).read_text())
        for n in ast.walk(arbre):
            # ctx.sound("x") / brain.ctx.sound("x")
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "sound" and n.args \
                    and isinstance(n.args[0], ast.Constant):
                trouves.add((nom, n.args[0].value))
            # ("geste", "son") des sequences, et tuples de sons ("chirp", "inquire") des etats
            if isinstance(n, ast.Tuple) and all(isinstance(e, ast.Constant) for e in n.elts):
                vals = [e.value for e in n.elts]
                if len(vals) == 2 and isinstance(vals[0], str) and vals[0] in __import__("gestures").GESTES:
                    if vals[1] is not None:
                        trouves.add((nom, vals[1]))
    hors = [(f, t) for f, t in trouves if t not in SONS_CANARD]
    assert not hors, f"sons hors de la banque du canard : {hors}"
    assert len(trouves) > 20, "le scan doit trouver les sons du code"


def test_aucune_synthese_vocale_ni_texte_parle():
    """Ni bibliotheque de synthese vocale importee, ni appel facon say()/speak()/tts() : inspection du code (AST), pas
    du texte (les commentaires qui expliquent la regle ont le droit d'en parler)."""
    tts = {"pyttsx3", "gtts", "espeakng", "espeak", "piper", "TTS", "festival", "pico2wave", "edge_tts"}
    appels = {"say", "speak", "tts", "text_to_speech", "synthesize"}
    for nom in MODULES:
        for n in ast.walk(ast.parse((RACINE / nom).read_text())):
            if isinstance(n, ast.Import):
                assert not {a.name.split(".")[0] for a in n.names} & tts, f"{nom} importe une synthese vocale"
            if isinstance(n, ast.ImportFrom) and n.module:
                assert n.module.split(".")[0] not in tts, f"{nom} importe une synthese vocale"
            if isinstance(n, ast.Call):
                f = n.func
                nom_appel = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                assert nom_appel not in appels, f"{nom} : appel {nom_appel}()"
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith("robot.") \
                    and n.value in ("robot.say", "robot.speak", "robot.tts"):
                raise AssertionError(f"{nom} : {n.value}")


def test_un_son_inconnu_est_refuse():
    c = FauxClient()
    b = Brain(c, Humeur(), seed=1)
    b.ctx.sound("bonjour")
    assert not any(m == "robot.sound" for m, _ in c.appels) and b.ctx.sons_refuses == 1


def test_camera_lue_en_local_seulement():
    canard.verifier_local("http://127.0.0.1:8080/frame")
    canard.verifier_local("http://localhost:8080/frame")
    for distant in ("http://192.168.1.50:8080/frame", "https://exemple.org/frame"):
        with pytest.raises(SystemExit):
            canard.verifier_local(distant)


def test_rien_que_des_etats_vers_home_assistant():
    """Ce qui part vers HA : des nombres, des textes courts, des booleens - jamais d'image, de son ni de tableau."""
    pont = pont_ha.PontHA({"url": "http://x", "surveillance": [], "publier_toutes_les_s": 1}, "J", log=lambda m: None)
    b = Brain(FauxClient(), Humeur(), seed=2)
    b.presents.add("Raphael")
    simule(b, 5)
    pont.photographier(b, {"policy": "stand", "safety": {"fallen": False}, "battery": {"percent": 80, "volts": 7.9},
                           "odom": {"position": [1.0, 2.0, 0.1], "yaw": 0.3}})
    for entite, (etat, attrs) in pont.entites_du_canard().items():
        for v in [etat, *attrs.values()]:
            assert v is None or isinstance(v, (int, float, bool)) or (isinstance(v, str) and len(v) <= 255), (entite, v)


def test_seul_pont_ha_parle_au_reseau():
    """Hors du pont Home Assistant, aucun module embarque n'ouvre de connexion reseau autre que locale."""
    reseau = re.compile(r"urlopen|websockets|paho|requests\.|socket\.AF_INET|http\.client|http\.server")
    for nom in MODULES:
        if nom in ("pont_ha.py", "vision.py", "appli.py", "imprimantes.py"):
            # vision : la camera en local seulement (canard.verifier_local) ; appli : serveur du RESEAU LOCAL seulement,
            # qui n'envoie que des etats (test_appli.test_reseau_local_seulement, et aucun appel sortant ci-dessous) ;
            # imprimantes : LIT les imprimantes du reseau local seulement (test_imprimante_du_reseau_local_seulement)
            continue
        code = (RACINE / nom).read_text()
        assert not reseau.search(code), f"{nom} ouvre une connexion reseau"


def test_l_application_ne_fait_aucun_appel_sortant():
    """appli.py repond au telephone ; il n'ouvre lui-meme aucune connexion vers l'exterieur."""
    code = (RACINE / "appli.py").read_text()
    assert not re.search(r"urlopen|websockets|paho|requests\.|http\.client|socket\.AF_INET", code)


def test_imprimante_du_reseau_local_seulement():
    """Les imprimantes suivies en direct sont sur le reseau local : une adresse Internet est refusee."""
    import configuration
    import imprimantes
    assert configuration.adresse_locale("192.168.1.30") and configuration.adresse_locale("prusa-mk4.local")
    assert not configuration.adresse_locale("8.8.8.8") and not configuration.adresse_locale("prusa.example.com")
    i = imprimantes.Imprimantes([{"nom": "A", "type": "prusalink", "adresse": "8.8.8.8"},
                                 {"nom": "B", "type": "sdcp", "adresse": "10.0.0.5"}], log=lambda m: None)
    assert [x["nom"] for x in i.liste] == ["B"]
