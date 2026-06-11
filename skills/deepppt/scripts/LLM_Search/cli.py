#!/usr/bin/env python3
"""
LLM_Search CLI — 统一命令行入口
================================
提供 build / search / stats / info 四大命令。

用法：
  python cli.py build                # 构建全部向量索引
  python cli.py build --type ppt     # 仅 PPT
  python cli.py build --type img --force  # 仅图片，强制重建
  python cli.py search "金融架构图"   # 搜索 PPT 页面
  python cli.py search "数据中心" --mode image --top-k 5
  python cli.py search "AI方案" --mode both
  python cli.py stats                # 查看索引统计
  python cli.py info                 # 查看系统信息
"""

import argparse
import logging
import sys
from pathlib import Path

# 确保可以导入 LLM_Search 包
# 当前文件: scripts/LLM_Search/cli.py
# 需要将 scripts/ 加入 sys.path 才能 import LLM_Search
_SCRIPT_DIR = Path(__file__).resolve().parent          # .../LLM_Search/
_PARENT_DIR = _SCRIPT_DIR.parent                        # .../scripts/
if str(_PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(_PARENT_DIR))


def cmd_build(args):
    """构建向量索引"""
    from LLM_Search.indexer import VectorIndexBuilder

    print("\n🔨 开始构建向量索引...\n")
    builder = VectorIndexBuilder()

    idx_type = args.type or "all"
    force = args.force
    from_db = getattr(args, "from_db", False)
    from_pptx = getattr(args, "from_pptx", False)

    if idx_type == "ppt":
        builder.build_ppt(force=force, from_db=from_db, from_pptx=from_pptx)
    elif idx_type == "img":
        builder.build_images(force=force)
    else:
        builder.build_all(force=force, from_db=from_db, from_pptx=from_pptx)

    builder.print_stats()
    print("✅ 构建完成\n")


def cmd_search(args):
    """语义搜索"""
    from LLM_Search.search import SemanticSearcher

    query = args.query
    mode = args.mode or "ppt"
    top_k = args.top_k or 10

    searcher = SemanticSearcher()
    results = searcher.search(query, mode=mode, top_k=top_k)
    searcher.print_results(results, query)


def cmd_stats(args):
    """查看索引统计"""
    from LLM_Search.store import VectorStore

    stores = [
        ("PPT 页面", VectorStore("ppt_slides")),
        ("图片", VectorStore("images")),
    ]

    print("\n" + "=" * 60)
    print("  LLM_Search 向量索引统计")
    print("=" * 60)
    for label, store in stores:
        st = store.stats()
        print(f"\n  [{label}]")
        print(f"    引擎: {st['engine']}")
        print(f"    条目: {st['total']}")
        print(f"    维度: {st['dimension']}")
        print(f"    目录: {st['store_dir']}")
        if st["by_source_type"]:
            for typ, cnt in st["by_source_type"].items():
                print(f"      - {typ}: {cnt}")
    print()


def cmd_info(args):
    """查看系统信息"""
    import numpy as np

    print("\n" + "=" * 60)
    print("  LLM_Search 系统信息")
    print("=" * 60)

    print(f"\n  Python: {sys.version}")
    print(f"  NumPy:  {np.__version__}")

    # FAISS
    try:
        import faiss
        print(f"  FAISS:  {faiss.__version__}")
    except ImportError:
        print("  FAISS:  未安装 (将使用 NumPy 降级方案)")

    # sentence-transformers
    try:
        import sentence_transformers
        print(f"  Sentence-Transformers: {sentence_transformers.__version__}")
    except ImportError:
        print("  Sentence-Transformers: 未安装")

    # 向量存储
    from LLM_Search.store import VectorStore
    from LLM_Search.config import VECTOR_STORE_DIR, DEFAULT_MODEL_NAME

    print(f"\n  默认模型: {DEFAULT_MODEL_NAME}")
    print(f"  向量存储目录: {VECTOR_STORE_DIR}")

    ppt_store = VectorStore("ppt_slides")
    img_store = VectorStore("images")
    print(f"  PPT 索引: {ppt_store.count} 条 ({ppt_store.engine_type})")
    print(f"  图片索引: {img_store.count} 条 ({img_store.engine_type})")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="LLM_Search — 基于向量嵌入的语义搜索引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py build                          # 构建全部向量索引
  python cli.py build --type ppt --force       # 强制重建PPT索引
  python cli.py search "金融行业架构图"          # 搜索PPT页面
  python cli.py search "数据中心" --mode image   # 搜索图片
  python cli.py search "AI方案" --mode both --top-k 5
  python cli.py stats                          # 查看统计
  python cli.py info                           # 系统信息
        """,
    )

    sub = parser.add_subparsers(dest="command", help="子命令")

    # build
    p_build = sub.add_parser("build", help="构建向量索引")
    p_build.add_argument("--type", choices=["ppt", "img", "all"], default="all")
    p_build.add_argument("--force", action="store_true", help="强制重建")
    p_build.add_argument("--from-db", action="store_true", help="从 kb_ai.db 构建")
    p_build.add_argument("--from-pptx", action="store_true", help="从 PPTX 直接读取（零依赖自举）")

    # search
    p_search = sub.add_parser("search", help="语义搜索")
    p_search.add_argument("query", help="搜索查询")
    p_search.add_argument("--mode", choices=["ppt", "image", "both"], default="ppt")
    p_search.add_argument("--top-k", type=int, default=10)

    # stats
    sub.add_parser("stats", help="查看索引统计")

    # info
    sub.add_parser("info", help="查看系统信息")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # 设置 logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    commands = {
        "build": cmd_build,
        "search": cmd_search,
        "stats": cmd_stats,
        "info": cmd_info,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
