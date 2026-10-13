"""Score the board detector against a composited clip's ground-truth sidecar.

Runs the model on every --every'th frame of media/<clip>/composited.mp4 and matches predicted
boxes to ground-truth boards (greedy by IoU of the visible box, >= --iou). Reports:
  precision / recall           over all boards, and recall for hideable ones (gambling, alcohol)
  brand / category accuracy    among matched boards
  corner error (px)            matched boards' on-screen corners vs ground truth
  treatment split              hideable boards the app would replace (conf >= REPLACE_MIN_CONFIDENCE)
                               vs blur, vs miss entirely
Writes the numbers to media/<clip>/eval.detector.json or eval.sidecar.json.

Only quote numbers from a clip of a match the detector never saw (metro_ucv_01); the tachira
clips share a match with the training set.

The source is either detector weights (.pt: raw per-frame detections) or a model sidecar (.json
from detect.py: tracked and smoothed), so the two can be compared on the same clip.

Usage: python pipeline/eval_detector.py media/train/runs/boards/weights/best.pt metro_ucv_01 [--every 1]
       python pipeline/eval_detector.py media/metro_ucv_01/sidecar.model.json metro_ucv_01
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from videoio import read_frames

ROOT = Path(__file__).resolve().parent.parent
BRANDS_JSON = ROOT / "assets" / "brands" / "brands.json"
REPLACE_MIN_CONFIDENCE = 0.6  # app/src/cleansheet/config.ts
HIDEABLE = ("gambling", "alcohol")


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """IoU of two xyxy boxes."""
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(gt: list[np.ndarray], pred: list[np.ndarray], thresh: float) -> list[tuple[int, int]]:
    pairs = sorted(((iou(g, p), gi, pi) for gi, g in enumerate(gt) for pi, p in enumerate(pred)), reverse=True)
    used_g, used_p, out = set(), set(), []
    for v, gi, pi in pairs:
        if v < thresh:
            break
        if gi not in used_g and pi not in used_p:
            used_g.add(gi); used_p.add(pi); out.append((gi, pi))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="detector weights (.pt) or a model sidecar (.json)")
    ap.add_argument("clip", help="name under media/")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--conf", type=float, default=0.25, help="detections below this don't count at all")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--imgsz", type=int, default=1280)
    args = ap.parse_args()

    clip_dir = ROOT / "media" / args.clip
    track = json.loads((clip_dir / "sidecar.json").read_text())
    W, H = track["width"], track["height"]
    gt_frames = {round(f["t"] * track["fps"]): f["objects"] for f in track["frames"]}
    category = {b["name"]: b["category"] for b in json.loads(BRANDS_JSON.read_text())["brands"]}

    if args.source.suffix == ".json":
        model_track = json.loads(args.source.read_text())
        by_frame = {round(f["t"] * model_track["fps"]): f["objects"] for f in model_track["frames"]}

        def predict(i: int, _frame: np.ndarray):
            objs = by_frame.get(i, [])
            boxes = [np.array([o["bbox"][0] * W, o["bbox"][1] * H, (o["bbox"][0] + o["bbox"][2]) * W,
                               (o["bbox"][1] + o["bbox"][3]) * H]) for o in objs]
            return (boxes, [o["confidence"] for o in objs], [o.get("brand") for o in objs],
                    [np.array(o["quad"]) * [W, H] for o in objs])
    else:
        from ultralytics import YOLO

        model = YOLO(str(args.source))

        def predict(_i: int, frame: np.ndarray):
            r = model.predict(frame, imgsz=args.imgsz, conf=args.conf, device="mps", agnostic_nms=True, verbose=False)[0]
            return (list(r.boxes.xyxy.cpu().numpy()), list(r.boxes.conf.cpu().numpy()),
                    [model.names[int(c)] for c in r.boxes.cls.cpu().numpy()], list(r.keypoints.xy.cpu().numpy()))

    n_gt = n_pred = n_match = 0
    n_hide = n_hide_replace = n_hide_blur = 0
    brand_ok = cat_ok = 0
    corner_err: list[float] = []
    frames_scored = 0
    for i, frame in enumerate(read_frames(clip_dir / "composited.mp4")):
        if i % args.every or i not in gt_frames:
            continue
        frames_scored += 1
        gts = gt_frames[i]
        gt_boxes = [np.array([o["bbox"][0] * W, o["bbox"][1] * H, (o["bbox"][0] + o["bbox"][2]) * W,
                              (o["bbox"][1] + o["bbox"][3]) * H]) for o in gts]
        boxes, confs, brands, kpts = predict(i, frame)
        pairs = match(gt_boxes, boxes, args.iou)
        n_gt += len(gts); n_pred += len(boxes); n_match += len(pairs)
        matched = {gi: pi for gi, pi in pairs}
        for gi, o in enumerate(gts):
            hideable = o["category"] in HIDEABLE
            n_hide += hideable
            if gi not in matched:
                continue
            pi = matched[gi]
            brand = brands[pi]
            brand_ok += brand == o["brand"]
            cat_ok += category.get(brand) == o["category"]
            if hideable:
                if confs[pi] >= REPLACE_MIN_CONFIDENCE:
                    n_hide_replace += 1
                else:
                    n_hide_blur += 1
            for (gx, gy), (px, py) in zip(o["quad"], kpts[pi]):
                gx, gy = gx * W, gy * H
                if 0 <= gx <= W and 0 <= gy <= H:
                    corner_err.append(float(np.hypot(gx - px, gy - py)))

    ce = np.array(corner_err) if corner_err else np.array([np.nan])
    res = {
        "source": str(args.source), "clip": args.clip, "frames": frames_scored, "conf": args.conf, "iou": args.iou,
        "gt_boards": n_gt, "detections": n_pred, "matched": n_match,
        "precision": n_match / max(n_pred, 1), "recall": n_match / max(n_gt, 1),
        "brand_accuracy": brand_ok / max(n_match, 1), "category_accuracy": cat_ok / max(n_match, 1),
        "hideable_boards": n_hide, "hideable_recall": (n_hide_replace + n_hide_blur) / max(n_hide, 1),
        "hideable_replaced": n_hide_replace / max(n_hide, 1), "hideable_blurred": n_hide_blur / max(n_hide, 1),
        "corner_err_px": {"mean": float(np.nanmean(ce)), "median": float(np.nanmedian(ce)),
                          "p90": float(np.nanpercentile(ce, 90))},
    }
    (clip_dir / f"eval.{'sidecar' if args.source.suffix == '.json' else 'detector'}.json").write_text(json.dumps(res, indent=2) + "\n")
    print(f"{args.clip}: {frames_scored} frames, {n_gt} boards, {n_pred} detections")
    print(f"  precision {res['precision']:.3f}  recall {res['recall']:.3f}  "
          f"(hideable recall {res['hideable_recall']:.3f}: {res['hideable_replaced']:.3f} replaced, "
          f"{res['hideable_blurred']:.3f} blurred)")
    print(f"  brand acc {res['brand_accuracy']:.3f}  category acc {res['category_accuracy']:.3f}")
    print(f"  corner error px: mean {res['corner_err_px']['mean']:.1f}  median {res['corner_err_px']['median']:.1f}  "
          f"p90 {res['corner_err_px']['p90']:.1f}")


if __name__ == "__main__":
    main()
