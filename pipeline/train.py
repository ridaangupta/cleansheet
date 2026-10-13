"""Train the board detector: YOLO pose with 4 corner keypoints (TL, TR, BR, BL) per board.

Builds media/train/<run>/ from the per-clip datasets composite.py writes (media/<clip>/dataset),
symlinking images and labels into train/ and val/ splits, writes data.yaml, and trains on MPS.
Class = brand (classes.txt from composite.py, the same for every clip); the category comes from
the brand. Horizontal flips are off: they mirror the brand text.

Validation is a clip from a training match (early stopping only). The honest numbers come from a
clip of a different match, measured with eval_detector.py, never from this val split.

Every board slot in a clip shows one brand for the whole clip, so a single composite lets the
model learn "this spot = this brand". Re-composite training clips with other --seed values
into media/seeds/<clip>_s<seed> (see `make dataset`) so the same boards carry different brands.

Usage: python pipeline/train.py --train synth tachira_01 tachira_02 tachira_04 --val tachira_03
         [--model yolo11n-pose.pt] [--epochs 60] [--imgsz 1280] [--name boards]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "media"


def link_split(clips: list[str], dest: Path) -> int:
    for sub in ("images", "labels"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    n = 0
    for clip in clips:
        src = MEDIA / clip / "dataset"
        if not (src / "images").is_dir():
            raise SystemExit(f"{src} missing: run composite.py on footage/{clip}.mp4 first")
        for img in sorted((src / "images").glob("*.jpg")):
            for sub, path in (("images", img), ("labels", src / "labels" / f"{img.stem}.txt")):
                # Prefixed with the dataset dir: seed variants of one clip share image names.
                link = dest / sub / f"{clip.replace('/', '_')}__{path.name}"
                if not link.exists():
                    os.symlink(path, link)
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", nargs="+", required=True,
                    help="dataset dirs under media/: clip names, or seed variants like seeds/tachira_01_s11")
    ap.add_argument("--val", nargs="+", required=True)
    ap.add_argument("--model", default="yolo11n-pose.pt")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=1280, help="the far rows are ~10 px tall at 720p; don't shrink")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--name", default="boards")
    args = ap.parse_args()

    run_dir = MEDIA / "train" / args.name
    n_train = link_split(args.train, run_dir / "train")
    n_val = link_split(args.val, run_dir / "val")
    classes = (MEDIA / args.train[0] / "dataset" / "classes.txt").read_text().split("\n")
    classes = [c for c in classes if c]
    yaml = [f"path: {run_dir}", "train: train/images", "val: val/images",
            "kpt_shape: [4, 3]", "flip_idx: [1, 0, 3, 2]", "names:"]
    yaml += [f"  {i}: {name}" for i, name in enumerate(classes)]
    (run_dir / "data.yaml").write_text("\n".join(yaml) + "\n")
    print(f"{n_train} train / {n_val} val images, {len(classes)} classes -> {run_dir / 'data.yaml'}")

    from ultralytics import YOLO  # slow import; keep --help fast

    model = YOLO(args.model)
    model.train(
        data=str(run_dir / "data.yaml"), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        device="mps", project=str(MEDIA / "train" / "runs"), name=args.name, exist_ok=True,
        fliplr=0.0, mosaic=1.0, close_mosaic=10, degrees=0.0, scale=0.3, translate=0.1,
        hsv_h=0.01, hsv_s=0.5, hsv_v=0.4, patience=20, workers=4, plots=True,
    )


if __name__ == "__main__":
    main()
