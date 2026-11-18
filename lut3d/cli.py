# -*- coding: utf-8 -*-
"""命令行入口：加载 .cube，跑一幅 512x512 的验证图并输出统计。

用法::

    python -m lut3d.cli data/lut.cube --out graded.json

统计口径：

- ``max_error``      三线性输出与参考映射的最大逐通道绝对误差。
                     ``data/lut.cube`` 是恒等 LUT，参考映射即“钳制到域内”。
- ``clamped_pixels`` 至少有一个输入通道落在 LUT 域外的像素数。
- ``elapsed_seconds`` ``apply_lut`` 处理整幅图像的实际耗时。

加 ``--bench`` 会再跑一遍 1024x1024，用于检查耗时是否随像素数线性增长。
"""

from __future__ import annotations

import argparse
import json
import time

import lut3d as m


def make_image(width, height, lo=-0.1, hi=1.1):
    """确定性渐变图：每个通道都覆盖 [lo, hi]，因此包含域外像素。"""
    image = []
    append = image.append
    span = hi - lo
    for y in range(height):
        gy = lo + span * (y / (height - 1))
        for x in range(width):
            gx = lo + span * (x / (width - 1))
            gb = lo + span * (((x * 7 + y * 13) % width) / (width - 1))
            append((gx, gy, gb))
    return image


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def evaluate(lut, image):
    """应用 LUT，返回 (输出, 最大误差, 钳制像素数, 耗时秒)。"""
    lo, hi = lut.domain_min, lut.domain_max

    start = time.perf_counter()
    output = m.apply_lut(lut, image)
    elapsed = time.perf_counter() - start

    # data/lut.cube 为恒等 LUT：参考值 = 输入钳制到域内。
    pairs = []
    clamped = 0
    for src, dst in zip(image, output):
        if (src[0] < lo[0] or src[0] > hi[0]
                or src[1] < lo[1] or src[1] > hi[1]
                or src[2] < lo[2] or src[2] > hi[2]):
            clamped += 1
        expected = (
            _clamp(src[0], lo[0], hi[0]),
            _clamp(src[1], lo[1], hi[1]),
            _clamp(src[2], lo[2], hi[2]),
        )
        pairs.append((dst, expected))

    return output, m.measure_error(pairs), clamped, elapsed


def main(argv=None):
    ap = argparse.ArgumentParser(description="lut3d：解析 .cube 并三线性应用")
    ap.add_argument("path", help=".cube 文件路径")
    ap.add_argument("--out", default=None, help="统计结果写入的 JSON 路径")
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--height", type=int, default=512)
    ap.add_argument("--bench", action="store_true",
                    help="额外跑 2 倍边长，检查耗时增长是否接近线性")
    a = ap.parse_args(argv)

    lut = m.load_cube(a.path)
    image = make_image(a.width, a.height)
    _, max_error, clamped, elapsed = evaluate(lut, image)

    result = {
        "lut": a.path,
        "size": lut.size,
        "domain_min": list(lut.domain_min),
        "domain_max": list(lut.domain_max),
        "width": a.width,
        "height": a.height,
        "pixels": len(image),
        "max_error": max_error,
        "clamped_pixels": clamped,
        "elapsed_seconds": elapsed,
    }

    print("LUT %dx%dx%d, domain [%s] -> [%s]"
          % (lut.size, lut.size, lut.size,
             ", ".join("%g" % v for v in lut.domain_min),
             ", ".join("%g" % v for v in lut.domain_max)))
    print("image %dx%d = %d pixels" % (a.width, a.height, len(image)))
    print("max_error       = %.12g" % max_error)
    print("clamped_pixels  = %d / %d" % (clamped, len(image)))
    print("elapsed_seconds = %.4f" % elapsed)

    if a.bench:
        big_w, big_h = a.width * 2, a.height * 2
        big_image = make_image(big_w, big_h)
        _, _, _, big_elapsed = evaluate(lut, big_image)
        ratio_pixels = len(big_image) / len(image)
        ratio_time = big_elapsed / elapsed if elapsed > 0 else float("inf")
        print("bench %dx%d = %d pixels: %.4f s (x%.2f pixels, x%.2f time)"
              % (big_w, big_h, len(big_image), big_elapsed, ratio_pixels, ratio_time))
        result["bench"] = {
            "width": big_w,
            "height": big_h,
            "pixels": len(big_image),
            "elapsed_seconds": big_elapsed,
            "pixel_ratio": ratio_pixels,
            "time_ratio": ratio_time,
        }

    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print("wrote %s" % a.out)

    return result


if __name__ == "__main__":
    main()
