# Le cerveau directement sur le canard (aucun appareil externe)

**État : préparé, NON TESTÉ** (robot pas livré). C'est la cible : `canard.py` tourne sur la carte du robot (Radxa Zero 3,
RK3566, Armbian/Debian d'après le dépôt officiel), à côté de `robotd`, `tofd` et `mediad`, et ne parle qu'à eux, en local.

| Dépend de | Local au robot ? |
|---|---|
| `robotd` (`/run/robotd.sock`), `tofd` (`/run/tofd/tof.sock`), caméra (`mediad`, `127.0.0.1:8080/frame`) | oui |
| Mémoire (`~/.local/share/microduck/memoire.json`), exploration, chargeur, coins, taquineries | oui |
| Réflexes sonores, commandes vocales | oui (Vosk hors ligne, sons analysés en mémoire, jamais envoyés), **si** le micro est partagé : `contrib/robotd-audio-capture.patch` + `asound.conf` (le micro est mono-client et `robotd` l'occupe) |
| Caresse entendue (`pet-detect` officiel, audio) | oui, **si** `robotd` la publie (`contrib/robotd-audio-state.patch`) et `[audio] pet_detect = true` |
| Veille du chat (`--chat`, YOLO) | probablement trop lent sur le CPU : à porter sur le NPU du RK3566 |
| Tout ce qui vient de Home Assistant (présence, imprimantes, sonnette, météo, fumée, aspirateur, boutons, entités) | non : HA tourne sur ton Pi existant. Sans `ha.toml`, le cerveau tourne quand même, ces fonctions ne se déclenchent simplement pas |

## Installation (sur le robot, en SSH)

```bash
sudo apt install -y python3-venv
sudo useradd -r -m -d /opt/microduck-cerveau -s /usr/sbin/nologin microduck-cerveau
# droits sur les sockets de robotd / tofd : groupe à vérifier sur le robot (ls -l /run/robotd.sock /run/tofd/tof.sock)
sudo usermod -aG audio microduck-cerveau      # lire le micro partage
sudo -u microduck-cerveau python3 -m venv /opt/microduck-cerveau/venv
sudo -u microduck-cerveau /opt/microduck-cerveau/venv/bin/pip install -r requirements-robot.txt
# copier les modules du cerveau (liste exacte : python3 deploy/robot/modules.py) et ha.toml (600, jamais sur GitHub)
# dans /opt/microduck-cerveau/ ; micro partage : sudo cp asound.conf /etc/asound.conf (et [audio] de robotd.toml, voir le fichier)
# commandes vocales : modele francais Vosk, telecharge UNE fois ici puis tout est hors ligne :
#   https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip -> /opt/microduck-cerveau/modeles/ ;
#   [cerveau] nom = "..." et modele_vosk = "/opt/microduck-cerveau/modeles/vosk-model-small-fr-0.22" dans ha.toml
# mises a jour depuis l'appli : le script lance par systemd avant le cerveau (ExecStartPre)
sudo install -m 755 -o microduck-cerveau mettre_a_jour.sh /opt/microduck-cerveau/mettre_a_jour.sh
sudo cp microduck-cerveau.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now microduck-cerveau && journalctl -u microduck-cerveau -f
```

## Les deux règles du projet, vérifiées par `test_regles.py`

- Le canard ne s'exprime **qu'avec ses sons de canard** (`alarm`, `greet`, `inquire`, `peck`, `chirp`, `coo`, `wheee`) :
  tout autre son est refusé ; pas de synthèse vocale. `quacksat` est écarté pour cette raison (et parce qu'il envoie le
  son du micro hors du canard).
- **Rien n'est analysé ailleurs que sur le canard** : `canard.py` refuse une caméra lue à distance ; seul le pont
  Home Assistant parle au réseau, et il n'envoie que des états (nombres, textes courts).

## À mesurer à la livraison, avant de le laisser tourner 24 h/24

- CPU et RAM réels sur le RK3566 à côté de `robotd` (mesuré sur PC : 29 Mo et < 1 % pour cerveau + pont, sans caméra ;
  la veille de balle ajoute 2 images/s, la détection de mouvement 5 images/s seulement pendant le jeu) ; `Nice=10` laisse
  la priorité à la boucle de contrôle.
- Consommation : la caméra analysée en continu coûte de la batterie ; baisser `VeilleBalle.periode_s` si besoin.
- Si la marge manque : alléger SUR le robot (cadences de la caméra, veille du chat coupée) — **pas** de repli sur un
  appareil externe : règle du projet, aucune donnée du canard n'est analysée ailleurs que sur lui.
