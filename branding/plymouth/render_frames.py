#!/usr/bin/env python3
"""Draw the Nocturne boot mark: an open champagne V, one stroke at a time."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
SIZE = 256
CHAMPAGNE = (198, 165, 106, 255)
IVORY = (246, 241, 231, 255)
WIDTH = 7

# The same proportions as branding/logo/vital-symbol.svg, without the ring.
# The baseline sits under the feet so the mark cannot be read as an A.
APEX = (128, 74)
LEFT = (74, 168)
RIGHT = (182, 168)
BASE_A = (102, 190)
BASE_B = (154, 190)


def _lerp(start: tuple[int, int], end: tuple[int, int], amount: float) -> tuple[int, int]:
    return (
        int(start[0] + (end[0] - start[0]) * amount),
        int(start[1] + (end[1] - start[1]) * amount),
    )


def _stroke(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], amount: float) -> None:
    if amount <= 0:
        return
    draw.line((*start, *_lerp(start, end, min(amount, 1.0))), fill=CHAMPAGNE, width=WIDTH)


def frame(count: int) -> Image.Image:
    """Eight cumulative frames. 1–3 grow the left arm, 4–6 the right, 7 the baseline, 8 the dot."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    left = min(max(count, 0) / 3, 1)
    right = min(max(count - 3, 0) / 3, 1)
    _stroke(draw, APEX, LEFT, left)
    _stroke(draw, APEX, RIGHT, right)
    if count >= 1:
        draw.ellipse((APEX[0] - 4, APEX[1] - 4, APEX[0] + 4, APEX[1] + 4), fill=CHAMPAGNE)
    if count >= 7:
        draw.line((*BASE_A, *BASE_B), fill=IVORY, width=4)
    if count >= 8:
        draw.ellipse((APEX[0] - 7, APEX[1] - 22, APEX[0] + 7, APEX[1] - 8), fill=CHAMPAGNE)
    return image


def main() -> None:
    for index in range(1, 9):
        frame(index).save(OUT / f"frame-{index:02d}.png")
    poster = Image.new("RGBA", (1280, 720), (12, 15, 20, 255))
    mark = frame(8).resize((300, 300), Image.Resampling.LANCZOS)
    poster.alpha_composite(mark, (490, 150))
    draw = ImageDraw.Draw(poster)
    draw.line((520, 500, 760, 500), fill=CHAMPAGNE, width=3)
    poster.convert("RGB").save(OUT / "boot-frame.png")


if __name__ == "__main__":
    main()
