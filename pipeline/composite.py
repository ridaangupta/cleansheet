"""Composite fictional sponsors onto annotated boards and emit ground truth.

Outputs in --out (default media/<clip>/):
  composited.mp4          the "broadcast" with fake sponsors (source audio kept if present)
  sidecar.json            ground-truth sidecar track (shared/sidecar/schema.json)
  dataset/images/*.jpg    every --frame-stride'th frame
  dataset/labels/*.txt    YOLO pose labels for those frames: class cx cy w h, then the 4 corners
                          (TL, TR, BR, BL) as x y v; off-screen corners are 0 0 0 (normalized)
  dataset/classes.txt     one brand name per line, class index = line number
  manifest.json           board -> brand assignment and run settings

Realism (so the composite reads as part of the broadcast, not pasted on): before writing, a
pass over sample frames measures the real board pixels each fake board covers. Each board's art
is tone-matched to them (brightness, contrast, saturation), gets thin dark seams, and is softened
by a clip-wide blur matched to the footage's sharpness. Boards split from one row get their own
shuffled brand order with no neighbouring repeats. --plain turns all of this off.

Usage: python pipeline/composite.py footage/synth.mp4 [--boards footage/synth.boards.json] [--plain]
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


def assign_brands(boards: list[dict], on_air: list[dict], seed: int, mix_rows: bool = False) -> dict[str, str]:
    names = [b["name"] for b in on_air]
    random.Random(seed).shuffle(names)
    out = {}
    if not mix_rows:
        for k, board in enumerate(boards):
            out[board["id"]] = board.get("brand") or names[k % len(names)]
        return out
    # Each row (boards "<row>-NN" from boards.expand) gets its own random order without
    # neighbouring repeats, so rows don't repeat one sequence in lockstep.
    rows: dict[str, list[dict]] = {}
    for board in boards:
        rows.setdefault(board["id"].rsplit("-", 1)[0] if "-" in board["id"] else board["id"], []).append(board)
    for row_id, members in rows.items():
        rng = random.Random(f"{seed}:{row_id}")
        prev = None
        for board in members:
            if board.get("brand"):
                out[board["id"]] = prev = board["brand"]
                continue
            choice = rng.choice([n for n in names if n != prev] or names)
            out[board["id"]] = prev = choice
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


def pose_label(cls: int, bbox: tuple[float, float, float, float], quad: np.ndarray, w: int, h: int) -> str:
    """YOLO pose line: the visible box, then each corner as x y v (v=2 on screen, 0 0 0 off it)."""
    bx, by, bw, bh = bbox
    parts = [str(cls), f"{(bx + bw / 2) / w:.6f}", f"{(by + bh / 2) / h:.6f}", f"{bw / w:.6f}", f"{bh / h:.6f}"]
    for x, y in quad:
        parts += [f"{x / w:.6f}", f"{y / h:.6f}", "2"] if 0 <= x <= w and 0 <= y <= h else ["0", "0", "0"]
    return " ".join(parts)


def quad_mask(shape: tuple[int, int], quad: np.ndarray, erode: int = 2) -> np.ndarray:
    mask = np.zeros(shape, np.uint8)
    cv2.fillConvexPoly(mask, np.round(quad).astype(np.int32), 255)
    if erode:
        mask = cv2.erode(mask, np.ones((2 * erode + 1, 2 * erode + 1), np.uint8))
    return mask > 0


def lab_stats(img: np.ndarray, mask: np.ndarray | None = None) -> tuple[float, float, float]:
    """(L mean, L std, chroma mean) in OpenCV 8-bit Lab, over `mask` if given."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    px = lab[mask] if mask is not None else lab.reshape(-1, 3)
    chroma = np.hypot(px[:, 1] - 128, px[:, 2] - 128)
    return float(px[:, 0].mean()), float(px[:, 0].std()), float(chroma.mean())


def tone_match(art: np.ndarray, target: tuple[float, float, float]) -> np.ndarray:
    """Pull the art's brightness, contrast and saturation toward the real board it replaces.

    Partial, clamped matching: the fake brand stays legible and on-brand, but sits at the
    scene's light level (dusk vs night) instead of looking like a lit screen.
    """
    l_mean, l_std, chroma = lab_stats(art)
    t_mean, t_std, t_chroma = target
    lab = cv2.cvtColor(art, cv2.COLOR_BGR2LAB).astype(np.float32)
    k = float(np.clip(t_std / max(l_std, 1e-3), 0.7, 1.0))
    mean = 0.55 * l_mean + 0.45 * t_mean
    lab[..., 0] = (lab[..., 0] - l_mean) * k + mean
    c = float(np.clip(t_chroma / max(chroma, 1e-3), 0.65, 1.0))
    lab[..., 1:] = (lab[..., 1:] - 128) * c + 128
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def add_seams(art: np.ndarray) -> np.ndarray:
    """Thin dark edges where neighbouring boards meet, plus a slightly darker frame."""
    out = art.astype(np.float32)
    h, w = art.shape[:2]
    sw = max(2, round(w * 0.006))
    out[:, :sw] *= 0.25
    out[:, w - sw:] *= 0.25
    out[: max(1, h // 60)] *= 0.6
    out[h - max(1, h // 60):] *= 0.6
    return out.astype(np.uint8)


def warp_art(art: np.ndarray, quad: np.ndarray, frame_shape: tuple[int, int]):
    """Warp `art` onto `quad`; returns (x0, y0, warped float32, alpha) or None if off-screen."""
    h, w = frame_shape
    x0, y0 = np.floor(quad.min(axis=0)).astype(int)
    x1, y1 = np.ceil(quad.max(axis=0)).astype(int)
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    ah, aw = art.shape[:2]
    src = np.float32([[0, 0], [aw, 0], [aw, ah], [0, ah]])
    M = cv2.getPerspectiveTransform(src, (quad - [x0, y0]).astype(np.float32))
    size = (x1 - x0, y1 - y0)
    warped = cv2.warpPerspective(art, M, size, flags=cv2.INTER_AREA).astype(np.float32)
    alpha = cv2.warpPerspective(np.ones((ah, aw), np.float32), M, size, flags=cv2.INTER_LINEAR)[..., None]
    return x0, y0, warped, alpha


def lap_var(gray: np.ndarray, mask: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_32F)[mask].var())


SIGMAS = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)


def measure(video: Path, boards: list[dict], art_for, samples: int = 12) -> tuple[dict, float]:
    """Per-board Lab stats of the real pixels under each board, and a clip-wide blur sigma.

    Stats are medians over `samples` frames spread across the clip (fixed per board, so the
    tone can't flicker). The sigma is the median, over sampled boards, of the blur that gives
    the warped art the same Laplacian variance (fine detail) as the real board it covers.
    """
    _, _, _, n = probe(video)
    picks = set(np.linspace(0, max(n - 1, 0), samples).astype(int).tolist())
    stats: dict[str, list] = {}
    sigmas: list[float] = []
    for i, frame in enumerate(read_frames(video)):
        if i not in picks:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        for board in boards:
            quad = board["quads"].get(i)
            if quad is None:
                continue
            mask = quad_mask(frame.shape[:2], quad)
            if mask.sum() < 150:
                continue
            stats.setdefault(board["id"], []).append(lab_stats(frame, mask))
            w = warp_art(art_for(board["id"]), quad, frame.shape[:2])
            if w is None:
                continue
            x0, y0, warped, alpha = w
            sub = mask[y0:y0 + warped.shape[0], x0:x0 + warped.shape[1]] & (alpha[..., 0] > 0.99)
            if sub.sum() < 150:
                continue
            target = lap_var(gray[y0:y0 + warped.shape[0], x0:x0 + warped.shape[1]], sub)
            wg = cv2.cvtColor(np.clip(warped, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
            errs = [abs(np.log(lap_var(cv2.GaussianBlur(wg, (0, 0), s), sub) + 1) - np.log(target + 1)) for s in SIGMAS]
            sigmas.append(SIGMAS[int(np.argmin(errs))])
    per_board = {k: tuple(np.median(np.array(v), axis=0).tolist()) for k, v in stats.items()}
    sigma = float(np.median(sigmas)) if sigmas else 0.6
    return per_board, sigma


def paste(frame: np.ndarray, art: np.ndarray, quad: np.ndarray, rng: np.random.Generator,
          sigma: float = 0.6, noise: float = 2.0) -> None:
    """Warp `art` onto `quad` in place, borrowing the board's shading so it sits in the scene."""
    w = warp_art(art, quad, frame.shape[:2])
    if w is None:
        return
    x0, y0, warped, alpha = w
    y1, x1 = y0 + warped.shape[0], x0 + warped.shape[1]

    roi = frame[y0:y1, x0:x1].astype(np.float32)
    lum = cv2.GaussianBlur(cv2.cvtColor(roi.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 3)
    inside = alpha[..., 0] > 0.5
    ref = np.median(lum[inside]) if inside.any() else 1.0
    shade = np.clip(lum / max(ref, 1.0), 0.75, 1.15)[..., None]
    warped = cv2.GaussianBlur(warped * shade, (0, 0), sigma)
    warped += rng.normal(0, noise, warped.shape).astype(np.float32)

    frame[y0:y1, x0:x1] = np.clip(roi * (1 - alpha) + warped * alpha, 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--boards", type=Path, help="default: <video stem>.boards.json next to the video")
    ap.add_argument("--out", type=Path, help="default: media/<video stem>")
    ap.add_argument("--sidecar-hz", type=float, help="sidecar sample rate; default every frame")
    ap.add_argument("--frame-stride", type=int, default=2, help="export every Nth frame to the dataset")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--plain", action="store_true", help="no tone matching, seams, blur matching or row mixing")
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
    real = data.get("tracking") == "camera" and not args.plain  # broadcast footage, not synth
    assignment = assign_brands(boards, on_air, args.seed, mix_rows=real)
    quads = {b["id"]: b["quads"] for b in boards}
    kinds = {b["id"]: b["kind"] for b in boards}

    sigma, noise = 0.6, 2.0
    art = {board_id: images[brand] for board_id, brand in assignment.items()}
    if real:
        seamed = {name: add_seams(img) for name, img in images.items()}
        stats, sigma = measure(video, boards, lambda bid: seamed[assignment[bid]])
        art = {bid: tone_match(seamed[assignment[bid]], stats[bid]) if bid in stats else seamed[assignment[bid]]
               for bid in assignment}
        noise = 1.0
        print(f"realism: tone-matched {len(stats)} boards, blur sigma {sigma:g}")

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
                    paste(frame, art[board_id], quad, rng, sigma, noise)
                    bbox = visible_bbox(quad, width, height)
                    if bbox is None:
                        continue
                    objects.append(SidecarObject(
                        id=board_id, kind=kinds[board_id], category=category[brand], brand=brand,
                        quad=[[float(x) / width, float(y) / height] for x, y in quad],
                        confidence=1.0,
                    ))
                    labels.append(pose_label(classes.index(brand), bbox, quad, width, height))
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
        "assignment": assignment, "realism": {"enabled": real, "blur_sigma": sigma},
    }, indent=2) + "\n")
    print(f"wrote {final}: {frame_count} frames, sidecar {len(track.frames)} samples @ {hz:g} Hz, "
          f"{n_labels} labels in {len(list(img_dir.glob('*.jpg')))} dataset images")


if __name__ == "__main__":
    main()
