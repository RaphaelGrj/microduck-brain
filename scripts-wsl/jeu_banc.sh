#!/bin/bash
# Jeu complet (arena_chat) avec la passe directe DROITE chargee a la place de kick_right. Usage : jeu_directe.sh [parties]
export PATH="$HOME/.local/bin:$PATH"
N="${1:-8}"
cd $HOME && bash run-scene.sh arena_chat | tail -1
cd $HOME/microduck-brain
[ "$2" = base ] || bash ~/run-brain.sh charge_politique.py kick_right $HOME/.cache/duck-sim/policies/passe/kick_directe_right_1199.onnx 2>&1 | head -1
sleep 3
MICRODUCK_TIR=passe bash ~/run-brain.sh ~/microduck-brain/jeu_eval.py $N 1 > ~/jeu_directe_${2:-dir}.log 2>&1
bash ~/run-brain.sh charge_politique.py kick_right officielle 2>&1 | head -1 >/dev/null
bash ~/stop_sim.sh >/dev/null 2>&1
tail -15 ~/jeu_directe_${2:-dir}.log
