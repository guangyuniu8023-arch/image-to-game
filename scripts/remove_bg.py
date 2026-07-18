#!/usr/bin/env python3
"""纯色/近纯色背景抠图：把背景变透明，输出裁剪好的 PNG 精灵素材。

用法: python3 remove_bg.py <输入图> <输出.png> [容差=30]

原理: 取图片四角的中位色作为背景色，把与边缘相连的近背景色区域标为透明
      （洪水填充式，只去外围背景，保住主体内部相近颜色），再腐蚀 1px 去
      残留白边，最后裁剪到内容包围盒。适合证件照式白底/纯色底图片。
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
    tol = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0

    img = Image.open(src).convert("RGBA")
    arr = np.array(img)
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(float)

    # 四角 8x8 区域的中位色 = 背景色
    c = 8
    corners = np.concatenate([
        rgb[:c, :c].reshape(-1, 3), rgb[:c, -c:].reshape(-1, 3),
        rgb[-c:, :c].reshape(-1, 3), rgb[-c:, -c:].reshape(-1, 3),
    ])
    bg_color = np.median(corners, axis=0)

    # 与背景色相近、且与图片边缘相连的像素 → 透明
    near = np.all(np.abs(rgb - bg_color) <= tol, axis=2)
    lab, _ = ndimage.label(near)
    border_labels = set(np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]])).tolist()) - {0}
    bg = np.isin(lab, list(border_labels))
    arr[bg, 3] = 0

    # 腐蚀 1px 去残留边缘
    solid_mask = ndimage.binary_erosion(arr[:, :, 3] > 0, iterations=1)
    arr[:, :, 3] = np.where(solid_mask, arr[:, :, 3], 0)

    ys, xs = np.where(arr[:, :, 3] > 0)
    if len(ys) == 0:
        print("错误: 抠图后没有剩余内容，请调小容差或换抠图方案", file=sys.stderr)
        sys.exit(1)

    # 裁剪到内容包围盒（留 10px 边距）
    pad = 10
    y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + pad + 1)
    Image.fromarray(arr[y0:y1, x0:x1]).save(dst)
    print(f"OK {dst}  背景色={bg_color.astype(int).tolist()}  尺寸={x1 - x0}x{y1 - y0}")


if __name__ == "__main__":
    main()
