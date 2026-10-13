#!/usr/bin/env bash
# Rebuild footage/metro_ucv_01.mp4, the held-out evaluation clip (a different match and stadium
# from the tachira training clips), from the public-domain VTV broadcast on Wikimedia Commons
# (license details in footage/LICENSES.md). Downloads ~1.7 GB once into media/sources/.
#
# Usage: footage/metro_ucv.sh
set -euo pipefail
cd "$(dirname "$0")/.."

src=media/sources/metro_ucv.webm
url="https://upload.wikimedia.org/wikipedia/commons/8/86/FUTVE_Torneo_Clausura_2026_-_Metropolitano_Vs._UCV.webm"
if [[ ! -f "$src" ]]; then
  mkdir -p "$(dirname "$src")"
  # One continuous request; Commons rate-limits bursts (HTTP 429), so don't parallelize.
  curl -fL -A "Cleansheet-hackathon/0.1 (footage pipeline)" -o "$src.part" "$url"
  mv "$src.part" "$src"
fi

# Scorebug (top left) and the "EN VIVO" tag + clock (top right).
.venv/bin/python pipeline/cut_clip.py "$src" 2465 12 footage/metro_ucv_01.mp4 \
  --mask 0.05,0.045,0.19,0.165 --mask 0.80,0.04,0.17,0.045
