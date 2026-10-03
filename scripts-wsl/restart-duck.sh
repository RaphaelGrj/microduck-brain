#!/bin/bash
# Arrete proprement l'ancien duck-sim (down via shim sudo -n). Le demarrage se fait
# dans un appel separe : bash ~/start-duck.sh (un lancement imbrique ici ne survit pas).
export PATH="$HOME/bin-shim:$PATH"
cd "$HOME/microduck" || exit 1
timeout 60 scripts/duck-sim down > "$HOME/down.out" 2>&1 < /dev/null
sleep 2
: > "$HOME/duck-sim.out"
echo arrete
