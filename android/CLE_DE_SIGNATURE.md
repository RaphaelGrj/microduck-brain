# La clé de signature de l'APK Microduck

## À quoi elle sert

Android exige que chaque APK soit **signé** par une clé. La signature dit au téléphone qui a construit l'APK.

Quand une mise à jour arrive, Android compare sa signature à celle de l'appli déjà installée :

- **même clé** : la mise à jour s'installe par-dessus. Les canards connus, les réglages et les codes mémorisés sont
  conservés ;
- **clé différente** : Android refuse (« Application non installée », ou « conflit avec un paquet existant »). Il
  faut alors désinstaller l'appli, ce qui efface ses données, puis installer la nouvelle.

La clé doit donc rester **la même pour toute la vie de l'appli**. La perdre ne casse rien sur le canard. En revanche,
chaque téléphone devra désinstaller l'appli une fois.

## Ce qu'elle contient

| Fichier | Rôle |
|---|---|
| `microduck.keystore` | la clé elle-même (format PKCS12, alias `microduck`, RSA 2048, valable ~27 ans) |
| mot de passe | protège le fichier ; le même sert pour la clé et pour le fichier |

Empreinte SHA-256 du certificat des APK 0.3 à 1.0 :
`EB:0B:B6:17:AA:EB:34:C7:60:A6:34:01:0F:30:47:71:39:B7:33:CF:7E:81:02:CF:96:44:1D:33:B2:4C:CD:C6`

L'empreinte n'est pas un secret : elle sert à vérifier qu'un APK vient bien de toi. La commande est
`apksigner verify --print-certs microduck.apk`.

## Règles

1. **Jamais dans un dépôt Git**, même privé. Toute personne qui possède la clé et son mot de passe peut publier une
   fausse « mise à jour » que ton téléphone accepterait.
2. **Garde deux copies hors ligne**, par exemple une dans un gestionnaire de mots de passe (pièce jointe + mot de
   passe) et une sur une clé USB rangée.
3. Sur un PC, garde-la dans `~/.microduck-android/` (dossier en `chmod 700`). `android/construire.sh` va l'y chercher
   tout seul. S'il n'en trouve pas, il en **crée une nouvelle** : c'est le piège à éviter.

## La mettre dans GitHub (publication automatique)

Le workflow `.github/workflows/apk.yml` construit et publie l'APK quand on pose une étiquette `apk-v*`. Il a besoin
de deux **secrets**, chiffrés par GitHub et jamais affichés, même dans les journaux.

1. Sur le PC, convertir la clé en texte :
   - Linux / WSL : `base64 -w0 microduck.keystore > cle.txt`
   - Windows PowerShell : `[Convert]::ToBase64String([IO.File]::ReadAllBytes("microduck.keystore")) | Set-Content cle.txt`
2. Sur GitHub, dans `RaphaelGrj/microduck-brain`, ouvrir **Settings → Secrets and variables → Actions → New
   repository secret** :
   - `MICRODUCK_KEYSTORE_B64` : coller le contenu de `cle.txt` (une seule ligne) ;
   - `MICRODUCK_KEYSTORE_MOT_DE_PASSE` : coller le mot de passe, **sans espace ni retour à la ligne** à la fin.
3. Supprimer `cle.txt`.

Ensuite, pour publier une version :

1. monter `android:versionCode` (+1) et `android:versionName` dans `android/AndroidManifest.xml` ;
2. commiter ;
3. lancer `git tag apk-v1.1 && git push origin apk-v1.1`.

L'APK apparaît dans **Releases**. L'appli propose alors la mise à jour d'elle-même, grâce à `version.json`.

## Construire à la main (sans GitHub)

Sous Ubuntu ou WSL, il faut :

- les paquets `aapt apksigner dalvik-exchange zipalign android-sdk-platform-23` ;
- la clé dans `~/.microduck-android/microduck.keystore` ;
- son mot de passe dans `~/.microduck-android/mot-de-passe`, en `chmod 600`.

Ensuite : `bash android/construire.sh`. L'APK est écrit dans `android/sortie/microduck.apk`.

## Si la clé est perdue

Supprime `~/.microduck-android/`. `construire.sh` crée une nouvelle clé à la construction suivante. Remplace les deux
secrets GitHub par la nouvelle clé. Sur chaque téléphone, désinstalle l'appli puis installe le nouvel APK, une seule
fois. Les données du canard ne sont pas touchées : elles vivent sur le canard, pas dans l'appli.
