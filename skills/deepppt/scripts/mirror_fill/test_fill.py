#!/usr/bin/env python3
"""
mirror_fill: fill + save 功能测试
=====================================
工作流: inspect → fill → save
"""

import sys
import os
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)

from mirror_fill import MirrorFiller

src = os.path.join(
    SCRIPTS_DIR, "projects", "huawei_solution_ppt169_20260602",
    "exports", "huawei_solution_20260602_163633.pptx"
)
output = os.path.join(
    SCRIPTS_DIR, "projects", "test_fill_output.pptx"
)

print("=" * 70)
print("STEP 1: Inspect")
print("=" * 70)

filler = MirrorFiller(src, slide_num=1, layout="left_right")
filler.inspect()

print("=" * 70)
print("STEP 2: find_text - 精确定位文本内容")
print("=" * 70)

# 用 find_text 搜索关键文本，绕过控制台编码问题
for keyword in ["DCS", "华为", "Huawei", "Confidential", "安全", "智能", "生态"]:
    results = filler.find_text(keyword)
    for idx, text in results:
        # 打印原始字符码，避免编码问题导致的乱码
        text_bytes = text.encode('utf-8', errors='replace')
        print(f"  Shape #{idx}: text_len={len(text)} text_hex={text.encode('utf-8', errors='replace').hex()[:80]}...")
        print(f"  Shape #{idx}: {repr(text[:200])}")

print()
print("=" * 70)
print("STEP 3: fill - 执行文本替换")
print("=" * 70)

# 根据 inspect 看到的文本（即使显示乱码）进行替换
# left 区域有多个文本，right 区域有 "1/5"
# 先替换 right 区域的文本
filler.fill("left_right", {
    "right": {"1/5": "2/5"}
})

print()
print("=" * 70)
print("STEP 4: save - 保存 PPTX")
print("=" * 70)

result_path = filler.save(output)
print(f"\n输出文件大小: {result_path.stat().st_size} 字节")

print("\n" + "=" * 70)
print("验证: 重新打开保存的文件进行 inspect")
print("=" * 70)

# 验证：重新加载输出的文件，检查 right 区域是否已替换
filler2 = MirrorFiller(result_path, slide_num=1, layout="left_right")
filler2.inspect()

right_results = filler2.find_text("2/5")
print(f"\n验证替换结果: 找到 \"2/5\" 的次数 = {len(right_results)}")
for idx, text in right_results:
    print(f"  Shape #{idx}: {repr(text)}")
