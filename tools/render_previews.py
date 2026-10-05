#!/usr/bin/env python3
"""Rasterize Vital OS branding and compose preview frames.

The previews are drawings of the real SVG assets, not photographs of a
running desktop. A booted ISO can replace them later.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "branding"
SHOTS = ROOT / "docs" / "screenshots"

GRAPHITE = (7, 8, 11, 255)
GRAPHITE_900 = (14, 17, 22, 255)
GRAPHITE_800 = (22, 26, 33, 255)
IVORY = (246, 241, 231, 255)
CHAMPAGNE = (198, 165, 106, 255)
MUTED = (138, 132, 120, 255)


def die(message: str) -> None:
    print(f"render_previews: {message}", file=sys.stderr)
    raise SystemExit(1)


def rsvg(source: Path, dest: Path, width: int | None = None, height: int | None = None) -> None:
    tool = shutil.which("rsvg-convert")
    if tool is None:
        die("rsvg-convert is not installed (package librsvg2-bin)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [tool, "-o", str(dest)]
    if width:
        command.extend(["-w", str(width)])
    if height:
        command.extend(["-h", str(height)])
    command.append(str(source))
    subprocess.check_call(command)


def find_font(*needles: str) -> Path | None:
    roots = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".ttf", ".otf"}:
                continue
            name = path.name.lower()
            if all(needle.lower() in name for needle in needles):
                return path
    return None


def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    if bold:
        path = find_font("inter", "bold") or find_font("inter", "medium") or find_font("inter")
    else:
        path = find_font("inter", "regular") or find_font("inter")
    if path is None:
        return ImageFont.load_default()
    return ImageFont.truetype(str(path), size=size)


def paste_center(base: Image.Image, overlay: Image.Image, cx: int, cy: int) -> None:
    base.alpha_composite(overlay, (cx - overlay.width // 2, cy - overlay.height // 2))


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def compose_desktop(wallpaper: Image.Image, symbol: Image.Image, dest: Path) -> None:
    image = wallpaper.convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    draw.rectangle((0, 0, width, 36), fill=(9, 11, 14, 230))
    mark = symbol.resize((22, 22), Image.Resampling.LANCZOS)
    image.alpha_composite(mark, (16, 7))
    font = load_font(15)
    small = load_font(13)
    clock = "Mon 5 Oct    09:41"
    bbox = draw.textbbox((0, 0), clock, font=font)
    draw.text(((width - (bbox[2] - bbox[0])) / 2, 8), clock, font=font, fill=IVORY)
    draw.text((width - 168, 9), "Wi-Fi     100%", font=small, fill=IVORY)

    dock_w, dock_h = 560, 74
    dock_x = (width - dock_w) // 2
    dock_y = height - 96
    rounded(draw, (dock_x, dock_y, dock_x + dock_w, dock_y + dock_h), 22, (14, 17, 22, 190))
    draw.rounded_rectangle(
        (dock_x, dock_y, dock_x + dock_w, dock_y + dock_h),
        radius=22,
        outline=(198, 165, 106, 90),
        width=1,
    )
    for index in range(6):
        ix = dock_x + 28 + index * 86
        iy = dock_y + 14
        rounded(draw, (ix, iy, ix + 46, iy + 46), 12, (30, 36, 46, 255))
        if index == 0:
            mini = symbol.resize((28, 28), Image.Resampling.LANCZOS)
            image.alpha_composite(mini, (ix + 9, iy + 9))
        draw.ellipse((ix + 18, iy + 50, ix + 26, iy + 56), fill=CHAMPAGNE if index < 3 else (0, 0, 0, 0))

    win_w, win_h = 760, 460
    win_x = (width - win_w) // 2
    win_y = 120
    rounded(draw, (win_x, win_y, win_x + win_w, win_y + win_h), 22, (16, 19, 24, 235))
    draw.rounded_rectangle(
        (win_x, win_y, win_x + win_w, win_y + win_h),
        radius=22,
        outline=(198, 165, 106, 70),
        width=1,
    )
    hero = symbol.resize((96, 96), Image.Resampling.LANCZOS)
    image.alpha_composite(hero, (win_x + win_w // 2 - 48, win_y + 70))
    title_font = load_font(40, bold=True)
    body_font = load_font(18)
    title = "Vital OS"
    tb = draw.textbbox((0, 0), title, font=title_font)
    draw.text((win_x + (win_w - (tb[2] - tb[0])) / 2, win_y + 190), title, font=title_font, fill=IVORY)
    lines = [
        "A quiet desktop. Graphite, ivory, champagne.",
        "Version 0.1.0  ·  based on Ubuntu 24.04 LTS",
    ]
    y = win_y + 260
    for line in lines:
        lb = draw.textbbox((0, 0), line, font=body_font)
        color = CHAMPAGNE if "Version" in line else MUTED
        draw.text((win_x + (win_w - (lb[2] - lb[0])) / 2, y), line, font=body_font, fill=color)
        y += 32
    image.convert("RGB").save(dest, "PNG", optimize=True)


def compose_gdm(wallpaper: Image.Image, symbol: Image.Image, dest: Path) -> None:
    image = wallpaper.convert("RGBA")
    veil = Image.new("RGBA", image.size, (7, 8, 11, 70))
    image.alpha_composite(veil)
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    card_w, card_h = 420, 460
    x = (width - card_w) // 2
    y = (height - card_h) // 2 - 10
    rounded(draw, (x, y, x + card_w, y + card_h), 28, (14, 17, 22, 210))
    draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=28, outline=(198, 165, 106, 80), width=1)
    hero = symbol.resize((88, 88), Image.Resampling.LANCZOS)
    image.alpha_composite(hero, (width // 2 - 44, y + 36))
    font = load_font(22, bold=True)
    small = load_font(16)
    name = "Vital Live"
    nb = draw.textbbox((0, 0), name, font=font)
    draw.text((width / 2 - (nb[2] - nb[0]) / 2, y + 150), name, font=font, fill=IVORY)
    field = (x + 48, y + 220, x + card_w - 48, y + 268)
    draw.rounded_rectangle(field, radius=12, fill=(7, 8, 11, 180), outline=CHAMPAGNE, width=1)
    draw.text((field[0] + 16, field[1] + 12), "Password", font=small, fill=MUTED)
    banner = "Vital OS 0.1.0"
    bb = draw.textbbox((0, 0), banner, font=small)
    draw.text((width / 2 - (bb[2] - bb[0]) / 2, y + card_h - 48), banner, font=small, fill=CHAMPAGNE)
    image.convert("RGB").save(dest, "PNG", optimize=True)


def compose_plymouth(symbol: Image.Image, wordmark: Image.Image, dest: Path, logo_dest: Path) -> None:
    canvas = Image.new("RGBA", (1920, 1080), GRAPHITE)
    logo = Image.new("RGBA", (640, 280), (0, 0, 0, 0))
    mark = symbol.resize((120, 120), Image.Resampling.LANCZOS)
    logo.alpha_composite(mark, ((640 - mark.width) // 2, 8))
    wm = wordmark.resize((420, int(wordmark.height * 420 / wordmark.width)), Image.Resampling.LANCZOS)
    logo.alpha_composite(wm, ((640 - wm.width) // 2, 150))
    logo.save(logo_dest, "PNG")
    paste_center(canvas, logo, 960, 500)
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((860, 690, 980, 693), fill=CHAMPAGNE)
    draw.rectangle((980, 690, 1060, 693), fill=(198, 165, 106, 50))
    canvas.convert("RGB").save(dest, "PNG", optimize=True)


def export_assets(export_dir: Path, shots: bool) -> None:
    export_dir.mkdir(parents=True, exist_ok=True)
    if shots:
        SHOTS.mkdir(parents=True, exist_ok=True)

    symbol_svg = BRAND / "logo" / "vital-symbol.svg"
    word_svg = BRAND / "logo" / "vital-wordmark.svg"
    lock_svg = BRAND / "logo" / "vital-lockup.svg"
    wall_svg = BRAND / "wallpapers" / "nocturne.svg"
    arc_svg = BRAND / "wallpapers" / "nocturne-arc.svg"

    symbol = export_dir / "symbol-512.png"
    rsvg(symbol_svg, symbol, width=512)
    for size, name in ((256, "symbol-256.png"), (128, "symbol-128.png"), (48, "symbol-48.png"), (192, "gdm-logo.png")):
        rsvg(symbol_svg, export_dir / name, width=size)
    rsvg(word_svg, export_dir / "wordmark.png", width=900)
    rsvg(lock_svg, export_dir / "lockup.png", width=1200)
    rsvg(wall_svg, export_dir / "wallpaper-nocturne.png", width=1920, height=1080)
    rsvg(arc_svg, export_dir / "wallpaper-arc.png", width=1920, height=1080)
    shutil.copyfile(export_dir / "wallpaper-nocturne.png", export_dir / "lock-background.png")
    shutil.copyfile(export_dir / "wallpaper-nocturne.png", export_dir / "grub-background.png")

    progress = Image.new("RGBA", (64, 4), CHAMPAGNE)
    progress.save(export_dir / "plymouth-progress.png")

    symbol_img = Image.open(symbol).convert("RGBA")
    word_img = Image.open(export_dir / "wordmark.png").convert("RGBA")
    wall = Image.open(export_dir / "wallpaper-nocturne.png").convert("RGBA")

    compose_plymouth(symbol_img, word_img, export_dir / "plymouth-frame.png", export_dir / "plymouth-logo.png")
    compose_gdm(wall, symbol_img, export_dir / "gdm-frame.png")
    compose_desktop(wall, symbol_img, export_dir / "desktop-frame.png")

    font = find_font("inter", "regular") or find_font("inter")
    if font and shutil.which("grub-mkfont"):
        subprocess.check_call(
            ["grub-mkfont", "-o", str(export_dir / "inter.pf2"), "-s", "16", str(font)]
        )

    if shots:
        pairs = {
            "symbol.png": symbol,
            "wordmark.png": export_dir / "wordmark.png",
            "lockup.png": export_dir / "lockup.png",
            "wallpaper.png": export_dir / "wallpaper-nocturne.png",
            "wallpaper-arc.png": export_dir / "wallpaper-arc.png",
            "plymouth.png": export_dir / "plymouth-frame.png",
            "gdm.png": export_dir / "gdm-frame.png",
            "desktop.png": export_dir / "desktop-frame.png",
        }
        for name, source in pairs.items():
            shutil.copyfile(source, SHOTS / name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, help="Directory for ISO build assets")
    parser.add_argument("--skip-docs", action="store_true", help="Do not write docs/screenshots")
    args = parser.parse_args()
    export_dir = args.export or (ROOT / "build" / "work" / "brand")
    export_assets(export_dir, shots=not args.skip_docs)
    print(f"Rendered branding assets in {export_dir}")
    if not args.skip_docs:
        print(f"Wrote previews to {SHOTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
