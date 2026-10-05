# Intégration Home Assistant (état au 2026-10-03)

## Architecture

```
 imprimantes 3D ──(PrusaLink / HACS elegoo)──> Home Assistant ──WebSocket state_changed──> pont_ha.py ──> brain.py ──> robotd
                                                      ^                                         │                      (gestes + voix)
                                                      └────────── REST  POST /api/states ───────┘   état du canard (batterie, chute, position...)
```

- **`pont_ha.py`** tourne **hors du robot** (PC / serveur), à côté du cerveau. Il parle à HA par son API
  standard (WebSocket pour écouter, REST pour publier / appeler un service) et au robot par `robotd`
  (donc le même code marche contre `duck-sim`, un robot réel ou distant).
- **Maison → canard** : une transition d'état d'une entité surveillée (`ha.toml`, section `[[surveillance]]`)
  devient un événement du cerveau : `impression_finie` (geste « oui » + quack d'accueil), `impression_echec`
  (geste « surpris » + alarme, **réveille le canard s'il dort**), `impression_commencee` (curieux + son
  interrogatif), `alerte`. Le suffixe `:MK4S` indique quelle imprimante.
- **Canard → maison** : entités `sensor.microduck_etat` (état d'esprit du cerveau), `sensor.microduck_energie`,
  `sensor.microduck_politique`, `binary_sensor.microduck_tombe` (classe *problem*), `sensor.microduck_batterie`
  (si le robot la fournit : absente de `duck-sim`), `sensor.microduck_position` (odométrie). Publiées sur
  changement, et toutes les `publier_toutes_les_s` secondes sinon. `HAClient.appeler_service` permet au canard
  de déclencher une scène (`scene.turn_on`) — **pas encore branché à un comportement**.
- **La « voix »** est celle du canard (`robot.sound` : alarm, greet, inquire, peck, chirp, coo, wheee). Des
  phrases parlées passeront par `quacksat` (satellite vocal Assist qui tourne sur le robot), à intégrer plus tard.

## Ton installation : Home Assistant OS sur Raspberry Pi 3B+

- **Le Pi 3B+ n'a que 1 Go de RAM** : le cerveau et le pont ne doivent PAS tourner dessus (voir « Où fait-on tourner le
  cerveau ? » plus bas). Ils parlent à HA par l'API réseau (port 8123).
- Utilise l'**adresse IP** du Pi dans la config (le nom `homeassistant.local` ne se résout pas toujours depuis WSL) et
  fixe-lui une adresse (réservation DHCP dans ta box).
- **Mosquitto (MQTT) sur le même Pi : oui, c'est raisonnable.** C'est un broker très léger (de l'ordre de quelques Mo
  de RAM pour un usage domestique ; je ne l'ai pas mesuré sur ton Pi). Ce qui use un Pi 3B+ sous HA OS, c'est HA
  lui-même (souvent la moitié de la RAM), les autres add-ons et l'**usure de la carte SD** (base de données) — pas
  Mosquitto. Pour surveiller : ajoute l'intégration *System Monitor* (RAM, CPU, disque) avant et après l'installation.
  Garde-fous : peu de messages (le pont publie sur changement, jamais plus d'une fois toutes les 10 s), pas de
  messages « retained » inutiles. Si la RAM dépasse ~85 %, on revient au mode REST (déjà fonctionnel, sans broker).
- MQTT apporterait : entités avec `unique_id` (elles survivent au redémarrage de HA), appareil « Microduck » regroupé,
  boutons pour commander le canard depuis HA. **Pas encore codé** (en attente de ton oui).

## Tu n'as que des Pi 3B+ : ça suffit pour le pont + cerveau (mesuré), pas pour la vision

Mesuré sur le PC : pont + cerveau = **29 Mo de RAM et 0,4–0,8 % d'un cœur** (10 à 50 trames d'état/s). Un Pi 3B+ (Cortex-A53) est
plusieurs fois plus lent (estimation ×5–10) : largement assez, avec 1 Go. Les modules concernés n'utilisent que la bibliothèque
standard + `websockets` et sont compatibles Python 3.11 (celui de Raspberry Pi OS Bookworm). Ce qui **ne** tourne **pas** sur un Pi 3B+ :
la vision (jeu de balle) et YOLO (chat) — ils restent sur le PC à la demande, ou sur le robot plus tard.
Fichiers d'installation prêts mais **non testés sur un Pi** : `deploy/pi/` (README, deux services systemd, requirements).

## Où fait-on tourner le cerveau ? (sans laisser le PC allumé)

Le PC n'est nécessaire que **pendant le développement** (c'est lui qui fait tourner le simulateur). En usage normal, le
cerveau et le pont doivent tourner sur une machine allumée en permanence. Options, de la plus adaptée à la moins :

| Option | Verdict |
|---|---|
| **Un autre Raspberry Pi** (4 ou 5 idéal ; un Pi 3 / Zero 2 W suffit pour le pont seul) | **Recommandé.** Linux complet, 24 h/24, quelques watts. Le pont (Python + `websockets`) est minuscule ; la vision (couleur) tient sur un Pi 4 ; YOLO pour le chat est plus lent (~0,3–1 s/image à estimer). |
| **Le robot lui-même** (RK3566, 1 Go, comme `quacksat`) | Possible pour le pont et les réactions simples (pas de réseau entre cerveau et `robotd`), mais la RAM est partagée avec les démons ; à décider quand le robot sera là. |
| **Ton S24+** (Termux) | **Déconseillé comme hôte** : Android suspend les applications en arrière-plan (économie de batterie), le cerveau s'arrêterait sans prévenir. Très bien comme **télécommande / notifications** via l'appli Home Assistant. |
| Le Pi 3B+ de HA OS (add-on) | Non : 1 Go déjà bien occupé par HA. |

**Comment un cerveau distant atteint le robot** : `robotd` n'écoute que sur un socket local du robot. Un cerveau sur un autre
Pi s'y connecte par un **tunnel SSH de socket Unix** (`ssh -L` redirige un socket distant vers un socket local ; le robot a
déjà SSH, c'est ainsi que `quacksat` s'y déploie). Le code actuel (`RobotdClient`) parle à un socket Unix : il n'y a rien à
changer côté cerveau. **À valider sur le vrai robot** (pas encore livré).

## Le fichier de configuration (ce que tu remplis)

`~/microduck-brain/ha.toml`, soit `\\wsl.localhost\Ubuntu\home\raphael\microduck-brain\ha.toml` depuis Windows. Il est **ignoré par git**
(`.gitignore`) et en droits `600`. Sections : `[home_assistant]` (IP, jeton), `[mqtt]`, `[reseau]` (où tourne quoi),
`[[imprimante]]` (une par imprimante), `[[habitant]]`, `[[appareil]]` (messager : sonnette, lave-linge…), `[[declencheur]]`
(une entité HA → un événement du cerveau), `[cerveau]` (routines : heures calmes, bonjour du matin), `[notes]` (libre). Tout ce qui reste à `A_REMPLIR` est ignoré. Le programme
**avertit** si ce fichier n'est pas ignoré par git, et n'affiche jamais le jeton.

## Mise en route chez toi (ce que je ne peux pas faire à ta place)

1. Dans HA : profil (en bas à gauche) → *Sécurité* → *Jetons d'accès longue durée* → créer un jeton (il ne s'affiche qu'une fois).
2. Remplir `ha.toml` (IP du Pi, jeton, et laisser les imprimantes à `A_REMPLIR` pour l'instant).
3. `bash ~/run-brain.sh pont_ha.py ha.toml --verifier` : teste l'URL, le jeton, le WebSocket, le broker MQTT, et **liste les
   entités qui ressemblent à une imprimante** : il suffit de recopier leurs noms dans `[[imprimante]]`.
4. `bash ~/run-brain.sh canard.py ha.toml` (le simulateur ou le robot doit tourner) : le canard **complet** (cerveau + HA +
   capteur de distance + caméra). `pont_ha.py ha.toml` lance encore le cerveau seul avec HA, mais sans ToF ni caméra
   (le canard ne marche alors jamais, et ni la main tendue ni le jeu ne sont actifs).

Intégrations HA à installer pour les imprimantes (déjà existantes, non écrites par nous) :
- Prusa **MK4S** : intégration officielle *PrusaLink* (états `idle, busy, printing, paused, finished, stopped,
  error, attention`). La **MK3S** n'est supportée qu'avec un Raspberry Pi Zero faisant tourner PrusaLink
  (≥ 0.7.2) ; sinon ce sera une surveillance indirecte (Prusa Connect n'a pas d'API locale documentée ici).
- **Elegoo Saturn 4 Ultra** : intégration communautaire *elegoo-homeassistant* (HACS, protocole SDCP) ;
  **les valeurs d'état exactes sont à relever chez toi**.

## Messager de la maison, boutons et routines (2026-10-05)

- **`[[appareil]]`** : sonnette (`type = "sonnette"` pour un `binary_sensor`, `"sonnette_event"` pour une entité `event.*` dont
  chaque appui change l'état), machine connectée (`"machine"` : états `finished`/`end`/`complete`… de Home Connect, LG ThinQ,
  SmartThings) ou **appareil « bête » sur une prise qui mesure la puissance** (`"puissance"` : en marche au-dessus de `seuil_w`,
  fini après `fin_apres_s` sous le seuil — un lave-linge s'arrête quelques minutes pendant le trempage —, et seulement après un
  vrai cycle de `marche_min_s`). Le canard réagit (sonnette : tête qui se redresse + alarme puis interrogatif ; machine finie :
  « il y a quelque chose » + signe). **Si personne n'est à la maison**, les fins d'impression / de machine sont **gardées et
  redites à l'accueil** du prochain habitant qui rentre (`sensor.microduck_messages` : nombre et liste).
- **Boutons** (avec MQTT) : `button.microduck_jouer_soleil` et `button.microduck_fin_jeu` apparaissent sur l'appareil Microduck
  (jeu « 1-2-3 soleil »). Seules ces deux commandes sont acceptées sur `microduck/commande`. Sans MQTT : une Entrée « Bouton »
  (`input_button`) reliée par `[[declencheur]] evenement = "jeu_soleil"`.
- **`[cerveau]`** : `heures_calmes = [23, 7]` (assis et silencieux la nuit, comme l'interrupteur calme), `bonjour = "7:30"`
  (une fois par jour : étirement + bonjour si quelqu'un est là, dans les 4 h qui suivent).
- Tout cela est testé contre le faux HA / faux broker (`test_ha.py`), **pas encore sur ton instance**.

## Ce qui est validé, et ce qui ne l'est pas

Validé (`python test_ha.py`, contre `mock_ha.py`, un **faux** HA qui imite l'API d'après la documentation) :
transitions d'état → événements (et seulement elles : même état, `unavailable`, entité non surveillée,
état sans réaction ignorés ; insensible à la casse), deux imprimantes, jeton refusé (message clair, jeton jamais
écrit dans les logs), publication des entités, chute remontée, appel de service, reconnexion après coupure,
réactions du cerveau (celebre/alerte, l'alerte réveille la sieste), lecture de la config à sections (champs
`A_REMPLIR` ignorés) et commande `--verifier` (REST, WebSocket, broker, liste d'entités, mauvais jeton expliqué).

Validé aussi **contre `duck-sim`** (`python demo_ha.py`, faux HA + pont + cerveau + canard simulé) : impression
qui démarre → état `info` (tête +0,37 rad), qui se termine → `celebre` (geste « oui »), échec → `alerte`
(geste « surpris », amplitude de tête 0,48 rad) ; `robot.sound` accepté par `robotd` (greet / alarm / inquire) ;
`sensor.microduck_*` publiés. *Le son n'est pas écouté* dans la simulation : on voit seulement que `robotd` l'accepte.

**Pas validé** : contre un vrai Home Assistant (formats copiés de la documentation, pas testés sur ton instance) ;
noms d'entités et d'états réels des imprimantes ; comportement quand `quacksat` tourne en même temps.

## À faire ensuite

- Valider chez toi (URL + jeton + noms d'entités), puis ajuster `ha.exemple.toml`.
- **MQTT discovery** à la place du REST si tu as un broker (entités propres : `unique_id`, appareil « Microduck »,
  elles survivent au redémarrage de HA).
- **Arbitrage `quacksat` / cerveau** : tous deux sont clients de `robotd` (`robot.move` / `robot.head` : le
  dernier écrit gagne) ; il faudra un partage clair (par ex. le cerveau se tait pendant une conversation).
- Le canard qui **va vers l'habitant** quand une impression échoue : il sait maintenant aller vers un point connu à
  l'odométrie (`navigation.py`), mais ne sait pas OÙ est l'habitant (UWB plus tard) ; en attendant, il garde le message.
- Scènes déclenchées par le canard (NFC, geste, présence) via `appeler_service`.
