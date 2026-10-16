#!/bin/bash
# Evaluation de la passe douce (BallKickPasse) dans duck-sim (scene arena requise : bash ~/run-scene.sh arena).
# Usage : passe_eval.sh <right|left> <iteration|officielle> [repetitions=2] [--garder]
# Exporte le checkpoint en ONNX, le charge dans le slot kick_<pied>, balaie x = 7..15 cm avec les seuils d'une passe
# (vitesse de pointe 0,3 a 0,9 m/s, cap a moins de 35 deg), puis remet l'officielle (sauf --garder).
# Le run est celui qui contient model_<it>.pt (--agent.resume ecrit dans un NOUVEAU dossier : ne pas prendre le dernier a l'aveugle).
pied="$1"; it="$2"; rep="${3:-2}"; garder=""
[ "$4" = "--garder" ] || [ "$3" = "--garder" ] && garder=1
[[ "$rep" =~ ^[0-9]+$ ]] || rep=2
case "$pied" in right) S=Right ;; left) S=Left ;; *) echo "pied ?"; exit 1 ;; esac
export PATH="$HOME/.local/bin:$PATH"
DXS="-0.02,0,0.015,0.03,0.045,0.06"
DYS="-0.025,0,0.025"
if [ "$it" != "officielle" ]; then
  RUN=$(ls -d "$HOME"/microduck_rl/logs/rsl_rl/ball_kick_passe_"$pied"/*/ | while read d; do [ -f "${d}model_${it}.pt" ] && echo "$d"; done | tail -1)
  [ -n "$RUN" ] || { echo "aucun run avec model_${it}.pt"; exit 1; }
  OUT="$HOME/.cache/duck-sim/policies/passe/kick_passe_${pied}_${it}.onnx"
  mkdir -p "$(dirname "$OUT")"
  cd "$HOME/microduck_rl" || exit 1
  uv run python scripts/export.py "Mjlab-BallKickPasse-Flat-Backlash-MicroDuck-$S" \
    --checkpoint-file "${RUN}model_${it}.pt" --onnx-file "$OUT" --num-envs 1 2>&1 | grep -i "written\|error" || exit 1
  cd "$HOME/microduck-brain" || exit 1
  bash "$HOME/run-brain.sh" charge_politique.py "kick_$pied" "$OUT" | head -1
  sleep 2
fi
cd "$HOME/microduck-brain" || exit 1
echo "=== passe $pied : $it ($rep repetitions, 0,3 <= vmax <= 0,9 m/s) ==="
KICK_VMIN=${KICK_VMIN:-0.3} KICK_VMAX=${KICK_VMAX:-0.9} KICK_DXS=$DXS KICK_DYS=$DYS bash "$HOME/run-brain.sh" kick_sweep.py "$pied" "$rep" 2>&1 | grep -v "^$"
if [ "$it" != "officielle" ] && [ -z "$garder" ]; then
  bash "$HOME/run-brain.sh" charge_politique.py "kick_$pied" officielle | head -1
fi
