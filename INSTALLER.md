# Installer le cerveau sur ton Microduck

Ce guide s'adresse à une personne qui possède un **[Microduck](https://github.com/pollen-robotics/microduck)** et veut
y faire tourner ce cerveau. Il dit aussi, sans enjoliver, **ce qui est validé et ce qui ne l'est pas**.

> **Honnêteté d'abord** : l'auteur n'a pas encore reçu son robot. Tout a été développé contre `duck-sim` (le simulateur
> officiel) et une suite de tests sans simulateur. **Rien n'a tourné sur un vrai canard.** Si tu es le premier à essayer,
> tu fais de la validation : n'hésite pas à ouvrir une issue avec ce que tu constates.

Le code est sous licence **Apache-2.0** (voir `LICENSE`), comme la pile officielle de Pollen : tu peux l'utiliser, le
modifier et le partager librement.

## Ce qu'il te faut

- Un Microduck à jour (`robotd`, `tofd`, `mediad` officiels). Le cerveau ne parle qu'à eux, par leur API locale.
- Un accès SSH au robot.
- Facultatif : Home Assistant (le cerveau et l'appli marchent sans), un micro partagé (patchs, voir ci-dessous).

## Étape 0 : récupérer le code (sur ton ordinateur)

```bash
sudo apt install -y git curl                     # Linux / WSL ; sous macOS : git est déjà là
curl -LsSf https://astral.sh/uv/install.sh | sh  # installe « uv », qui gère Python tout seul (ouvre un nouveau terminal ensuite)
git clone https://github.com/RaphaelGrj/microduck-brain.git
cd microduck-brain
```

## Niveau 1 : sans robot (le plus sûr, commence ici)

Vérifie que tout fonctionne chez toi, sans rien risquer :

```bash
uv run --with pytest pytest -q $(ls test_*.py | grep -v test_chat_affiche)
```

Tu dois voir `... passed` à la fin (environ 2 minutes). Pour voir le canard vivre, installe `duck-sim`
(le simulateur officiel, voir le dépôt `pollen-robotics/microduck`) puis lance le cerveau contre lui :
`scripts-wsl/README.md` décrit les scripts (`start-duck.sh`, `jumeau.sh`) et les pièges déjà rencontrés.

## Niveau 2 : sur le robot, à l'essai

Branche-toi au robot (les identifiants sont ceux de la documentation officielle du Microduck) :

```bash
ssh <utilisateur>@<ip-du-robot>
```

Puis, **sur le robot**, récupère le code et fais une mesure sans rien installer :

```bash
sudo apt install -y git python3-venv
git clone https://github.com/RaphaelGrj/microduck-brain.git
cd microduck-brain
python3 -m venv .venv && .venv/bin/pip install -r deploy/robot/requirements-robot.txt
.venv/bin/python bench_cerveau.py          # mesure CPU / RAM du cerveau sur le robot
```

Pose le canard sur un support, prêt à le saisir, puis lance-le à la main (Ctrl+C pour arrêter) :

```bash
.venv/bin/python canard.py
```

## Niveau 3 : sur le robot, en service permanent

Une seule commande, toujours depuis le dossier cloné sur le robot :

```bash
sudo bash deploy/robot/installer.sh
```

Elle crée un utilisateur dédié, installe l'environnement, copie le cerveau dans `/opt/microduck-cerveau` et le démarre
comme service (il repart tout seul après un redémarrage). Ensuite :

```bash
journalctl -u microduck-cerveau -f           # suivre ses messages (Ctrl+C pour quitter)
sudo systemctl stop microduck-cerveau        # l'arrêter (le robot reste utilisable avec le logiciel officiel)
sudo systemctl disable --now microduck-cerveau   # ne plus le lancer au démarrage
sudo bash deploy/robot/installer.sh          # après un « git pull » : met à jour les fichiers (ha.toml et mémoire conservés)
```

Sur ton téléphone, sur le même Wi-Fi, ouvre `http://<ip-du-canard>:8090` : au premier démarrage, l'installation guidée
te demande son nom, les habitants et un code. Rien d'autre à écrire à la main.

Le micro partagé (commandes vocales, réflexes sonores) est facultatif et demande des patchs de `robotd` :
`sudo bash deploy/robot/installer.sh --avec-micro`, puis `deploy/robot/README.md`.

> Le script d'installation n'a **jamais tourné sur un vrai robot** (seule la copie des fichiers a été essayée). S'il
> échoue, copie le message d'erreur dans une issue : c'est exactement le retour dont le projet a besoin.

## État de validation

| Domaine | État |
|---|---|
| Logique comportementale (états, personnalité, jeux, taquineries, santé) | testée (suite complète) et validée dans `duck-sim` (`valider_sim.py`) |
| Marche, regard, balle vue par la caméra, approche + tir | validés dans `duck-sim` ; **zone morte de la marche** documentée (`ZONE_MORTE.md`) |
| Appli téléphone / ordinateur, Home Assistant, imprimantes | testées contre des faux serveurs ; HA réel connecté côté auteur ; MQTT en attente de Mosquitto |
| Servo du bec à l'index 9, caresse par le courant des servos | **hypothèses** : `duck-sim` n'a pas de servo de bec (14 servos au lieu de 15) |
| Micro, réflexes sonores, commandes vocales | **non testés** : demandent les patchs `contrib/robotd-audio-*.patch` (non acceptés en amont) |
| Veille du chat (YOLO) | trop lourde pour le CPU : à porter sur le NPU |
| CPU / RAM / batterie sur le vrai RK3566 | **à mesurer** |
| Passe douce (`BallKickPasse`) | entraînée côté fork `microduck_rl`, évaluation en simulateur en cours |

## Ce qui est à toi, jamais à publier

- `ha.toml` / `configuration.json` : adresse et jeton de Home Assistant, clés des imprimantes, code de l'appli.
- `lieux.json` et les plans : la géométrie de ta maison. Les photos (`photos_chat/`) et les modèles (`modeles/`) sont
  ignorés par git.
- Pars de `ha.exemple.toml`. Sans configuration, le canard lance son installation guidée depuis le téléphone.

## Les règles du projet

Le canard ne s'exprime qu'avec ses sons de canard (pas de voix) et **rien n'est analysé hors du canard** (images, sons,
distances) : seul Home Assistant reçoit des états. `test_regles.py` les vérifie.

## Réutiliser seulement une partie

Les politiques RL se chargent seules, sans le cerveau (`charge_politique.py`, contrat 61 entrées / 14 sorties) ; l'appli
et le pont Home Assistant peuvent aussi servir seuls.
