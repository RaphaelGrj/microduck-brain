#!/usr/bin/env bash
# Cree TA cle de signature de l'APK Microduck, la sauvegarde, et la donne a GitHub. A lancer UNE fois (Linux ou WSL) :
#   bash android/creer_cle.sh [dossier-de-sauvegarde]
#   ex. bash android/creer_cle.sh /mnt/mmc-SN128_0x5c36c07b-part1/microduck/microduck-app
# Sans dossier : Documents de Windows (WSL), sinon le dossier personnel.
# Ensuite GitHub construit et publie l'APK tout seul a chaque nouvelle version (workflow .github/workflows/apk.yml).
# Explications : android/CLE_DE_SIGNATURE.md. Rien de ce que fait ce script n'est envoye ailleurs que sur GitHub
# (secrets chiffres) et dans le dossier de sauvegarde.
set -euo pipefail

DEPOT="${MICRODUCK_DEPOT:-RaphaelGrj/microduck-brain}"
CLES="${MICRODUCK_CLES:-$HOME/.microduck-android}"
KS="$CLES/microduck.keystore"
MDP="$CLES/mot-de-passe"

etape() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }
ok() { printf '\033[1;32m   ok\033[0m %s\n' "$*"; }

# --- 1. La cle -------------------------------------------------------------------------------------------------
etape "1/3  La cle de signature"
mkdir -p "$CLES"; chmod 700 "$CLES"
if [ -f "$KS" ] && [ -f "$MDP" ]; then
  ok "deja creee ($KS) : je la garde (ne JAMAIS la remplacer, sinon il faut desinstaller l'appli)."
else
  command -v openssl >/dev/null || { echo "openssl manquant : sudo apt install -y openssl"; exit 1; }
  ( umask 077
    head -c 24 /dev/urandom | base64 | tr -d '/+=\n' > "$MDP"
    tmp="$(mktemp -d)"
    openssl req -x509 -newkey rsa:2048 -nodes -days 10000 -subj "/CN=Microduck" \
      -keyout "$tmp/cle.pem" -out "$tmp/certificat.pem" 2>/dev/null
    # PKCS12 a l'ancienne (3DES) : lisible par tous les apksigner/keytool, recents ou non
    openssl pkcs12 -export -name microduck -inkey "$tmp/cle.pem" -in "$tmp/certificat.pem" \
      -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES -macalg sha1 -passout "file:$MDP" -out "$KS"
    rm -rf "$tmp" )
  chmod 600 "$KS" "$MDP"
  ok "creee : $KS"
fi
EMPREINTE="$(openssl pkcs12 -in "$KS" -passin "file:$MDP" -nokeys -clcerts 2>/dev/null \
  | openssl x509 -noout -fingerprint -sha256 | cut -d= -f2)"
ok "empreinte : $EMPREINTE"

# --- 2. La sauvegarde (dossier donne, sinon Documents cote Windows, sinon le dossier personnel) --------------------
etape "2/3  Sauvegarde de la cle"
DOCS=""
SAUVE="${1:-${MICRODUCK_SAUVEGARDE:-}}"
if [ -z "$SAUVE" ] && command -v powershell.exe >/dev/null 2>&1; then
  w="$(powershell.exe -NoProfile -Command '[Environment]::GetFolderPath("MyDocuments")' 2>/dev/null | tr -d '\r')"
  [ -n "$w" ] && DOCS="$(wslpath "$w" 2>/dev/null || true)"
fi
if [ -z "$SAUVE" ]; then
  [ -d "$DOCS" ] || DOCS="$HOME"
  SAUVE="$DOCS/Microduck - cle APK (SECRET)"
fi
mkdir -p "$SAUVE"
chmod 700 "$SAUVE" 2>/dev/null || true         # (carte SD en exFAT : pas de droits Unix, sans gravite)
if [ -e "$SAUVE/microduck.keystore" ] && ! cmp -s "$KS" "$SAUVE/microduck.keystore"; then
  echo "   $SAUVE contient deja une AUTRE cle : je n'y touche pas. Choisis un autre dossier."; exit 1
fi
cp "$KS" "$SAUVE/microduck.keystore"
cp "$MDP" "$SAUVE/mot-de-passe.txt"
cat > "$SAUVE/LISEZ-MOI.txt" <<EOF
Cle de signature de l'application Microduck (creee le $(date +%F)).

- microduck.keystore + mot-de-passe.txt = la cle. A garder, a ne JAMAIS publier ni envoyer.
- Fais-en une 2e copie hors du PC (cle USB rangee, ou gestionnaire de mots de passe).
- Empreinte (pas secrete, sert a reconnaitre tes APK) : $EMPREINTE
- PC neuf : copier ces deux fichiers dans ~/.microduck-android/ (WSL), le mot de passe sous le nom "mot-de-passe".
- Explications : android/CLE_DE_SIGNATURE.md dans le depot microduck-brain.
EOF
ok "copiee dans : $SAUVE"

# --- 3. GitHub ---------------------------------------------------------------------------------------------------
etape "3/3  Donner la cle a GitHub (secrets chiffres du depot $DEPOT)"
if ! command -v gh >/dev/null; then
  echo "   L'outil GitHub (gh) n'est pas installe : je l'installe (ton mot de passe sudo est demande)."
  sudo apt-get update -qq && sudo apt-get install -y -qq gh || true
fi
if ! command -v gh >/dev/null; then
  echo "   Impossible d'installer gh. La cle est prete et sauvegardee : il reste a la donner a GitHub a la main,"
  echo "   voir « La mettre dans GitHub » dans android/CLE_DE_SIGNATURE.md."
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "   Connexion a GitHub : choisis GitHub.com, HTTPS, puis « Login with a web browser »,"
  echo "   et colle le code a 8 caracteres qui s'affiche dans la page qui s'ouvre."
  gh auth login --hostname github.com --git-protocol https --web
fi
base64 -w0 "$KS" | gh secret set MICRODUCK_KEYSTORE_B64 --repo "$DEPOT"
gh secret set MICRODUCK_KEYSTORE_MOT_DE_PASSE --repo "$DEPOT" < "$MDP"
ok "secrets MICRODUCK_KEYSTORE_B64 et MICRODUCK_KEYSTORE_MOT_DE_PASSE enregistres sur GitHub"

etape "Termine"
cat <<EOF
   GitHub construira et publiera l'APK tout seul a chaque nouvelle version (onglet « Releases » du depot).
   Une seule fois : sur le telephone, DESINSTALLE l'appli Microduck 1.0 (elle etait signee par une autre cle),
   puis installe la nouvelle depuis :
     https://github.com/$DEPOT/releases/latest/download/microduck.apk
   Les reglages du canard ne sont pas perdus (ils sont sur le canard) ; il faudra juste re-saisir son code.
EOF
