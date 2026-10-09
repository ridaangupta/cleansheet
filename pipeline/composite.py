"""Composite fictional sponsors onto annotated boards and emit ground truth.

Outputs in --out (default media/<clip>/):
  composited.mp4          the "broadcast" with fake sponsors (source audio kept if present)
  sidecar.json            ground-truth sidecar track (shared/sidecar/schema.json)
  dataset/images/*.jpg    every --frame-stride'th frame
  dataset/labels/*.txt    YOLO labels for those frames: class cx cy w h (normalized)
  dataset/classes.txt     one brand name per line, class index = line number
  manifest.json           board -> brand assignment and run settings

Usage: python pipeline/composite.py footage/synth.mp4 [--boards footage/synth.boards.json]
"""

from __future__ import annotations

import argparse
import json
import random
import tempfile
from pathlib import Path

import cv2
import numpy as np

import boards as boards_io
from sidecar import SidecarFrame, SidecarObject, SidecarTrack
from videoio import VideoWriter, has_audio, mux_audio, probe, read_frames

ROOT = Path(__file__).resolve().parent.parent
BRANDS_JSON = ROOT / "assets" / "brands" / "brands.json"
MIN_VISIBLE_PX = 6
MIN_VISIBLE_FRACTION = 0.25


def load_brands() -> tuple[list[dict], dict[str, np.ndarray]]:
    """Brands that can appear in a broadcast (everything except replacements) and their images."""
    data = json.loads(BRANDS_JSON.read_text())
    on_air = [b for b in data["brands"] if b["category"] != "replacement"]
    images = {b["name"]: cv2.imread(str(BRANDS_JSON.parent / b["file"]), cv2.IMREAD_COLOR) for b in on_air}
    return on_air, images


def assign_brands(boards: list[dict], on_air: list[dict], seed: int) -> dict[str, str]:
    names = [b["name"] for b in on_air]
    random.Random(seed).shuffle(names)
    out = {}
    for k, board in enumerate(boards):
        out[board["id"]] = board.get("brand") or names[k % len(names)]
    return out


def visible_bbox(quad: np.ndarray, w: int, h: int) -> tuple[float, float, float, float] | None:
    """Clipped [x, y, w, h] in pixels, or None if too little of the quad is on screen."""
    x0, y0 = quad.min(axis=0)
    x1, y1 = quad.max(axis=0)
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    if cx1 - cx0 < MIN_VISIBLE_PX or cy1 - cy0 < MIN_VISIBLE_PX:
        return None
    full = max((x1 - x0) * (y1 - y0), 1e-6)
    if (cx1 - cx0) * (cy1 - cy0) / full < MIN_VISIBLE_FRACTION:
        return None
    return float(cx0), float(cy0), float(cx1 - cx0), float(cy1 - cy0)


def paste(frame: np.ndarray, art: np.ndarray, quad: np.ndarray, rng: np.random.Generator) -> None:
    """Warp `art` onto `quad` in place, borrowing the board's shading so it sits in the scene."""
    h, w = frame.shape[:2]
    x0, y0 = np.floor(quad.min(axis=0)).astype(int)
    x1, y1 = np.ceil(quad.max(axis=0)).astype(int)
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    ah, aw = art.shape[:2]
    src = np.float32([[0, 0], [aw, 0], [aw, ah], [0, ah]])
    M = cv2.getPerspectiveTransform(src, (quad - [x0, y0]).astype(np.float32))
    size = (x1 - x0, y1 - y0)
    warped = cv2.warpPerspective(art, M, size, flags=cv2.INTER_AREA).astype(np.float32)
    alpha = cv2.warpPerspective(np.ones((ah, aw), np.float32), M, size, flags=cv2.INTER_LINEAR)[..., None]

    roi = frame[y0:y1, x0:x1].astype(np.float32)
    lum = cv2.GaussianBlur(cv2.cvtColor(roi.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 3)
    inside = alpha[..., 0] > 0.5
    ref = np.median(lum[inside]) if inside.any() else 1.0
    shade = np.clip(lum / max(ref, 1.0), 0.75, 1.15)[..., None]
    warped = cv2.GaussianBlur(warped * shade, (0, 0), 0.6)
    warped += rng.normal(0, 2.0, warped.shape).astype(np.float32)

    frame[y0:y1, x0:x1] = np.clip(roi * (1 - alpha) + warped * alpha, 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--boards", type=Path, help="default: <video stem>.boards.json next to the video")
    ap.add_argument("--out", type=Path, help="default: media/<video stem>")
    ap.add_argument("--sidecar-hz", type=float, help="sidecar sample rate; default every frame")
    ap.add_argument("--frame-stride", type=int, default=5, help="export every Nth frame to the dataset")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    video: Path = args.video
    boards_path = args.boards or video.with_suffix(".boards.json")
    out_dir = args.out or ROOT / "media" / video.stem
    img_dir, lbl_dir = out_dir / "dataset" / "images", out_dir / "dataset" / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    width, height, fps, _ = probe(video)
    data = boards_io.load(boards_path)
    on_air, images = load_brands()
    category = {b["name"]: b["category"] for b in on_air}
    classes = [b["name"] for b in on_air]
    # Rows are split into their individual boards here, so everything below sees plain boards.
    boards = boards_io.expand(data["boards"])
    assignment = assign_brands(boards, on_air, args.seed)
    quads = {b["id"]: b["quads"] for b in boards}
    kinds = {b["id"]: b["kind"] for b in boards}

    hz = args.sidecar_hz or fps
    track = SidecarTrack(video_id=video.stem, fps=fps, width=width, height=height, source="ground_truth")
    rng = np.random.default_rng(args.seed)
    n_labels = 0

    with tempfile.TemporaryDirectory() as tmp:
        silent = Path(tmp) / "video.mp4"
        with VideoWriter(silent, width, height, fps) as writer:
            for i, frame in enumerate(read_frames(video)):
                objects, labels = [], []
                for board_id, per_frame in quads.items():
                    quad = per_frame.get(i)
                    if quad is None:
                        continue
                    brand = assignment[board_id]
                    paste(frame, images[brand], quad, rng)
                    bbox = visible_bbox(quad, width, height)
                    if bbox is None:
                        continue
                    bx, by, bw, bh = bbox
                    objects.append(SidecarObject(
                        id=board_id, kind=kinds[board_id], category=category[brand], brand=brand,
                        quad=[[round(float(x) / width, 5), round(float(y) / height, 5)] for x, y in quad],
                        bbox=[round(bx / width, 5), round(by / height, 5), round(bw / width, 5), round(bh / height, 5)],
                        confidence=1.0,
                    ))
                    labels.append(f"{classes.index(brand)} {(bx + bw / 2) / width:.6f} {(by + bh / 2) / height:.6f} {bw / width:.6f} {bh / height:.6f}")
                writer.write(frame)

                if i == 0 or int(i * hz / fps) != int((i - 1) * hz / fps):
                    track.frames.append(SidecarFrame(t=i / fps, objects=objects))
                if i % args.frame_stride == 0:
                    name = f"{video.stem}_{i:06d}"
                    cv2.imwrite(str(img_dir / f"{name}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    (lbl_dir / f"{name}.txt").write_text("\n".join(labels) + ("\n" if labels else ""))
                    n_labels += len(labels)
                frame_count = i + 1

        final = out_dir / "composited.mp4"
        if has_audio(video):
            mux_audio(silent, video, final)
        else:
            final.unlink(missing_ok=True)
            silent.replace(final)

    track.save(out_dir / "sidecar.json")
    (out_dir / "dataset" / "classes.txt").write_text("\n".join(classes) + "\n")
    (out_dir / "manifest.json").write_text(json.dumps({
        "video": str(video), "boards": str(boards_path), "frames": frame_count, "fps": fps,
        "sidecar_hz": hz, "frame_stride": args.frame_stride, "seed": args.seed,
        "assignment": assignment,
    }, indent=2) + "\n")
    print(f"wrote {final}: {frame_count} frames, sidecar {len(track.frames)} samples @ {hz:g} Hz, "
          f"{n_labels} labels in {len(list(img_dir.glob('*.jpg')))} dataset images")


if __name__ == "__main__":
    main()
