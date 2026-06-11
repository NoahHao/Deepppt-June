#!/usr/bin/env python3
"""
image_extract 模块初始化
"""
from .extractor import extract_images, ExtractedImage
from .indexer import scan_and_index, load_index
from .search import search as search_images

# ppt_generator 导入（可选依赖 python-pptx）
try:
    from .ppt_generator import generate_ppt
    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False

__all__ = [
    'extract_images',
    'ExtractedImage',
    'scan_and_index',
    'load_index',
    'search_images',
    'generate_ppt',
]
