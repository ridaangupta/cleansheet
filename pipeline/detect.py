"""Run the board detector over a stream and write a model sidecar track (source "model").

Per frame the detector gives boxes, a brand class and 4 corner keypoints. On top of that:

  hidden corners  corners of boards cut by the frame edge are rebuilt from a neighbouring board
                  (fill_hidden_corners); the model only learned on-screen corners
  camera motion   one homography per frame step (boards.camera_motion): broadcast cameras only
                  pan/tilt/zoom, so it moves every board the same way
  tracking        detections are linked across frames by IoU against the previous frame's boards
                  moved by the camera step; a track survives --max-gap missed frames
  smoothing       each track's corners on frame i are the confidence-weighted median of its
                  detections within +-WINDOW frames, each warped into frame i by the camera
                  motion. This removes keypoint jitter and fills short gaps
  per-track       brand = confidence-weighted vote; confidence = median detection confidence, so a
  attributes      board doesn't flicker between the app's replace and blur treatments

Usage: python pipeline/detect.py media/train/runs/boards/weights/best.pt media/<clip>/composited.mp4
         [--out media/<clip>/sidecar.model.json] [--ignore x,y,w,h ...]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

import boards as boards_io
from composite import visible_bbox
from eval_detector import iou
from sidecar import SidecarFrame, SidecarObject, SidecarTrack
from videoio import probe, read_frames

ROOT = Path(__file__).resolve().parent.parent
BRANDS_JSON = ROOT / "assets" / "brands" / "brands.json"
WINDOW = 5        # smoothing half-window, frames
MIN_DETECTIONS = 6  # shorter tracks are dropped as noise
MOTION_SCALE = 0.5  # camera motion is estimated on half-size frames
KPT_VISIBLE = 0.5   # keypoint confidence below this = corner off screen (trained unlabelled)
KPT_FILLED = 0.3    # smoothing weight of a rebuilt off-screen corner, below any seen one


@dataclass
class Det:
    box: np.ndarray    # xyxy px
    conf: float
    cls: int
    quad: np.ndarray   # (4, 2) px
    kconf: np.ndarray  # (4,)


@dataclass
class Track:
    id: str
    dets: dict[int, Det] = field(default_factory=dict)
    last: int = 0


def quad_box(q: np.ndarray, w: int, h: int) -> np.ndarray:
    x0, y0 = q.min(axis=0)
    x1, y1 = q.max(axis=0)
    return np.array([max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)])


def warp(H: np.ndarray, q: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(q.reshape(-1, 1, 2).astype(np.float64), H).reshape(4, 2)


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    cum = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cum, cum[-1] / 2)])


def fill_hidden_corners(dets: list[Det]) -> list[Det]:
    """Rebuild off-screen corners (keypoint confidence < KPT_VISIBLE) of boards cut by the frame edge.

    The model is trained with off-screen corners unlabelled, so it can't place them: their
    keypoints collapse onto the visible edge, and a warp onto that quad blows up across the
    screen. Boards in a row share a size, so a hidden corner is its visible partner on the same
    edge (TL-TR, BL-BR) moved by that edge of the nearest fully visible board in the frame.
    Detections that can't be rebuilt that way are dropped.
    """
    full = [d for d in dets if (d.kconf >= KPT_VISIBLE).all()]
    out = []
    for d in dets:
        hidden = d.kconf < KPT_VISIBLE
        if not hidden.any():
            out.append(d)
            continue
        if not full:
            continue
        centre = d.quad[~hidden].mean(axis=0) if (~hidden).any() else d.quad.mean(axis=0)
        n = min(full, key=lambda f: np.linalg.norm(f.quad.mean(axis=0) - centre)).quad
        quad = d.quad.copy()
        ok = True
        for c, partner in ((0, 1), (1, 0), (3, 2), (2, 3)):
            if not hidden[c]:
                continue
            if hidden[partner]:
                ok = False
                break
            quad[c] = quad[partner] + (n[c] - n[partner])
        if ok:
            out.append(Det(d.box, d.conf, d.cls, quad, np.where(hidden, KPT_FILLED, d.kconf)))
    return out


def merge_duplicates(tracks: list[Track], min_iou: float = 0.5) -> list[Track]:
    """Merge tracks that cover the same board: a missed match starts a second track on it.

    Two tracks are the same board if their boxes overlap (median IoU >= min_iou) on the frames
    both detected. Longest tracks absorb shorter ones; on shared frames the surer detection wins.
    """
    tracks = sorted(tracks, key=lambda t: -len(t.dets))
    kept: list[Track] = []
    for t in tracks:
        for k in kept:
            shared = set(t.dets) & set(k.dets)
            if shared and np.median([iou(t.dets[i].box, k.dets[i].box) for i in shared]) >= min_iou:
                for i, d in t.dets.items():
                    if i not in k.dets or d.conf > k.dets[i].conf:
                        k.dets[i] = d
                break
        else:
            kept.append(t)
    return kept


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("weights", type=Path)
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, help="default: sidecar.model.json next to the video")
    ap.add_argument("--ignore", action="append", default=[],
                    help="x,y,w,h (fractions) of screen-fixed graphics to keep out of camera motion; "
                         "default: the clip's footage/<clip>.boards.json 'ignore'")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--max-gap", type=int, default=8, help="frames a track survives without a detection")
    ap.add_argument("--match-iou", type=float, default=0.3)
    args = ap.parse_args()

    video: Path = args.video
    clip = video.parent.name
    out = args.out or video.with_name("sidecar.model.json")
    W, H, fps, _ = probe(video)
    ignore = [[float(v) for v in s.split(",")] for s in args.ignore]
    boards_json = ROOT / "footage" / f"{clip}.boards.json"
    if not ignore and boards_json.exists():
        ignore = boards_io.load(boards_json).get("ignore", [])

    # Camera motion in full-size pixels: step[i] maps frame i-1 to frame i.
    C = boards_io.camera_motion(boards_io.load_gray(video, MOTION_SCALE), ignore)
    S = np.diag([1 / MOTION_SCALE, 1 / MOTION_SCALE, 1.0])
    C = [S @ c @ np.linalg.inv(S) for c in C]

    def rel(j: int, i: int) -> np.ndarray:
        """Homography moving frame j's pixels to frame i (short spans only; cumulative drift)."""
        return C[i] @ np.linalg.inv(C[j])

    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    names = model.names
    category = {b["name"]: b["category"] for b in json.loads(BRANDS_JSON.read_text())["brands"]}

    tracks: list[Track] = []
    active: list[Track] = []
    n_frames = 0
    for i, frame in enumerate(read_frames(video)):
        n_frames = i + 1
        r = model.predict(frame, imgsz=args.imgsz, conf=args.conf, device="mps", agnostic_nms=True, verbose=False)[0]
        kxy = r.keypoints.xy.cpu().numpy()
        kc = r.keypoints.conf.cpu().numpy() if r.keypoints.conf is not None else np.ones(kxy.shape[:2])
        dets = [Det(b, float(c), int(k), q, kcf) for b, c, k, q, kcf in zip(
            r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(), r.boxes.cls.cpu().numpy(), kxy, kc)]
        dets = fill_hidden_corners(dets)

        active = [t for t in active if i - t.last <= args.max_gap]
        # Each active track's last detection, moved into this frame by the camera.
        predicted = [quad_box(warp(rel(t.last, i), t.dets[t.last].quad), W, H) for t in active]
        pairs = sorted(((iou(p, d.box), ti, di) for ti, p in enumerate(predicted) for di, d in enumerate(dets)),
                       reverse=True)
        used_t, used_d = set(), set()
        for v, ti, di in pairs:
            if v < args.match_iou:
                break
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti); used_d.add(di)
            active[ti].dets[i] = dets[di]; active[ti].last = i
        for di, d in enumerate(dets):
            if di not in used_d:
                t = Track(id=f"t{len(tracks) + 1:03d}", dets={i: d}, last=i)
                tracks.append(t); active.append(t)

    tracks = merge_duplicates(tracks)
    tracks = [t for t in tracks if len(t.dets) >= MIN_DETECTIONS]
    track_out = SidecarTrack(video_id=clip, fps=fps, width=W, height=H, source="model")
    per_frame: list[list[SidecarObject]] = [[] for _ in range(n_frames)]
    for t in tracks:
        votes: dict[int, float] = {}
        for d in t.dets.values():
            votes[d.cls] = votes.get(d.cls, 0.0) + d.conf
        brand = names[max(votes, key=votes.get)]
        conf = float(np.median([d.conf for d in t.dets.values()]))
        frames = sorted(t.dets)
        for i in range(frames[0], frames[-1] + 1):
            near = [j for j in range(i - WINDOW, i + WINDOW + 1) if j in t.dets]
            if not near:
                continue  # inside a gap longer than the window: drop rather than guess
            quads = np.stack([warp(rel(j, i), t.dets[j].quad) for j in near])          # (n, 4, 2)
            wts = np.stack([t.dets[j].conf * np.maximum(t.dets[j].kconf, 0.05) for j in near])  # (n, 4)
            quad = np.array([[weighted_median(quads[:, c, a], wts[:, c]) for a in (0, 1)] for c in range(4)])
            bbox = visible_bbox(quad, W, H)
            if bbox is None:
                continue
            bx, by, bw, bh = bbox
            per_frame[i].append(SidecarObject(
                id=t.id, kind="board", category=category.get(brand, "neutral"), brand=brand,
                quad=[[round(float(x) / W, 5), round(float(y) / H, 5)] for x, y in quad],
                bbox=[round(bx / W, 5), round(by / H, 5), round(bw / W, 5), round(bh / H, 5)],
                confidence=round(conf, 3),
            ))
    for i, objects in enumerate(per_frame):
        track_out.frames.append(SidecarFrame(t=i / fps, objects=objects))
    track_out.save(out)
    print(f"wrote {out}: {n_frames} frames, {len(tracks)} tracks, "
          f"{sum(len(o) for o in per_frame)} objects")


if __name__ == "__main__":
    main()
