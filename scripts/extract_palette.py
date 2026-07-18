#!/usr/bin/env python3
"""提取图片主色调，输出 5 个主色 HEX 及占比，用于游戏 UI/世界点缀配色。

用法: python3 extract_palette.py <图片>
"""
import sys
from collections import Counter

import numpy as np
from PIL import Image


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    im = Image.open(sys.argv[1]).convert("RGBA")
    arr = np.array(im)
    mask = arr[:, :, 3] > 128
    rgb = arr[:, :, :3][mask].astype(float) if mask.any() else arr[:, :, :3].reshape(-1, 3).astype(float)
    q = (rgb // 32 * 32 + 16).astype(int)
    cnt = Counter(map(tuple, q[::7]))
    for c, n in cnt.most_common(5):
        print(f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}  {n / len(q) * 100:.1f}%")


if __name__ == "__main__":
    main()
