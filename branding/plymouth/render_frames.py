#!/usr/bin/env python3
"""Draw the Nocturne boot mark as it appears, one stroke at a time."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
SIZE = 256
CHAMPAGNE = (198, 165, 106, 255)
IVORY = (230, 211, 164, 255)
STEPS = (
    ((128, 46), (108, 112)),
    ((108, 112), (88, 176)),
    ((88, 176), (108, 176)),
    ((108, 176), (118, 144)),
    ((118, 144), (138, 144)),
    ((138, 144), (148, 176)),
    ((148, 176), (168, 176)),
    ((168, 176), (128, 46)),
)


def frame(count: int) -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for start, end in STEPS[:count]:
        draw.line((*start, *end), fill=CHAMPAGNE, width=8)
    if count >= len(STEPS):
        draw.line((120, 118, 136, 118), fill=IVORY, width=6)
        draw.ellipse((176, 64, 192, 80), fill=CHAMPAGNE)
    return image


def main() -> None:
    for index in range(1, len(STEPS) + 1):
        frame(index).save(OUT / f"frame-{index:02d}.png")
    poster = Image.new("RGBA", (1280, 720), (12, 15, 20, 255))
    mark = frame(len(STEPS)).resize((280, 280), Image.Resampling.LANCZOS)
    poster.alpha_composite(mark, (500, 160))
    draw = ImageDraw.Draw(poster)
    draw.line((500, 470, 780, 470), fill=CHAMPAGNE, width=3)
    poster.convert("RGB").save(OUT / "boot-frame.png")


if __name__ == "__main__":
    main()
