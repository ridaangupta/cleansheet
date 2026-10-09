"""Burn the frame number into a copy of a video, for measuring overlay sync on devices without
requestVideoFrameCallback (the Vega Virtual Device).

The app's sync HUD prints the frame it is drawing overlays for; a screenshot then shows both
numbers, and their difference is the sync error in frames. Never use the output for training.

Usage: python pipeline/burn_frames.py media/synth/composited.mp4 [out.mp4]
  out defaults to <input dir>/frames_burned.mp4; package it with
  pipeline/package_hls.sh <out> media/<clip>/hls_tc
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

from videoio import VideoWriter, probe, read_frames


def main() -> None:
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.parent / "frames_burned.mp4"
    width, height, fps, _ = probe(src)
    scale = height / 360
    with VideoWriter(out, width, height, fps) as writer:
        for i, frame in enumerate(read_frames(src)):
            text = f"F{i:04d}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, max(1, int(2 * scale)))
            # Top-right, on a black plate so it reads at small window sizes.
            x0, y0 = width - tw - int(16 * scale), int(10 * scale)
            pad = int(6 * scale)
            cv2.rectangle(frame, (x0 - pad, y0 - pad), (x0 + tw + pad, y0 + th + pad), (0, 0, 0), -1)
            cv2.putText(frame, text, (x0, y0 + th), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255),
                        max(1, int(2 * scale)), cv2.LINE_AA)
            writer.write(frame)
    print(f"wrote {out} ({i + 1} frames at {fps:g} fps)")


if __name__ == "__main__":
    main()
