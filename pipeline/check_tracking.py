"""Measure board tracking against ground truth on a synthetic clip.

Uses the sparse "keyframes" in a synthetic boards.json as if they were hand annotations,
densifies them with linear interpolation and with optical-flow tracking, and reports corner
error against the dense ground-truth "frames".

Usage: python pipeline/check_tracking.py footage/synth.mp4 footage/synth.boards.json
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

import boards as boards_io


def corner_errors(pred: dict, truth: dict) -> np.ndarray:
    common = sorted(set(pred) & set(truth))
    return np.concatenate([np.linalg.norm(pred[i] - truth[i], axis=1) for i in common])


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    video, boards_path = Path(sys.argv[1]), Path(sys.argv[2])
    data = boards_io.load(boards_path)
    scale = 0.5
    gray = boards_io.load_gray(video, scale)

    C = boards_io.camera_motion(gray)
    lin_all, trk_all, cam_all, cam1_all, fallbacks = [], [], [], [], 0
    for board in data["boards"]:
        truth = boards_io._parse(board["frames"])
        kfs = boards_io.keyframes(board)
        if len(kfs) < 2:
            continue
        lin_all.append(corner_errors(boards_io.interpolate(kfs), truth))
        tracked, fb = boards_io.track(gray, kfs, scale)
        trk_all.append(corner_errors(tracked, truth))
        fallbacks += fb
        cam_all.append(corner_errors(boards_io.track_camera(C, kfs, scale), truth))
        first = min(kfs)
        cam1_all.append(corner_errors(boards_io.track_camera(C, {first: kfs[first]}, scale), truth))

    lin, trk = np.concatenate(lin_all), np.concatenate(trk_all)
    print(f"corner error in px (mean / p95 / max), {len(lin)} corners")
    print(f"  linear interpolation: {lin.mean():6.2f} / {np.percentile(lin, 95):6.2f} / {lin.max():6.2f}")
    print(f"  optical-flow tracking: {trk.mean():6.2f} / {np.percentile(trk, 95):6.2f} / {trk.max():6.2f}")
    print(f"  segments that fell back to linear: {fallbacks}")
    for name, errs in (("camera motion, all keyframes", cam_all), ("camera motion, first keyframe only", cam1_all)):
        e = np.concatenate(errs)
        print(f"  {name}: {e.mean():6.2f} / {np.percentile(e, 95):6.2f} / {e.max():6.2f}")


if __name__ == "__main__":
    main()
