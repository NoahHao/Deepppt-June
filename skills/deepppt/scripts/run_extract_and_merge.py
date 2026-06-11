#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""提取两个单页PPTX并合并。"""

import os, sys, zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from _zip_utils import extract_slides

# 源文件路径（放在项目根目录下 data/input/ 中）
INPUT_ROOT = os.path.join(PROJECT_ROOT, 'data', 'input')
src1 = os.path.join(INPUT_ROOT, '兴业银行案例.pptx')
src2 = os.path.join(INPUT_ROOT, 'Atlas 850的产品介绍.docx.pdf.pptx')

# 输出目录
OUTPUT_ROOT = os.path.join(PROJECT_ROOT, 'data', 'output')
os.makedirs(OUTPUT_ROOT, exist_ok=True)

# 单页PPTX路径
out1 = os.path.join(OUTPUT_ROOT, '兴业银行案例_page_1.pptx')
out2 = os.path.join(OUTPUT_ROOT, 'Atlas850产品介绍_page_1.pptx')
merged_path = os.path.join(OUTPUT_ROOT, '兴业银行案例_Atlas850_合并.pptx')

print('=' * 60)
print('Step 1: 提取 兴业银行案例 page 1')
print('=' * 60)
extract_slides(src1, out1, [1])

print()
print('=' * 60)
print('Step 2: 提取 Atlas 850产品介绍 page 1')
print('=' * 60)
extract_slides(src2, out2, [1])

print()
print('=' * 60)
print('Step 3: 验证提取结果')
print('=' * 60)
for p in [out1, out2]:
    if os.path.exists(p):
        with zipfile.ZipFile(p, 'r') as z:
            slides = [n for n in z.namelist()
                      if 'ppt/slides/slide' in n and n.endswith('.xml') and '_rels' not in n]
            print(f'  {os.path.basename(p)}: {len(slides)} slide(s) - {slides}')
    else:
        print(f'  {os.path.basename(p)}: NOT FOUND')

print()
print('=' * 60)
print('Step 4: 合并两个单页PPTX')
print('=' * 60)

from pptx_merge import merge_slides

result = merge_slides([out1, out2], merged_path)
print(f'合并完成: {result}')

# 验证合并结果
with zipfile.ZipFile(result, 'r') as z:
    slides = [n for n in z.namelist()
              if 'ppt/slides/slide' in n and n.endswith('.xml') and '_rels' not in n]
    print(f'合并后幻灯片数: {len(slides)}')
    for s in sorted(slides):
        print(f'  {s}')

print(f'\n最终输出文件: {result}')
