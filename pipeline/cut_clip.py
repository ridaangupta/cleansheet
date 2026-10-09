"""Cut a segment from a broadcast into a pipeline-ready clip in footage/.

Scales to 1280x720 at a constant 30 fps (what the rest of the pipeline assumes), drops audio
(commentary can name real sponsors), and pixelates fixed screen regions such as the scorebug
and broadcaster/bank watermarks so no real brand survives outside the boards. Boards are
handled later by annotate.py + composite.py.

Usage:
  python pipeline/cut_clip.py <broadcast> <start s> <seconds> footage/<name>.mp4 \
      --mask 0.02,0.03,0.17,0.12 --mask 0.88,0.02,0.10,0.12
  Masks are x,y,w,h as fractions of the frame. Then log the clip in footage/LICENSES.md.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

OUT_W, OUT_H, OUT_FPS = 1280, 720, 30
BLOCK = 24  # pixelation block size in output pixels


def mask_filter(masks: list[tuple[float, float, float, float]]) -> str:
    """ffmpeg filtergraph: scale, then pixelate each mask rectangle in place."""
    chains = [f"[0:v]fps={OUT_FPS},scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1,split={len(masks) + 1}[base]" +
              "".join(f"[m{k}]" for k in range(len(masks)))]
    prev = "base"
    for k, (x, y, w, h) in enumerate(masks):
        px, py = int(x * OUT_W), int(y * OUT_H)
        pw, ph = max(BLOCK, int(w * OUT_W)), max(BLOCK, int(h * OUT_H))
        chains.append(f"[m{k}]crop={pw}:{ph}:{px}:{py},scale={max(1, pw // BLOCK)}:{max(1, ph // BLOCK)},"
                      f"scale={pw}:{ph}:flags=neighbor[p{k}]")
        chains.append(f"[{prev}][p{k}]overlay={px}:{py}[o{k}]")
        prev = f"o{k}"
    return ";".join(chains), prev


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("start", type=float)
    ap.add_argument("seconds", type=float)
    ap.add_argument("out", type=Path)
    ap.add_argument("--mask", action="append", default=[], help="x,y,w,h as fractions of the frame")
    args = ap.parse_args()

    masks = [tuple(float(v) for v in m.split(",")) for m in args.mask]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(args.start), "-i", str(args.video),
           "-t", str(args.seconds), "-an"]
    if masks:
        graph, last = mask_filter(masks)
        cmd += ["-filter_complex", graph, "-map", f"[{last}]"]
    else:
        cmd += ["-vf", f"fps={OUT_FPS},scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", str(args.out)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)
    print(f"wrote {args.out} ({args.seconds:g} s from {args.start:g} s, {len(masks)} masked regions)")


if __name__ == "__main__":
    main()
