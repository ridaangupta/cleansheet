"""Add drift-correction keyframes to a camera-tracked row by registering frames against a reference.

Camera tracking (boards.camera_motion) drifts: on metro_ucv_01 a row's anchor was ~70 px off
after 12 s. For each target frame this straightens the row out of the frame along its tracked
quad, finds a slice of the row from the reference keyframe in it (template match over shift and
scale, then affine ECC, which also removes shear), and writes the corrected quad as a keyframe.
Then it re-densifies the clip. Matches scoring below --min-score (slice off screen, players in
front) are skipped.

The slice [u0, u1] is in units of the row's anchor quad (0 = its left edge, 1 = right edge) and
must be on screen in both the reference and the target frame. Check the result with overlays:
rows can bend on screen (curved perimeter, lens distortion), and a bent row needs splitting.

Usage: python pipeline/refine_rows.py footage/<clip>.mp4 <row id> --ref 0 --targets 60,120,180 [--slice 0,0.5]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

import boards as boards_io

PX = 2.0  # straightened-row pixels per image pixel


def grab(video: Path, i: int) -> np.ndarray:
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, frame = cap.read()
    if not ok:
        raise SystemExit(f"can't read frame {i} of {video}")
    return frame


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("row", help="board id in the boards json")
    ap.add_argument("--boards", type=Path, help="default: <video stem>.boards.json next to the video")
    ap.add_argument("--ref", type=int, required=True, help="a keyframe of the row to register against")
    ap.add_argument("--targets", required=True, help="comma-separated frames to add keyframes at")
    ap.add_argument("--slice", default="0,0.5", help="u0,u1: part of the row to match, in anchor lengths")
    ap.add_argument("--min-score", type=float, default=0.5)
    args = ap.parse_args()

    path = args.boards or args.video.with_suffix(".boards.json")
    data = boards_io.load(path)
    row = next(b for b in data["boards"] if b["id"] == args.row)
    if "frames" not in row:
        boards_io.densify_all(args.video, data)
    u0, u1 = (float(v) for v in args.slice.split(","))

    q_ref = np.array(row["keyframes"][str(args.ref)], np.float32)
    W = int(np.linalg.norm(q_ref[1] - q_ref[0]) * PX)
    H = int(np.linalg.norm(q_ref[3] - q_ref[0]) * PX)
    unit = np.float32([[0, 0], [W, 0], [W, H], [0, H]])

    def straighten(frame: np.ndarray, quad: np.ndarray, ua: float, ub: float, va: float, vb: float) -> np.ndarray:
        """The row region u in [ua, ub], v in [va, vb] (anchor units), as a straight grayscale strip."""
        M = cv2.getPerspectiveTransform(unit, np.float32(quad))
        T = np.float32([[1, 0, ua * W], [0, 1, va * H], [0, 0, 1]])
        out = cv2.warpPerspective(frame, M @ T, (int((ub - ua) * W), int((vb - va) * H)),
                                  flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR, borderValue=0)
        return cv2.cvtColor(out, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # Template: the slice plus some stands/pitch above and below. Search: a wider window around it.
    tv0, tv1, su, sv0, sv1 = -0.4, 1.4, 0.25, -1.2, 2.2
    tmpl = straighten(grab(args.video, args.ref), q_ref, u0, u1, tv0, tv1)
    for k in (int(v) for v in args.targets.split(",")):
        if str(k) not in row["frames"]:
            print(f"f{k}: the row isn't tracked on this frame (outside its keyframe range), skipped")
            continue
        qk = np.array(row["frames"][str(k)], np.float32)
        img = straighten(grab(args.video, k), qk, u0 - su, u1 + su, sv0, sv1)
        best = (-1.0, 1.0, (0, 0))
        for s in np.arange(0.90, 1.1001, 0.01):
            r = cv2.matchTemplate(img, cv2.resize(tmpl, None, fx=s, fy=s), cv2.TM_CCOEFF_NORMED)
            _, v, _, loc = cv2.minMaxLoc(r)
            if v > best[0]:
                best = (v, s, loc)
        score, s, (lx, ly) = best
        if score < args.min_score:
            print(f"f{k}: match score {score:.2f} < {args.min_score}, skipped")
            continue
        # A maps template px into search-window px; ECC refines it from the template match.
        A = np.float32([[s, 0, lx], [0, s, ly]])
        try:
            _, A = cv2.findTransformECC(tmpl, img, A, cv2.MOTION_AFFINE,
                                        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5), None, 5)
        except cv2.error:
            print(f"f{k}: ECC didn't converge, using the template match")
        origin = np.array([(u0 - su) * W, sv0 * H])
        corners = [origin + A @ np.array([cx - u0 * W, cy - tv0 * H, 1.0]) for cx, cy in unit]
        quad = cv2.perspectiveTransform(np.float32(corners)[None], cv2.getPerspectiveTransform(unit, qk))[0]
        shift = (quad - qk).mean(axis=0)
        print(f"f{k}: score {score:.3f}, moved {shift[0]:+.1f}, {shift[1]:+.1f} px")
        row["keyframes"][str(k)] = [[round(float(x), 2), round(float(y), 2)] for x, y in quad]

    row["keyframes"] = dict(sorted(row["keyframes"].items(), key=lambda kv: int(kv[0])))
    print(boards_io.densify_all(args.video, data))
    boards_io.save(path, data)


if __name__ == "__main__":
    main()
