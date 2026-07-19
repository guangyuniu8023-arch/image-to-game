#!/usr/bin/env python3
"""make_contact_sheet.py — 素材一致性验收拼图（assets.md「角色图驱动策略」第 4 步的可执行载体）

把角色图与全套素材拼成一张验收图：主角大图居左（验收基准），素材网格排列，
每件下方标注文件名；透明底素材铺在棋盘格上（白边/水印残留/描边粗细一眼可见）。

验收四看（assets.md 一致性验收）：描边粗细一致 / 上色方式一致 / 明暗方向一致 /
配色家族一致——不像"这个角色世界里的东西"的单件，只重新生成那一件。

用法：
  python3 scripts/make_contact_sheet.py 主角.png 素材1.png 素材2.png ... [-o out.png]
  python3 scripts/make_contact_sheet.py 主角.png 素材目录/ [-o out.png]   # 目录取 *.png 排序
  python3 scripts/make_contact_sheet.py 主角.png 素材目录/ --exclude 主角.png,bg.jpg
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CELL = 190          # 素材格边长
PAD = 16            # 格内留白
LABEL_H = 24        # 文件名标签高
BG = (232, 234, 238)
CK1, CK2, CKS = (255, 255, 255), (218, 221, 226), 10   # 棋盘格两色与格子px


def checker(w, h):
    bg = Image.new("RGB", (w, h), CK1)
    d = ImageDraw.Draw(bg)
    for yy in range(0, h, CKS):
        for xx in range(0, w, CKS):
            if (xx // CKS + yy // CKS) % 2:
                d.rectangle([xx, yy, xx + CKS - 1, yy + CKS - 1], fill=CK2)
    return bg


def load_thumb(path, box):
    im = Image.open(path).convert("RGBA")
    im.thumbnail((box, box), Image.LANCZOS)
    return im


def paste_cell(canvas, im, x, y, w, h):
    """棋盘格底 + 居中贴图"""
    canvas.paste(checker(w, h), (x, y))
    canvas.paste(im, (x + (w - im.width) // 2, y + (h - im.height) // 2), im)


def label(draw, text, x, y, w, font):
    t = text if len(text) <= 24 else text[:22] + "…"
    try:
        tw = draw.textlength(t, font=font)
    except Exception:
        tw = len(t) * 6
    draw.text((x + (w - tw) / 2, y + 6), t, fill=(40, 44, 52), font=font)


def main():
    ap = argparse.ArgumentParser(description="素材一致性验收 contact sheet（assets.md）")
    ap.add_argument("hero", help="角色图（验收基准，居左大图）")
    ap.add_argument("assets", nargs="+", help="素材文件或目录（目录取 *.png，字典序）")
    ap.add_argument("-o", "--output", default="contact_sheet.png")
    ap.add_argument("--cols", type=int, default=4, help="素材网格列数，默认 4")
    ap.add_argument("--exclude", default="", help="逗号分隔的文件名，从目录展开中剔除")
    args = ap.parse_args()

    excl = {s.strip() for s in args.exclude.split(",") if s.strip()}
    files = []
    for a in args.assets:
        p = Path(a)
        if p.is_dir():
            files.extend(sorted(p.glob("*.png")))
        elif p.is_file():
            files.append(p)
        else:
            print(f"跳过（不存在）: {a}", file=sys.stderr)
    files = [f for f in files if f.name not in excl and f.name != Path(args.hero).name]
    if not files:
        sys.exit("没有可拼的素材")

    cols = max(1, args.cols)
    rows = math.ceil(len(files) / cols)
    hero_w = CELL + 60
    W = hero_w + cols * CELL
    H = max(rows * (CELL + LABEL_H), 2 * (CELL + LABEL_H))
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    # 主角区：占满左侧全高
    hh = H - LABEL_H
    hero = load_thumb(args.hero, min(hero_w - 2 * PAD, hh - 2 * PAD))
    paste_cell(canvas, hero, 0, 0, hero_w, hh)
    label(draw, Path(args.hero).name + " [BASE]", 0, hh, hero_w, font)   # ASCII：默认位图字体不含 CJK

    # 素材网格
    for i, f in enumerate(files):
        gx = hero_w + (i % cols) * CELL
        gy = (i // cols) * (CELL + LABEL_H)
        im = load_thumb(f, CELL - 2 * PAD)
        paste_cell(canvas, im, gx, gy, CELL, CELL)
        label(draw, f.name, gx, gy + CELL, CELL, font)

    canvas.save(args.output)
    print(f"contact sheet → {args.output}  主角 1 + 素材 {len(files)} 件  {W}x{H}")
    print("验收四看：描边粗细 / 上色方式 / 明暗方向 / 配色家族；跑偏的单件只重新生成那一件")


if __name__ == "__main__":
    main()
