#!/usr/bin/env bash
# Mise a jour du cerveau demandee depuis l'application (Sante -> Mises a jour), lancee par systemd AVANT le cerveau
# (ExecStartPre de microduck-cerveau.service). NON TESTE sur le robot.
#   ~/.local/share/microduck/mise_a_jour contient « installer <branche> » ou « revenir ».
# installer : telecharge le cerveau depuis GitHub, verifie qu'il compile, garde la version actuelle dans precedente/,
#             puis remplace les modules et l'interface. revenir : remet precedente/.
# Seul echange avec Internet du canard, et seulement a la demande : le code, jamais aucune donnee.
set -euo pipefail
ICI="${MICRODUCK_ICI:-/opt/microduck-cerveau}"
DONNEES="${MICRODUCK_DONNEES:-${HOME:-$ICI}/.local/share/microduck}"
DEMANDE="$DONNEES/mise_a_jour"
DEPOT="RaphaelGrj/microduck-brain"
[ -f "$DEMANDE" ] || exit 0
read -r ACTION BRANCHE < "$DEMANDE" || true
rm -f "$DEMANDE"
journal() { echo "mise a jour : $*"; echo "$(date -Is) $*" >> "$DONNEES/mises_a_jour.log"; }

if [ "$ACTION" = "revenir" ]; then
  [ -d "$ICI/precedente" ] || { journal "pas de version precedente"; exit 0; }
  cp -a "$ICI/precedente/." "$ICI/"
  journal "retour a la version precedente ($(cat "$ICI/VERSION" 2>/dev/null))"
  exit 0
fi
[ "$ACTION" = "installer" ] || { journal "demande inconnue : $ACTION"; exit 0; }
BRANCHE="${BRANCHE:-main}"
case "$BRANCHE" in *[!A-Za-z0-9._/-]*) journal "branche refusee"; exit 0;; esac

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SHA=$(curl -fsS "https://api.github.com/repos/$DEPOT/commits/$BRANCHE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
curl -fsSL "https://codeload.github.com/$DEPOT/tar.gz/$SHA" | tar -xz -C "$TMP"
NOUVEAU=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)
MODULES=$(cd "$NOUVEAU" && python3 deploy/robot/modules.py)
( cd "$NOUVEAU" && python3 -m py_compile $(echo "$MODULES" | grep '\.py$') ) || { journal "le nouveau cerveau ne compile pas : rien change"; exit 0; }

rm -rf "$ICI/precedente"; mkdir -p "$ICI/precedente"
for m in $(cd "$ICI" && ls *.py 2>/dev/null) interface VERSION mettre_a_jour.sh; do
  [ -e "$ICI/$m" ] && cp -a "$ICI/$m" "$ICI/precedente/"
done
for m in $MODULES; do
  m="${m%/}"
  if [ "$m" = "deploy/robot/mettre_a_jour.sh" ]; then cp -a "$NOUVEAU/$m" "$ICI/mettre_a_jour.sh"; continue; fi
  rm -rf "${ICI:?}/$m"; cp -a "$NOUVEAU/$m" "$ICI/$m"
done
echo "${SHA:0:7} $(date +%F)" > "$ICI/VERSION"
journal "installe ${SHA:0:7} ($BRANCHE)"
