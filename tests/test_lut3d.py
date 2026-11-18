# -*- coding: utf-8 -*-
import json
import math
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lut3d as mod  # noqa: E402
from lut3d import cli  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CUBE = os.path.join(DATA, "lut.cube")


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def write_cube(text):
    fd, path = tempfile.mkstemp(suffix=".cube")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def identity_cube(size, domain_min=(0.0, 0.0, 0.0), domain_max=(1.0, 1.0, 1.0)):
    lines = ["LUT_3D_SIZE %d" % size,
             "DOMAIN_MIN %r %r %r" % domain_min,
             "DOMAIN_MAX %r %r %r" % domain_max]
    for b in range(size):
        for g in range(size):
            for r in range(size):
                lines.append("%r %r %r" % (
                    domain_min[0] + (domain_max[0] - domain_min[0]) * r / (size - 1),
                    domain_min[1] + (domain_max[1] - domain_min[1]) * g / (size - 1),
                    domain_min[2] + (domain_max[2] - domain_min[2]) * b / (size - 1),
                ))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 1. 解析
# ---------------------------------------------------------------------------

def test_load_and_size():
    lut = mod.load_cube(CUBE)
    assert lut.size == 2
    assert lut.domain_min == (0.0, 0.0, 0.0)
    assert lut.domain_max == (1.0, 1.0, 1.0)
    assert len(lut.data) == 2 ** 3 * 3


def test_parse_skips_comments_and_blank_lines():
    path = write_cube(
        "# 顶部注释\n"
        "\n"
        "TITLE \"带 # 的标题\"\n"
        "   \n"
        "LUT_3D_SIZE 2   # 行尾注释\n"
        "# 中间注释\n"
        "DOMAIN_MIN 0 0 0\n"
        "\n"
        "DOMAIN_MAX 1 1 1\n"
        "0 0 0  # 第一个格点\n"
        "\n"
        "1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n"
    )
    try:
        lut = mod.load_cube(path)
    finally:
        os.remove(path)
    assert lut.size == 2
    assert lut.node_color(0, 0, 0) == (0.0, 0.0, 0.0)
    assert lut.node_color(1, 1, 1) == (1.0, 1.0, 1.0)
    assert lut.data[3:6] == (1.0, 0.0, 0.0)  # 红色变化最快


def test_parse_domain_and_input_range():
    path = write_cube("LUT_3D_SIZE 1\nLUT_3D_INPUT_RANGE -0.5 0.5\n0.3 0.4 0.5\n")
    try:
        lut = mod.load_cube(path)
    finally:
        os.remove(path)
    assert lut.domain_min == (-0.5, -0.5, -0.5)
    assert lut.domain_max == (0.5, 0.5, 0.5)


def test_bad_size_raises():
    path = write_cube("LUT_3D_SIZE 2\n0.0 0.0 0.0\n")
    try:
        try:
            mod.load_cube(path)
        except NotImplementedError:
            raise
        except Exception:
            pass
        else:
            raise AssertionError("尺寸不符必须报错")
    finally:
        os.remove(path)


def test_too_many_rows_raises():
    path = write_cube(
        "LUT_3D_SIZE 2\n"
        + "0 0 0\n" * 8
        + "1 1 1\n"  # 多一行，必须报错，不得截断
    )
    try:
        try:
            mod.load_cube(path)
        except ValueError as exc:
            assert "9" in str(exc)
        else:
            raise AssertionError("数据行过多必须报错")
    finally:
        os.remove(path)


def test_missing_size_raises():
    path = write_cube("0 0 0\n1 1 1\n")
    try:
        try:
            mod.load_cube(path)
        except ValueError:
            pass
        else:
            raise AssertionError("缺少 LUT_3D_SIZE 必须报错")
    finally:
        os.remove(path)


def test_bad_data_row_raises():
    for body in ("0 0 0\n1 1\n", "0 0 0\n1 1 nan\n", "0 0 0\n1 1 1 1\n"):
        lines = ["LUT_3D_SIZE 2"] + body.splitlines()
        lines += ["0 0 0"] * (8 - (len(lines) - 1))
        path = write_cube("\n".join(lines[:9]) + "\n")
        try:
            try:
                mod.load_cube(path)
            except ValueError:
                pass
            else:
                raise AssertionError("非法数据行必须报错：%r" % body)
        finally:
            os.remove(path)


def test_lut_constructor_validates():
    with_exc = lambda fn: _expect(fn, (TypeError, ValueError))
    with_exc(lambda: mod.LUT3D(0, (0, 0, 0), (1, 1, 1), ()))
    with_exc(lambda: mod.LUT3D(2, (1, 0, 0), (0, 1, 1), [(0, 0, 0)] * 8))
    with_exc(lambda: mod.LUT3D(2, (0, 0, 0), (1, 1, 1), [(0, 0, 0)] * 7))
    with_exc(lambda: mod.LUT3D(2, (0, 0, 0), (1, 1, 1), [(0, 0, float("nan"))] * 8))


def _expect(fn, exc_types):
    try:
        fn()
    except exc_types:
        return
    raise AssertionError("预期抛出 %r" % (exc_types,))


# ---------------------------------------------------------------------------
# 2. 三线性插值精度
# ---------------------------------------------------------------------------

def _quadratic_lut(size):
    """构造一个三通道各自平方的 LUT，用来检验插值而非最近邻。"""
    data = []
    for b in range(size):
        for g in range(size):
            for r in range(size):
                data.append(((r / (size - 1)) ** 2,
                             (g / (size - 1)) ** 2,
                             (b / (size - 1)) ** 2))
    return mod.LUT3D(size, (0, 0, 0), (1, 1, 1), data)


def test_trilinear_exact_at_nodes():
    lut = _quadratic_lut(3)
    for i in range(3):
        for j in range(3):
            for k in range(3):
                rgb = (i / 2, j / 2, k / 2)
                out = mod.apply_lut(lut, rgb)
                assert out == ((i / 2) ** 2, (j / 2) ** 2, (k / 2) ** 2)


def test_trilinear_matches_linear_function_exactly():
    """线性映射在三线性插值下应逐值复现（存在舍入误差）。"""
    size = 4
    data = [(0.1 + 0.8 * r / (size - 1),
             0.2 + 0.5 * g / (size - 1),
             0.3 + 0.4 * b / (size - 1))
            for b in range(size) for g in range(size) for r in range(size)]
    lut = mod.LUT3D(size, (0, 0, 0), (1, 1, 1), data)
    for t in (0.0, 0.03, 0.17, 0.5, 0.61, 0.99, 1.0):
        out = mod.apply_lut(lut, (t, t, t))
        assert abs(out[0] - (0.1 + 0.8 * t)) < 1e-12
        assert abs(out[1] - (0.2 + 0.5 * t)) < 1e-12
        assert abs(out[2] - (0.3 + 0.4 * t)) < 1e-12


def test_trilinear_beats_nearest_neighbor():
    """2x2x2 恒等 LUT 在正中心：三线性给 0.5，最近邻只能给 0 或 1。"""
    data = [(r, g, b) for b in range(2) for g in range(2) for r in range(2)]
    lut = mod.LUT3D(2, (0, 0, 0), (1, 1, 1), data)
    out = mod.apply_lut(lut, (0.5, 0.5, 0.5))
    assert all(abs(v - 0.5) < 1e-12 for v in out)
    # 非对角位置同样必须是插值，而非落到某个节点。
    out = mod.apply_lut(lut, (0.25, 0.75, 0.5))
    assert all(abs(a - b) < 1e-12 for a, b in zip(out, (0.25, 0.75, 0.5)))
    lut33 = _quadratic_lut(33)
    pairs = []
    for i in range(101):
        t = i / 100
        out = mod.apply_lut(lut33, (t, t, t))
        pairs.append((out, (t * t, t * t, t * t)))
    # 33 格点的分段线性近似平方函数，最大误差远小于最近邻的 ~0.03。
    assert mod.measure_error(pairs) < 1e-3


def test_trilinear_mixed_axes():
    """验证红/绿/蓝三个轴的下标顺序正确，而不是只测对角。"""
    size = 2
    data = [(r, g, b) for b in range(size) for g in range(size) for r in range(size)]
    lut = mod.LUT3D(size, (0, 0, 0), (1, 1, 1), data)
    out = mod.apply_lut(lut, (0.25, 0.5, 0.75))
    assert out == (0.25, 0.5, 0.75)
    swapped = mod.apply_lut(lut, (1.0, 0.0, 0.5))
    assert swapped == (1.0, 0.0, 0.5)


# ---------------------------------------------------------------------------
# 3. 域外钳制
# ---------------------------------------------------------------------------

def test_clamp_outside_domain():
    lut = mod.load_cube(CUBE)
    out = mod.apply_lut(lut, (-0.5, 2.0, 1.5))
    assert all(0.0 <= v <= 1.0 for v in out)


def test_clamp_matches_boundary_values():
    lut = _quadratic_lut(3)
    below = mod.apply_lut(lut, (-10.0, -1e-6, 0.25))
    at_min = mod.apply_lut(lut, (0.0, 0.0, 0.25))
    assert below == at_min
    above = mod.apply_lut(lut, (10.0, 2.0, 0.25))
    at_max = mod.apply_lut(lut, (1.0, 1.0, 0.25))
    assert above == at_max


def test_nan_input_does_not_propagate():
    lut = _quadratic_lut(3)
    out = mod.apply_lut(lut, (float("nan"), 0.5, float("inf")))
    assert all(math.isfinite(v) for v in out)
    # NaN 按域下界、+inf 按域上界处理。
    assert out == mod.apply_lut(lut, (0.0, 0.5, 1.0))


def test_clamped_count_in_cli():
    lut = mod.load_cube(CUBE)
    image = [(-1, 0, 0), (0.5, 0.5, 0.5), (2, 2, 2), (0, 0, 1)]
    _, err, clamped, _ = cli.evaluate(lut, image)
    assert clamped == 2
    assert err < 1e-12


# ---------------------------------------------------------------------------
# 4. 校验：恒等、误差口径
# ---------------------------------------------------------------------------

def test_identity_lut_roundtrip():
    lut = mod.load_cube(CUBE)
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        out = mod.apply_lut(lut, (v, v, v))
        assert abs(out[0] - v) < 0.02 and abs(out[1] - v) < 0.02 and abs(out[2] - v) < 0.02


def test_identity_33_preserves_values():
    path = write_cube(identity_cube(33))
    try:
        lut = mod.load_cube(path)
    finally:
        os.remove(path)
    for t in (0.0, 1 / 255, 0.123456, 0.5, 0.789, 1.0):
        out = mod.apply_lut(lut, (t, t, t))
        for a, b in zip(out, (t, t, t)):
            assert abs(a - b) < 1e-12


def test_measure_error_zero_for_same():
    lut = mod.load_cube(CUBE)
    pairs = [(0.2, 0.3, 0.4)]
    vals = mod.apply_lut(lut, pairs[0])
    assert mod.measure_error([(vals, list(vals))]) < 1e-9


def test_measure_error_is_max_abs_channel():
    assert mod.measure_error([((0.1, 0.2, 0.3), (0.1, 0.2, 0.3))]) == 0.0
    assert abs(mod.measure_error([((0.1, 0.2, 0.3), (0.1, 0.2, 0.35))]) - 0.05) < 1e-12
    assert mod.measure_error([((0.1, 0.2, 0.3), (0.0, 0.2, 0.3)),
                              ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))]) == 0.1
    assert mod.measure_error([]) == 0.0
    assert mod.measure_error([((float("nan"), 0, 0), (0, 0, 0))]) == math.inf


def test_measure_error_rejects_bad_pairs():
    _expect(lambda: mod.measure_error([(0.1, 0.2)]), (ValueError, TypeError))
    _expect(lambda: mod.measure_error([((0, 0), (0, 0, 0))]), ValueError)


# ---------------------------------------------------------------------------
# 5. 边界：1x1x1、负值域、纯黑白
# ---------------------------------------------------------------------------

def test_single_node_lut():
    lut = mod.LUT3D(1, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), [(0.2, 0.4, 0.6)])
    for rgb in ((0, 0, 0), (0.5, 0.5, 0.5), (1, 1, 1), (-5, 5, 0.25)):
        assert mod.apply_lut(lut, rgb) == (0.2, 0.4, 0.6)


def test_single_node_lut_from_file():
    path = write_cube("LUT_3D_SIZE 1\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n0.2 0.4 0.6\n")
    try:
        lut = mod.load_cube(path)
    finally:
        os.remove(path)
    assert mod.apply_lut(lut, (0.9, 0.1, 0.5)) == (0.2, 0.4, 0.6)


def test_negative_domain():
    path = write_cube(identity_cube(3, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)))
    try:
        lut = mod.load_cube(path)
    finally:
        os.remove(path)
    assert lut.domain_min == (-1.0, -1.0, -1.0)
    for t in (-1.0, -0.5, 0.0, 0.25, 1.0):
        out = mod.apply_lut(lut, (t, t, t))
        assert abs(out[0] - t) < 1e-12
    assert mod.apply_lut(lut, (-2.0, 2.0, 0.0)) == mod.apply_lut(lut, (-1.0, 1.0, 0.0))


def test_asymmetric_negative_domain():
    lut = mod.LUT3D(2, (-2.0, 0.0, 5.0), (0.0, 1.0, 9.0),
                    [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
                     (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1)])
    assert mod.apply_lut(lut, (-1.0, 0.5, 7.0)) == (0.5, 0.5, 0.5)
    assert mod.apply_lut(lut, (-100.0, -100.0, -100.0)) == (0.0, 0.0, 0.0)
    assert mod.apply_lut(lut, (100.0, 100.0, 100.0)) == (1.0, 1.0, 1.0)


def test_pure_black_and_white():
    lut = _quadratic_lut(33)
    assert mod.apply_lut(lut, (0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0)
    assert mod.apply_lut(lut, (1.0, 1.0, 1.0)) == (1.0, 1.0, 1.0)
    # 纯黑纯白在域外也钳制到端点，结果确定。
    assert mod.apply_lut(lut, (-1.0, -1.0, -1.0)) == (0.0, 0.0, 0.0)
    assert mod.apply_lut(lut, (2.0, 2.0, 2.0)) == (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# 6. 规模
# ---------------------------------------------------------------------------

def _image(width, height):
    return [(x / (width - 1), y / (height - 1), (x * 7 + y * 13) % width / (width - 1))
            for y in range(height) for x in range(width)]


def test_512x512_with_33_lut_under_5s():
    path = write_cube(identity_cube(33))
    try:
        lut = mod.load_cube(path)
    finally:
        os.remove(path)
    image = _image(512, 512)
    start = time.perf_counter()
    out = mod.apply_lut(lut, image)
    elapsed = time.perf_counter() - start
    assert len(out) == len(image)
    assert elapsed < 5.0, "512x512 配 33^3 耗时 %.2fs，超过 5s" % elapsed


def test_doubling_image_size_is_near_linear():
    lut = _quadratic_lut(33)
    small = _image(128, 128)
    large = _image(256, 256)

    def best_of(image, runs=3):
        best = float("inf")
        for _ in range(runs):
            start = time.perf_counter()
            mod.apply_lut(lut, image)
            best = min(best, time.perf_counter() - start)
        return best

    t_small = best_of(small)
    t_large = best_of(large)
    # 像素数 4 倍；允许较大抖动，但必须明显低于超线性的 16 倍。
    assert t_large / t_small < 10.0, "耗时比 %.2f，疑似超线性" % (t_large / t_small)


# ---------------------------------------------------------------------------
# 7. 批量接口与 CLI
# ---------------------------------------------------------------------------

def test_apply_accepts_iterables():
    lut = mod.load_cube(CUBE)
    image = [(0.1, 0.2, 0.3), (0.4, 0.5, 0.6)]
    single = [mod.apply_lut(lut, p) for p in image]
    assert mod.apply_lut(lut, image) == single
    assert mod.apply_lut(lut, iter(image)) == single


def test_apply_rejects_bad_input():
    lut = mod.load_cube(CUBE)
    _expect(lambda: mod.apply_lut(lut, (0.1, 0.2)), TypeError)
    _expect(lambda: mod.apply_lut(lut, [(0.1, 0.2, 0.3), (0.1, 0.2)]), TypeError)
    _expect(lambda: mod.apply_lut("not a lut", (0.1, 0.2, 0.3)), TypeError)


def test_cli_writes_json():
    out = os.path.join(tempfile.gettempdir(), "lut3d_cli_test.json")
    try:
        result = cli.main([CUBE, "--out", out, "--width", "16", "--height", "8"])
        with open(out, encoding="utf-8") as fh:
            data = json.load(fh)
    finally:
        if os.path.exists(out):
            os.remove(out)
    assert data["size"] == 2
    assert data["pixels"] == 128
    assert data["max_error"] < 1e-12
    assert data["clamped_pixels"] > 0
    assert data["elapsed_seconds"] > 0
    assert result["max_error"] == data["max_error"]
