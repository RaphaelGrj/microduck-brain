#!/bin/bash
# Passe directe : $1 = right|left, ajustement fin depuis la passe actuelle (log ~/directe_$1.log)
export PATH="$HOME/.local/bin:$PATH"
cd ~/microduck_rl
case "$1" in right) S=Right ;; left) S=Left ;; esac
MICRODUCK_WARM_START=1 uv run train Mjlab-BallKickPasseDirecte-Flat-Backlash-MicroDuck-$S --env.scene.num-envs 4096 \
  --agent.logger tensorboard --agent.resume True --agent.load-run init_$1 --agent.max-iterations 1200 > ~/directe_$1.log 2>&1
