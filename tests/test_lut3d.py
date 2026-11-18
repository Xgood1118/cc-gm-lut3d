# -*- coding: utf-8 -*-
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lut3d as mod  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def test_load_and_size():
    lut = mod.load_cube(os.path.join(DATA, "lut.cube"))
    assert lut.size == 2


def test_identity_lut_roundtrip():
    lut = mod.load_cube(os.path.join(DATA, "lut.cube"))
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        out = mod.apply_lut(lut, (v, v, v))
        assert abs(out[0] - v) < 0.02 and abs(out[1] - v) < 0.02 and abs(out[2] - v) < 0.02


def test_clamp_outside_domain():
    lut = mod.load_cube(os.path.join(DATA, "lut.cube"))
    out = mod.apply_lut(lut, (-0.5, 2.0, 1.5))
    assert all(0.0 <= v <= 1.0 for v in out)


def test_trilinear_between_nodes():
    lut = mod.load_cube(os.path.join(DATA, "lut.cube"))
    out = mod.apply_lut(lut, (0.5, 0.5, 0.5))
    assert all(abs(v - 0.5) < 0.03 for v in out)


def test_measure_error_zero_for_same():
    lut = mod.load_cube(os.path.join(DATA, "lut.cube"))
    pairs = [(0.2, 0.3, 0.4)]
    vals = mod.apply_lut(lut, pairs[0])
    assert mod.measure_error([(vals, list(vals))]) < 1e-9


def test_bad_size_raises():
    p = os.path.join(DATA, "bad.cube")
    with open(p, "w", encoding="utf-8") as f:
        f.write("LUT_3D_SIZE 2\n0.0 0.0 0.0\n")
    try:
        try:
            mod.load_cube(p)
        except NotImplementedError:
            raise
        except Exception:
            pass
        else:
            raise AssertionError("尺寸不符必须报错")
    finally:
        os.remove(p)
