#!/usr/bin/env python3
"""
image_extract 命令行入口
========================
支持四个子命令：
  scan <path>      — 扫描目录或文件，提取图片并建立索引
  search <query>   — 在索引中搜索图片
  stats            — 显示索引统计信息
  ppt <index> <out> — 从索引生成 PPTX（图片等比例缩放，纯白背景）

使用方式：
  python image_extract.py scan 华为LightAI/
  python image_extract.py search "金融行业客户案例架构图"
  python image_extract.py search "LightAI 组网图"
  python image_extract.py stats
  python image_extract.py ppt index.json output.pptx

整合 recommendation：
  1. 与 PPT_Recall 风格一致，索引存放在 images/image_extract_index.json
  2. 图片归档在 images/archive/ 下，使用唯一命名
  3. 搜索支持自然语言，自动分词匹配
  4. PPT 生成：等比例缩放图片（防止变形）、纯白背景（无底板）
"""

import sys
import json
from pathlib import Path

# 确保同目录下可导入
_SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(_SCRIPT_DIR.parent))  # 加入 scripts 目录（父目录）以便使用 from image_extract import ...
sys.path.insert(0, str(_SCRIPT_DIR))         # 也加入当前目录便于直接导入

from image_extract.indexer import scan_and_index, load_index, _format_bytes
from image_extract.search import search as search_images
from image_extract.search import DEFAULT_INDEX


def cmd_scan(target_path, output_path=None):
    """扫描并建立索引"""
    target = Path(target_path)
    if not target.exists():
        print(f"错误: 路径不存在: {target}")
        return 1
    
    print(f"扫描目标: {target}")
    print(f"{'开始扫描...':>12}")
    
    index = scan_and_index(target, output_path, verbose=True)
    
    if index['total_images'] > 0:
        print(f"\n✅ 完成! 共处理 {index['total_files']} 个文件, "
              f"提取 {index['total_images']} 张唯一图片")
        print(f"   索引文件已保存")
        print(f"   图片归档目录: {index['archive_root']}")
        
        # 显示文件级统计
        print(f"\n   文件明细:")
        for fpath, fstat in index['files'].items():
            p = Path(fpath)
            print(f"     {p.name}: {fstat['image_count']} 张图 ({_format_bytes(fstat['total_bytes'])})")
    else:
        print("\n⚠️  未提取到图片")
    
    return 0


def cmd_search(query, index_path=None, top_k=10, format_filter=None):
    """搜索图片"""
    if not query:
        print("请提供搜索关键词")
        return 1
    
    results = search_images(query, index_path, top_k, format_filter)
    
    if not results:
        print("未找到匹配的图片")
    
    return 0


def cmd_stats(index_path=None):
    """显示索引统计信息"""
    if index_path is None:
        # 自动查找（与 search.py 逻辑一致：优先基于脚本目录，而非当前工作目录）
        candidates = [
            _SCRIPT_DIR / 'images' / 'image_extract_index.json',
            _SCRIPT_DIR.parent / 'images' / 'image_extract_index.json',
        ]
        for c in candidates:
            if c.exists():
                index_path = str(c)
                break
    
    if index_path is None or not Path(index_path).exists():
        print("索引文件不存在")
        print("请先运行: python image_extract.py scan <目录>")
        return 1
    
    index = load_index(index_path)
    images = index.get('images', {})
    files = index.get('files', {})
    
    print(f"\n📊 索引统计")
    print(f"  索引文件: {index_path}")
    print(f"  最后扫描: {index.get('last_scan', 'unknown')}")
    print(f"  处理文件: {index.get('total_files', 0)}")
    print(f"  唯一图片: {index.get('total_images', 0)}")
    print(f"  去重: {index.get('total_duplicates_removed', 0)} 张")
    print(f"  归档目录: {index.get('archive_root', '')}")
    
    # 格式分布统计
    format_counts = {}
    for key, entry in images.items():
        fmt = entry.get('format', 'unknown')
        format_counts[fmt] = format_counts.get(fmt, 0) + 1
    
    if format_counts:
        print(f"\n  图片格式分布:")
        for fmt, count in sorted(format_counts.items(), key=lambda x: -x[1]):
            print(f"    .{fmt}: {count} 张")
    
    # 文件级统计
    if files:
        print(f"\n  文件明细:")
        for fpath, fstat in files.items():
            p = Path(fpath)
            print(f"    {p.name}: {fstat['image_count']} 张 ({_format_bytes(fstat['total_bytes'])})")
    
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    
    cmd = sys.argv[1]
    
    if cmd == "scan":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        if not target:
            print("请指定扫描目标 (目录或文件)")
            return 1
        output = None
        if "--output" in sys.argv:
            idx = sys.argv.index("--output")
            output = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        return cmd_scan(target, output)
    
    elif cmd == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        # 解析参数
        index_path = None
        top_k = 10
        format_filter = None
        if query:
            args_parts = query.split()
            cleaned_parts = []
            for part in args_parts:
                if part.startswith("--"):
                    break
                cleaned_parts.append(part)
            query = " ".join(cleaned_parts)
        
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
        
        return cmd_search(query, index_path, top_k, format_filter)
    
    elif cmd == "stats":
        index_path = None
        if "--index" in sys.argv:
            idx = sys.argv.index("--index")
            if idx + 1 < len(sys.argv):
                index_path = sys.argv[idx + 1]
        return cmd_stats(index_path)
    
    elif cmd == "ppt":
        # 延迟导入 ppt_generator（该模块需要 python-pptx，非必须依赖）
        try:
            from image_extract.ppt_generator import generate_ppt as generate_ppt_images, _load_index
        except ImportError as e:
            print(f"无法导入 ppt_generator 模块: {e}")
            print("请安装 python-pptx: pip install python-pptx")
            return 1
        
        if len(sys.argv) < 4:
            print("用法: python image_extract.py ppt <index_json_path> <output_pptx_path>")
            print("选项:")
            print("  --max-images N    每张幻灯片最大图片数 (默认: 6)")
            return 1
        
        index_path = sys.argv[2]
        output_path = sys.argv[3]
        
        max_images = 6
        if "--max-images" in sys.argv:
            idx = sys.argv.index("--max-images")
            if idx + 1 < len(sys.argv):
                max_images = int(sys.argv[idx + 1])
        
        result = generate_ppt_images(index_path, output_path, max_ppt_images=max_images)
        print(f"PPT 已生成: {result}")
        return 0
    
    else:
        print(f"未知命令: {cmd}")
        print("支持命令: scan, search, stats, ppt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
