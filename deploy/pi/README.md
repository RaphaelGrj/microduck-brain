# Faire tourner le pont Home Assistant + cerveau sur un Raspberry Pi 3B+ (24 h/24, sans le PC)

**État : préparé, NON TESTÉ sur un Pi** (je n'en ai pas ; mesures faites sur le PC, voir plus bas). À essayer avec ton
Pi de rechange, de préférence **avant** la livraison du robot, en pointant le tunnel sur le simulateur ou en attendant.

## Ce qui tourne là, et ce qui ne tourne PAS

| Sur le Pi 3B+ | Pas sur le Pi 3B+ |
|---|---|
| `canard.py` = `brain.py` + `pont_ha.py` + capteur de distance + caméra (2026-10-05) | Le jeu de balle avec vision (approche, tir) |
| `brain.py` (états, humeur, gestes, réactions aux notifications, main tendue, caresse, coin de sieste) | Le détecteur de chat (YOLO : ~1 à 3 s par image sur un Cortex-A53, à confirmer) — `--chat` à ne pas activer ici |
| Détection de mouvement « 1-2-3 soleil » (différence d'images, ~13 ms/image sur PC, 5 images/s **seulement pendant le jeu**) | Le simulateur et l'entraînement (restent sur le PC) |
| Le tunnel SSH vers `robotd`, `tofd` et la caméra | |

Mesuré sur le PC (Python 3.12, simulateur) : **29 Mo de RAM, 0,4 à 0,8 % d'un cœur** pour pont + cerveau, à 10 à 50 trames d'état
par seconde. Un Cortex-A53 est plusieurs fois plus lent qu'un cœur de PC (estimation : ×5 à ×10) : on reste sous ~10 % d'un cœur
et sous 50 Mo, sur 1 Go. `etat_hz` dans `ha.toml` (`[reseau]`, 10 à 50) réduit encore la charge.
Pont + cerveau seuls n'utilisent que la bibliothèque standard + `websockets` ; le capteur de distance (`tof.py` → `geometry.py`) et
la détection de mouvement ajoutent **numpy et OpenCV** (`opencv-python-headless`, roues aarch64 sur PyPI) : la mesure de 29 Mo est
donc à refaire avec `canard.py` (estimation : +40 à 60 Mo pour OpenCV). Tout est compatible Python 3.11 (`python diag_py311.py
brain.py pont_ha.py canard.py ...`, test statique), donc le Python de Raspberry Pi OS Bookworm suffit.

## Installation (à faire sur le Pi ; les commandes `sudo` sont à taper par toi)

1. Flasher **Raspberry Pi OS Lite 64 bits** (Raspberry Pi Imager : active SSH, mets ton nom d'utilisateur, le Wi-Fi si besoin).
   Si possible **câble Ethernet** (plus fiable que le Wi-Fi pour un service permanent). Réserve-lui une IP dans ta box.
2. Sur le Pi :
   ```bash
   sudo apt update && sudo apt install -y python3-venv
   sudo useradd -r -m -d /opt/microduck -s /usr/sbin/nologin microduck       # compte de service sans privilèges
   sudo -u microduck python3 -m venv /opt/microduck/venv
   sudo -u microduck /opt/microduck/venv/bin/pip install -r requirements-pi.txt
   ```
3. Depuis le PC, copier les modules et `ha.toml` (jamais `ha.toml` par e-mail ni sur GitHub ; `scp` direct) :
   ```bash
   M="canard pont_ha brain gestures poc_robotd_client exploration memoire main_tendue caresse navigation mouvement tof geometry vision"
   scp $(for m in $M; do echo $m.py; done) ha.toml  <toi>@<ip-du-pi>:/tmp/
   # puis sur le Pi :
   for m in $M; do sudo install -o microduck -g microduck -m 644 /tmp/$m.py /opt/microduck/; done
   sudo install -o microduck -g microduck -m 600 /tmp/ha.toml /opt/microduck/ha.toml && rm /tmp/ha.toml
   ```
4. Clé SSH pour joindre le robot (quand il sera là) : `sudo -u microduck ssh-keygen -t ed25519 -f /opt/microduck/.ssh/id_ed25519 -N ""`,
   puis autoriser la clé publique sur le robot et mettre l'IP du robot dans `microduck-tunnel.service`.
5. Services :
   ```bash
   sudo cp microduck-tunnel.service microduck-pont.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now microduck-tunnel microduck-pont
   journalctl -u microduck-pont -f          # voir ce que fait le pont
   ```

## Pourquoi un tunnel SSH (et ce qu'il transporte)

`robotd` n'écoute que sur un socket Unix du robot (`/run/robotd.sock`). `ssh -L socket_local:socket_distant` le rend disponible sur le
Pi (`/run/microduck/robotd.sock`), et le cerveau le lit via la variable `ROBOTD_SOCK`. Aucun changement de code. Même chose pour le
capteur de distance (`tofd` → `/run/microduck/tofd.sock`, variable `TOFD_SOCK` ; chemin sur le robot **supposé** `/run/tofd.sock`) et la
caméra (route `/frame` de `mediad` ramenée sur `127.0.0.1:8080` du Pi : l'image ne sort jamais du tunnel, règle de vie « vie privée »). **À valider sur le vrai
robot** (droits sur le socket, compte SSH dédié, comportement à la perte du Wi-Fi : le deadman de `robotd` arrête le robot si les
commandes cessent, et le service redémarre tout seul).

## Limites à connaître

- Si le Pi tombe, le canard garde ses comportements propres mais ne réagit plus aux notifications ; rien de dangereux.
- Pas d'alimentation de secours, carte SD fragile : sauvegarde `ha.toml` ailleurs (hors GitHub).
- Pour `quacksat` (voix) sur le robot en parallèle : voir la note d'arbitrage dans `HOME_ASSISTANT.md`.
