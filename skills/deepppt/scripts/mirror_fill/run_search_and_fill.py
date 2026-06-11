#!/usr/bin/env python3
"""
run_search_and_fill — 一键搜索+填充 入口脚本
===============================================

工作流:
  1. 调用 LLM_Search 语义搜索向量库，检索 "DCS解决方案" 等关键词
  2. 根据搜索结果定位最匹配的源 PPTX 幻灯片
  3. 使用 mirror_fill 的 XML 层文本替换引擎
  4. 将 PPT 右侧区域文字替换为 VMware 的 3 项优势能力
  5. 输出新的 PPTX 文件

Usage:
    python3 run_search_and_fill.py
"""

import sys
import os
from pathlib import Path

# 确保可以导入本包
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from mirror_fill import Filler, FillManifest, SearchAndFill, PipelineContext

# ═══════════════════════════════════════════════════════
# 配置区
# ═══════════════════════════════════════════════════════

# 1. 要搜索的关键词（触发向量库检索）
SEARCH_QUERIES = [
    "DCS解决方案",           # 搜索 DCS 解决方案相关内容
    "DCS 数据中心 架构图",    # 备选搜索词
]

# 2. 要替换的新文本（VMware 的 3 项优势能力）
VMWARE_ADVANTAGES = [
    "vSphere 虚拟化：资源利用率提升 3-5 倍，降低硬件总拥有成本",
    "vSAN 存储虚拟化：简化存储架构，性能线性扩展至 PB 级",
    "VMware Aria 智能运维：AI 驱动运维，预测性分析降低故障宕机 60%",
]

# 3. 搜索参数
TOP_K = 3               # 每个搜索词返回的候选幻灯片数量

# 4. 输出目录
OUTPUT_DIR = _THIS_DIR / "search_fill_output"


# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  mirror_fill — 搜索 + 填充 一键工作流")
    print("=" * 70)
    print()
    print(f"🔍 搜索关键词: {SEARCH_QUERIES}")
    print(f"📝 待填充文本: ")
    for i, adv in enumerate(VMWARE_ADVANTAGES, 1):
        print(f"    {i}. {adv}")
    print()

    # ------------------------------------------------------------------
    # Step 1: 创建 PipelineContext（配置流水线上下文）
    # ------------------------------------------------------------------
    ctx = PipelineContext(
        search_queries=SEARCH_QUERIES,
        top_k=TOP_K,
        output_dir=OUTPUT_DIR,
        debug=True,
    )

    # ------------------------------------------------------------------
    # Step 2: 初始化 SearchAndFill 执行器
    # ------------------------------------------------------------------
    print("📦 初始化 SearchAndFill 执行器...")
    ssf = SearchAndFill(ctx)
    print("   ✅ 初始化完成")
    print()

    # ------------------------------------------------------------------
    # Step 3: 执行 LLM_Search（触发向量库检索）
    # ------------------------------------------------------------------
    print("-" * 70)
    print(" STEP 1: LLM_Search 语义搜索（触发向量库检索）")
    print("-" * 70)

    results = ssf.search()
    print()

    if not results:
        print("❌ 搜索未返回任何结果！")
        print("   请检查 LLM_Search 索引是否已构建。")
        sys.exit(1)

    # 打印搜索结果摘要
    for i, res in enumerate(results):
        print(f"   #{i}: {res.get('display_text', '')[:80]}")
        print(f"       source: {res.get('source_pptx', 'N/A')}")
        print(f"       score