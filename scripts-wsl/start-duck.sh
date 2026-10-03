#!/bin/bash
# Lance duck-sim sans fenetre MuJoCo (DUCK_SIM_VIEWER=0 -> --headless dans le corps),
# avec la camera (DUCK_SIM_CAMERAS=a). Sortie dans ~/duck-sim.out ; stdin/stdout detaches
# pour ne pas bloquer l'appelant.
# - bin-shim/sudo = sudo -n : evite que `duck-sim down` reste bloque sur un mot de passe.
# - GST_PLUGIN_PATH : webrtcsink compile a la main (Pollen ne publie que de l'aarch64).
export PATH="$HOME/bin-shim:$PATH"
# 0.15.4 (prefix ~/.local-015) ; l'ancienne 0.14.5 reste dans ~/.local en secours.
export GST_PLUGIN_PATH="${GST_RS_DIR:-$HOME/.local-015/lib/x86_64-linux-gnu/gstreamer-1.0}"
# webrtcsink choisit l'encodeur H.264 par rang ; nvh264enc (NVENC, rang 257) l'emporte sur
# x264enc mais son flux echoue (sps/pps, not-negotiated). Pollen ne corrige que macOS :
# on le declasse ici pour retomber sur x264enc (logiciel, suffisant en 640x360).
export GST_PLUGIN_FEATURE_RANK="nvh264enc:0,nvautogpuh264enc:0"
source "$HOME/.cargo/env"
cd "$HOME/microduck" || exit 1
DUCK_SIM_VIEWER=0 DUCK_SIM_CAMERAS="${DUCK_SIM_CAMERAS-a}" DUCK_SIM_RL="$HOME/microduck_rl" DUCK_SIM_SCENE=apartment \
  setsid scripts/duck-sim > "$HOME/duck-sim.out" 2>&1 < /dev/null &
