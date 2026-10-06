# La clé de signature de l'APK Microduck

## Ce que tu as à faire (une seule fois, 5 minutes)

1. Sous **Linux** (ou WSL), dans le dossier du dépôt `microduck-brain` (branche `main`, après `git pull`) :
   ```
   bash android/creer_cle.sh /mnt/mmc-SN128_0x5c36c07b-part1/microduck/microduck-app
   ```
   Le chemin indique où ranger la sauvegarde de la clé. Sans chemin, elle va dans Documents (WSL) ou dans ton
   dossier personnel.
2. Réponds à ce qu'il demande :
   - **le mot de passe de WSL**, si l'outil GitHub (`gh`) n'est pas encore installé ;
   - la **connexion à GitHub** : choisir `GitHub.com`, puis `HTTPS`, puis `Login with a web browser`. Une page
     s'ouvre : tu y colles le code à 8 caractères affiché dans WSL, puis tu valides.
3. Attends la première version publiée par GitHub : onglet **Releases** du dépôt, à la prochaine version de l'appli.
   Sur le téléphone, **désinstalle une fois** l'appli Microduck installée (1.0 ou 1.1, signées par l'ancienne clé).
   Installe ensuite la nouvelle depuis
   <https://github.com/RaphaelGrj/microduck-brain/releases/latest/download/microduck.apk>.
   Tu devras retaper le code du canard.

Rien d'autre à faire ensuite. À chaque nouvelle version, GitHub construit l'APK, le signe avec ta clé et le publie.
L'appli te propose alors la mise à jour d'elle-même.

### Ce que fait le script

| Étape | Effet |
|---|---|
| 1. Création | Crée **ta** clé dans `~/.microduck-android/`, un dossier lisible par toi seul. Si elle existe déjà, il la garde. |
| 2. Sauvegarde | Copie la clé dans **Documents → `Microduck - cle APK (SECRET)`** côté Windows : la clé, son mot de passe et un `LISEZ-MOI.txt`. |
| 3. GitHub | Dépose la clé dans les **secrets** du dépôt `microduck-brain`. Ce sont des coffres chiffrés : GitHub ne les montre jamais, même à toi, et les cache dans les journaux. |

Le script ne contient aucun secret et n'envoie rien ailleurs que sur GitHub et dans tes Documents. On peut le
relancer sans risque : il ne remplace jamais une clé existante.

### Pourquoi désinstaller une fois

Les APK 1.0 et 1.1 ont été signés par une clé créée dans la session cloud de Claude. Cette clé disparaîtra avec la session, et
elle ne doit pas te parvenir par une conversation. Pour la même raison, la clé n'est ni dans le dépôt ni envoyée
par Claude. La tienne est créée chez toi, donc elle n'a jamais existé ailleurs.

## À quoi sert une clé de signature

Android exige que chaque APK soit **signé**. La signature dit au téléphone qui a construit l'appli.

Quand une mise à jour arrive, Android compare sa signature à celle de l'appli installée :

- **même clé** : la mise à jour s'installe par-dessus, et tout est conservé (canards connus, codes, réglages) ;
- **clé différente** : Android refuse (« Application non installée »). Il faut alors désinstaller l'appli, ce qui
  efface ses données, puis installer la nouvelle.

La clé doit donc rester **la même pour toute la vie de l'appli**. Si tu la perds, rien ne casse sur le canard, mais
chaque téléphone devra désinstaller l'appli une fois.

## Règles

1. **Jamais dans un dépôt Git**, même privé, et jamais envoyée par message ou par e-mail. Quelqu'un qui a la clé et
   son mot de passe peut publier une fausse « mise à jour » que ton téléphone accepterait.
2. **Fais une deuxième copie** du dossier de sauvegarde **hors du PC** : une clé USB rangée, ou ton gestionnaire de
   mots de passe (le fichier en pièce jointe, plus le mot de passe).
3. **PC neuf** : recopie `microduck.keystore` et `mot-de-passe.txt` dans `~/.microduck-android/` (WSL), en renommant
   le second en `mot-de-passe`. Ce n'est utile que pour construire l'APK sur le PC ; GitHub a déjà sa copie.

## Publier une nouvelle version (c'est Claude qui le fait d'habitude)

Monter `android:versionCode` (+1) et `android:versionName` dans `android/AndroidManifest.xml`, puis pousser.
Le workflow `.github/workflows/apk.yml` crée la release `apk-v<version>` : onglet **Actions** pour suivre la
construction, onglet **Releases** pour le résultat. Sans clé sur GitHub, il ne publie rien et l'indique en
avertissement.

Pour vérifier qu'un APK vient bien de toi :
`apksigner verify --print-certs microduck.apk`. L'empreinte doit être celle du `LISEZ-MOI.txt`.

## Faire la partie GitHub à la main (si le script n'y arrive pas)

1. Dans WSL :
   ```
   base64 -w0 ~/.microduck-android/microduck.keystore > ~/cle.txt
   ```
2. Sur GitHub, ouvre `RaphaelGrj/microduck-brain`, puis **Settings → Secrets and variables → Actions → New
   repository secret**, et crée deux secrets :
   - `MICRODUCK_KEYSTORE_B64` : le contenu de `~/cle.txt`, sur une seule ligne ;
   - `MICRODUCK_KEYSTORE_MOT_DE_PASSE` : le contenu de `~/.microduck-android/mot-de-passe`.
3. Supprime le fichier temporaire : `rm ~/cle.txt`.

## Construire l'APK sur le PC (facultatif)

Installe les outils une fois :
```
sudo apt install aapt apksigner dalvik-exchange zipalign android-sdk-platform-23 openjdk-17-jdk-headless
```
Puis lance `bash android/construire.sh`. L'APK est écrit dans `android/sortie/microduck.apk`.

## Si la clé est perdue

1. Supprime `~/.microduck-android/`.
2. Relance `bash android/creer_cle.sh` : il crée une nouvelle clé et remplace les secrets GitHub.
3. Sur chaque téléphone, désinstalle l'appli puis réinstalle-la, une seule fois.

Les données du canard ne sont pas touchées : elles vivent sur le canard, pas dans l'appli.
