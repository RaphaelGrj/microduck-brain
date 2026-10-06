# Microduck pour ordinateur (Windows, macOS, Linux)

La même application que sur le téléphone. Elle trouve le canard sur le Wi-Fi de la maison et ouvre l'interface qu'il
sert lui-même, plus un **mode démo** pour l'essayer sans le canard. Elle n'embarque aucune logique : mettre à jour le
cerveau met l'appli à jour.

**Télécharger** : <https://github.com/RaphaelGrj/microduck-brain/releases>, la release « Microduck pour ordinateur ».

| Système | Fichier |
|---|---|
| Windows | `…-windows-installation.exe` (installe et crée un raccourci) ou `…-windows-portable.exe` (sans installation) |
| macOS | `…-mac-arm64.dmg` (puces Apple M1 à M4) ou `…-mac-x64.dmg` (Mac Intel) |
| Linux | `…-linux-x86_64.AppImage` (n'importe quelle distribution : `chmod +x` puis double-clic) ou `…-linux-amd64.deb` (Ubuntu, Debian : `sudo apt install ./Microduck-….deb`) |

## Premier lancement : l'appli n'est pas signée

Signer une application coûte un certificat payant (Apple 99 €/an, Microsoft…). Le système demande donc une fois de
confirmer.

- **Windows** : « Windows a protégé votre ordinateur » → **Informations complémentaires** → **Exécuter quand même**.
- **macOS** :
  1. Ouvre le `.dmg` et glisse Microduck dans Applications.
  2. Au premier lancement, macOS refuse.
  3. Va dans **Réglages Système → Confidentialité et sécurité**, puis **Ouvrir quand même**.
  4. En cas de « Microduck est endommagé », lance dans le Terminal : `xattr -cr /Applications/Microduck.app`.
- **Linux** : rien de spécial. Pour l'AppImage : `chmod +x Microduck-*.AppImage`.

## Ce qu'elle fait

- **Chercher mon canard** : elle interroge le réseau local (port 8090) et garde la liste des canards connus.
- **Son adresse** : `192.168.1.42`, si la recherche ne le trouve pas (Wi-Fi invité, réseau découpé).
- **Notifications** de l'ordinateur pour les alertes du canard (chute, batterie, impression…), tant que la fenêtre est
  ouverte.
- **Enregistrer** : sauvegardes, photos, fiches d'impression, chorégraphies et schémas de couleurs, avec la fenêtre
  « Enregistrer sous ».
- **Menu Microduck → Changer de canard** (Ctrl+Maj+H) pour revenir à l'accueil.
- Elle ne parle qu'aux adresses du réseau local. Les liens vers Printables, Cults ou GitHub s'ouvrent dans le
  navigateur.

## La construire soi-même

Il faut Node.js 22 :

```
cd ordinateur
npm ci
npm start                                      # la lancer sans paquet
npx electron-builder --linux AppImage deb      # (ou --win, --mac sur le systeme correspondant)
```

GitHub construit les trois systèmes tout seul quand la version de `package.json` change : workflow
`.github/workflows/ordinateur.yml`.
