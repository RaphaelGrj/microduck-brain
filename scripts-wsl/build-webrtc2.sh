#!/bin/bash
# Compile gst-plugin-webrtc 0.15.4 (plus proche de GStreamer 1.28) dans un prefix separe,
# pour ne pas ecraser la 0.14.5 qui fonctionne. Priorite basse (l'entrainement tourne).
set -u
export PATH="$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
export CARGO_BUILD_JOBS=8
exec > "$HOME/build-webrtc2.log" 2>&1

echo "== $(date +%H:%M:%S) clone 0.15.4"
if [ ! -d "$HOME/gst-plugins-rs-015" ]; then
  git clone --depth 1 --branch 0.15.4 https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs.git "$HOME/gst-plugins-rs-015" \
    || { echo "ECHEC clone"; exit 1; }
fi
cd "$HOME/gst-plugins-rs-015" || exit 1
echo "== $(date +%H:%M:%S) build"
nice -n 19 cargo cinstall -p gst-plugin-webrtc --prefix="$HOME/.local-015" --release \
  || { echo "ECHEC build"; exit 1; }
find "$HOME/.local-015" -name "libgstrswebrtc.so"
echo "BUILD_OK"
