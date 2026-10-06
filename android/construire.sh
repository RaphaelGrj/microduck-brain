#!/usr/bin/env bash
# Construit l'APK de l'application Microduck sans Android Studio ni Gradle : outils des paquets Ubuntu/Debian.
#   sudo apt install aapt apksigner dalvik-exchange zipalign android-sdk-platform-23 openjdk-17-jdk-headless
#   bash android/construire.sh            -> android/sortie/microduck.apk
# La cle de signature est creee au premier lancement dans ~/.microduck-android/ (HORS du depot : jamais sur GitHub).
# Garder cette cle : une mise a jour de l'appli doit etre signee par la meme, sinon il faut desinstaller d'abord.
set -euo pipefail

ICI="$(cd "$(dirname "$0")" && pwd)"
RACINE="$(dirname "$ICI")"
SDK_JAR="${ANDROID_JAR:-/usr/lib/android-sdk/platforms/android-23/android.jar}"
CLES="${MICRODUCK_CLES:-$HOME/.microduck-android}"
TMP="$ICI/construction"
SORTIE="$ICI/sortie"

for outil in aapt javac dalvik-exchange zipalign apksigner keytool; do
  command -v "$outil" >/dev/null || { echo "outil manquant : $outil (voir l'en-tete du script)"; exit 1; }
done
[ -f "$SDK_JAR" ] || { echo "android.jar introuvable : $SDK_JAR"; exit 1; }

rm -rf "$TMP"; mkdir -p "$TMP"/{gen,classes,res/drawable-nodpi,assets} "$SORTIE"

# 1. Ressources : l'icone et l'interface servie par le canard (pour le mode demo, sans le canard).
cp "$RACINE/interface/icone.png" "$TMP/res/drawable-nodpi/icone.png"
cp -r "$RACINE/interface" "$TMP/assets/interface"

# 2. R.java, puis le paquet de ressources.
aapt package -f -m -J "$TMP/gen" -M "$ICI/AndroidManifest.xml" -S "$TMP/res" -I "$SDK_JAR"
aapt package -f -M "$ICI/AndroidManifest.xml" -S "$TMP/res" -A "$TMP/assets" -I "$SDK_JAR" -F "$TMP/brut.apk"

# 3. Java 8 (dx ne connait pas plus recent), puis le bytecode Android (classes.dex).
javac -nowarn -Xlint:-options -source 8 -target 8 -encoding UTF-8 -bootclasspath "$SDK_JAR" -d "$TMP/classes" \
  $(find "$ICI/src" "$TMP/gen" -name '*.java')
dalvik-exchange --dex --min-sdk-version=23 --output="$TMP/classes.dex" "$TMP/classes"
(cd "$TMP" && zip -q -j brut.apk classes.dex)

# 4. Alignement et signature (cle locale, creee une fois).
mkdir -p "$CLES"; chmod 700 "$CLES"
if [ ! -f "$CLES/microduck.keystore" ]; then
  head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$CLES/mot-de-passe"; chmod 600 "$CLES/mot-de-passe"
  keytool -genkeypair -keystore "$CLES/microduck.keystore" -alias microduck -keyalg RSA -keysize 2048 \
    -validity 10000 -dname "CN=Microduck" -storepass "$(cat "$CLES/mot-de-passe")" -keypass "$(cat "$CLES/mot-de-passe")"
fi
zipalign -f -p 4 "$TMP/brut.apk" "$TMP/aligne.apk"
apksigner sign --ks "$CLES/microduck.keystore" --ks-pass "file:$CLES/mot-de-passe" --ks-key-alias microduck \
  --min-sdk-version 23 --out "$SORTIE/microduck.apk" "$TMP/aligne.apk"
apksigner verify "$SORTIE/microduck.apk"
rm -rf "$TMP"
echo "APK : $SORTIE/microduck.apk ($(du -h "$SORTIE/microduck.apk" | cut -f1))"
