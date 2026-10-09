"""Find long, uncut wide-camera stretches in a full match broadcast, to pick demo/training clips.

Decodes the video small (--fps samples per second), detects cuts from colour-histogram jumps,
and keeps cut-free stretches whose lower frame is mostly pitch green (the main wide camera;
close-ups, crowd shots and studio segments fail it). Writes a JSON list of segments and a
contact sheet with one thumbnail per segment, for a human to pick from.

Usage: python pipeline/find_shots.py <broadcast.webm> [--min-seconds 10] [--out media/shots/<stem>]
Then cut picks with: ffmpeg -ss <start> -i <broadcast> -t <dur> ... (see cut_clip.py)
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

W, H = 192, 108


def frames(path: Path, fps: float):
    proc = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-i", str(path), "-vf", f"fps={fps},scale={W}:{H}",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE,
    )
    size = W * H * 3
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    proc.wait()


def green_fraction(hsv: np.ndarray) -> float:
    """Share of pitch-green pixels in the lower 60% of the frame."""
    lower = hsv[int(H * 0.4):]
    mask = (lower[..., 0] >= 30) & (lower[..., 0] <= 90) & (lower[..., 1] >= 50) & (lower[..., 2] >= 40)
    return float(mask.mean())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--min-seconds", type=float, default=10.0)
    ap.add_argument("--min-green", type=float, default=0.6)
    ap.add_argument("--cut-threshold", type=float, default=0.35, help="Bhattacharyya distance between samples")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    out = args.out or Path("media/shots") / args.video.stem
    out.mkdir(parents=True, exist_ok=True)

    segments, thumbs = [], []
    seg_start, seg_frames, prev_hist = None, [], None

    def close(end_t: float) -> None:
        if seg_start is None or not seg_frames:
            return
        dur = end_t - seg_start
        greens = [g for g, _ in seg_frames]
        if dur >= args.min_seconds and np.median(greens) >= args.min_green:
            segments.append({"start": round(seg_start, 2), "end": round(end_t, 2), "seconds": round(dur, 1),
                             "green": round(float(np.median(greens)), 2)})
            thumbs.append(seg_frames[len(seg_frames) // 2][1])

    for i, frame in enumerate(frames(args.video, args.fps)):
        t = i / args.fps
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        cut = prev_hist is not None and cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA) > args.cut_threshold
        prev_hist = hist
        g = green_fraction(hsv)
        if cut or g < args.min_green * 0.75:
            close(t)
            seg_start, seg_frames = (t, [(g, frame)]) if g >= args.min_green * 0.75 else (None, [])
        else:
            if seg_start is None:
                seg_start = t
            seg_frames.append((g, frame))
        if i % int(args.fps * 600) == 0:
            print(f"  {t / 60:.0f} min, {len(segments)} segments", flush=True)
    close((i + 1) / args.fps)

    (out / "segments.json").write_text(json.dumps({"video": str(args.video), "segments": segments}, indent=1))
    if thumbs:
        cols = 6
        tiles = []
        for k, (seg, th) in enumerate(zip(segments, thumbs)):
            th = th.copy()
            label = f"{k}: {int(seg['start'] // 60)}:{int(seg['start'] % 60):02d} {seg['seconds']:.0f}s"
            cv2.putText(th, label, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(th, label, (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)
            tiles.append(th)
        tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % cols)
        rows = [np.hstack(tiles[r:r + cols]) for r in range(0, len(tiles), cols)]
        cv2.imwrite(str(out / "contact.jpg"), np.vstack(rows))
    total = sum(s["seconds"] for s in segments)
    print(f"{len(segments)} segments, {total / 60:.1f} min total -> {out}/segments.json, contact.jpg")


if __name__ == "__main__":
    main()
