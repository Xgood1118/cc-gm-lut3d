# -*- coding: utf-8 -*-
"""lut3d: 解析 .cube 3D LUT，并按三线性插值应用。

公开 API（保持骨架中的名字与签名）：

- :class:`LUT3D`            —— 3D LUT 容器
- :func:`load_cube`         —— 解析 ``.cube`` 文件
- :func:`apply_lut`         —— 单个 RGB 或整幅图像的三线性插值
- :func:`measure_error`     —— 最大逐通道绝对误差

仅使用 Python 标准库。
"""

from __future__ import annotations

import math
import numbers

__all__ = ["LUT3D", "apply_lut", "load_cube", "measure_error"]


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def _as_triple(value, what):
    """把长度 3 的序列转成 3 个 float 组成的元组，并做有限性检查。"""
    try:
        items = tuple(value)
    except TypeError:
        raise TypeError("%s 必须是长度为 3 的序列" % what) from None
    if len(items) != 3:
        raise ValueError("%s 必须包含 3 个分量，实际为 %d 个" % (what, len(items)))
    out = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, numbers.Real):
            raise TypeError("%s 的分量必须是实数" % what)
        f = float(item)
        if not math.isfinite(f):
            raise ValueError("%s 的分量必须是有限实数，得到 %r" % (what, item))
        out.append(f)
    return tuple(out)


def _is_pixel(obj):
    """判断 obj 是否是一个 ``(r, g, b)`` 像素。"""
    try:
        if len(obj) != 3:
            return False
        for item in obj:
            if isinstance(item, bool) or not isinstance(item, numbers.Real):
                return False
        return True
    except TypeError:
        return False


# ---------------------------------------------------------------------------
# LUT 容器
# ---------------------------------------------------------------------------

class LUT3D:
    """3D LUT 容器。

    参数
    ----
    size
        每个通道的格点数（``1`` 表示单格 LUT）。
    domain_min, domain_max
        输入域，形如 ``(r, g, b)``；每个通道必须 ``min < max``。
    data
        颜色表。既可以是 ``size**3`` 个 ``(r, g, b)`` 三元组，也可以是
        扁平的 ``size**3 * 3`` 个浮点数。

    数据顺序与 ``.cube`` 文件一致：**红色变化最快，其次绿色，蓝色最慢**，
    即 ``index = r + g * size + b * size**2``。

    属性
    ----
    size, domain_min, domain_max
        构造时传入的值。
    data
        规范化后的扁平元组，长度为 ``size**3 * 3``。
    """

    __slots__ = ("size", "domain_min", "domain_max", "data")

    def __init__(self, size, domain_min, domain_max, data):
        if isinstance(size, bool) or not isinstance(size, numbers.Integral):
            raise TypeError("size 必须是整数")
        size = int(size)
        if size < 1:
            raise ValueError("size 必须 >= 1，得到 %d" % size)

        lo = _as_triple(domain_min, "domain_min")
        hi = _as_triple(domain_max, "domain_max")
        for c, name in enumerate("rgb"):
            if not lo[c] < hi[c]:
                raise ValueError(
                    "domain_min 的 %s 分量必须小于 domain_max（%r >= %r）"
                    % (name, lo[c], hi[c])
                )

        n = size ** 3
        try:
            length = len(data)
        except TypeError:
            raise TypeError("data 必须是可迭代的序列") from None

        if length == n:
            flat = []
            for i, item in enumerate(data):
                if _is_pixel(item):
                    for v in item:
                        f = float(v)
                        if not math.isfinite(f):
                            raise ValueError(
                                "data 第 %d 个格点包含非有限值 %r" % (i, v)
                            )
                        flat.append(f)
                elif isinstance(item, numbers.Real) and not isinstance(item, bool):
                    raise ValueError(
                        "data 长度为 %d（按三元组解释），但第 %d 项不是 (r, g, b)"
                        % (n, i)
                    )
                else:
                    raise TypeError("data 第 %d 项必须是 (r, g, b) 三元组" % i)
        elif length == n * 3:
            flat = []
            for i, item in enumerate(data):
                if isinstance(item, bool) or not isinstance(item, numbers.Real):
                    raise TypeError("扁平 data 的第 %d 项不是实数" % i)
                f = float(item)
                if not math.isfinite(f):
                    raise ValueError("扁平 data 的第 %d 项不是有限值" % i)
                flat.append(f)
        else:
            raise ValueError(
                "data 长度与 size 不符：size=%d 需要 %d 个三元组（或 %d 个扁平值），"
                "实际得到 %d 项" % (size, n, n * 3, length)
            )

        self.size = size
        self.domain_min = lo
        self.domain_max = hi
        self.data = tuple(flat)

    # -- 便于调试/校验的只读辅助方法 -------------------------------------
    def node_color(self, r, g, b):
        """返回格点 ``(r, g, b)``（0 起始索引）对应的输出颜色。"""
        size = self.size
        for name, i in (("r", r), ("g", g), ("b", b)):
            if not isinstance(i, numbers.Integral) or not 0 <= i < size:
                raise IndexError("%s 索引 %r 超出 [0, %d)" % (name, i, size))
        base = (int(r) + int(g) * size + int(b) * size * size) * 3
        d = self.data
        return (d[base], d[base + 1], d[base + 2])

    def node_input(self, r, g, b):
        """返回格点 ``(r, g, b)`` 对应的输入坐标。size==1 时返回域中点。"""
        lo, hi = self.domain_min, self.domain_max
        size = self.size
        if size == 1:
            return tuple((lo[c] + hi[c]) * 0.5 for c in range(3))
        return tuple(
            lo[c] + (hi[c] - lo[c]) * (idx / (size - 1))
            for c, idx in enumerate((r, g, b))
        )

    def __repr__(self):
        return "LUT3D(size=%d, domain_min=%r, domain_max=%r)" % (
            self.size,
            self.domain_min,
            self.domain_max,
        )


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def load_cube(path):
    """解析 ``.cube`` 3D LUT 文件并返回 :class:`LUT3D`。

    支持 ``TITLE``、``LUT_3D_SIZE``、``DOMAIN_MIN``、``DOMAIN_MAX``、
    ``LUT_3D_INPUT_RANGE``；``#`` 之后的内容与空行会被跳过。

    声明尺寸与实际数据行数不一致、缺少尺寸声明、数值非法时抛出
    ``ValueError``，绝不截断或补零。
    """
    size = None
    domain_min = (0.0, 0.0, 0.0)
    domain_max = (1.0, 1.0, 1.0)
    values = []
    seen_size = False

    with open(path, "r", encoding="utf-8-sig") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            keyword = parts[0].upper()

            def fail(msg):
                raise ValueError("%s 第 %d 行：%s" % (path, lineno, msg))

            if keyword == "TITLE":
                # 标题可带引号，直接忽略。
                continue

            if keyword == "LUT_3D_SIZE":
                if len(parts) != 2:
                    fail("LUT_3D_SIZE 需要且仅需要 1 个参数")
                if seen_size:
                    fail("重复的 LUT_3D_SIZE 声明")
                try:
                    n = int(parts[1])
                except ValueError:
                    fail("LUT_3D_SIZE 的参数不是整数：%r" % parts[1])
                if n < 1:
                    fail("LUT_3D_SIZE 必须 >= 1，得到 %d" % n)
                size = n
                seen_size = True
                continue

            if keyword in ("LUT_1D_SIZE", "LUT_1D_INPUT_RANGE"):
                fail("%s 不受支持：本模块只处理 3D LUT" % keyword)

            if keyword in ("DOMAIN_MIN", "DOMAIN_MAX"):
                if len(parts) != 4:
                    fail("%s 需要 3 个参数" % keyword)
                triple = []
                for token in parts[1:]:
                    try:
                        v = float(token)
                    except ValueError:
                        fail("%s 的参数不是数字：%r" % (keyword, token))
                    if not math.isfinite(v):
                        fail("%s 的参数必须是有限值：%r" % (keyword, token))
                    triple.append(v)
                if keyword == "DOMAIN_MIN":
                    domain_min = tuple(triple)
                else:
                    domain_max = tuple(triple)
                continue

            if keyword == "LUT_3D_INPUT_RANGE":
                if len(parts) != 3:
                    fail("LUT_3D_INPUT_RANGE 需要 2 个参数")
                try:
                    lo = float(parts[1])
                    hi = float(parts[2])
                except ValueError:
                    fail("LUT_3D_INPUT_RANGE 的参数不是数字")
                if not (math.isfinite(lo) and math.isfinite(hi)):
                    fail("LUT_3D_INPUT_RANGE 的参数必须是有限值")
                domain_min = (lo, lo, lo)
                domain_max = (hi, hi, hi)
                continue

            # 其余非数字开头的行视为未知指令。
            if not _looks_numeric(parts[0]):
                fail("未知指令 %r" % parts[0])

            if len(parts) != 3:
                fail("数据行必须恰好包含 3 个数字，实际 %d 个" % len(parts))
            triple = []
            for token in parts:
                try:
                    v = float(token)
                except ValueError:
                    fail("数据行中的 %r 不是数字" % token)
                if not math.isfinite(v):
                    fail("数据行中的 %r 不是有限值" % token)
                triple.append(v)
            values.append(tuple(triple))

    if size is None:
        raise ValueError("%s：缺少 LUT_3D_SIZE 声明" % path)

    for c, name in enumerate("rgb"):
        if not domain_min[c] < domain_max[c]:
            raise ValueError(
                "%s：domain_min 的 %s 分量必须小于 domain_max（%r >= %r）"
                % (path, name, domain_min[c], domain_max[c])
            )

    expected = size ** 3
    actual = len(values)
    if actual != expected:
        raise ValueError(
            "%s：LUT_3D_SIZE=%d 需要 %d 行数据，实际读到 %d 行%s"
            % (
                path,
                size,
                expected,
                actual,
                "（数据不足，禁止补零）" if actual < expected
                else "（数据过多，禁止截断）",
            )
        )

    return LUT3D(size, domain_min, domain_max, values)


def _looks_numeric(token):
    try:
        float(token)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# 应用（三线性插值）
# ---------------------------------------------------------------------------

def _make_pixel_fn(lut):
    """把 LUT 的常量绑定进闭包，返回单像素三线性插值函数。

    批量应用时只建一次闭包，避免每个像素重复查属性。
    """
    d = lut.data
    size = lut.size
    stride_g = size * 3
    stride_b = size * size * 3
    limit = size - 1

    if size == 1:
        # 单格 LUT：整个域只有一种输出，不可能产生 NaN。
        color = (d[0], d[1], d[2])
        return lambda rgb: color

    l0, l1, l2 = lut.domain_min
    h0, h1, h2 = lut.domain_max
    # 域长度归一化系数：输入 -> 格点坐标
    k0 = limit / (h0 - l0)
    k1 = limit / (h1 - l1)
    k2 = limit / (h2 - l2)

    def pixel(rgb):
        # --- 各通道钳制到域内并归一化为格点坐标 ---
        # NaN 按域下界处理：结果确定，且绝不向输出传播 NaN。
        x = rgb[0]
        if x != x:
            x = l0
        elif x < l0:
            x = l0
        elif x > h0:
            x = h0
        pos = (x - l0) * k0
        i0 = int(pos)
        if i0 >= limit:
            i0 = limit - 1
            fr = 1.0
        else:
            fr = pos - i0

        y = rgb[1]
        if y != y:
            y = l1
        elif y < l1:
            y = l1
        elif y > h1:
            y = h1
        pos = (y - l1) * k1
        j0 = int(pos)
        if j0 >= limit:
            j0 = limit - 1
            fg = 1.0
        else:
            fg = pos - j0

        z = rgb[2]
        if z != z:
            z = l2
        elif z < l2:
            z = l2
        elif z > h2:
            z = h2
        pos = (z - l2) * k2
        kk = int(pos)
        if kk >= limit:
            kk = limit - 1
            fb = 1.0
        else:
            fb = pos - kk

        # --- 8 个角点的扁平下标（.cube 顺序：红最快、蓝最慢）---
        base = i0 * 3 + j0 * stride_g + kk * stride_b
        o000 = base
        o100 = base + 3
        o010 = base + stride_g
        o110 = base + stride_g + 3
        o001 = base + stride_b
        o101 = base + stride_b + 3
        o011 = base + stride_b + stride_g
        o111 = base + stride_b + stride_g + 3

        # --- 8 个权重，3 个输出通道共用 ---
        ar = 1.0 - fr
        ag = 1.0 - fg
        ab = 1.0 - fb
        ar_ag = ar * ag
        ar_fg = ar * fg
        fr_ag = fr * ag
        fr_fg = fr * fg
        w000 = ar_ag * ab
        w001 = ar_ag * fb
        w010 = ar_fg * ab
        w011 = ar_fg * fb
        w100 = fr_ag * ab
        w101 = fr_ag * fb
        w110 = fr_fg * ab
        w111 = fr_fg * fb

        # 单次表达式内联求值（不建临时列表），保证 512x512 规模的速度。
        r = (d[o000] * w000 + d[o100] * w100 + d[o010] * w010
             + d[o110] * w110 + d[o001] * w001 + d[o101] * w101
             + d[o011] * w011 + d[o111] * w111)
        o000 += 1; o100 += 1; o010 += 1; o110 += 1
        o001 += 1; o101 += 1; o011 += 1; o111 += 1
        g = (d[o000] * w000 + d[o100] * w100 + d[o010] * w010
             + d[o110] * w110 + d[o001] * w001 + d[o101] * w101
             + d[o011] * w011 + d[o111] * w111)
        o000 += 1; o100 += 1; o010 += 1; o110 += 1
        o001 += 1; o101 += 1; o011 += 1; o111 += 1
        b = (d[o000] * w000 + d[o100] * w100 + d[o010] * w010
             + d[o110] * w110 + d[o001] * w001 + d[o101] * w101
             + d[o011] * w011 + d[o111] * w111)
        return (r, g, b)

    return pixel


def _apply_pixel(lut, rgb):
    """对单个像素做三线性插值，返回 ``(r, g, b)`` 浮点元组。"""
    return _make_pixel_fn(lut)(rgb)


def apply_lut(lut, rgb):
    """按三线性插值应用 LUT。

    参数
    ----
    lut : LUT3D
    rgb
        单个像素 ``(r, g, b)``，或像素序列 ``[(r, g, b), ...]``。
        - 单像素返回 ``(r, g, b)`` 元组；
        - 像素序列返回等长的元组列表。

    输入先钳制到 LUT 域内（``NaN`` 按下界处理），因此不会回绕，
    也不会返回 NaN。``1x1x1`` 的 LUT 对任何输入都返回该唯一颜色。
    """
    if not isinstance(lut, LUT3D):
        raise TypeError("lut 必须是 LUT3D 实例，得到 %r" % type(lut).__name__)

    pixel_fn = _make_pixel_fn(lut)
    if _is_pixel(rgb):
        return pixel_fn(rgb)

    try:
        iterator = iter(rgb)
    except TypeError:
        raise TypeError("rgb 必须是 (r, g, b) 或像素序列 [(r, g, b), ...]") from None

    out = []
    append = out.append
    for index, pixel in enumerate(iterator):
        if not _is_pixel(pixel):
            raise TypeError(
                "第 %d 个像素不是 (r, g, b) 三元组：%r" % (index, pixel)
            )
        append(pixel_fn(pixel))
    return out


# ---------------------------------------------------------------------------
# 误差度量
# ---------------------------------------------------------------------------

def measure_error(pairs):
    """返回最大逐通道绝对误差（L∞）。

    参数 ``pairs`` 为 ``(预测值, 参考值)`` 的可迭代对象，二者都是
    ``(r, g, b)``。误差定义为所有样本、所有通道上 ``abs(预测 - 参考)``
    的最大值，单位与 LUT 输出一致（通常为归一化的 0–1）。

    空输入返回 ``0.0``；任一非有限误差返回 ``inf``。
    """
    max_error = 0.0
    for index, pair in enumerate(pairs):
        try:
            predicted, expected = pair
        except (TypeError, ValueError):
            raise ValueError("第 %d 项不是 (预测值, 参考值) 二元组" % index) from None
        try:
            pred = tuple(float(v) for v in predicted)
            exp = tuple(float(v) for v in expected)
        except (TypeError, ValueError):
            raise ValueError("第 %d 项的分量无法转为数值" % index) from None
        if len(pred) != len(exp):
            raise ValueError(
                "第 %d 项的预测值与参考值维度不同：%d != %d"
                % (index, len(pred), len(exp))
            )
        for a, b in zip(pred, exp):
            e = abs(a - b)
            if not math.isfinite(e):
                return math.inf
            if e > max_error:
                max_error = e
    return max_error
