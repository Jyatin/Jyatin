#!/usr/bin/env python3
"""
Turns a headshot into a typing ASCII portrait SVG.

Usage:
    python3 scripts/generate_portrait.py path/to/photo.jpg

Requires:
    pip install pillow numpy opencv-python-headless rembg onnxruntime

Photo guidelines (garbage in, garbage out — ASCII draws with shadow, not detail):
  - side light at ~45 degrees, not flat frontal light
  - crop tight: chin to just above the hair
  - 1200px+ source resolution
  - plain background, slight angle (not dead-on)
"""
import sys
import numpy as np
from PIL import Image
import cv2

RAMP = " .`:-=+*cs#%@"          # 13 levels, blank end maps to background
COLS = 90
CHAR_W = 7.74                    # advance width baked into the grid — see README Part 1
FONT_SIZE = 12.9
STAGGER = 0.09                   # seconds between each row starting its wipe


def remove_background(img: Image.Image) -> Image.Image:
    from rembg import remove, new_session
    # u2net is the ~176MB model the guide references — the newer default
    # (bria-rmbg, ~1GB) can OOM on small CI/sandbox runners.
    session = new_session("u2net")
    cut = remove(img, session=session)        # RGBA, subject only
    bg = Image.new("RGBA", cut.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, cut).convert("RGB")


def to_ascii_grid(img: Image.Image):
    w, h = img.size
    rows = max(1, round(COLS * (h / w) * 0.48))
    small = img.resize((COLS, rows), Image.LANCZOS)
    arr = np.array(small.convert("L"))

    # bilateral filter: smooth skin, keep edges
    arr = cv2.bilateralFilter(arr, d=5, sigmaColor=50, sigmaSpace=50)

    # CLAHE: local contrast so a flatly-lit face doesn't render as one tone
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    arr = clahe.apply(arr)

    # darkening curve — without this the face washes out and loses features
    norm = (arr.astype(np.float32) / 255.0) ** 1.7
    arr = (norm * 255).astype(np.uint8)

    chars = []
    for row in arr:
        line = []
        for v in row:
            idx = round((v / 255) * (len(RAMP) - 1))
            # invert: bright pixel -> blank, dark pixel -> dense glyph
            line.append(RAMP[len(RAMP) - 1 - idx])
        chars.append(line)
    return chars, rows


def build_svg(chars, rows):
    row_len = len(chars[0])
    art_w = row_len * CHAR_W
    art_h = rows * (FONT_SIZE * 1.15)
    pad = 20
    w, h = art_w + pad * 2, art_h + pad * 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
        f'width="{w:.0f}" height="{h:.0f}">',
        "<defs>",
        # font-face goes here once you've generated ramp.woff2 — see README Part 4
        # '<style>@font-face{font-family:"ramp";src:url(data:font/woff2;base64,...) '
        # 'format("woff2");}</style>',
        "</defs>",
    ]

    for i, row in enumerate(chars):
        line = "".join(row).replace(" ", "\u00a0")  # preserve leading/trailing space
        y = pad + (i + 1) * (FONT_SIZE * 1.15)
        clip_id = f"wipe{i}"
        begin = f"{i * STAGGER:.2f}s"
        parts.append(
            f'<clipPath id="{clip_id}">'
            f'<rect x="{pad}" y="{y - FONT_SIZE}" width="0" height="{FONT_SIZE * 1.3:.1f}">'
            f'<animate attributeName="width" from="0" to="{art_w:.0f}" '
            f'dur="0.5s" begin="{begin}" fill="freeze"/>'
            f'</rect></clipPath>'
        )
        parts.append(
            f'<text x="{pad}" y="{y}" font-family="ramp, monospace" '
            f'font-size="{FONT_SIZE}" fill="var(--fgColor-default, #ccc)" '
            f'clip-path="url(#{clip_id})" xml:space="preserve">{line}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    if len(sys.argv) < 2:
        print("usage: generate_portrait.py <photo.jpg>")
        sys.exit(1)

    src = Image.open(sys.argv[1]).convert("RGB")
    cutout = remove_background(src)
    chars, rows = to_ascii_grid(cutout)
    svg = build_svg(chars, rows)

    out = "assets/portrait.svg"
    with open(out, "w") as f:
        f.write(svg)
    print(f"wrote {out}  ({rows} rows x {COLS} cols)")


if __name__ == "__main__":
    main()
