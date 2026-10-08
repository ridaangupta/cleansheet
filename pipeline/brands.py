"""Render fictional sponsor banners into assets/brands/.

Every brand here is invented. Never add a real company's name or logo.

Categories:
  gambling, alcohol  - what viewers can choose to hide
  neutral            - ordinary sponsors that stay on screen (negatives for the detector)
  replacement        - family-safe sponsors the app swaps in

Usage: python pipeline/brands.py
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "brands"
SIZE = (800, 200)  # 4:1, roughly the shape of a perimeter board

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


@dataclass(frozen=True)
class Brand:
    name: str
    category: str
    bg: str
    fg: str
    accent: str
    mark: str  # circle | diamond | star | wave | chevron


BRANDS = [
    Brand("BetNova", "gambling", "#2a0f4f", "#ffd447", "#ff5fa2", "star"),
    Brand("SpinStake", "gambling", "#111111", "#ff3b30", "#ffffff", "circle"),
    Brand("LuckLadder", "gambling", "#0b6b3a", "#ffffff", "#ffd447", "chevron"),
    Brand("Hopfield Lager", "alcohol", "#c77d1a", "#fff6e0", "#5a2d0c", "circle"),
    Brand("Marrow Rum", "alcohol", "#5c1020", "#f3d7a1", "#f3d7a1", "wave"),
    Brand("Northpeak Mobile", "neutral", "#0e3a8a", "#ffffff", "#5ec8ff", "chevron"),
    Brand("Velocet Sportswear", "neutral", "#f2f2f2", "#141414", "#ff6a00", "diamond"),
    Brand("Fernvale Market", "replacement", "#e9f7ec", "#1d6b35", "#7cc68d", "wave"),
    Brand("Quillo Juice", "replacement", "#ff8a00", "#ffffff", "#ffe066", "circle"),
    Brand("Tidewell Bank", "replacement", "#0a5c66", "#ffffff", "#9be7e0", "diamond"),
    Brand("Kitebox Toys", "replacement", "#ffffff", "#e0245e", "#1da1f2", "star"),
]


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def draw_mark(draw: ImageDraw.ImageDraw, kind: str, cx: float, cy: float, r: float, color: str) -> None:
    if kind == "circle":
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    elif kind == "diamond":
        draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=color)
    elif kind == "star":
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * 0.45
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        draw.polygon(pts, fill=color)
    elif kind == "chevron":
        w = r * 0.55
        draw.polygon([(cx - r, cy - r), (cx - r + w, cy - r), (cx + r, cy), (cx - r + w, cy + r), (cx - r, cy + r), (cx, cy)], fill=color)
    elif kind == "wave":
        for k in range(3):
            y = cy - r * 0.6 + k * r * 0.6
            draw.arc([cx - r, y - r * 0.4, cx, y + r * 0.4], 180, 360, fill=color, width=int(r * 0.22))
            draw.arc([cx, y - r * 0.4, cx + r, y + r * 0.4], 0, 180, fill=color, width=int(r * 0.22))


def render(brand: Brand) -> Image.Image:
    w, h = SIZE
    img = Image.new("RGB", SIZE, brand.bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, h - 18, w, h], fill=brand.accent)

    mark_r = h * 0.28
    mark_cx = 30 + mark_r
    draw_mark(draw, brand.mark, mark_cx, h / 2 - 6, mark_r, brand.accent)

    text_left = mark_cx + mark_r + 30
    max_w = w - text_left - 30
    size = 120
    while size > 20:
        font = load_font(size)
        x0, y0, x1, y1 = draw.textbbox((0, 0), brand.name, font=font)
        if x1 - x0 <= max_w and y1 - y0 <= h * 0.55:
            break
        size -= 4
    tx = text_left + (max_w - (x1 - x0)) / 2 - x0
    ty = (h - 18 - (y1 - y0)) / 2 - y0
    draw.text((tx, ty), brand.name, font=font, fill=brand.fg)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for brand in BRANDS:
        file = f"{slug(brand.name)}.png"
        render(brand).save(OUT_DIR / file)
        manifest.append({"name": brand.name, "category": brand.category, "file": file})
    (OUT_DIR / "brands.json").write_text(json.dumps({"size": list(SIZE), "brands": manifest}, indent=2) + "\n")
    print(f"wrote {len(manifest)} brands to {OUT_DIR}")


if __name__ == "__main__":
    main()
