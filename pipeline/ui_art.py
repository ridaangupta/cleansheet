"""Generate the app's catalogue images from our own material, replacing the sports sample's CDN
images (which show real brands, e.g. Adidas kits).

  assets/ui/900x700/<n>.jpg        landscape heroes/covers: crops of our composited broadcast clips
  assets/ui/300x450/<n>.jpg        portrait posters: crops of the same clips
  assets/ui/250x250/<n>.jpg        square tiles: generated team badges
  assets/ui/profiles/<n>p.jpg      profile avatars: initials on a colour
  assets/ui/thumbnails/thumbnail-NN.jpg   team thumbnails: generated badges
  assets/ui/players/<n>.png        player/team logos (replaces robohash.org): initials badges
  assets/ui/loading.png            seek-bar thumbnail placeholder
  app/assets/image/SportsApp.png   app icon

Exactly the files the app's static data references are written (scanned from
app/src/api/*/staticData/*.json), so a URL never points at a missing image.

Only clips whose composites were checked to cover every real board are used (tachira_02, _03);
crops never upscale, so kit details stay illegible, and skip the top band (pixelated scorebug).
Fixed seed: the same images every run.

Usage: python pipeline/ui_art.py
"""

from __future__ import annotations

import colorsys
import random
import re
from pathlib import Path

import cv2
import numpy as np

from videoio import read_frames

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "ui"
CLIPS = ["tachira_02", "tachira_03"]
URL_PREFIX = "http://10.0.2.2:8787/assets/ui/"
FONT = cv2.FONT_HERSHEY_DUPLEX


def palette(i: int, s: float = 0.55, v: float = 0.62) -> tuple[int, int, int]:
    """Distinct, muted BGR colours by golden-ratio hue steps."""
    r, g, b = colorsys.hsv_to_rgb((i * 0.618034) % 1.0, s, v)
    return int(b * 255), int(g * 255), int(r * 255)


def grade(img: np.ndarray, rng: random.Random) -> np.ndarray:
    """Light per-image colour grade plus a bottom vignette, so tiles read as a set, not raw frames."""
    out = img.astype(np.float32)
    out *= np.array([rng.uniform(0.9, 1.1), rng.uniform(0.95, 1.05), rng.uniform(0.9, 1.1)], np.float32)
    h = out.shape[0]
    # 1.0 down to 45% of the height, then a smooth fade to 0.55 at the bottom.
    t = np.clip((np.arange(h, dtype=np.float32) / h - 0.45) / 0.55, 0, 1)
    out *= (1.0 - 0.45 * t * t)[:, None, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def sample_frames(n: int, rng: random.Random) -> list[np.ndarray]:
    frames = []
    for clip in CLIPS:
        frames += [f for i, f in enumerate(read_frames(ROOT / "media" / clip / "composited.mp4")) if i % 9 == 0]
    rng.shuffle(frames)
    return [frames[i % len(frames)] for i in range(n)]


def crop(frame: np.ndarray, w: int, h: int, rng: random.Random) -> np.ndarray:
    """Random crop of aspect w:h at >= target size (no upscaling), below the top 25%, resized down."""
    H, W = frame.shape[:2]
    y_min = int(H * 0.25)
    ch = min(H - y_min, int(W * h / w))
    ch = max(int(ch * rng.uniform(0.85, 1.0)), h)
    cw = int(ch * w / h)
    if cw > W:
        cw, ch = W, int(W * h / w)
    x = rng.randint(0, W - cw)
    y = rng.randint(y_min, max(y_min, H - ch))
    return cv2.resize(frame[y:y + ch, x:x + cw], (w, h), interpolation=cv2.INTER_AREA)


def badge(size: int, colour: tuple[int, int, int], shape: str, pattern: int) -> np.ndarray:
    """A text-free crest: shield or roundel in `colour`, with a stripe/chevron/band pattern."""
    img = np.full((size, size, 3), 24, np.uint8)
    c, r = size // 2, int(size * 0.42)
    mask = np.zeros((size, size), np.uint8)
    if shape == "shield":
        pts = np.array([[c - r, c - r], [c + r, c - r], [c + r, c + r // 4], [c, c + r], [c - r, c + r // 4]], np.int32)
        cv2.fillPoly(mask, [pts], 255, cv2.LINE_AA)
    else:
        cv2.circle(mask, (c, c), r, 255, -1, cv2.LINE_AA)
    body = np.zeros_like(img)
    body[:] = colour
    light = tuple(min(255, int(v * 1.5) + 40) for v in colour)
    t = max(4, size // 14)
    if pattern % 3 == 0:  # vertical stripes
        for x in range(c - r, c + r, 3 * t):
            cv2.rectangle(body, (x, 0), (x + t, size), light, -1)
    elif pattern % 3 == 1:  # chevron
        cv2.polylines(body, [np.array([[c - r, c - t], [c, c + r // 2], [c + r, c - t]], np.int32)], False, light, 2 * t, cv2.LINE_AA)
    else:  # diagonal band
        cv2.line(body, (c - r, c + r), (c + r, c - r), light, 2 * t, cv2.LINE_AA)
    a = (mask.astype(np.float32) / 255)[..., None]
    img = (img * (1 - a) + body * a).astype(np.uint8)
    edge = cv2.dilate(mask, np.ones((max(3, size // 40),) * 2, np.uint8)) - mask
    img[edge > 0] = (235, 235, 235)
    return img


def avatar(size: int, colour: tuple[int, int, int]) -> np.ndarray:
    """A person outline on a coloured disc (no initials, which wouldn't match the profile names)."""
    img = np.full((size, size, 3), 24, np.uint8)
    c = size // 2
    cv2.circle(img, (c, c), int(size * 0.45), colour, -1, cv2.LINE_AA)
    white = (245, 245, 245)
    cv2.circle(img, (c, int(c * 0.78)), int(size * 0.14), white, -1, cv2.LINE_AA)
    cv2.ellipse(img, (c, int(size * 0.78)), (int(size * 0.24), int(size * 0.17)), 0, 180, 360, white, -1, cv2.LINE_AA)
    return img


def referenced() -> list[str]:
    """Image paths under assets/ui/ that the app's static data points at."""
    names: set[str] = set()
    for f in (ROOT / "app" / "src" / "api").glob("*/staticData/*.json"):
        names.update(re.findall(re.escape(URL_PREFIX) + r'([^"]+)', f.read_text()))
    return sorted(names)


def main() -> None:
    rng = random.Random(23)
    names = referenced()
    photos = [n for n in names if n.startswith(("900x700/", "300x450/"))]
    frames = sample_frames(len(photos), rng)
    k = 0
    for i, name in enumerate(names):
        path = OUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        folder = name.split("/")[0] if "/" in name else ""
        if folder in ("900x700", "300x450"):
            w, h = (900, 700) if folder == "900x700" else (300, 450)
            img = grade(crop(frames[k], w, h, rng), rng)
            k += 1
        elif folder == "profiles":
            img = avatar(200, palette(i + 7, 0.45, 0.7))
        elif folder == "players":
            img = badge(100, palette(i + 11, 0.5, 0.65), "circle", i)
        else:  # 250x250 tiles, team thumbnails, and root-level team images
            img = badge(250, palette(i), "shield" if i % 2 else "circle", i // 2)
        params = [cv2.IMWRITE_JPEG_QUALITY, 88] if path.suffix in (".jpg", ".jpeg") else []
        cv2.imwrite(str(path), img, params)

    cv2.imwrite(str(OUT / "loading.png"), np.full((180, 320, 3), 30, np.uint8))

    icon = np.zeros((512, 512, 3), np.uint8)
    icon[:] = (40, 30, 18)
    cv2.circle(icon, (256, 220), 120, (246, 125, 47), -1, cv2.LINE_AA)
    cv2.rectangle(icon, (166, 200), (346, 240), (255, 255, 255), -1, cv2.LINE_AA)
    (tw, _), _ = cv2.getTextSize("Cleansheet", FONT, 2.0, 4)
    cv2.putText(icon, "Cleansheet", (256 - tw // 2, 430), FONT, 2.0, (255, 255, 255), 4, cv2.LINE_AA)
    cv2.imwrite(str(ROOT / "app" / "assets" / "image" / "SportsApp.png"), icon)
    print(f"wrote {len(names) + 1} images to {OUT} and the app icon")


if __name__ == "__main__":
    main()
