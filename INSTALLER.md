# Installer le cerveau sur ton Microduck

Ce guide s'adresse à une personne qui possède un **[Microduck](https://github.com/pollen-robotics/microduck)** et veut
y faire tourner ce cerveau. Il dit aussi, sans enjoliver, **ce qui est validé et ce qui ne l'est pas**.

> **Honnêteté d'abord** : l'auteur n'a pas encore reçu son robot. Tout a été développé contre `duck-sim` (le simulateur
> officiel) et une suite de tests sans simulateur. **Rien n'a tourné sur un vrai canard.** Si tu es le premier à essayer,
> tu fais de la validation : n'hésite pas à ouvrir une issue avec ce que tu constates.

## Ce qu'il te faut

- Un Microduck à jour (`robotd`, `tofd`, `mediad` officiels). Le cerveau ne parle qu'à eux, par leur API locale.
- Un accès SSH au robot.
- Facultatif : Home Assistant (le cerveau et l'appli marchent sans), un micro partagé (patchs, voir ci-dessous).

## Trois niveaux d'essai, du plus sûr au plus engageant

1. **Sans robot** : lance `duck-sim` puis le cerveau (`scripts-wsl/README.md`, `scripts-wsl/jumeau.sh`). Les tests :
   `uv run --with pytest pytest -q $(ls test_*.py | grep -v test_chat_affiche)` (aucun simulateur requis).
2. **Sur le robot, à la main** : `python3 canard.py` en SSH, canard posé sur un support, prêt à être coupé. Commence par
   `bench_cerveau.py` (mesure CPU/RAM sur le RK3566) puis `valider_sim.py`, dont le scénario `bec_index`.
3. **Sur le robot, en service** : `deploy/robot/README.md` (utilisateur dédié, systemd, mises à jour depuis l'appli).

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
