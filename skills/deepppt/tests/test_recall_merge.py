#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""使用项目自带的 PPT_Recall/merge.py 进行完整的 recall 和合并。"""

import os, sys, zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 将 PPT_Recall 目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'PPT_Recall'))
from merge import merge_slides

# 源文件路径（来自 knowledge_base）
kb_dir = os.path.join(PROJECT_ROOT, 'knowledge_base')
src1 = os.path.join(kb_dir, 'customer_cases', '客户案例.pptx')
src2 = os.path.join(kb_dir, 'product_intro', '产品能力.pptx')

# 输出目录（在 PROJECT_ROOT 下创建 data/output）
out_dir = os.path.join(PROJECT_ROOT, 'data', 'output')
os.makedirs(out_dir, exist_ok=True)

merged_path = os.path.join(out_dir, '兴业银行案例_Atlas850_合并.pptx')

# 通过 merge_slides 统一入口完成所有工作
# entries 格式: [(pptx_path, slide_num), ...]
# 客户案例.pptx Slide 3 = 兴业银行案例; 产品能力.pptx Slide 1 = Atlas 850E 产品介绍
entries = [
    (src1, 3),  # 兴业银行案例（第3页）
    (src2, 1),  # Atlas 850E 产品介绍（第1页）
]

print('=' * 60)
print('PPT Recall 合并流程')
print('=' * 60)
print(f'输入: {len(entries)} 个源文件')
for p, n in entries:
    exists = '✓' if os.path.exists(p) else '✗ 不存在'
    print(f'  [{exists}] {os.path.basename(p)}: 第{n}页')

print()
result = merge_slides(entries, merged_path)

# 验证结果
print()
print('=' * 60)
print('验证合并结果')
print('=' * 60)
if os.path.exists(result):
    with zipfile.ZipFile(result, 'r') as z:
        slides = [n for n in z.namelist()
                  if 'ppt/slides/slide' in n and n.endswith('.xml') and '_rels' not in n]
        print(f'最终输出文件: {result}')
        print(f'幻灯片总数: {len(slides)}')
        for s in sorted(slides):
            print(f'  {s}')
else:
    print(f'输出文件不存在: {result}')
