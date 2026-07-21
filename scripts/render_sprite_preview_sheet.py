#!/usr/bin/env python3
"""Render normalized sprite frames with optional root/socket overlays."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw


NUMBER_RE = re.compile(r"(\d+)")


def natural_key(path: Path) -> list[int | str]:
    parts: list[int | str] = []
    for chunk in NUMBER_RE.split(path.stem):
        if not chunk:
            continue
        parts.append(int(chunk) if chunk.isdigit() else chunk)
    parts.append(path.suffix)
    return parts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a labeled checkerboard preview from normalized sprite frames."
    )
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--gap", type=int, default=16)
    parser.add_argument("--meta", help="Optional sprite-meta.json; draws root and interaction sockets.")
    parser.add_argument("--scale", type=int, default=2, help="Integer preview scale. Default: 2.")
    return parser.parse_args()


def checkerboard(size: tuple[int, int], tile: int = 16) -> Image.Image:
    image = Image.new("RGBA", size, (244, 244, 244, 255))
    draw = ImageDraw.Draw(image)
    colors = ((244, 244, 244, 255), (220, 224, 228, 255))
    for top in range(0, size[1], tile):
        for left in range(0, size[0], tile):
            draw.rectangle(
                (left, top, min(size[0], left + tile), min(size[1], top + tile)),
                fill=colors[((left // tile) + (top // tile)) % 2],
            )
    return image


def draw_cross(draw: ImageDraw.ImageDraw, x: float, y: float, scale: int, color: tuple[int, ...]) -> None:
    px, py = round(x * scale), round(y * scale)
    radius = max(5, 4 * scale)
    draw.line((px - radius, py, px + radius, py), fill=color, width=max(1, scale))
    draw.line((px, py - radius, px, py + radius), fill=color, width=max(1, scale))


def main() -> None:
    args = parse_args()
    if args.columns < 1 or args.gap < 0 or args.scale < 1:
        raise SystemExit("--columns/--scale must be positive and --gap non-negative.")
    frames = sorted(Path(args.frames_dir).glob("[0-9][0-9].png"), key=natural_key)
    if not frames:
        raise SystemExit("No normalized NN.png frames found.")
    images = [Image.open(path).convert("RGBA") for path in frames]
    if len({image.size for image in images}) != 1:
        raise SystemExit("Normalized frames do not share one size.")

    meta = json.loads(Path(args.meta).read_text(encoding="utf-8")) if args.meta else None
    if meta and len(meta.get("frames", [])) != len(images):
        raise SystemExit("Metadata frame count does not match PNG frame count.")

    frame_w, frame_h = images[0].size
    scaled_w, scaled_h = frame_w * args.scale, frame_h * args.scale
    label_h = 24
    rows = math.ceil(len(images) / args.columns)
    sheet_w = args.columns * scaled_w + max(0, args.columns - 1) * args.gap
    sheet_h = rows * (scaled_h + label_h) + max(0, rows - 1) * args.gap
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(sheet)

    for index, (path, image) in enumerate(zip(frames, images)):
        row, col = divmod(index, args.columns)
        left = col * (scaled_w + args.gap)
        top = row * (scaled_h + label_h + args.gap)
        tile = checkerboard((scaled_w, scaled_h), tile=max(8, 16 * args.scale))
        tile.alpha_composite(image.resize((scaled_w, scaled_h), Image.Resampling.NEAREST))
        sheet.alpha_composite(tile, (left, top))
        draw.text((left + 4, top + scaled_h + 5), path.stem, fill=(32, 32, 32, 255))

        if meta:
            root = meta["root_anchor"]
            overlay = ImageDraw.Draw(sheet)
            draw_cross(overlay, left / args.scale + root["x"], top / args.scale + root["y"],
                       args.scale, (10, 100, 220, 255))
            for socket_index, (name, point) in enumerate(meta["frames"][index].get("sockets", {}).items()):
                px = left + point[0] * args.scale
                py = top + point[1] * args.scale
                radius = max(4, 3 * args.scale)
                overlay.ellipse((px - radius, py - radius, px + radius, py + radius),
                                outline=(220, 40, 90, 255), width=max(1, args.scale))
                overlay.text((px + radius + 2, py - radius - socket_index * 10), name,
                             fill=(80, 20, 40, 255))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"preview: {out} | frames={len(images)} columns={args.columns} scale={args.scale}")


if __name__ == "__main__":
    main()
