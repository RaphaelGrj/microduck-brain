#!/bin/bash
# Lance un script du cerveau dans son environnement uv : bash ~/run-brain.sh <script.py> [args...]
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/microduck-brain" || exit 1
exec uv run python -u "$@"
