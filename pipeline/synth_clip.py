"""Generate a synthetic broadcast-style clip with blank perimeter boards and exact board geometry.

The camera pans, zooms and changes keystone over a painted stadium, so board quads move and
skew like a real broadcast. Use it to exercise the compositor, tracker and player sync before
real CC0 footage is ready.

Outputs footage/<name>.mp4 and footage/<name>.boards.json (dense "frames" = ground truth,
plus sparse "keyframes" to test the tracker against).

Usage: python pipeline/synth_clip.py [--name synth] [--seconds 12] [--fps 30]
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

import boards as boards_io
from videoio import VideoWriter

ROOT = Path(__file__).resolve().parent.parent
OUT_W, OUT_H = 1280, 720
PANO_W, PANO_H = 4000, 1400
BOARD_TOP, BOARD_H = 520, 80
BOARD_W, BOARD_GAP, BOARD_X0 = 340, 24, 80


def board_rects() -> list[np.ndarray]:
    rects = []
    x = BOARD_X0
    while x + BOARD_W <= PANO_W - BOARD_X0:
        rects.append(np.float32([[x, BOARD_TOP], [x + BOARD_W, BOARD_TOP], [x + BOARD_W, BOARD_TOP + BOARD_H], [x, BOARD_TOP + BOARD_H]]))
        x += BOARD_W + BOARD_GAP
    return rects


def paint_stadium(rng: np.random.Generator) -> np.ndarray:
    pano = np.zeros((PANO_H, PANO_W, 3), np.uint8)

    # Stands: a crowd of small coloured blocks, darker higher up, with tier lines.
    crowd = rng.integers(40, 230, size=(BOARD_TOP // 6, PANO_W // 6, 3), dtype=np.uint8)
    crowd = cv2.resize(crowd, (PANO_W, BOARD_TOP), interpolation=cv2.INTER_NEAREST)
    shade = np.linspace(0.45, 0.9, BOARD_TOP, dtype=np.float32)[:, None, None]
    pano[:BOARD_TOP] = (crowd * shade).astype(np.uint8)
    for y in range(60, BOARD_TOP, 90):
        cv2.line(pano, (0, y), (PANO_W, y), (60, 60, 60), 4)

    # Pitch with mowing stripes and markings.
    pitch_top = BOARD_TOP + BOARD_H
    for k, x in enumerate(range(0, PANO_W, 160)):
        color = (60, 140, 50) if k % 2 == 0 else (70, 160, 60)
        cv2.rectangle(pano, (x, pitch_top), (x + 160, PANO_H), color, -1)
    noise = rng.normal(0, 6, size=(PANO_H - pitch_top, PANO_W, 1)).astype(np.int16)
    pano[pitch_top:] = np.clip(pano[pitch_top:].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    white = (235, 235, 235)
    cv2.line(pano, (0, pitch_top + 30), (PANO_W, pitch_top + 30), white, 6)
    cv2.line(pano, (PANO_W // 2, pitch_top + 30), (PANO_W // 2, PANO_H), white, 6)
    cv2.ellipse(pano, (PANO_W // 2, 1150), (330, 200), 0, 0, 360, white, 6)
    cv2.rectangle(pano, (-10, 900), (500, PANO_H + 10), white, 6)
    cv2.rectangle(pano, (PANO_W - 500, 900), (PANO_W + 10, PANO_H + 10), white, 6)

    # Blank boards: light panel, dark frame, a little vertical shading.
    for r in board_rects():
        (x0, y0), (x1, y1) = r[0].astype(int), r[2].astype(int)
        grad = np.linspace(225, 190, y1 - y0, dtype=np.float32)[:, None, None]
        pano[y0:y1, x0:x1] = np.repeat(grad, x1 - x0, axis=1).astype(np.uint8)
        cv2.rectangle(pano, (x0, y0), (x1 - 1, y1 - 1), (35, 35, 35), 3)
    return pano


def camera(t: float, duration: float) -> np.ndarray:
    """Source quad in panorama coordinates (TL, TR, BR, BL) seen by the camera at time t."""
    u = t / duration
    ease = 0.5 - 0.5 * math.cos(math.pi * u)
    cx = 750 + ease * (PANO_W - 1500) + 12 * math.sin(7.3 * t) + 6 * math.sin(13.1 * t)
    vw = 1500 + 260 * math.sin(2 * math.pi * u * 1.5)
    vh = vw * OUT_H / OUT_W
    cy = 700 + 8 * math.sin(5.7 * t)
    top_spread = 1.18  # farther rows look smaller, so the top of the view covers more width
    skew = 0.07 * vw * math.sin(2 * math.pi * u)
    top, bottom = cy - vh * 0.42, cy + vh * 0.58
    return np.float32([
        [cx - vw / 2 * top_spread + skew, top],
        [cx + vw / 2 * top_spread + skew, top],
        [cx + vw / 2, bottom],
        [cx - vw / 2, bottom],
    ])


def visible(quad: np.ndarray) -> bool:
    x0, y0 = quad.min(axis=0)
    x1, y1 = quad.max(axis=0)
    return x1 > 0 and y1 > 0 and x0 < OUT_W and y0 < OUT_H


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="synth")
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--keyframe-every", type=int, default=45, help="spacing of sparse keyframes written for tracker tests")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    pano = paint_stadium(rng)
    rects = board_rects()
    n = int(round(args.seconds * args.fps))
    dst = np.float32([[0, 0], [OUT_W, 0], [OUT_W, OUT_H], [0, OUT_H]])

    # Players jog around the pitch (below the boards, so no occlusion to handle yet).
    players = [
        dict(x=float(rng.uniform(300, PANO_W - 300)), y=float(rng.uniform(800, 1300)),
             vx=float(rng.uniform(-90, 90)), vy=float(rng.uniform(-30, 30)),
             color=(40, 40, 220) if k % 2 else (230, 230, 230))
        for k in range(22)
    ]

    out_dir = ROOT / "footage"
    video_path = out_dir / f"{args.name}.mp4"
    tracks: list[dict[int, np.ndarray]] = [{} for _ in rects]
    with VideoWriter(video_path, OUT_W, OUT_H, args.fps) as writer:
        for i in range(n):
            t = i / args.fps
            scene = pano.copy()
            for p in players:
                p["x"] += p["vx"] / args.fps
                p["y"] = float(np.clip(p["y"] + p["vy"] / args.fps, 760, PANO_H - 40))
                cx, cy = int(p["x"]), int(p["y"])
                cv2.ellipse(scene, (cx, cy + 22), (16, 6), 0, 0, 360, (30, 80, 30), -1)
                cv2.rectangle(scene, (cx - 9, cy - 30), (cx + 9, cy + 20), p["color"], -1)
                cv2.circle(scene, (cx, cy - 40), 9, (90, 120, 170), -1)
            H = cv2.getPerspectiveTransform(camera(t, args.seconds), dst)
            frame = cv2.warpPerspective(scene, H, (OUT_W, OUT_H), flags=cv2.INTER_LINEAR)
            writer.write(frame)
            for b, r in enumerate(rects):
                q = cv2.perspectiveTransform(r.reshape(-1, 1, 2), H).reshape(4, 2)
                if visible(q):
                    tracks[b][i] = q

    boards = []
    for b, quads in enumerate(tracks):
        if not quads:
            continue
        idx = sorted(quads)
        kf_idx = sorted(set(idx[:: args.keyframe_every]) | {idx[-1]})
        boards.append({
            "id": f"b{b + 1:02d}",
            "kind": "board",
            "keyframes": boards_io._dump({i: quads[i] for i in kf_idx}),
            "frames": boards_io._dump(quads),
        })
    boards_io.save(out_dir / f"{args.name}.boards.json", {
        "video": video_path.name, "width": OUT_W, "height": OUT_H, "fps": args.fps, "frame_count": n,
        "synthetic": True, "boards": boards,
    })
    print(f"wrote {video_path} ({n} frames) and {len(boards)} boards")


if __name__ == "__main__":
    main()
