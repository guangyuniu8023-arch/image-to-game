#!/usr/bin/env python3
"""Hard-gate normalized sprite frames before runtime integration."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit frame count, alpha, size, baseline, distinct poses, metadata and seed lock."
    )
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--meta", help="Optional sprite-meta.json.")
    parser.add_argument("--anchor", help="Approved seed; requires frame 01 to match after normalization.")
    parser.add_argument("--min-distinct", type=int, default=2)
    parser.add_argument("--baseline-tol", type=int, default=2)
    return parser.parse_args()


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def normalized_anchor(
    anchor: Image.Image,
    size: tuple[int, int],
    root_y: float,
    scale: float,
    resample: str,
    alpha_threshold: int,
) -> Image.Image:
    anchor = anchor.convert("RGBA")
    alpha = anchor.getchannel("A").point(lambda value: 255 if value > alpha_threshold else 0)
    box = alpha.getbbox()
    if box is None:
        raise ValueError("anchor contains no visible pixels")
    content = anchor.crop(box)
    target_w, target_h = size
    content = content.resize(
        (max(1, round(content.width * scale)), max(1, round(content.height * scale))),
        Image.Resampling.NEAREST if resample == "nearest" else Image.Resampling.LANCZOS,
    )
    frame = Image.new("RGBA", size, (0, 0, 0, 0))
    frame.alpha_composite(content, ((target_w - content.width) // 2, round(root_y) - content.height))
    return frame


def main() -> None:
    args = parse_args()
    problems: list[str] = []
    frames = sorted(Path(args.frames_dir).glob("[0-9][0-9].png"))
    if len(frames) != args.expected:
        fail(problems, f"expected {args.expected} frames, found {len(frames)}")
    if not frames:
        fail(problems, "no NN.png frames found")

    images = [Image.open(path).convert("RGBA") for path in frames]
    sizes = {image.size for image in images}
    if len(sizes) > 1:
        fail(problems, f"frame sizes differ: {sorted(sizes)}")
    for path, image in zip(frames, images):
        alpha = image.getchannel("A")
        box = alpha.getbbox()
        if box is None:
            fail(problems, f"{path.name} has no visible content")
        if alpha.getextrema()[0] == 255:
            fail(problems, f"{path.name} has no transparent pixels")

    hashes = {hashlib.sha256(image.tobytes()).hexdigest() for image in images}
    if len(hashes) < args.min_distinct:
        fail(problems, f"only {len(hashes)} distinct frame(s); need {args.min_distinct}")

    meta = None
    if args.meta:
        meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
        if meta.get("frame_count") != len(images):
            fail(problems, "metadata frame_count does not match PNG count")
        if images and meta.get("frame_size") != list(images[0].size):
            fail(problems, "metadata frame_size does not match PNG size")
        root = meta.get("root_anchor", {})
        root_y = root.get("y")
        if not isinstance(root_y, (int, float)):
            fail(problems, "metadata root_anchor.y is missing")
        else:
            for path, image in zip(frames, images):
                box = image.getchannel("A").getbbox()
                if box and abs(box[3] - root_y) > args.baseline_tol:
                    fail(problems, f"{path.name} baseline {box[3]} differs from root {root_y}")
        meta_frames = meta.get("frames", [])
        if len(meta_frames) != len(images):
            fail(problems, "metadata frames array does not match PNG count")
        for frame in meta_frames:
            for name, point in frame.get("sockets", {}).items():
                if not isinstance(point, list) or len(point) != 2:
                    fail(problems, f"socket {name!r} is not [x,y]")
                    continue
                if images and not (0 <= point[0] < images[0].width and 0 <= point[1] < images[0].height):
                    fail(problems, f"socket {name!r} is outside the frame: {point}")

    if args.anchor and images:
        if not meta:
            fail(problems, "--anchor audit requires --meta for shared scale/root data")
        else:
            root_y = meta.get("root_anchor", {}).get("y")
            meta_frames = meta.get("frames", [])
            scale = meta_frames[0].get("source_scale") if meta_frames else None
            if not isinstance(scale, (int, float)):
                # Backward compatibility for metadata written before per-frame
                # source scales were recorded.
                scale = meta.get("shared_scale")
            resample = meta.get("resample")
            alpha_threshold = meta.get("alpha_threshold", 0)
            if not isinstance(root_y, (int, float)) or not isinstance(scale, (int, float)):
                fail(problems, "metadata lacks root_anchor.y/frame-01 source scale for seed audit")
            elif resample not in {"nearest", "lanczos"}:
                fail(problems, "metadata resample is invalid for seed audit")
            elif not isinstance(alpha_threshold, int) or not 0 <= alpha_threshold <= 255:
                fail(problems, "metadata alpha_threshold is invalid for seed audit")
            else:
                try:
                    expected = normalized_anchor(
                        Image.open(args.anchor), images[0].size, root_y, scale, resample, alpha_threshold
                    )
                    if ImageChops.difference(expected, images[0]).getbbox() is not None:
                        fail(problems, "frame 01 does not match the normalized approved seed")
                except ValueError as error:
                    fail(problems, str(error))

    if problems:
        print("SPRITE AUDIT: FAIL")
        for problem in problems:
            print("- " + problem)
        raise SystemExit(1)
    print(
        f"SPRITE AUDIT: PASS | frames={len(images)} size={images[0].size[0]}x{images[0].size[1]} "
        f"distinct={len(hashes)}"
    )


if __name__ == "__main__":
    main()
