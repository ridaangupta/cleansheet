"""Board geometry for a clip: the `<clip>.boards.json` format, keyframe interpolation, and tracking.

boards.json:
{
  "video": "synth.mp4", "width": 1280, "height": 720, "fps": 30, "frame_count": 360,
  "boards": [
    {
      "id": "b01",
      "kind": "board",                       # board | jersey
      "brand": "BetNova",                    # optional; composite.py assigns one if missing
      "keyframes": {"0": [[x, y] x4], ...},  # pixel corners TL, TR, BR, BL, hand-annotated
      "frames":    {"0": [[x, y] x4], ...}   # optional dense per-frame quads (tracked or synthetic)
    }
  ]
}

A board exists only between its first and last keyframe (or on the frames listed in "frames").
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

Quad = np.ndarray  # shape (4, 2), float32, pixel coordinates


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def save(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=1) + "\n")


def _parse(entries: dict) -> dict[int, Quad]:
    return {int(k): np.asarray(v, dtype=np.float32) for k, v in entries.items()}


def _dump(quads: dict[int, Quad]) -> dict[str, list]:
    return {str(i): np.round(q, 2).tolist() for i, q in sorted(quads.items())}


def keyframes(board: dict) -> dict[int, Quad]:
    return _parse(board.get("keyframes", {}))


def interpolate(kfs: dict[int, Quad]) -> dict[int, Quad]:
    """Linear interpolation of corners between consecutive keyframes."""
    idx = sorted(kfs)
    out = {i: kfs[i] for i in idx}
    for a, b in zip(idx, idx[1:]):
        for i in range(a + 1, b):
            w = (i - a) / (b - a)
            out[i] = (1 - w) * kfs[a] + w * kfs[b]
    return out


def resolve(board: dict) -> dict[int, Quad]:
    """Per-frame quads for a board: dense frames if present, else interpolated keyframes."""
    if board.get("frames"):
        return _parse(board["frames"])
    return interpolate(keyframes(board))


def load_gray(video: Path, scale: float) -> list[np.ndarray]:
    from videoio import read_frames

    frames = []
    for f in read_frames(video):
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if scale != 1.0:
            g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        frames.append(g)
    return frames


def _region_mask(shape: tuple[int, int], quad: Quad) -> np.ndarray | None:
    """Mask around a quad to pick features from: the board plus the stands/pitch next to it."""
    h, w = shape
    x0, y0 = quad.min(axis=0)
    x1, y1 = quad.max(axis=0)
    bh = max(y1 - y0, 8)
    bw = max(x1 - x0, 8)
    x0, x1 = int(max(0, x0 - 0.25 * bw)), int(min(w, x1 + 0.25 * bw))
    y0, y1 = int(max(0, y0 - 1.5 * bh)), int(min(h, y1 + 1.5 * bh))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    mask = np.zeros(shape, np.uint8)
    mask[y0:y1, x0:x1] = 255
    return mask


def _step(prev: np.ndarray, nxt: np.ndarray, quad: Quad) -> Quad | None:
    """Move a quad from one frame to the next with a RANSAC homography over tracked features."""
    mask = _region_mask(prev.shape, quad)
    if mask is None:
        return None
    pts = cv2.goodFeaturesToTrack(prev, maxCorners=300, qualityLevel=0.01, minDistance=5, mask=mask)
    if pts is None or len(pts) < 12:
        return None
    moved, status, _ = cv2.calcOpticalFlowPyrLK(prev, nxt, pts, None, winSize=(21, 21), maxLevel=3)
    ok = status.ravel() == 1
    if ok.sum() < 12:
        return None
    H, inliers = cv2.findHomography(pts[ok], moved[ok], cv2.RANSAC, 2.0)
    if H is None or inliers.sum() < 10:
        return None
    return cv2.perspectiveTransform(quad.reshape(-1, 1, 2), H).reshape(4, 2)


def _propagate(gray: list[np.ndarray], quad: Quad, start: int, end: int) -> dict[int, Quad] | None:
    """Track `quad` from frame `start` to `end` (either direction). None if tracking is lost."""
    step = 1 if end >= start else -1
    out = {start: quad}
    cur = quad
    for i in range(start, end, step):
        cur = _step(gray[i], gray[i + step], cur)
        if cur is None:
            return None
        out[i + step] = cur
    return out


def track(gray: list[np.ndarray], kfs: dict[int, Quad], scale: float = 1.0) -> tuple[dict[int, Quad], int]:
    """Densify keyframes by tracking forward and backward between each pair and blending.

    The blend weight moves linearly from the earlier keyframe to the later one, so drift is
    pinned to zero at every keyframe. Segments where tracking fails fall back to linear
    interpolation. Returns (quads, number_of_fallback_segments).
    """
    idx = sorted(kfs)
    out: dict[int, Quad] = {i: kfs[i] for i in idx}
    fallbacks = 0
    for a, b in zip(idx, idx[1:]):
        qa, qb = kfs[a] * scale, kfs[b] * scale
        fwd = _propagate(gray, qa, a, b)
        bwd = _propagate(gray, qb, b, a)
        if fwd is None and bwd is None:
            out.update(interpolate({a: kfs[a], b: kfs[b]}))
            fallbacks += 1
            continue
        for i in range(a + 1, b):
            w = (i - a) / (b - a)
            if fwd is not None and bwd is not None:
                q = (1 - w) * fwd[i] + w * bwd[i]
            else:
                # One direction failed: correct the surviving track for its drift at the far keyframe.
                trk, far, far_q = (fwd, b, qb) if fwd is not None else (bwd, a, qa)
                drift = far_q - trk[far]
                q = trk[i] + (w if trk is fwd else 1 - w) * drift
            out[i] = q / scale
    return out, fallbacks


def densify_all(video: Path, data: dict, scale: float = 0.5) -> dict[str, int]:
    """Run `track` for every board with 2+ keyframes, writing results to board["frames"]."""
    gray = load_gray(video, scale)
    report = {}
    for board in data["boards"]:
        kfs = keyframes(board)
        if len(kfs) < 2:
            continue
        quads, fallbacks = track(gray, kfs, scale)
        board["frames"] = _dump(quads)
        report[board["id"]] = fallbacks
    return report
