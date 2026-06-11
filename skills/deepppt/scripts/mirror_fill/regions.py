#!/usr/bin/env python3
"""
mirror_fill regions — 幻灯片区域定义和 shape 定位
===================================================

通用区域系统，支持任意布局（左右/左中右/上下/自定义）。

区域用 EMU 坐标定义（与 python-pptx shape.left/top 一致）：
  - 标准 16:9 幻灯片: 12192000 x 6858000 EMU
  - 1 inch = 914400 EMU

预设布局可直接使用，也可自定义 SlideRegion。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class SlideRegion:
    """幻灯片上一个矩形区域。

    Attributes:
        name: 区域名称 (如 "left", "right", "header")
        x_range: X 坐标范围 (min_emu, max_emu)，None 表示不限
        y_range: Y 坐标范围 (min_emu, max_emu)，None 表示不限
    """
    name: str
    x_range: Tuple[int, int] | None = None
    y_range: Tuple[int, int] | None = None

    def contains(self, left: int, top: int) -> bool:
        """判断坐标 (left, top) 是否在此区域内"""
        if self.x_range:
            if left < self.x_range[0] or left > self.x_range[1]:
                return False
        if self.y_range:
            if top < self.y_range[0] or top > self.y_range[1]:
                return False
        return True

    def __repr__(self):
        parts = [f"name={self.name}"]
        if self.x_range:
            parts.append(f"x={self.x_range[0]}-{self.x_range[1]}")
        if self.y_range:
            parts.append(f"y={self.y_range[0]}-{self.y_range[1]}")
        return f"SlideRegion({', '.join(parts)})"


# ═══════════════════════════════════════════════════════
# 预设布局模板
# ═══════════════════════════════════════════════════════

# 标准 16:9 幻灯片尺寸 (EMU)
SLIDE_W = 12_192_000
SLIDE_H = 6_858_000 


def _make_layout(**regions: Tuple) -> Dict[str, SlideRegion]:
    """快捷创建布局字典"""
    result = {}
    for name, (x1, x2, y1, y2) in regions.items():
        result[name] = SlideRegion(
            name=name,
            x_range=(int(x1), int(x2)),
            y_range=(int(y1), int(y2)),
        )
    return result


# 左右二分
LAYOUT_LEFT_RIGHT = _make_layout(
    left  = (0,        8_000_000, 0, SLIDE_H),
    right = (8_000_000, SLIDE_W,   0, SLIDE_H),
)

# 左中右三分
LAYOUT_LEFT_CENTER_RIGHT = _make_layout(
    left   = (0,         4_000_000, 0, SLIDE_H),
    center = (4_000_000,  9_000_000, 0, SLIDE_H),
    right  = (9_000_000, SLIDE_W,   0, SLIDE_H),
)

# 上下二分
LAYOUT_TOP_BOTTOM = _make_layout(
    top    = (0, SLIDE_W, 0,         3_500_000),
    bottom = (0, SLIDE_W, 3_500_000, SLIDE_H),
)

# 上中下三分
LAYOUT_TOP_MIDDLE_BOTTOM = _make_layout(
    top    = (0, SLIDE_W, 0,         2_200_000),
    middle = (0, SLIDE_W, 2_200_000, 4_600_000),
    bottom = (0, SLIDE_W, 4_600_000, SLIDE_H),
)

# 全部预设
PRESET_LAYOUTS = {
    "left_right": LAYOUT_LEFT_RIGHT,
    "left_center_right": LAYOUT_LEFT_CENTER_RIGHT,
    "top_bottom": LAYOUT_TOP_BOTTOM,
    "top_middle_bottom": LAYOUT_TOP_MIDDLE_BOTTOM,
}


def get_layout(name: str) -> Dict[str, SlideRegion]:
    """获取预设布局"""
    if name in PRESET_LAYOUTS:
        return PRESET_LAYOUTS[name]
    raise ValueError(
        f"未知布局: {name}。可用: {list(PRESET_LAYOUTS.keys())}"
    )


def custom_layout(**regions: Tuple) -> Dict[str, SlideRegion]:
    """创建自定义布局。

    Args:
        **regions: 区域名=(x1, x2, y1, y2)，EMU 单位
                   例如: custom_layout(hero=(0, 12M, 0, 3M), cards=(0, 12M, 3M, 7M))

    Returns:
        Dict[str, SlideRegion]
    """
    return _make_layout(**regions)
