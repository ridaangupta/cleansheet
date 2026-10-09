#!/usr/bin/env bash
# Screenshot the Vega Virtual Device window (the Vega screenshot tool only works on hardware).
# Captures just that window, never the rest of the screen. The window must be on screen:
# minimized or other-Space windows return a stale image.
#
# Usage: scripts/vvd_screenshot.sh out.png
set -euo pipefail

out="${1:?usage: vvd_screenshot.sh out.png}"
cache="${TMPDIR:-/tmp}/cleansheet-vvd-window"

if [[ ! -x "$cache" ]]; then
  cat > "$cache.swift" <<'EOF'
import CoreGraphics
let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as! [[String: Any]]
// The device window is the largest one the vega-virtual-device process owns.
let best = list
  .filter { ($0[kCGWindowOwnerName as String] as? String) == "vega-virtual-device" }
  .max { a, b in
    let ba = a[kCGWindowBounds as String] as! [String: Double], bb = b[kCGWindowBounds as String] as! [String: Double]
    return ba["Width"]! * ba["Height"]! < bb["Width"]! * bb["Height"]!
  }
if let w = best { print(w[kCGWindowNumber as String]!) }
EOF
  swiftc -O "$cache.swift" -o "$cache"
fi

wid="$("$cache")"
if [[ -z "$wid" ]]; then
  echo "Vega Virtual Device window not found on screen (start it, and un-minimize it)" >&2
  exit 1
fi
screencapture -x -o -l "$wid" "$out"
echo "$out"
