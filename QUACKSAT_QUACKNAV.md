# quacksat et quacknav : cohabitation avec notre cerveau (étude du 2026-10-04)

Deux projets communautaires d'Andrea Genovese, Apache-2.0, lus (pas exécutés) à leurs versions du 2026-10-03 :
`andreagenovese/quacksat` (v0.1.0-rc1) et `andreagenovese/quacknav` (v0.2.0-rc2). Validés seulement sur le jumeau MuJoCo,
comme nous ; essais sur un vrai canard annoncés pour décembre 2026.

## Ce qu'ils font

- **quacksat** tourne SUR le canard : micro, mot d'éveil (« hey Daffy » ou un mot à soi), puis trois façons de répondre :
  `wyoming` (satellite **Assist de Home Assistant** : reconnaissance vocale, intentions et synthèse dans HA), `agent`
  (pont WebSocket vers un LLM avec outils), `direct` (le canard appelle lui-même des API compatibles OpenAI). C'est un
  client ordinaire de `robotd` : il envoie `robot.head` (balancement « je réfléchis »), `robot.move` et `robot.do` quand
  on lui demande quelque chose.
- **quack-navd** (dépôt quacknav) est un démon de navigation, sur le canard aussi, qui parle le même dialecte que `robotd`
  (`/run/quack-nav/nav.sock`, `nav.catalog` / `nav.call`) : carte de la maison faite en explorant (une session par
  charge), **lieux nommés** (« ici c'est la cuisine »), `robot.where_am_i`, `robot.go_to {place}`, retour à la maison
  au démarrage (il se relocalise tout seul), et un **garde-fou anti-chute** qui lit les faisceaux du ToF vers le sol.

## Ce que ça change pour nous

1. **Sécurité : `robotd` n'a aucune protection contre les escaliers** (écrit dans quacknav, à vérifier dans le code de
   robotd). Notre promenade (`tof.py`, `brain.Wander`) évite les obstacles, pas les **trous**. Sur le vrai robot : soit
   passer nos déplacements par `quack-navd` (`robot.move` y est gardé), soit ajouter la détection de vide à `tof.py`
   (faisceaux vers le bas qui voient plus loin que le sol attendu). **À faire avant toute promenade autonome réelle.**
2. **Arbitrage** : deux clients de `robotd`, le dernier écrit gagne (`robot.move`, `robot.head` à 50 Hz). Notre cerveau
   envoie la tête et la marche à CHAQUE trame : il écraserait le balancement de quacksat et, pire, un « avance » demandé à
   la voix. Règle retenue : **pendant une conversation, le cerveau n'envoie plus rien** (état `ecoute`). Le signal vient de
   Home Assistant : le satellite Wyoming y est une entité `assist_satellite.*` dont l'état passe par `listening`,
   `processing`, `responding` puis revient à `idle` (fait dans `pont_ha.py`, section `[home_assistant] satellite_vocal`).
   Même principe à prévoir avec quack-navd : pendant un trajet ou une exploration (`robot.map_status` → `explore.state`
   `running` / `relocalizing` / `searching`, ou `self_started`), le cerveau ne commande pas la marche.
3. **Navigation et pièce** : plutôt que réécrire une carte, s'appuyer sur quack-navd : `robot.where_am_i` donnerait la
   **pièce** (entité HA `sensor.microduck_piece`, demandée dans la feuille de route), et `robot.go_to {"place": "entrée"}`
   l'**accueil au retour** qui marche vers la porte. Nos balises UWB deviennent un « plus tard » éventuel.
4. **Vocal** : pas besoin d'écrire notre propre vocal ; quacksat en mode `wyoming` suffit pour « Assist » dans HA. Notre
   cerveau garde la personnalité (réactions, gestes, sons) ; quacksat garde la parole.

## Ordre proposé à la livraison du robot

quacksat (`wyoming`) installé sur le canard → entité `assist_satellite` dans HA → `satellite_vocal` dans `ha.toml` →
quack-navd + carte de la maison + lieux (« entrée », « salon »…) → client quack-navd dans le cerveau (pièce, aller à).
