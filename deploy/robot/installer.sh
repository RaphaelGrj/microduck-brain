#!/usr/bin/env bash
# Installe le cerveau du Microduck SUR le robot, en une commande. NON TESTE sur un vrai robot (robot pas livre).
# A lancer en SSH sur le robot, depuis le dossier du depot clone :   sudo bash deploy/robot/installer.sh [--avec-micro]
# Sans danger a relancer (mise a jour des fichiers, ha.toml et la memoire du canard ne sont jamais ecrases).
# MICRODUCK_ESSAI=1 : ne fait que copier les fichiers (ICI=dossier de test), sans apt / utilisateur / systemd.
set -euo pipefail
ICI="${ICI:-/opt/microduck-cerveau}"
UTIL="microduck-cerveau"
DEPOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MICRO=""; [ "${1:-}" = "--avec-micro" ] && MICRO="--micro"
ESSAI="${MICRODUCK_ESSAI:-}"
etape() { echo; echo "==> $*"; }

[ -n "$ESSAI" ] || [ "$(id -u)" = 0 ] || { echo "Lance-moi avec sudo :  sudo bash deploy/robot/installer.sh"; exit 1; }
[ -f "$DEPOT/canard.py" ] || { echo "Dossier du depot introuvable ($DEPOT) : clone d'abord microduck-brain."; exit 1; }

if [ -z "$ESSAI" ]; then
  etape "1/6 Verifications (le robot doit deja faire tourner robotd)"
  [ -S /run/robotd.sock ] || { echo "ERREUR : /run/robotd.sock absent. Le logiciel officiel du Microduck tourne-t-il ? (systemctl status robotd)"; exit 1; }
  [ -S /run/tofd/tof.sock ] || echo "ATTENTION : /run/tofd/tof.sock absent : sans capteur de distance, le canard ne marchera pas seul (securite)."
  etape "2/6 Paquets systeme"
  apt-get install -y python3-venv curl
  etape "3/6 Utilisateur dedie ($UTIL)"
  id "$UTIL" >/dev/null 2>&1 || useradd -r -m -d "$ICI" -s /usr/sbin/nologin "$UTIL"
  # acces aux sockets de robotd / tofd : on ajoute l'utilisateur au groupe proprietaire de chaque socket
  for s in /run/robotd.sock /run/tofd/tof.sock; do
    [ -S "$s" ] && usermod -aG "$(stat -c %G "$s")" "$UTIL" || true
  done
  usermod -aG audio "$UTIL"
fi

etape "4/6 Copie du cerveau dans $ICI"
mkdir -p "$ICI"
for m in $(cd "$DEPOT" && python3 deploy/robot/modules.py); do
  m="${m%/}"
  if [ "$m" = "deploy/robot/mettre_a_jour.sh" ]; then install -m 755 "$DEPOT/$m" "$ICI/mettre_a_jour.sh"; continue; fi
  rm -rf "${ICI:?}/$m"; cp -a "$DEPOT/$m" "$ICI/$m"
done
echo "installation locale $(date +%F)" > "$ICI/VERSION"
[ -f "$ICI/ha.toml" ] || echo "(pas de ha.toml : facultatif, l'appli du telephone propose une installation guidee)"
[ -n "$ESSAI" ] && { echo "essai termine : fichiers copies dans $ICI"; exit 0; }
chown -R "$UTIL":"$UTIL" "$ICI"

etape "5/6 Environnement Python (quelques minutes)"
[ -d "$ICI/venv" ] || sudo -u "$UTIL" python3 -m venv "$ICI/venv"
sudo -u "$UTIL" "$ICI/venv/bin/pip" install --quiet -r "$DEPOT/deploy/robot/requirements-robot.txt"

etape "6/6 Service systemd"
sed "s| --micro||" "$DEPOT/deploy/robot/microduck-cerveau.service" > /etc/systemd/system/microduck-cerveau.service
if [ -n "$MICRO" ]; then
  sed -i "s|canard.py ha.toml|canard.py ha.toml --micro|" /etc/systemd/system/microduck-cerveau.service
  echo "Micro partage : il faut aussi les patchs de robotd et deploy/robot/asound.conf (voir deploy/robot/README.md)."
fi
systemctl daemon-reload
systemctl enable --now microduck-cerveau
sleep 3
systemctl --no-pager --lines=15 status microduck-cerveau || true
echo
echo "Fini. Suivre les messages :   journalctl -u microduck-cerveau -f"
echo "Appli du telephone :           http://<ip-du-canard>:8090  (premier demarrage : installation guidee)"
echo "Arreter le cerveau :           sudo systemctl stop microduck-cerveau   (le robot reste commandable par l'officiel)"
