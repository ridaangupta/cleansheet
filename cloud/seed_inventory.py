"""Seed the sponsor inventory: a replacement sponsor for every hideable board slot of each clip.

Reads media/<clip>/sidecar.json and sidecar.model.json (ground-truth and model track ids don't
collide, so both live under video#<video id>), and assigns the fictional replacement sponsors
from assets/brands/brands.json round-robin in left-to-right order of each board's first
appearance, so neighbouring boards differ. Writes with the AWS CLI (no boto3 dependency).

Usage: python cloud/seed_inventory.py [clip ...] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import sidecar  # noqa: E402

TABLE = "cleansheet-inventory"
HIDEABLE = ("gambling", "alcohol")
CLIPS = ("synth", "tachira_01", "tachira_02", "tachira_03", "tachira_04", "metro_ucv_01")


def slots(clip: str, sponsors: list[str]) -> tuple[str, dict[str, str]]:
    video_id, assigned = clip, {}
    for name in ("sidecar.json", "sidecar.model.json"):
        path = ROOT / "media" / clip / name
        if not path.exists():
            continue
        track = sidecar.load(path)
        video_id = track["video_id"]
        first_x: dict[str, float] = {}
        for f in track["frames"]:
            for o in f["objects"]:
                if o["category"] in HIDEABLE and o["id"] not in first_x:
                    first_x[o["id"]] = sum(x for x, _ in o["quad"]) / 4
        # Round-robin per sidecar: interleaving both tracks' ids would break the rotation.
        for k, bid in enumerate(sorted(first_x, key=first_x.get)):
            assigned[bid] = sponsors[k % len(sponsors)]
    return video_id, assigned


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips", nargs="*", default=list(CLIPS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--profile", default="cleansheet")
    args = ap.parse_args()

    brands = json.loads((ROOT / "assets" / "brands" / "brands.json").read_text())["brands"]
    sponsors = [b["name"] for b in brands if b["category"] == "replacement"]
    for clip in args.clips:
        video_id, assigned = slots(clip, sponsors)
        print(f"{clip}: {len(assigned)} slots under video#{video_id}")
        items = [{"PutRequest": {"Item": {"pk": {"S": f"video#{video_id}"}, "sk": {"S": f"board#{bid}"},
                                          "sponsor": {"S": s}}}} for bid, s in assigned.items()]
        for k in range(0, len(items), 25):  # BatchWriteItem takes at most 25
            if args.dry_run:
                continue
            out = subprocess.run(
                ["aws", "dynamodb", "batch-write-item", "--profile", args.profile, "--region", "us-east-2",
                 "--request-items", json.dumps({TABLE: items[k:k + 25]}), "--output", "json"],
                check=True, capture_output=True, text=True)
            if json.loads(out.stdout).get("UnprocessedItems"):
                sys.exit(f"{clip}: DynamoDB left items unprocessed; re-run")


if __name__ == "__main__":
    main()
