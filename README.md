# microduck-brain — le cerveau du canard

Le cerveau comportemental d'un **[Microduck](https://github.com/pollen-robotics/microduck)** (Pollen Robotics) :
ce qui en fait un membre du foyer plutôt qu'une démo. Il décide quoi faire à chaque instant, perçoit son entourage
(caméra, capteur de distance, micro) et dialogue avec Home Assistant.

Il tourne **sur le robot**, à côté des démons officiels (`robotd`, `tofd`, `mediad`), et ne parle qu'à eux en local.
Il ne fait que commander le robot via l'API JSON-RPC de `robotd` (marche, tête, sons, compétences entraînées) : aucun
réseau de neurones n'est entraîné ici. Le même code pilote le vrai robot ou le canard simulé de `duck-sim`.

> **État** : le robot n'est pas encore livré. Tout est développé contre `duck-sim` et couvert par une suite de tests
> sans simulateur (277 tests). Une partie a été écrite sans simulateur et attend la validation groupée
> (`scripts-wsl/valider-tout.sh`).

## Ce qu'il sait faire

- **Une vie autonome**, sur le modèle de la machine à états M9 de Pollen (ses 16 états) :
  - repos, promenade sans se cogner ni tomber d'une marche, siestes avec petits rêves ;
  - énergie et éveil, rythme de la journée et des saisons ;
  - personnalité (curiosité, sociabilité, espièglerie, prudence) qui évolue avec ce qu'il vit.
- **Des réactions à son entourage** :
  - accueil quand quelqu'un rentre, main tendue, caresse ;
  - ton grondeur ou câlin quand on dit son nom ;
  - timidité avec un visiteur, discrétion pendant un appel téléphonique ;
  - sursaut, abri pendant l'orage ou les pétards, danse au rythme de la musique ;
  - suivi du chat des yeux.
- **Des jeux** : jeu de balle avec la vraie position de la balle vue par la caméra, cache-cache, 1-2-3 soleil.
- **Des taquineries**, avec un budget, un signal « stop » et une mémoire des blagues.
- **La surveillance de sa propre santé** : batterie dans la durée, usure des servos, journal des chutes, auto-test
  chaque matin.
- **Home Assistant dans les deux sens** :
  - la maison le prévient : impressions 3D, sonnette, machines, météo, calendrier, alarme incendie ;
  - il publie ses états ;
  - il déclenche des scènes, y compris par commande vocale reconnue sur le canard ;
  - mode garde quand la maison est vide.

## L'application Microduck (téléphone)

**Avec ou sans Home Assistant.** Au premier démarrage, sans configuration, le canard ouvre une installation de
30 minutes : depuis le téléphone, on choisit son nom, les habitants et le code de l'appli. Tout le reste se règle dans
l'appli (Réglages → Connexions) : Home Assistant (facultatif), imprimantes 3D suivies en direct (Prusa par PrusaLink,
Elegoo par SDCP), appareils, code enfant. `ha.toml` devient facultatif ; ce que l'appli écrit (`configuration.json`,
`configuration.py`) prend le dessus section par section. L'appli existe en français et en anglais (`interface/i18n.js`).


Le canard sert lui-même son application, sans Home Assistant et sans serveur ailleurs (`appli.py` + `interface/`).
1. Dans `ha.toml`, définis un code d'au moins 6 caractères :
   ```toml
   [appli]
   code = "ton-code"
   ```
2. Sur le téléphone, connecté au même Wi-Fi, ouvre `http://<ip-du-canard>:8090` et entre le code.
3. Ajoute la page à l'écran d'accueil : elle s'ouvre ensuite comme une appli.

**Sur iPhone et iPad** : l'appli web du canard s'installe depuis Safari, sans App Store.
1. Le téléphone sur le Wi-Fi de la maison, ouvre `http://<ip-du-canard>:8090`. Le plus simple : Réglages → Sur un
   autre appareil → QR, puis scanner avec l'appareil photo.
2. Dans Safari : **Partager → Sur l'écran d'accueil**. Elle s'ouvre ensuite en plein écran, comme une appli.

Limites, propres à iOS pour une page web servie en `http` sur le réseau local :
- pas de notifications en arrière-plan (les alertes s'affichent dans l'appli) ;
- pas de widget ;
- pas de présence par le Wi-Fi.

Une vraie appli de l'App Store demanderait un Mac et un compte développeur Apple (99 €/an).

**Sur ordinateur** (Windows, macOS, Linux) : `ordinateur/`, application Electron qui trouve le canard toute seule.
GitHub la construit à chaque version : <https://github.com/RaphaelGrj/microduck-brain/releases>. Mode d'emploi :
`ordinateur/README.md`.

**Appli Android** (`android/`) : un APK de 180 Ko qui trouve le canard tout seul sur le Wi-Fi et ouvre l'interface
en plein écran, plus un **mode démo** pour l'essayer sans le robot. Il ne contient aucune logique : l'interface reste
servie par le canard, donc une mise à jour du cerveau met l'appli à jour. Construction sans Android Studio :
`bash android/construire.sh` (outils des paquets Ubuntu, voir l'en-tête du script). Télécharger la dernière version :
<https://github.com/RaphaelGrj/microduck-brain/releases/latest/download/microduck.apk>. La clé de signature se crée une
fois par `bash android/creer_cle.sh`, hors du dépôt : voir `android/CLE_DE_SIGNATURE.md`.

**Sections** :
- **Accueil** : humeur, batterie, qui est là, journal du jour.
- **Jouer** : balle, cache-cache, 1-2-3 soleil, danse, tours.
- **Commander** : petits pas guidés, avec les garde-fous du cerveau (pas d'obstacle, pas de vide, pas de recul), et le regard.
- **Santé** : bouton **lancer le diagnostic**, batterie, **ses 3 batteries** (après un échange, il demande
  laquelle est mise ; cycles, autonomie et santé de chacune), servos, températures, chutes, version.
- **Caractère** : personnalité, voix, êtres connus.
- **Réglages** : mode calme, mode garde, couper les taquineries, effacer sa carte, **lieux**.
  - Le canard reconnaît où il est par son Wi-Fi (`lieux.py`) : sur un réseau inconnu, il crée un lieu ; de retour
    sur un réseau connu, il y rebascule.
  - Chaque lieu peut être renommé, lié à un autre réseau (répéteur), archivé, restauré ou supprimé.
  - Chaque lieu garde sa dernière carte, qu'on peut regarder dans l'appli.
- **Journal** : **sa semaine** (une barre par jour, les totaux), puis ce qu'il a fait.
- **Alertes** (accueil) et **notifications** de l'APK : chute, batterie faible, diagnostic en échec, garde, alarme
  incendie, impressions et machines finies ou ratées. Le canard les tient (`GET /api/alertes`), le téléphone les lit.
- **Réglages → Sa journée** : heures calmes, bonjour du matin (semaine, week-end), repas, auto-test, rythme. Ils sont
  gardés dans `reglages.json` (`reglages.py`) et prennent le dessus sur `ha.toml`, qui n'est jamais réécrit.
- **Widget Android** : son état et sa batterie sur l'écran d'accueil.
- **Où es-tu ?** (accueil) : trois petits `chirp` pour le retrouver (pas en mode calme).
- **Son look** : le Microduck de l'accueil prend les couleurs du schéma actif du design, pose par pose (ombrage et
  carte des pièces rendus par `outils/rendu_microduck.py`).
- **Design → Fiche d'impression** (quoi imprimer, dans quelle couleur, avec les liens des STL d'origine) et
  **Photo** (image 4:3 du Microduck 3D, pour partager ou illustrer une fiche du catalogue).
- **Réglages → Mise en route** : la liste du jour de la livraison, cochée toute seule quand le canard peut vérifier ;
  repliée, et masquable (Réglages → Ce téléphone pour la réafficher).
- **Réglages → Routines** : « à 18 h 30 en semaine, il vient me voir », « le dimanche, il danse ».
- **Réglages → Sauvegarde** : ce qu'il a appris, ses lieux, tes schémas et ses réglages, dans un fichier sur le
  téléphone (jamais `ha.toml`) ; une restauration s'applique au prochain démarrage du canard.
- **Jouer** : statistiques et défi à plusieurs du jeu de balle ; **studio de chorégraphies** (`choregraphies.py` :
  tête, sons de canard, gestes, s'asseoir) ; **comportements** (politiques de `robotd` : installées, à essayer, à ajouter).
- **Caractère** : curseurs calme ↔ joueur, discret ↔ bavard, sage ↔ taquin.
- **Commander** : pas répétés tant que le doigt reste appuyé, regard au pavé tactile.
- **Santé → Mises à jour et rapport** : nouvelle version du cerveau installée sur demande
  (`deploy/robot/mettre_a_jour.sh`, retour possible), rapport de diagnostic sans donnée personnelle.
- **Aide** intégrée ; **profil enfant** (code enfant : jeux, regard, « Où es-tu ? »).
- **APK** : plusieurs canards ; publication automatique par GitHub Actions à chaque nouvelle version (`.github/workflows/apk.yml`) ;
  présence par le téléphone (quand il rejoint le Wi-Fi de la maison, le canard t'accueille, sans Home
  Assistant ; le départ, lui, vient de Home Assistant) et mise à jour proposée quand une nouvelle version est publiée.

**En haut à droite** :
- **Design** (palette) : le vrai Microduck en 3D, d'après son modèle officiel allégé (`outils/modele_3d.py`).
  - Toucher une pièce et la recolorer avec tes filaments ou une couleur libre.
  - Comparer avec l'origine, enregistrer des schémas (gardés sur le canard).
  - Poser ton propre STL, dessiné dans le repère de la pièce d'origine.
- **Marketplace** (sac) : les pièces du dépôt [microduck-catalogue](https://github.com/RaphaelGrj/microduck-catalogue).
  - Liens Printables et Cults, et « Essayer sur mon Microduck » dans le design.
  - Le catalogue est lu par le téléphone : le canard n'envoie rien.

L'accès est limité au réseau local, avec le code. Les commandes viennent d'une liste fermée et passent par le cerveau
comme n'importe quel événement. Aucune image ni aucun son n'est envoyé au téléphone.

## Deux règles, vérifiées par les tests (`test_regles.py`)

- **Il ne s'exprime qu'avec ses sons de canard** (`alarm`, `greet`, `inquire`, `peck`, `chirp`, `coo`, `wheee`) :
  pas de voix humaine, pas de synthèse vocale.
- **Tout est analysé sur le canard.** Images, sons et distances ne quittent jamais le robot. Une caméra lue à
  distance est refusée. Home Assistant ne reçoit que des états, et seule la commande vocale reconnue lui est
  transmise, jamais le son.

## Démarrer

Prérequis : Python 3.12 et [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run --with pytest pytest -q $(ls test_*.py | grep -v test_chat_affiche)   # la suite complète, sans simulateur
cp ha.exemple.toml ha.toml       # puis le remplir : ha.toml contient ton jeton Home Assistant, il est ignoré par git
uv run python canard.py ha.toml  # le canard complet (robotd local ; options : --micro, --chat, --sans-camera, --sans-ha)
```

- **Avec le simulateur** (WSL) : les scripts de `scripts-wsl/` lancent `duck-sim` avec la caméra et la vérité
  terrain.
- **Validation groupée en une commande** : `bash scripts-wsl/valider-tout.sh` lance les tests, le banc de coût et
  13 scénarios dans `duck-sim`, puis écrit un rapport.
- **Sur le robot** : `deploy/robot/README.md` (service systemd, micro partagé, commandes vocales hors ligne).

## Organisation

| Domaine | Fichiers |
|---|---|
| Point d'entrée | `canard.py` : cerveau, Home Assistant, ToF, caméra, micro |
| Cerveau | `brain.py` (boucle à 50 Hz, choix des états, événements) ; états : `etats_base.py`, `etats_vie.py`, `etats_jeux.py`, `etats_maison.py`, `etats_taquineries.py` ; `gestures.py` (gestes de tête) |
| Mémoire et caractère | `memoire.py` (sauvegarde locale), `lieux.py` (lieux reconnus par le Wi-Fi), `personnalite.py`, `habitudes.py`, `taquineries.py`, `exploration.py` (carte des zones visitées, coins favoris), `navigation.py` |
| Perception | `vision.py`, `geometry.py`, `track.py`, `balle.py` (la balle), `chat.py` + `animaux.py` (YOLO), `mouvement.py`, `tof.py` (distance, vides), `main_tendue.py`, `caresse.py` |
| Son | `audio.py` (réflexes sans réseau de neurones : chocs, claquements, musique, voix, alarme…), `commandes.py` (commandes vocales Vosk hors ligne) |
| Jeu de balle | `approach.py` (approche + tir), `jeu.py` (passe au joueur) |
| Santé | `diagnostic.py`, `bench_cerveau.py` (coût d'une trame : 0,03 ms en moyenne sur PC, budget 20 ms) |
| Application | `appli.py` (serveur local, API JSON, flux en direct), `configuration.py`, `imprimantes.py`, `choregraphies.py`, `interface/` (HTML, CSS, JS sans framework ; `demo.js` = canard imaginaire), `android/` (APK) |
| Home Assistant | `pont_ha.py`, `ha.exemple.toml` (modèle de configuration commenté), `mock_ha.py` / `mock_mqtt.py` (faux HA et faux broker pour les tests), `HOME_ASSISTANT.md` |
| Simulateur | `valider_sim.py` (13 scénarios), `truth.py` (vérité terrain du simulateur, sert seulement à mesurer), bancs `*_eval.py`, `scripts-wsl/` |
| Robot | `deploy/robot/` (installation sur le canard), `contrib/` (patchs proposés à `robotd` pour partager le micro) |
| Notes | `ZONE_MORTE.md` (vitesses sous lesquelles la marche ne démarre pas), `QUACKSAT_QUACKNAV.md` |
| Tests | `test_*.py` (endurance de plusieurs heures simulées, invariants de sécurité, une relecture = un test par défaut corrigé) |

Les scripts `diag_*.py` et `demo_*.py` sont des essais ponctuels contre `duck-sim`, gardés pour mémoire.

## Configuration

Tout se règle dans `ha.toml`, à partir de `ha.exemple.toml` :
- Home Assistant : URL, jeton, MQTT ;
- habitants, imprimantes, appareils (sonnette, machines, prise à puissance, météo, calendrier, fumée, aspirateur,
  température extérieure) ;
- déclencheurs (jeux, visiteur, compagnie) ;
- actions du canard vers la maison (`[[action]]`) ;
- section `[cerveau]` : nom, commandes vocales, heures calmes, bonjour du matin, repas, mode garde.

Le cerveau tourne aussi **sans** Home Assistant : les fonctions de la maison ne se déclenchent simplement pas.

Variables d'environnement utiles :

| Variable | Rôle |
|---|---|
| `MICRODUCK_FRAME_URL` | Adresse de la caméra (en local seulement) |
| `MICRODUCK_MEMOIRE` | Fichier de mémoire, `~/.local/share/microduck/memoire.json` par défaut |
| `MICRODUCK_MICRO` | Périphérique ALSA du micro partagé |
| `MICRODUCK_TIR` | Profil du tir (`officiel` par défaut) |

## Données personnelles

Ces éléments ne sont jamais mis dans le dépôt (voir `.gitignore`) :
- `ha.toml` et tout fichier de jeton ;
- les photos (`photos_chat/`, `*.png`) ;
- les modèles (`modeles/`, `*.onnx`).

La mémoire du canard (habitants, habitudes, personnalité) reste dans un fichier local sur le robot.

## Liens

- Projet et feuille de route : [microduck-project](https://github.com/RaphaelGrj/microduck-project)
- Entraînement (fork) : [microduck_rl](https://github.com/RaphaelGrj/microduck_rl)
- Logiciel officiel du robot : [pollen-robotics/microduck](https://github.com/pollen-robotics/microduck)

Support me : https://buymeacoffee.com/raphaelgrj
