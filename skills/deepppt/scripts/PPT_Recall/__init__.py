#!/usr/bin/env python3
"""
PPT_Recall — 知识库幻灯片召回模块
==================================
完全自包含，无任何外部项目依赖。

双路径检索（关键词 + AI 解耦）+ slide 级召回 + COM 粘贴（保持源格式）

合并铁规：
  1. 使用 ExecuteMso("PasteSourceFormatting") — 等效右键"保留源格式"
  2. 粘贴后新页保留源设计 — 锁定背景/颜色/字体
"""

from .engine import PPTRecallEngine
from .indexer import scan_and_index, load_index
from .merge import merge_slides

__all__ = ['PPTRecallEngine', 'scan_and_index', 'load_index', 'merge_slides']
