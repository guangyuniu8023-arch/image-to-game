#!/usr/bin/env python3
"""audit_ui_align.py — HUD/UI 对齐验收（ui-kit.md ⑤ 第 5 条的可执行载体）

整图缩略目检"看着居中"不算数。本工具对每个组件区域（region）做像素级测量：
  1. 估背景：取区域四角 8x8 补丁的亮度中位数；
  2. 底材（胶囊/按钮体）：行均亮度 > 背景 + cap-delta 的最长连续行段；
  3. 文字/icon 墨色：区域内亮度 ≥ 98 分位的像素所在行（亮文字假设，见下）；
  4. 报告：底材行范围/中心、墨色行范围/中心、垂直偏移、上下留空；
  5. 判定：|偏移| <= tol 且 上下留空差 <= tol → PASS，否则 FAIL；任一 FAIL 退出码 1。

用法：
  python3 scripts/audit_ui_align.py 截图.png --region x,y,w,h [--region ...] [--tol 2] [--cap-delta 18]

假设（不满足时不要硬用，改人工放大目检并在验收记录注明）：
  - 文字/icon 是区域内最亮的元素（白/亮色字 on 玻璃/深底）；金字黑底不适用；
  - 一个 region 只含一个组件（chip/按钮/标题栏各传一个 region），region 取自原生分辨率截图；
  - 底材整体比背景亮（玻璃胶囊/亮按钮）；深色幽灵按钮需调低 --cap-delta 或人工验。

溯源：v5 案例——整图目检报"居中"的 HUD，放大实测数字偏上 11px（测量前没钉
textBaseline 所致，见 ui-kit.md ④）。本工具把"region 放大 + 亮度剖面测行"制度化。
"""
import argparse
import sys

import numpy as np
from PIL import Image


def measure_region(gray, x, y, w, h, cap_delta, tol, name):
    reg = gray[y:y + h, x:x + w]
    if reg.size == 0:
        return None, f"region 越界: ({x},{y},{w},{h})"
    corners = np.concatenate([
        reg[:8, :8].ravel(), reg[:8, -8:].ravel(),
        reg[-8:, :8].ravel(), reg[-8:, -8:].ravel()])
    bg = float(np.median(corners))

    row_mean = reg.mean(axis=1)
    above = row_mean > bg + cap_delta
    # 最长连续 True 段 = 底材体
    best, cur = (0, 0, 0), 0  # (start, end_exclusive, length)
    runs, start = [], None
    for i, v in enumerate(above):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i)); start = None
    if start is not None:
        runs.append((start, len(above)))
    if not runs:
        return None, "未检出底材亮区（试调低 --cap-delta）"
    cs, ce = max(runs, key=lambda r: r[1] - r[0])
    cap_c = (cs + ce - 1) / 2.0

    # 墨色行：区域内亮度 ≥98 分位的像素
    thresh = float(np.percentile(reg, 98))
    ink_rows = np.where((reg >= thresh).any(axis=1))[0]
    if len(ink_rows) == 0:
        return None, "未检出墨色亮点"
    is_, ie = int(ink_rows[0]), int(ink_rows[-1])
    ink_c = (is_ + ie) / 2.0

    offset = ink_c - cap_c                      # 负=偏上，正=偏下
    top, bottom = is_ - cs, ce - 1 - ie         # 上下留空
    ok = abs(offset) <= tol and abs(top - bottom) <= tol
    report = (f"  {name}: 底材行 {cs}..{ce - 1} 中心 {cap_c:.1f} | "
              f"墨色行 {is_}..{ie} 中心 {ink_c:.1f} | "
              f"偏移 {offset:+.1f}px 上留空 {top} 下留空 {bottom} | "
              f"{'PASS' if ok else 'FAIL'}(tol={tol})")
    return ok, report


def main():
    ap = argparse.ArgumentParser(description="HUD/UI 组件对齐像素级验收（ui-kit.md ⑤）")
    ap.add_argument("shot", help="原生分辨率截图（--window-size 与舞台一致、无缩放）")
    ap.add_argument("--region", action="append", required=True,
                    help="x,y,w,h（组件外接矩形，可带名字：name=x,y,w,h）可传多个")
    ap.add_argument("--tol", type=float, default=2.0, help="偏移/留空差容差 px，默认 2")
    ap.add_argument("--cap-delta", type=float, default=18.0, help="底材亮区相对背景的亮度差，默认 18")
    args = ap.parse_args()

    gray = np.array(Image.open(args.shot).convert("L"), dtype=float)
    all_ok = True
    print(f"audit_ui_align: {args.shot}  tol=±{args.tol}px")
    for spec in args.region:
        name, _, coords = spec.partition("=")
        if not coords:
            name, coords = spec, spec
        try:
            x, y, w, h = [int(v) for v in coords.split(",")]
        except ValueError:
            print(f"  region 格式错误: {spec}（应为 x,y,w,h）"); all_ok = False; continue
        ok, msg = measure_region(gray, x, y, w, h, args.cap_delta, args.tol, name)
        print(msg)
        if ok is not True:
            all_ok = False
    print("RESULT:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
