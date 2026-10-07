#!/bin/bash
# Redemarre duck-sim sur une scene du fork : bash ~/run-scene.sh [testball|kick_right|kick_left|apartment|arena|arena_chat|maison]
# maison : TA maison (plan du lieu actuel, scan Quest) -> scene_maison.xml, regeneree a chaque lancement (canard jumeau).
nom="${1:-testball}"
export PATH="$HOME/bin-shim:$PATH"
D="$HOME/microduck_rl/src/mjlab_microduck/robot/microduck"
case "$nom" in
  apartment) scene=apartment ;;
  arena) scene="$D/scene_arena_testball.xml" ;;
  arena_chat) scene="$D/scene_arena_cat.xml" ;;      # genere par make_cat_scene.py (affiche de la photo du chat)
  maison)
    (cd "$HOME/microduck-brain" && uv run python plan_vers_mjcf.py) || exit 1
    scene="$D/scene_maison.xml" ;;
  *) scene="$D/scene_apartment_$nom.xml" ;;
esac
[ "$scene" = apartment ] || [ -f "$scene" ] || { echo "scene introuvable: $scene"; exit 1; }
bash "$HOME/restart-duck.sh" > /dev/null 2>&1
DUCK_SIM_SCENE="$scene" bash "$HOME/start-duck.sh" > /dev/null 2>&1 < /dev/null
bash "$HOME/wait-duck.sh"
echo "scene: $nom"
