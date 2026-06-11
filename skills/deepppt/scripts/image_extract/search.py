#!/usr/bin/env python3
"""
image_extract 语义搜索 — 自然语言检索图片索引
================================================
支持自然语言检索，如：
  "我需要金融行业的一个客户案例架构图"
  "我需要一份light AI 组网图"
  "搜索数据中心相关的系统架构图"

搜索逻辑：
  1. 标签匹配（search_tags）：对查询进行中文分词，匹配索引中的标签
  2. 上下文文本匹配：在 context_text 和 description_hint 中匹配查询关键词
  3. 综合评分排序

使用方式：
  python search.py <query> [--index <json_path>] [--top-k <N>] [--format <fmt>]
  python image_extract.py search <query>    （通过顶层入口）
"""

import json
import os
import re
from pathlib import Path
from typing import List, Optional

DEFAULT_INDEX = os.environ.get('DEFAULT_INDEX')  # 支持环境变量覆盖


def _tokenize(text: str) -> List[str]:
    """智能分词：提取中文词组（多种粒度）和英文单词"""
    tokens = set()
    # 中文连续词组（整体匹配）
    words = re.findall(r'[\u4e00-\u9fff]+', text)
    for w in words:
        tokens.add(w)
        # 对长词组也生成子词组（2-4字滑动窗口）
        if len(w) >= 4:
            for wlen in range(2, 5):
                for i in range(len(w) - wlen + 1):
                    tokens.add(w[i:i + wlen])
    # 英文单词
    tokens.update(w.lower() for w in re.findall(r'\b[a-zA-Z]{2,30}\b', text))
    # 数字
    tokens.update(re.findall(r'\d+', text))
    return list(tokens)


def search(query: str, index_path: str = None, top_k: int = 10, format_filter: str = None):
    """
    在图片索引中搜索匹配的图片。
    
    Args:
        query: 自然语言查询（如 "金融行业客户案例架构图"）
        index_path: 索引 JSON 路径（默认自动查找）
        top_k: 返回前 K 个结果
        format_filter: 可选格式过滤（png/jpeg/gif 等）
    
    Returns:
        list: 匹配的图片列表，按分数降序
    """
    if index_path is None:
        index_path = DEFAULT_INDEX
    if index_path is None:
        # 尝试自动查找（基于脚本所在目录，而非 cwd）
        script_dir = Path(__file__).parent.resolve()
        candidates = [
            script_dir / 'images' / 'image_extract_index.json',
            script_dir.parent / 'images' / 'image_extract_index.json',
        ]
        for c in candidates:
            if c.exists():
                index_path = str(c)
                break
    
    if index_path is None or not Path(index_path).exists():
        print(f"  索引文件不存在: {index_path}")
        print(f"  请先运行: python image_extract.py scan <目录>")
        return []
    
    # 加载索引
    with open(index_path, 'r', encoding='utf-8') as f:
        index = json.load(f)
    
    images = index.get('images', {})
    if not images:
        print("  索引为空，请先运行扫描")
        return []
    
    # 对查询进行分词
    query_tokens = _tokenize(query.lower())
    if not query_tokens:
        print("  查询为空")
        return []
    
    scored = []
    for key, entry in images.items():
        # 获取搜索标签
        tags = [t.lower() for t in entry.get('search_tags', [])]
        context = (entry.get('context_text', '') or '').lower()
        desc = (entry.get('description_hint', '') or '').lower()
        slide_title = (entry.get('slide_title', '') or '').lower()
        source_file = (entry.get('source_filename', '') or '').lower()
        archive_name = entry.get('archive_name', '').lower()
        
        score = 0.0
        
        # 1. 标签精确匹配（权重最高）
        for qt in query_tokens:
            for t in tags:
                if qt in t or t in qt:
                    score += 3.0
                    break
            # 查 source_file 中的关键词
            if qt in source_file:
                score += 2.0
            # 查 slide_title
            if qt in slide_title:
                score += 2.0
        
        # 2. 上下文文本匹配
        for qt in query_tokens:
            count = context.count(qt) + desc.count(qt)
            if count > 0:
                score += min(count * 1.0, 5.0)
        
        # 3. archive_name 匹配
        for qt in query_tokens:
            if qt in archive_name:
                score += 1.5
        
        if score > 0:
            scored.append((score, entry))
    
    # 按分数降序
    scored.sort(key=lambda x: -x[0])
    
    # 格式过滤
    if format_filter:
        scored = [(s, e) for s, e in scored
                  if e.get('format', '').lower() == format_filter.lower()]
    
    # 取 top_k
    results = scored[:top_k]
    
    # 打印结果
    print(f"\n  搜索: \"{query}\"")
    print(f"  索引: {index_path}")
    print(f"  共匹配 {len(results)} 条结果 (总图片数: {len(images)})\n")
    
    for i, (score, entry) in enumerate(results, 1):
        arc_path = entry.get('archive_path', '')
        fmt = entry.get('format', '?')
        size_kb = entry.get('size_bytes', 0) / 1024
        slide = entry.get('slide_number', '')
        title = entry.get('description_hint', '')
        
        print(f"  #{i} (得分: {score:.1f})")
        print(f"     文件名: {entry['archive_name']}")
        print(f"     格式: {fmt} ({size_kb:.0f}KB)")
        if slide:
            print(f"     页码: {slide}")
        if title:
            print(f"     描述: {title[:100]}")
        print(f"     来源: {entry.get('source_filename', '')}")
        print(f"     归档: {arc_path}")
        print()
    
    return results


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python search.py <query> [--index <json_path>] [--top-k <N>] [--format <fmt>]")
        print("示例:")
        print('  python search.py "金融行业客户案例架构图"')
        print('  python search.py "LightAI 组网图"')
        print('  python search.py "数据中心架构图" --format png')
        sys.exit(1)
    
    query = sys.argv[1]
    index_path = None
    top_k = 10
    format_filter = None
    
    if "--index" in sys.argv:
        idx = sys.argv.index("--index")
        if idx + 1 < len(sys.argv):
            index_path = sys.argv[idx + 1]
    if "--top-k" in sys.argv:
        idx = sys.argv.index("--top-k")
        if idx + 1 < len(sys.argv):
            top_k = int(sys.argv[idx + 1])
    if "--format" in sys.argv:
        idx = sys.argv.index("--format")
        if idx + 1 < len(sys.argv):
            format_filter = sys.argv[idx + 1]
    
    search(query, index_path, top_k, format_filter)
