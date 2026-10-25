#!/bin/bash
# Pilote Sprint : attend la fin du banc de jeu (duck-sim), puis 2048 envs, 400 iterations (~15 min).
# Sentinelles : sprint_speed (doit monter), sprint_rest_still (doit monter), sprint_tilt_penalty.
while pgrep -f "[j]eu_banc.sh" > /dev/null; do sleep 20; done
export PATH="$HOME/.local/bin:/usr/bin:/bin"
cd ~/microduck_rl || exit 1
uv run train Mjlab-Sprint-Flat-Backlash-MicroDuck --env.scene.num-envs 2048 --agent.logger tensorboard \
  --agent.max-iterations 400 > ~/sprint_pilote.log 2>&1
