#!/usr/bin/env python3
"""把一张 N×M 序列帧图（sprite sheet）切成独立帧 PNG，并逐帧裁掉透明边。

用法: python3 slice_sheet.py <sheet.png> <输出前缀> [--grid 2x2] [--order tl,tr,br,bl]
默认: --grid 2x2 --order tl,tr,bl,br（阅读顺序）。

注意：若 sheet 先经过 clean_sprite.py 清理，它会按内容包围盒整体裁剪，
象限中线可能偏离——切完必须拼接目检，发现角色被切断就调整 --order 或重新生成。
"""
import argparse
import os
import sys

from PIL import Image

POS = {"tl": (0, 0), "tr": (1, 0), "bl": (0, 1), "br": (1, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("prefix")
    ap.add_argument("--grid", default="2x2", help="列x行，默认 2x2")
    ap.add_argument("--order", default="tl,tr,bl,br", help="播放顺序，逗号分隔的格子位置")
    args = ap.parse_args()

    cols, rows = (int(v) for v in args.grid.lower().split("x"))
    order = [s.strip() for s in args.order.split(",")]
    if len(order) != cols * rows:
        sys.exit(f"--order 需要 {cols*rows} 个位置，收到 {len(order)} 个")

    im = Image.open(args.sheet).convert("RGBA")
    W, H = im.size
    for i, pos in enumerate(order, 1):
        if pos not in POS or cols != 2 or rows != 2:
            # 非 2x2 时按顺序号取格子（阅读顺序）
            idx = i - 1
            cx, cy = idx % cols, idx // cols
        else:
            cx, cy = POS[pos]
        cell = im.crop((cx * W // cols, cy * H // rows, (cx + 1) * W // cols, (cy + 1) * H // rows))
        bbox = cell.getbbox()
        if not bbox:
            sys.exit(f"第 {i} 帧（{pos}）为空——格子划分不对，检查 --order 或原图")
        cell.crop(bbox).save(f"{args.prefix}{i}.png")
        print(f"OK {args.prefix}{i}.png {cell.crop(bbox).size}")


if __name__ == "__main__":
    main()
