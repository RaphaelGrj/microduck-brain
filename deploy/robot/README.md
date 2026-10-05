# Le cerveau directement sur le canard (aucun appareil externe)

**État : préparé, NON TESTÉ** (robot pas livré). C'est la cible : `canard.py` tourne sur la carte du robot (Radxa Zero 3,
RK3566, Armbian/Debian d'après le dépôt officiel), à côté de `robotd`, `tofd` et `mediad`, et ne parle qu'à eux, en local.

| Dépend de | Local au robot ? |
|---|---|
| `robotd` (`/run/robotd.sock`), `tofd` (`/run/tofd/tof.sock`), caméra (`mediad`, `127.0.0.1:8080/frame`) | oui |
| Mémoire (`~/.local/share/microduck/memoire.json`), exploration, chargeur, coins, taquineries | oui |
| Réflexes sonores, caresse entendue | oui, **si** `robotd` publie `robot.state.audio` (`contrib/robotd-audio-state.patch`) — le micro est mono-client et `robotd` l'occupe |
| Veille du chat (`--chat`, YOLO) | probablement trop lent sur le CPU : à porter sur le NPU du RK3566 |
| Tout ce qui vient de Home Assistant (présence, imprimantes, sonnette, météo, fumée, aspirateur, boutons, entités) | non : HA tourne sur ton Pi existant. Sans `ha.toml`, le cerveau tourne quand même, ces fonctions ne se déclenchent simplement pas |

## Installation (sur le robot, en SSH)

```bash
sudo apt install -y python3-venv
sudo useradd -r -m -d /opt/microduck-cerveau -s /usr/sbin/nologin microduck-cerveau
# droits sur les sockets de robotd / tofd : groupe à vérifier sur le robot (ls -l /run/robotd.sock /run/tofd/tof.sock)
sudo -u microduck-cerveau python3 -m venv /opt/microduck-cerveau/venv
sudo -u microduck-cerveau /opt/microduck-cerveau/venv/bin/pip install -r requirements-robot.txt
# copier les modules du cerveau (+ ha.toml en 600, jamais sur GitHub) dans /opt/microduck-cerveau/, puis :
sudo cp microduck-cerveau.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now microduck-cerveau && journalctl -u microduck-cerveau -f
```

## À mesurer à la livraison, avant de le laisser tourner 24 h/24

- CPU et RAM réels sur le RK3566 à côté de `robotd` (mesuré sur PC : 29 Mo et < 1 % pour cerveau + pont, sans caméra ;
  la veille de balle ajoute 2 images/s, la détection de mouvement 5 images/s seulement pendant le jeu) ; `Nice=10` laisse
  la priorité à la boucle de contrôle.
- Consommation : la caméra analysée en continu coûte de la batterie ; baisser `VeilleBalle.periode_s` si besoin.
- Si la marge manque : repli sur le Pi externe (`deploy/pi/`).
