# -*- coding: utf-8 -*-
"""lut3d"""

from __future__ import annotations

__all__ = ["LUT3D", "apply_lut", "load_cube", "measure_error"]


class LUT3D:
    """LUT3D"""

    def __init__(self, size, domain_min, domain_max, data):
        """3D LUT 容器"""
        raise NotImplementedError("LUT3D.__init__ 尚未实现")


def load_cube(path):
    """解析 .cube 文件"""
    raise NotImplementedError("load_cube 尚未实现")


def apply_lut(lut, rgb):
    """按三线性插值应用"""
    raise NotImplementedError("apply_lut 尚未实现")


def measure_error(pairs):
    """返回最大误差"""
    raise NotImplementedError("measure_error 尚未实现")
