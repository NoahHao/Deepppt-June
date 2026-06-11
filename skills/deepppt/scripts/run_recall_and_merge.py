#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""将提取的单页 PPTX 合并。因为已经在 recall.py 中完成提取，这里只做合并。"""

import os, sys, zipfile

sys.path.insert(0, os.path.dirname(__file__))
from _zip_utils import extract_slides

# 配置
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_ROOT = os.path.join(PROJECT_ROOT, 'data', 'output')

# 单页PPTX路径
slide_pptx_1 = os.path.join(OUTPUT_ROOT, '兴业银行案例_page_1.pptx')
slide_pptx_2 = os.path.join(OUTPUT_ROOT, 'Atlas850产品介绍_page_1.pptx')

# 输出合并文件路径
merged_path = os.path.join(OUTPUT_ROOT, '兴业银行案例_Atlas850_合并.pptx')

# 源文件路径（放在项目根目录下 data/input/ 中）
INPUT_ROOT = os.path.join(PROJECT_ROOT, 'data', 'input')
src_path_1 = os.path.join(INPUT_ROOT, '兴业银行案例.pptx')
src_path_2 = os.path.join(INPUT_ROOT, 'Atlas 850的产品介绍.docx.pdf.pptx')

# 确保输出目录存在
os.makedirs(OUTPUT_ROOT, exist_ok=True)

# 提取第1页
print("=" * 60)
print("提取: 兴业银行案例 page 1")
print("=" * 60)
extract_slides(src_path_1, slide_pptx_1, [1])

print()

print("=" * 60)
print("提取: Atlas 850产品介绍 page 1")
print("=" * 60)
extract_slides(src_path_2, slide_pptx_2, [1])

# 确认提取结果
print()
print("=" * 60)
print("检测提取结果")
print("=" * 60)
for p in [slide_pptx_1, slide_pptx_2]:
    if os.path.exists(p):
        with zipfile.ZipFile(p, 'r') as z:
            slides = [n for n in z.namelist() 
                      if 'ppt/slides/slide' in n and n.endswith('.xml') and '_rels' not in n]
            print(f"  {os.path.basename(p)}: {len(slides)} slides - {slides}")
    else:
        print(f"  {os.path.basename(p)}: NOT FOUND")

# 现在合并
print()
print("=" * 60)
print("合并两个单页PPTX")
print("=" * 60)

# 使用项目自带的合并函数
from pptx_merge import merge_slides

result = merge_slides([slide_pptx_1, slide_pptx_2], merged_path)
print(f"\n合并完成: {result}")

# 验证
with zipfile.ZipFile(result, 'r') as z:
    slides = [n for n in z.namelist() 
              if 'ppt/slides/slide' in n and n.endswith('.xml') and '_rels' not in n]
    print(f"合并后幻灯片数: {len(slides)}")
    for s in sorted(slides):
        print(f"  {s}")
