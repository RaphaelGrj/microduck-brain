#!/bin/bash
# Canard jumeau (Quest, mode Jumeau) en une commande : duck-sim + cerveau avec son appli, en boucle.
#   bash ~/jumeau.sh [scene] [--avec-ha] [options de canard.py]
# scene : maison (TA maison, plan du lieu actuel - par defaut), testball (appartement), apartment, arena, arena_chat.
# Depuis l'appli (Reglages -> Casque), « Changer de scene » : le cerveau sort, la boucle relance duck-sim sur la
# nouvelle scene, puis le cerveau. Ctrl+C pour tout arreter.
# Sans --avec-ha, le cerveau tourne SANS Home Assistant : un canard simule ne doit pas allumer tes vraies lampes.
F="$HOME/.cache/duck-sim/scene_voulue"
mkdir -p "$(dirname "$F")"
case "$1" in maison|testball|apartment|arena|arena_chat) echo "$1" > "$F"; shift ;; esac
[ -s "$F" ] || echo maison > "$F"
HA="--sans-ha"
OPTS=()
for a in "$@"; do
  if [ "$a" = "--avec-ha" ]; then HA=""; else OPTS+=("$a"); fi
done
trap 'echo; echo "jumeau arrete"; exit 0' INT TERM
while true; do
  scene=$(tr -d '[:space:]' < "$F")
  echo "== scene : $scene"
  if ! bash "$HOME/run-scene.sh" "$scene"; then
    echo "== scene $scene impossible (pas de plan importe ?) : appartement a la place"
    echo testball > "$F"
    bash "$HOME/run-scene.sh" testball || { echo "duck-sim ne demarre pas : voir ~/duck-sim.out"; exit 1; }
  fi
  (cd "$HOME/microduck-brain" && MICRODUCK_JUMEAU=1 uv run python canard.py ha.toml $HA "${OPTS[@]}")
  code=$?
  # sortie propre (code 0) = changement de scene demande depuis l'appli ; sinon, on s'arrete pour lire l'erreur
  [ "$code" -eq 0 ] || { echo "== le cerveau s'est arrete (code $code) : jumeau arrete"; exit "$code"; }
  echo "== relance sur la scene demandee"
  sleep 1
done
