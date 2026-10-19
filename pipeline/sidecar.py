"""Python side of the sidecar track contract (see shared/sidecar/schema.json).

Writers build SidecarFrames of full SidecarObjects; save() stores each track's attributes once
(`tracks`) and only id + quad per frame. Readers use load(), which joins them back.

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
TRACK_FIELDS = ("kind", "category", "brand", "confidence")
DECIMALS = 4  # normalized coordinates: 1e-4 is ~0.13 px at 1280 wide


@dataclass
class SidecarObject:
    id: str
    kind: str  # "board" | "jersey"
    category: str
    quad: list[list[float]]  # TL, TR, BR, BL, normalized
    confidence: float  # one value per track
    brand: str | None = None


@dataclass
class SidecarFrame:
    t: float
    objects: list[SidecarObject] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"t": round(self.t, 6), "objects": [
            {"id": o.id, "quad": [[round(float(x), DECIMALS), round(float(y), DECIMALS)] for x, y in o.quad]}
            for o in self.objects]}


@dataclass
class SidecarTrack:
    video_id: str
    fps: float
    width: int
    height: int
    source: str = "ground_truth"
    frames: list[SidecarFrame] = field(default_factory=list)

    def to_json(self) -> dict:
        tracks: dict[str, dict] = {}
        for f in self.frames:
            for o in f.objects:
                info = {k: v for k, v in asdict(o).items() if k in TRACK_FIELDS and v is not None}
                if tracks.setdefault(o.id, info) != info:
                    raise ValueError(f"track {o.id} changes its attributes: {tracks[o.id]} vs {info}")
        return {
            "version": 2,
            "video_id": self.video_id,
            "source": self.source,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "tracks": tracks,
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
    orphans = {o["id"] for f in data["frames"] for o in f["objects"]} - data["tracks"].keys()
    if orphans:
        raise ValueError(f"object ids missing from tracks: {sorted(orphans)[:5]}")


def load(path: Path) -> dict:
    """A sidecar with every frame's objects joined with their track's attributes (like v1 files)."""
    data = json.loads(Path(path).read_text())
    validate(data)
    for f in data["frames"]:
        f["objects"] = [{**data["tracks"][o["id"]], **o} for o in f["objects"]]
    return data


def visible_bbox(quad: list[list[float]]) -> list[float]:
    """[x, y, w, h] of the part of a normalized quad inside the frame."""
    xs = [min(max(x, 0.0), 1.0) for x, _ in quad]
    ys = [min(max(y, 0.0), 1.0) for _, y in quad]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


MAX_FORESHORTENING = 2.0  # mirrors homography.ts: real boards stay under ~1.2


def foreshortening(quad) -> float:
    """Largest over smallest projective weight of the unit square -> quad homography over its corners
    (1 = no perspective, inf = the plane folds through the horizon). Same as homography.ts."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = [(float(x), float(y)) for x, y in quad]
    sx, sy = x0 - x1 + x2 - x3, y0 - y1 + y2 - y3
    den = (x1 - x2) * (y3 - y2) - (x3 - x2) * (y1 - y2)
    if den == 0:
        return float("inf")
    g = (sx * (y3 - y2) - (x3 - x2) * sy) / den
    h = ((x1 - x2) * sy - sx * (y1 - y2)) / den
    ws = [1.0, g + 1, g + h + 1, h + 1]
    lo, hi = min(ws), max(ws)
    return hi / lo if lo > 0 else float("inf")


def is_renderable(quad) -> bool:
    """Convex and not extremely foreshortened (homography.ts isRenderableQuad): anything else is a
    detector error that a warp draws as a triangle across the screen."""
    sign = 0.0
    for i in range(4):
        a, b, c = quad[i], quad[(i + 1) % 4], quad[(i + 2) % 4]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) < 1e-9 or (sign and (cross > 0) != (sign > 0)):
            return False
        sign = sign or cross
    return foreshortening(quad) <= MAX_FORESHORTENING


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    validate(data)
    n_obj = sum(len(f["objects"]) for f in data["frames"])
    span = data["frames"][-1]["t"] - data["frames"][0]["t"] if data["frames"] else 0
    print(f"OK {path}: {len(data['frames'])} frames over {span:.2f}s, {len(data['tracks'])} tracks, {n_obj} objects")


if __name__ == "__main__":
    main()
