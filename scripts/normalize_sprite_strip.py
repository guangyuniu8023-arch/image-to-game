#!/usr/bin/env python3
"""Normalize a horizontal animation strip with shared scale and root anchor.

Optional interaction sockets are transformed from raw per-slot coordinates into
the normalized game frames.  Root alignment and interaction sockets are kept
separate: the character root stays fixed while a ball/weapon/hand socket may
move across an action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage


RESAMPLING = {
    "nearest": Image.Resampling.NEAREST,
    "lanczos": Image.Resampling.LANCZOS,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split and normalize one horizontal sprite strip into fixed game frames."
    )
    parser.add_argument("--input", required=True, help="Raw horizontal strip PNG.")
    parser.add_argument("--out-dir", required=True, help="Output directory for numbered frames.")
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--frame-width", type=int, default=256)
    parser.add_argument("--frame-height", type=int, default=256)
    parser.add_argument("--anchor", help="Optional approved seed frame used in shared-scale calculation.")
    parser.add_argument("--lock-frame1", action="store_true", help="Replace frame 01 with the seed.")
    parser.add_argument("--resample", choices=sorted(RESAMPLING), default="lanczos")
    parser.add_argument("--alpha-threshold", type=int, default=8)
    parser.add_argument(
        "--component-min-ratio",
        type=float,
        default=0.0,
        help=(
            "Optional per-slot cleanup: remove disconnected alpha components smaller than this "
            "fraction of the largest component. Use 0.02 for minor neighboring-frame bleed; "
            "default 0 keeps every component."
        ),
    )
    parser.add_argument("--padding", type=float, default=0.06)
    parser.add_argument(
        "--socket-map",
        help=(
            "Optional JSON: {\"sockets\":{\"ball\":[[x,y], ...]}}; coordinates are local "
            "to each raw horizontal slot."
        ),
    )
    parser.add_argument("--meta-out", help="Metadata JSON path; defaults to <out-dir>/sprite-meta.json.")
    return parser.parse_args()


def content_box(image: Image.Image, threshold: int) -> tuple[int, int, int, int] | None:
    alpha = image.getchannel("A").point(lambda value: 255 if value > threshold else 0)
    return alpha.getbbox()


def filter_components(image: Image.Image, threshold: int, min_ratio: float) -> Image.Image:
    if min_ratio <= 0:
        return image
    array = np.array(image.convert("RGBA"))
    opaque = array[:, :, 3] > threshold
    labels, count = ndimage.label(opaque)
    if count <= 1:
        return image
    sizes = ndimage.sum(opaque, labels, range(1, count + 1))
    biggest = float(max(sizes))
    keep_labels = [index for index, size in enumerate(sizes, start=1) if size >= biggest * min_ratio]
    keep = np.isin(labels, keep_labels)
    array[~keep, 3] = 0
    return Image.fromarray(array, "RGBA")


def split_strip(strip: Image.Image, count: int) -> list[Image.Image]:
    step = strip.width / count
    return [
        strip.crop((round(index * step), 0, round((index + 1) * step), strip.height))
        for index in range(count)
    ]


def load_socket_map(path: str | None, frames: int) -> dict[str, list[list[float]]]:
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    sockets = payload.get("sockets", {})
    if not isinstance(sockets, dict):
        raise SystemExit("socket-map.sockets must be an object.")
    for name, points in sockets.items():
        if not isinstance(points, list) or len(points) != frames:
            raise SystemExit(f"Socket {name!r} must provide exactly {frames} points.")
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise SystemExit(f"Socket {name!r} contains a non-[x,y] point.")
    return sockets


def validate(args: argparse.Namespace) -> None:
    if args.frames < 1 or args.frame_width < 1 or args.frame_height < 1:
        raise SystemExit("Frame count and dimensions must be positive.")
    if args.lock_frame1 and not args.anchor:
        raise SystemExit("--lock-frame1 requires --anchor.")
    if not 0 <= args.padding < 0.45:
        raise SystemExit("--padding must be in [0, 0.45).")
    if not 0 <= args.component_min_ratio < 1:
        raise SystemExit("--component-min-ratio must be in [0, 1).")


def main() -> None:
    args = parse_args()
    validate(args)
    strip = Image.open(args.input).convert("RGBA")
    slots = [
        filter_components(slot, args.alpha_threshold, args.component_min_ratio)
        for slot in split_strip(strip, args.frames)
    ]
    boxes = [content_box(slot, args.alpha_threshold) for slot in slots]
    if any(box is None for box in boxes):
        empty = [str(index + 1) for index, box in enumerate(boxes) if box is None]
        raise SystemExit("No visible sprite content in frame(s): " + ", ".join(empty))

    seed_image: Image.Image | None = None
    seed_box: tuple[int, int, int, int] | None = None
    if args.anchor:
        seed_image = Image.open(args.anchor).convert("RGBA")
        seed_box = content_box(seed_image, args.alpha_threshold)
        if seed_box is None:
            raise SystemExit("Anchor frame contains no visible pixels.")

    # The generated strip and the approved Seed commonly come from different
    # source resolutions.  The strip establishes the shared in-game scale;
    # comparing raw Seed pixels to raw strip pixels would shrink every generated
    # pose whenever the Seed happens to be higher resolution.
    cropped_sizes = [(box[2] - box[0], box[3] - box[1]) for box in boxes if box is not None]
    max_w = max(width for width, _ in cropped_sizes)
    max_h = max(height for _, height in cropped_sizes)
    pad_x = round(args.frame_width * args.padding)
    pad_y = round(args.frame_height * args.padding)
    usable_w = args.frame_width - 2 * pad_x
    usable_h = args.frame_height - 2 * pad_y
    scale = min(usable_w / max_w, usable_h / max_h)

    sockets = load_socket_map(args.socket_map, args.frames)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_meta: list[dict[str, Any]] = []

    for index, (slot, box) in enumerate(zip(slots, boxes), start=1):
        assert box is not None
        source = slot.crop(box)
        source_box = box
        source_scale = scale
        if index == 1 and args.lock_frame1:
            assert seed_image is not None and seed_box is not None
            # Match the approved Seed to the visual box produced for raw frame
            # 01, while keeping the approved pixels themselves.  This locks
            # identity without assuming both inputs share one source DPI.
            target_width = max(1, round((box[2] - box[0]) * scale))
            target_height = max(1, round((box[3] - box[1]) * scale))
            seed_width = seed_box[2] - seed_box[0]
            seed_height = seed_box[3] - seed_box[1]
            source_scale = min(target_width / seed_width, target_height / seed_height)
            source = seed_image.crop(seed_box)
            source_box = seed_box

        width = max(1, round(source.width * source_scale))
        height = max(1, round(source.height * source_scale))
        source = source.resize((width, height), RESAMPLING[args.resample])
        x = (args.frame_width - width) // 2
        y = args.frame_height - pad_y - height
        frame = Image.new("RGBA", (args.frame_width, args.frame_height), (0, 0, 0, 0))
        frame.alpha_composite(source, (x, y))
        filename = f"{index:02d}.png"
        frame.save(out_dir / filename)

        mapped: dict[str, list[float]] = {}
        for name, points in sockets.items():
            raw_x, raw_y = points[index - 1]
            mapped[name] = [round(x + (raw_x - source_box[0]) * source_scale, 3),
                            round(y + (raw_y - source_box[1]) * source_scale, 3)]
        frame_meta.append(
            {
                "file": filename,
                "content_bbox": [x, y, x + width, y + height],
                "source_scale": round(source_scale, 8),
                "sockets": mapped,
            }
        )

    meta = {
        "version": 1,
        "frame_count": args.frames,
        "frame_size": [args.frame_width, args.frame_height],
        "resample": args.resample,
        "alpha_threshold": args.alpha_threshold,
        "component_min_ratio": args.component_min_ratio,
        "shared_scale": round(scale, 8),
        "root_anchor": {"name": "root", "x": args.frame_width / 2, "y": args.frame_height - pad_y},
        "frames": frame_meta,
    }
    meta_path = Path(args.meta_out) if args.meta_out else out_dir / "sprite-meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"normalized: {args.frames} frames -> {out_dir} | frame={args.frame_width}x{args.frame_height} "
        f"scale={scale:.5f} resample={args.resample} meta={meta_path}"
    )


if __name__ == "__main__":
    main()
