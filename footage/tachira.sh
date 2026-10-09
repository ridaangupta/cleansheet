#!/usr/bin/env bash
# Rebuild footage/tachira_0[1-4].mp4 from the public-domain VTV broadcast on Wikimedia Commons
# (license details in footage/LICENSES.md). Downloads ~2 GB once into media/sources/.
#
# Usage: footage/tachira.sh
set -euo pipefail
cd "$(dirname "$0")/.."

src=media/sources/tachira_rayo.webm
url="https://upload.wikimedia.org/wikipedia/commons/2/2d/FUTVE_Torneo_Clausura_2026_-_Deportivo_T%C3%A1chira_vs._Rayo_Zuliano.webm"
if [[ ! -f "$src" ]]; then
  mkdir -p "$(dirname "$src")"
  # One continuous request; Commons rate-limits bursts (HTTP 429), so don't parallelize.
  curl -fL -A "Cleansheet-hackathon/0.1 (footage pipeline)" -o "$src.part" "$url"
  mv "$src.part" "$src"
fi

# Scorebug (top left) and VTV logo (top right) are fixed for the whole broadcast.
masks=(--mask 0.06,0.04,0.185,0.18 --mask 0.875,0.045,0.09,0.11)
n=1
for start in 2660 4470 7130 8530; do
  .venv/bin/python pipeline/cut_clip.py "$src" "$start" 12 "footage/tachira_0$n.mp4" "${masks[@]}"
  n=$((n + 1))
done
