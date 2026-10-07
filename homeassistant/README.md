# Carte Microduck pour Home Assistant

Une carte de tableau de bord qui affiche ton canard :
- son état, sa batterie, son énergie et son éveil ;
- une alerte s'il est tombé ;
- l'interrupteur du mode calme ;
- des boutons : où es-tu, jeux, salut, arrêter le signal d'un minuteur ou du réveil, diagnostic.

Elle n'utilise que les entités que le canard publie déjà (`pont_ha.py`). Les boutons et l'interrupteur viennent de
MQTT discovery (`[mqtt] actif = true` dans `ha.toml`, add-on Mosquitto).

## Installation (une fois)

1. Copie `microduck-card.js` dans le dossier `www` de Home Assistant, c'est-à-dire `/config/www/` (add-on « File
   editor » ou « Samba »).
2. Va dans **Paramètres → Tableaux de bord → ⋮ → Ressources → Ajouter une ressource** :
   - URL : `/local/microduck-card.js`
   - type : **Module JavaScript**
3. Recharge la page (Ctrl+F5).
4. Sur un tableau de bord : **Modifier → Ajouter une carte → Microduck**. En YAML :

```yaml
type: custom:microduck-card
titre: Coin-Coin                    # facultatif
# image: /local/microduck.webp      # facultatif : une image de ton canard (copie-la aussi dans /config/www/)
# prefixe: microduck                # si tes entites s'appellent autrement que sensor.microduck_...
```

Pour l'image, copie par exemple `interface/microduck/debout.webp` de ce dépôt dans `/config/www/microduck.webp`.
Une adresse `http://` vers le canard serait bloquée si Home Assistant est en `https`.
