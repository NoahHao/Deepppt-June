#!/usr/bin/env python3
"""
image_extract — 文档图片提取与检索模块
============================================
从 DOCX/PPTX/PDF 文件中提取嵌入图片，建立语义索引，支持自然语言检索。

子命令：
  scan <path>      扫描目录或文件，提取图片并建立索引
  search <query>   自然语言检索图片（如 "金融行业客户案例架构图"）
  stats            显示索引统计信息

遵循项目惯例，与 PPT_Recall 互补：
  - image_extract + PPT_Recall = 完整的知识库检索体系
  - 索引存放在 images/image_extract_index.json
  - 图片归档在 images/archive/ 下

使用示例：
  python image_extract.py scan 华为LightAI/
  python image_extract.py search "金融行业客户案例架构图"
  python image_extract.py search "LightAI 组网图"
  python image_extract.py stats
"""

import sys
from pathlib import Path

# 确保能找到同目录下 image_extract 包
_SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_SCRIPT_DIR))

from image_extract.cli import main

if __name__ == "__main__":
    sys.exit(main())
