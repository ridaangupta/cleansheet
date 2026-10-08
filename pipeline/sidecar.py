"""Python side of the sidecar track contract (see shared/sidecar/schema.json).

Usage: python pipeline/sidecar.py media/synth/sidecar.json   # validate a track
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "shared" / "sidecar" / "schema.json"

CATEGORIES = ("gambling", "alcohol", "neutral")


@dataclass
class SidecarObject:
    id: str
    kind: str  # "board" | "jersey"
    category: str
    quad: list[list[float]]  # TL, TR, BR, BL, normalized
    confidence: float
    brand: str | None = None
    bbox: list[float] | None = None  # [x, y, w, h], normalized, clipped to frame

    def to_json(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SidecarFrame:
    t: float
    objects: list[SidecarObject] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"t": round(self.t, 6), "objects": [o.to_json() for o in self.objects]}


@dataclass
class SidecarTrack:
    video_id: str
    fps: float
    width: int
    height: int
    source: str = "ground_truth"
    frames: list[SidecarFrame] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "version": 1,
            "video_id": self.video_id,
            "source": self.source,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "frames": [f.to_json() for f in self.frames],
        }

    def save(self, path: Path) -> None:
        data = self.to_json()
        validate(data)
        path.write_text(json.dumps(data, separators=(",", ":")))


def validate(data: dict) -> None:
    """Raise ValueError if `data` is not a valid sidecar track."""
    schema = json.loads(SCHEMA_PATH.read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        where = "/".join(str(p) for p in e.path) or "<root>"
        raise ValueError(f"{len(errors)} schema error(s); first at {where}: {e.message}")
    times = [f["t"] for f in data["frames"]]
    if any(b < a for a, b in zip(times, times[1:])):
        raise ValueError("frames are not sorted by t")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    validate(data)
    n_obj = sum(len(f["objects"]) for f in data["frames"])
    span = data["frames"][-1]["t"] - data["frames"][0]["t"] if data["frames"] else 0
    print(f"OK {path}: {len(data['frames'])} frames over {span:.2f}s, {n_obj} objects")


if __name__ == "__main__":
    main()
