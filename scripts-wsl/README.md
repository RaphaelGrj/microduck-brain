# Scripts WSL pour `duck-sim` (caméra incluse)

Copiés ici depuis `~` pour être reproductibles. Pas de mot de passe, rien d'écrit hors du home.

| Script | Rôle |
|---|---|
| `build-webrtc.sh` / `build-webrtc2.sh` | Compile `gst-plugin-webrtc` (`webrtcsink`) depuis les sources : Pollen ne publie que de l'aarch64, rien pour x86_64. `2` = version 0.15.4 (celle qui marche avec GStreamer 1.28), prefix `~/.local-015`. |
| `start-duck.sh` | Lance `duck-sim` détaché : sans fenêtre MuJoCo, avec caméra, scène par défaut `testball` (appartement + balle), vérité terrain (30 poses par seconde, pièce par pièce : canard jumeau) et téléportation activées. |
| `run-scene.sh <scène>` | Redémarre `duck-sim` sur une scène du fork : `arena_chat` (arène + affiche de ton chat, générée par `make_cat_scene.py`), `arena` (sol plan sans murs + balle d'entraînement — **à utiliser pour évaluer une approche**), `testball`, `kick_right`, `kick_left`, `apartment`, **`maison`** (TA maison : scène générée depuis le plan importé par `plan_vers_mjcf.py`, pour le canard jumeau du Quest — `quest/README.md`). |
| `restart-duck.sh` | Arrête l'ancien `duck-sim` (`down`). À lancer avant `start-duck.sh`. |
| `wait-duck.sh` | Attend que le canard soit debout et résume (mediad, console web). |
| `valider-tout.sh [scénarios...]` | **Validation groupée en une commande** : tests, coût du cerveau (`bench_cerveau.py`), puis les scénarios de `valider_sim.py` dans `duck-sim`, scène par scène. Rapport daté `~/validation-AAAA-MM-JJ_HHMM.txt`, à me renvoyer. |
| `bin-shim/sudo` | `sudo -n` : `duck-sim down` appelle `sudo systemctl` et restait bloqué sur un mot de passe. |

## Ordre d'utilisation

```bash
bash ~/restart-duck.sh
bash ~/start-duck.sh > /dev/null 2>&1 < /dev/null; bash ~/wait-duck.sh   # même session !
```

Console web : <http://127.0.0.1:8080> (bouton *connect*), vidéo 30 FPS.

## Pièges trouvés (à ne pas redécouvrir)

- **Même session WSL** : si la session qui lance `start-duck.sh` se ferme avant la fin du
  démarrage, `duck-sim` est tué. Enchaîner `wait-duck.sh` dans la même commande.
- **`webrtcsink` absent** : non packagé sous Ubuntu → build source (voir scripts). Il faut
  `gstreamer1.0-nice` et `gstreamer1.0-tools` (apt) en plus des paquets `-dev`.
- **Version du plugin** : 0.14.5 donne `failed to set sps/pps` (GStreamer 1.28) ; **0.15.4 marche**.
- **Encodeur NVIDIA** : `nvh264enc` (rang 257) est choisi avant `x264enc` et son flux échoue ;
  `GST_PLUGIN_FEATURE_RANK="nvh264enc:0,nvautogpuh264enc:0"` le déclasse (Pollen ne le fait
  que pour macOS).
- **Évaluer sur la vérité terrain** : `DUCK_SIM_GROUNDTRUTH` / `DUCK_SIM_CONTROL` (fork
  `microduck_rl`, déjà posés par `start-duck.sh`) → `~/.cache/duck-sim/groundtruth.json` (poses
  réelles du canard et de la balle, 0,1 s) et téléportation de la balle / du canard
  (`truth.py`). Outils de test, absents sur le vrai robot.
- **L'appartement est trop étroit** pour une approche : le canard naît dans un couloir de 40 cm,
  les balles téléportées sont repoussées par les murs → `bash ~/run-scene.sh arena`.
- **Chemins `/home/...` depuis Git Bash** : le shell les réécrit en `C:/Program Files/Git/home/...`
  → préfixer par `MSYS_NO_PATHCONV=1`. Idem `~` (devient `C:/Users/...`) : écrire `$HOME` dans un `.sh`.
- **Processus de fond** : lancer avec `setsid bash script.sh > sortie 2>&1 < /dev/null &` sinon
  la session WSL qui se ferme tue le travail.
- **Quoting** : depuis Git Bash, `$VAR` et `$(...)` dans `wsl -d Ubuntu -- bash -c '...'` sont
  développés côté Windows. Mettre la logique dans un script `.sh` et l'appeler.
