#!/usr/bin/env python3
"""AI 透明素材清理：去水印/碎渣 + 裁剪到内容包围盒。

用法: python3 clean_sprite.py <输入.png> <输出.png> [保留比例=0.05]

原理: AI 生成的透明底素材常在角落带"AI生成"水印或零星碎块。
      对不透明像素做连通块标记，只保留面积接近主体的连通块
      （> 最大块的 保留比例），其余清成透明，最后裁剪到内容 bbox。
      不透明的背景图不适用——直接裁掉底部条带即可（见 references/assets.md）。
"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    ratio = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05

    a = np.array(Image.open(src).convert("RGBA"))
    op = a[:, :, 3] > 10
    lab, n = ndimage.label(op)
    sizes = ndimage.sum(op, lab, range(1, n + 1))
    biggest = sizes.max()
    keep = np.zeros_like(op)
    for i, s in enumerate(sizes, start=1):
        if s > biggest * ratio:
            keep[lab == i] = True
    a[:, :, 3] = np.where(keep, a[:, :, 3], 0)

    ys, xs = np.where(a[:, :, 3] > 10)
    if len(ys) == 0:
        print("错误: 清理后无内容（主体被误删？调小保留比例）", file=sys.stderr)
        sys.exit(1)
    pad = 8
    h, w = a.shape[:2]
    y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + pad + 1)
    Image.fromarray(a[y0:y1, x0:x1]).save(dst)
    print(f"OK {dst}  尺寸={x1 - x0}x{y1 - y0}")


if __name__ == "__main__":
    main()
