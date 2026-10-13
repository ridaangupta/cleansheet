"""Per-board obscuring textures for the app: one small PNG per sidecar board id.

Vega can't blur the video under an overlay, so the cloud blurs instead. Boards are flat and the
sidecar has their corners every frame, so each board is straightened out of the stream video
(the composited clip the viewer sees) on a few frames where it is most visible, the frames are
median-combined (drops players crossing in front), and the result is written as:

  textures/blur/<id>.png     heavily blurred: the app warps it onto the board with matrix4
  textures/mosaic/<id>.png   averaged into a coarse grid, upscaled with hard edges (pixelation look)
  textures/index.json        {id: {"w", "h", "frames"}} for the app and the sidecar v2 tracks table

Textures are static per board. LED boards that change content mid-clip would need one texture
per segment (not needed for the current composites, whose LED rows carry static art).

Usage: python pipeline/board_textures.py media/<clip> [--frames 5] [--height 48] [--sidecar sidecar.model.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from videoio import read_frames

MOSAIC = (12, 3)  # cells across, cells down


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip_dir", type=Path)
    ap.add_argument("--frames", type=int, default=5, help="frames combined per board")
    ap.add_argument("--height", type=int, default=48, help="texture height in px; width follows the board's aspect")
    ap.add_argument("--sidecar", default="sidecar.json",
                    help="track in clip_dir; sidecar.model.json (detect.py) writes to textures.model/")
    args = ap.parse_args()

    sidecar = json.loads((args.clip_dir / args.sidecar).read_text())
    out_dir = args.clip_dir / ("textures.model" if args.sidecar == "sidecar.model.json" else "textures")
    W, H = sidecar["width"], sidecar["height"]
    fps = sidecar["fps"]

    # For each board: (score, frame index, pixel quad) on every sidecar frame. Score = on-screen area,
    # with fully visible appearances always ranked first; boards never fully on screen (row ends at
    # the frame edge) fall back to their most visible frames, the off-screen part edge-replicated.
    seen: dict[str, list[tuple[float, int, np.ndarray]]] = {}
    for f in sidecar["frames"]:
        i = round(f["t"] * fps)
        for o in f["objects"]:
            q = (np.asarray(o["quad"], np.float32) * [W, H]).astype(np.float32)
            area = cv2.contourArea(q)
            if area < 1:
                continue
            clipped = np.clip(q, [0, 0], [W - 1, H - 1]).astype(np.float32)
            visible = cv2.contourArea(clipped) / area
            full = visible > 0.999
            seen.setdefault(o["id"], []).append(((1e9 if full else 0) + area * visible, i, q))

    # Pick frames spread over the board's best (largest) appearances.
    picks: dict[int, list[tuple[str, np.ndarray]]] = {}
    for bid, views in seen.items():
        views.sort(key=lambda v: -v[0])
        best = views[: max(args.frames * 4, args.frames)]
        best.sort(key=lambda v: v[1])
        for _, i, q in [best[k] for k in np.linspace(0, len(best) - 1, min(args.frames, len(best))).astype(int)]:
            picks.setdefault(i, []).append((bid, q))

    sizes: dict[str, tuple[int, int]] = {}
    stacks: dict[str, list[np.ndarray]] = {}
    for i, frame in enumerate(read_frames(args.clip_dir / "composited.mp4")):
        for bid, q in picks.get(i, []):
            if bid not in sizes:
                aspect = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / (
                    np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1]))
                sizes[bid] = (max(8, round(args.height * aspect)), args.height)
            w, h = sizes[bid]
            M = cv2.getPerspectiveTransform(q, np.float32([[0, 0], [w, 0], [w, h], [0, h]]))
            stacks.setdefault(bid, []).append(cv2.warpPerspective(frame, M, (w, h), flags=cv2.INTER_AREA,
                                                                  borderMode=cv2.BORDER_REPLICATE))

    out_blur, out_mosaic = out_dir / "blur", out_dir / "mosaic"
    out_blur.mkdir(parents=True, exist_ok=True)
    out_mosaic.mkdir(parents=True, exist_ok=True)
    index = {}
    for bid, imgs in stacks.items():
        flat = np.median(np.stack(imgs), axis=0).astype(np.uint8)
        w, h = sizes[bid]
        # Blur strong enough that no lettering survives at any board size; reflect edges so the
        # board's border colour carries to the texture edge instead of fading to black.
        sigma = h / 5
        blurred = cv2.GaussianBlur(cv2.copyMakeBorder(flat, h, h, h, h, cv2.BORDER_REFLECT), (0, 0), sigma)[h:-h, h:-h]
        cv2.imwrite(str(out_blur / f"{bid}.png"), blurred)
        cells = cv2.resize(flat, MOSAIC, interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out_mosaic / f"{bid}.png"), cv2.resize(cells, (w, h), interpolation=cv2.INTER_NEAREST))
        index[bid] = {"w": w, "h": h, "frames": len(imgs)}
    (out_dir / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    print(f"wrote {len(index)} board textures (blur + mosaic) to {args.clip_dir / 'textures'}")


if __name__ == "__main__":
    main()
