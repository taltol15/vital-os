#!/usr/bin/env python3
"""Draw the Nocturne boot mark: a champagne V, point down, one stroke at a time."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
SIZE = 256
CHAMPAGNE = (198, 165, 106, 255)
WIDTH = 7

# Same proportions as branding/logo/vital-symbol.svg, without the ring.
# The point is the bottom vertex. The arms open upward. There is no bar under it.
LEFT = (72, 78)
POINT = (128, 186)
RIGHT = (184, 78)


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
    """Eight frames. 1–3 grow the left arm down to the point, 4–6 the right arm up, 7–8 add the dot."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    left = min(max(count, 0), 3) / 3
    right = min(max(count - 3, 0), 3) / 3
    _stroke(draw, LEFT, POINT, left)
    _stroke(draw, POINT, RIGHT, right)
    if count >= 7:
        radius = 6
        draw.ellipse(
            (POINT[0] - radius, POINT[1] - radius, POINT[0] + radius, POINT[1] + radius),
            fill=CHAMPAGNE,
        )
    return image


def main() -> None:
    for index in range(1, 9):
        frame(index).save(OUT / f"frame-{index:02d}.png")
    poster = Image.new("RGBA", (1280, 720), (12, 15, 20, 255))
    mark = frame(8).resize((300, 300), Image.Resampling.LANCZOS)
    poster.alpha_composite(mark, (490, 160))
    poster.convert("RGB").save(OUT / "boot-frame.png")


if __name__ == "__main__":
    main()
