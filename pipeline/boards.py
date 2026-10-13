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
      "frames":    {"0": [[x, y] x4], ...},  # optional dense per-frame quads (tracked or synthetic)
      "split": 6,                            # optional: a row of boards, see below
      "extend": [1.0, 0.5],                  # optional, rows only
      "brands": ["BetNova", ...]             # optional, rows only: one per split board
    }
  ]
}

A board exists only between its first and last keyframe (or on the frames listed in "frames").
A board with a single keyframe is tracked across the whole clip by `densify_all`.

Top-level "tracking": "camera" (optional) tracks the camera instead of each board: one homography
per frame from features over the whole image, applied to every board. Right for broadcast
footage, where the camera only pans/tilts/zooms from a fixed spot (so the image motion is the
same homography for every plane) and per-board tracking gets confused by animated LED boards and
players. "ignore": [[x, y, w, h], ...] (fractions of the frame) excludes screen-fixed graphics
such as pixelated scorebugs from the camera features.

Rows: perimeter boards along one side of the pitch lie on one plane, so a whole row can be
annotated as a single quad and split into `split` equal boards (`expand`). The quad only has
to span a visible stretch of the row (anchor it on board seams you can find again);
`extend` = [left, right] continues the row past the clicked quad, in multiples of its length,
using the same homography, so the split boards stay perspective-correct off the clicked area.
`split` counts boards over the extended length: 6 boards in the clicked quad with extend [0, 2]
is split 18.
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


def row_quads(quad: Quad, split: int, extend: tuple[float, float] = (0.0, 0.0)) -> list[Quad]:
    """Split a row quad into `split` equal quads along its length (TL->TR), extended past both ends."""
    src = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])
    H = cv2.getPerspectiveTransform(src, quad.astype(np.float32))
    edges = np.linspace(-extend[0], 1 + extend[1], split + 1)
    out = []
    for u0, u1 in zip(edges, edges[1:]):
        pts = np.float32([[u0, 0], [u1, 0], [u1, 1], [u0, 1]]).reshape(-1, 1, 2)
        out.append(cv2.perspectiveTransform(pts, H).reshape(4, 2))
    return out


def expand(boards: list[dict]) -> list[dict]:
    """Resolve every board to per-frame quads, splitting rows into their individual boards.

    Returns dicts with "id", "kind", optional "brand", and "quads" ({frame: Quad}). Boards
    split from a row get ids "<row id>-01", "<row id>-02", ... in TL->TR order.
    """
    out = []
    for board in boards:
        quads = resolve(board)
        split = int(board.get("split", 1))
        if split <= 1:
            out.append({"id": board["id"], "kind": board.get("kind", "board"), "brand": board.get("brand"),
                        "quads": quads})
            continue
        extend = tuple(board.get("extend", (0.0, 0.0)))
        per_frame = {i: row_quads(q, split, extend) for i, q in quads.items()}
        brands = board.get("brands", [])
        for k in range(split):
            out.append({"id": f"{board['id']}-{k + 1:02d}", "kind": board.get("kind", "board"),
                        "brand": brands[k] if k < len(brands) else None,
                        "quads": {i: qs[k] for i, qs in per_frame.items()}})
    return out


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


def track_from(gray: list[np.ndarray], frame: int, quad: Quad, scale: float = 1.0) -> dict[int, Quad]:
    """Track a single keyframe forward and backward until the clip ends or tracking is lost."""
    out = {frame: quad}
    for step in (1, -1):
        cur, i = quad * scale, frame
        while 0 <= i + step < len(gray):
            cur = _step(gray[i], gray[i + step], cur)
            if cur is None:
                break
            i += step
            out[i] = cur / scale
    return out


def camera_motion(gray: list[np.ndarray], ignore: list[list[float]] = ()) -> list[np.ndarray]:
    """Cumulative homographies C[i] mapping frame 0 to frame i (in `gray` pixel coordinates).

    Features come from the whole frame minus `ignore` rectangles; RANSAC rejects players and
    animated boards. A failed step reuses the previous step's motion.
    """
    h, w = gray[0].shape
    mask = np.full((h, w), 255, np.uint8)
    for x, y, rw, rh in ignore:
        mask[int(y * h):int((y + rh) * h), int(x * w):int((x + rw) * w)] = 0
    out = [np.eye(3)]
    last = np.eye(3)
    for prev, nxt in zip(gray, gray[1:]):
        step = None
        pts = cv2.goodFeaturesToTrack(prev, maxCorners=800, qualityLevel=0.01, minDistance=7, mask=mask)
        if pts is not None and len(pts) >= 20:
            moved, status, _ = cv2.calcOpticalFlowPyrLK(prev, nxt, pts, None, winSize=(21, 21), maxLevel=3)
            ok = status.ravel() == 1
            if ok.sum() >= 20:
                H, inliers = cv2.findHomography(pts[ok], moved[ok], cv2.RANSAC, 1.5)
                if H is not None and inliers.sum() >= 15:
                    step = H
        last = step if step is not None else last
        out.append(last @ out[-1])
    return out


def _apply(H: np.ndarray, quad: Quad) -> Quad:
    return cv2.perspectiveTransform(quad.reshape(-1, 1, 2).astype(np.float64), H).reshape(4, 2).astype(np.float32)


def track_camera(C: list[np.ndarray], kfs: dict[int, Quad], scale: float) -> dict[int, Quad]:
    """Move keyframed quads with the camera motion `C`, blending between keyframes like `track`."""
    S, Si = np.diag([scale, scale, 1.0]), np.diag([1 / scale, 1 / scale, 1.0])
    idx = sorted(kfs)
    if len(idx) == 1:
        a = idx[0]
        return {i: _apply(Si @ C[i] @ np.linalg.inv(C[a]) @ S, kfs[a]) for i in range(len(C))}
    out = {}
    for a, b in zip(idx, idx[1:]):
        for i in range(a, b + 1):
            qa = _apply(Si @ C[i] @ np.linalg.inv(C[a]) @ S, kfs[a])
            qb = _apply(Si @ C[i] @ np.linalg.inv(C[b]) @ S, kfs[b])
            wgt = (i - a) / (b - a)
            out[i] = (1 - wgt) * qa + wgt * qb
    return out


def densify_all(video: Path, data: dict, scale: float = 0.5) -> dict[str, int | str]:
    """Track every keyframed board, writing results to board["frames"].

    Boards with 2+ keyframes are tracked between keyframes (`track`); the report value is the
    number of segments that fell back to linear interpolation. Boards with one keyframe are
    tracked across the whole clip (`track_from`); the report value is the frame range covered.
    """
    gray = load_gray(video, scale)
    report: dict[str, int | str] = {}
    if data.get("tracking") == "camera":
        C = camera_motion(gray, data.get("ignore", []))
        for board in data["boards"]:
            kfs = keyframes(board)
            if not kfs:
                continue
            board["frames"] = _dump(track_camera(C, kfs, scale))
            report[board["id"]] = f"camera, {len(kfs)} keyframe(s)"
        return report
    for board in data["boards"]:
        kfs = keyframes(board)
        if len(kfs) == 1:
            (frame, quad), = kfs.items()
            quads = track_from(gray, frame, quad, scale)
            report[board["id"]] = f"frames {min(quads)}-{max(quads)} of 0-{len(gray) - 1}"
        elif len(kfs) >= 2:
            quads, report[board["id"]] = track(gray, kfs, scale)
        else:
            continue
        board["frames"] = _dump(quads)
    return report
