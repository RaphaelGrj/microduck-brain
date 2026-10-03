#!/bin/bash
# Compile gst-plugin-webrtc (webrtcsink) pour x86_64 : Pollen ne publie que de l'aarch64.
# Installe dans ~/.local (pas de sudo). Priorite basse pour ne pas gener l'entrainement.
set -u
export PATH="$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
export CARGO_BUILD_JOBS=8
LOG="$HOME/build-webrtc.log"
exec > "$LOG" 2>&1

echo "== $(date +%H:%M:%S) cargo-c"
if ! cargo cinstall --version >/dev/null 2>&1; then
  nice -n 19 cargo install cargo-c --locked || { echo "ECHEC cargo-c"; exit 1; }
fi

echo "== $(date +%H:%M:%S) clone gst-plugins-rs 0.14.5"
if [ ! -d "$HOME/gst-plugins-rs" ]; then
  git clone --depth 1 --branch 0.14.5 https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs.git "$HOME/gst-plugins-rs" \
    || { echo "ECHEC clone"; exit 1; }
fi

echo "== $(date +%H:%M:%S) build gst-plugin-webrtc"
cd "$HOME/gst-plugins-rs" || exit 1
nice -n 19 cargo cinstall -p gst-plugin-webrtc --prefix="$HOME/.local" --release \
  || { echo "ECHEC build"; exit 1; }

echo "== $(date +%H:%M:%S) fichiers installes"
find "$HOME/.local" -name "libgstrswebrtc*" 2>/dev/null
echo "BUILD_OK"
