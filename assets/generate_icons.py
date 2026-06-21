"""Generate the app icon in all needed formats from a single drawn source.

Produces:
  - icon.png   (512x512 master)
  - icon.ico   (Windows, multi-size)
  - icon.icns  (macOS, multi-size)

Run from anywhere:  python assets/generate_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent

# Palette (matches ui/styles.py).
ACCENT = (91, 142, 240, 255)     # #5b8ef0
WHITE = (240, 240, 240, 255)     # #f0f0f0
BG = (26, 26, 26, 255)           # #1a1a1a


def _rounded(draw: ImageDraw.ImageDraw, box, radius, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_master(size: int = 512) -> Image.Image:
    """Draw a speech-bubble-with-play-button icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 512.0  # scale factor relative to the 512 design

    # Rounded square background.
    _rounded(d, [0, 0, size, size], radius=int(112 * s), fill=ACCENT)

    # Speech bubble (rounded rect) with a tail.
    bx0, by0, bx1, by1 = 96 * s, 120 * s, 416 * s, 360 * s
    _rounded(d, [bx0, by0, bx1, by1], radius=int(48 * s), fill=WHITE)
    # Tail: a triangle pointing down-left from the bubble's bottom.
    d.polygon(
        [(170 * s, 352 * s), (170 * s, 432 * s), (250 * s, 352 * s)],
        fill=WHITE,
    )

    # Play triangle centered in the bubble.
    cx, cy = 256 * s, 240 * s
    tw, th = 70 * s, 84 * s
    d.polygon(
        [(cx - tw / 2, cy - th / 2), (cx - tw / 2, cy + th / 2), (cx + tw / 1.4, cy)],
        fill=ACCENT,
    )
    return img


def main() -> None:
    master = draw_master(512)
    png_path = ASSETS / "icon.png"
    master.save(png_path)
    print(f"wrote {png_path}")

    # Windows ICO (embed common sizes).
    ico_path = ASSETS / "icon.ico"
    master.save(
        ico_path,
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"wrote {ico_path}")

    # macOS ICNS. Pillow needs a square RGBA image; it generates the member
    # sizes itself. Wrapped in try/except since ICNS save support varies.
    icns_path = ASSETS / "icon.icns"
    try:
        master.resize((1024, 1024)).save(icns_path)
        print(f"wrote {icns_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not write .icns ({exc}). "
              f"On macOS, generate it with iconutil/sips from icon.png.")


if __name__ == "__main__":
    main()
