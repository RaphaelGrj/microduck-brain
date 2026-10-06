#!/bin/bash
# Validation groupee en UNE commande (WSL, duck-sim installe) : tests, cout du cerveau, puis les scenarios de
# valider_sim.py dans duck-sim, scene par scene. Tout part dans un rapport date : ~/validation-AAAA-MM-JJ_HHMM.txt
#
#   setsid bash ~/microduck-brain/scripts-wsl/valider-tout.sh > /dev/null 2>&1 < /dev/null &   # en fond (~45 min)
#   bash ~/microduck-brain/scripts-wsl/valider-tout.sh bec_index autotest                       # quelques scenarios
#
# Prerequis : ~/run-scene.sh, ~/start-duck.sh, ~/restart-duck.sh, ~/wait-duck.sh (copies de ce dossier) et la branche
# a valider deja recuperee dans ~/microduck-brain (git pull : ce script ne touche pas a git).
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
set -o pipefail
cd "$HOME/microduck-brain" || exit 1
RAPPORT="$HOME/validation-$(date +%Y-%m-%d_%H%M).txt"
exec > >(tee "$RAPPORT") 2>&1

echo "=== Validation groupee du cerveau - $(date)"
echo "commit : $(git log --oneline -1 2>/dev/null)"
for s in run-scene.sh start-duck.sh restart-duck.sh wait-duck.sh; do
  [ -f "$HOME/$s" ] || { echo "MANQUE ~/$s : cp ~/microduck-brain/scripts-wsl/$s ~/"; exit 1; }
done

echo; echo "=== 1. Tests (sans simulateur)"
if ! uv run --with pytest pytest -q $(ls test_*.py | grep -v test_chat_affiche) 2>&1 | tail -3; then
  echo "ECHEC des tests : on s'arrete la"; exit 1
fi

echo; echo "=== 2. Cout du cerveau (budget 20 ms par trame)"
uv run python bench_cerveau.py --duree 300

echo; echo "=== 3. Scenarios dans duck-sim (la scene change toute seule)"
uv run python -u valider_sim.py --scenes-auto "$@"
code=$?

echo; echo "=== Fin - $(date)"
echo "detail par scenario : ~/.cache/duck-sim/validation.json ; ce rapport : $RAPPORT"
echo "A envoyer a Claude : ce rapport (il ne contient ni jeton, ni image, ni son)."
exit $code
