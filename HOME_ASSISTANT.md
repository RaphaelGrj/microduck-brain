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

## Mise en route chez toi (ce que je ne peux pas faire à ta place)

1. Dans HA : profil (en bas à gauche) → *Sécurité* → *Jetons d'accès longue durée* → créer un jeton.
2. Le coller **toi-même** dans `~/.config/microduck/ha_token` (une ligne, `chmod 600`). Il n'est jamais dans le
   dépôt, ni dans `ha.toml`, ni dans les logs.
3. Copier `ha.exemple.toml` en `ha.toml`, mettre l'URL de HA et les **vrais noms d'entités et d'états**
   (HA → *Outils de développement* → *États* : chercher l'imprimante et noter les valeurs qu'elle prend en fin
   d'impression, en échec, etc.).
4. `bash ~/run-brain.sh pont_ha.py ha.toml` (le simulateur ou le robot doit tourner).

Intégrations HA à installer pour les imprimantes (déjà existantes, non écrites par nous) :
- Prusa **MK4S** : intégration officielle *PrusaLink* (états `idle, busy, printing, paused, finished, stopped,
  error, attention`). La **MK3S** n'est supportée qu'avec un Raspberry Pi Zero faisant tourner PrusaLink
  (≥ 0.7.2) ; sinon ce sera une surveillance indirecte (Prusa Connect n'a pas d'API locale documentée ici).
- **Elegoo Saturn 4 Ultra** : intégration communautaire *elegoo-homeassistant* (HACS, protocole SDCP) ;
  **les valeurs d'état exactes sont à relever chez toi**.

## Ce qui est validé, et ce qui ne l'est pas

Validé (`python test_ha.py`, contre `mock_ha.py`, un **faux** HA qui imite l'API d'après la documentation) :
transitions d'état → événements (et seulement elles : même état, `unavailable`, entité non surveillée,
état sans réaction ignorés ; insensible à la casse), deux imprimantes, jeton refusé (message clair, jeton jamais
écrit dans les logs), publication des entités, chute remontée, appel de service, reconnexion après coupure,
réactions du cerveau (celebre/alerte, l'alerte réveille la sieste).

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
- Le canard qui **va vers l'habitant** quand une impression échoue (navigation : plus tard, UWB/odométrie).
- Scènes déclenchées par le canard (NFC, geste, présence) via `appeler_service`.
