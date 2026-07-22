#!/usr/bin/env python3
"""Build a transparent, game-style-aware edit canvas from an approved seed frame.

The seed occupies the first slot of one horizontal animation strip.  Remaining
slots stay transparent for a single whole-strip image edit.  This script only
prepares production input; it never decides which animation the game needs.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


RESAMPLING = {
    "nearest": Image.Resampling.NEAREST,
    "lanczos": Image.Resampling.LANCZOS,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Place an approved seed into slot 01 of a transparent horizontal strip canvas."
    )
    parser.add_argument("--seed", required=True, help="Approved transparent seed-frame PNG.")
    parser.add_argument("--out", required=True, help="Output edit-canvas PNG.")
    parser.add_argument("--frames", type=int, default=4, help="Horizontal slot count. Default: 4.")
    parser.add_argument("--slot-width", type=int, default=256)
    parser.add_argument("--slot-height", type=int, default=256)
    parser.add_argument("--canvas-width", type=int, default=1024)
    parser.add_argument("--canvas-height", type=int, default=1024)
    parser.add_argument(
        "--resample",
        choices=sorted(RESAMPLING),
        default="lanczos",
        help="Use nearest for pixel art; lanczos for illustration/vector/painted art.",
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.08,
        help="Fractional padding inside each slot. Default: 0.08.",
    )
    return parser.parse_args()


def alpha_crop(image: Image.Image) -> Image.Image:
    box = image.getchannel("A").getbbox()
    if box is None:
        raise SystemExit("Seed frame contains no visible pixels.")
    return image.crop(box)


def validate(args: argparse.Namespace) -> None:
    values = (args.frames, args.slot_width, args.slot_height, args.canvas_width, args.canvas_height)
    if any(value < 1 for value in values):
        raise SystemExit("Frame count and dimensions must be positive.")
    if not 0 <= args.padding < 0.45:
        raise SystemExit("--padding must be in [0, 0.45).")
    if args.frames * args.slot_width > args.canvas_width or args.slot_height > args.canvas_height:
        raise SystemExit("Horizontal frame slots do not fit inside the requested canvas.")


def main() -> None:
    args = parse_args()
    validate(args)
    seed = alpha_crop(Image.open(args.seed).convert("RGBA"))

    pad_x = round(args.slot_width * args.padding)
    pad_y = round(args.slot_height * args.padding)
    usable_w = args.slot_width - 2 * pad_x
    usable_h = args.slot_height - 2 * pad_y
    scale = min(usable_w / seed.width, usable_h / seed.height)
    size = (max(1, round(seed.width * scale)), max(1, round(seed.height * scale)))
    seed = seed.resize(size, RESAMPLING[args.resample])

    canvas = Image.new("RGBA", (args.canvas_width, args.canvas_height), (0, 0, 0, 0))
    strip_width = args.frames * args.slot_width
    strip_left = (args.canvas_width - strip_width) // 2
    strip_top = (args.canvas_height - args.slot_height) // 2
    x = strip_left + (args.slot_width - seed.width) // 2
    y = strip_top + args.slot_height - pad_y - seed.height
    canvas.alpha_composite(seed, (x, y))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(
        f"seed canvas: {out} | frames={args.frames} slots={args.slot_width}x{args.slot_height} "
        f"canvas={args.canvas_width}x{args.canvas_height} resample={args.resample}"
    )


if __name__ == "__main__":
    main()
