#!/usr/bin/env python3
"""
LightAI 图片语义搜索
=====================
从 vector_store/lightai_images.faiss 索引中搜索华为 LightAI 项目图片。

运行:
    cd scripts/
    python LLM_Search/vector_store/search_lightai.py
"""

import sys
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
_SCRIPTS_DIR = _THIS_FILE.parent.parent.parent  # vector_store → LLM_Search → scripts/
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import faiss, json
from LLM_Search.config import LIGHTAI_FAISS_INDEX, LIGHTAI_META_JSON
from LLM_Search.embedder import Embedder


def load_store():
    index = faiss.read_index(str(LIGHTAI_FAISS_INDEX))
    metadata = json.loads(LIGHTAI_META_JSON.read_text(encoding="utf-8"))
    return index, metadata


def search(query, top_k=5):
    print(f'🔍 "{query}"\n')
    index, metadata = load_store()
    embedder = Embedder()
    vec = embedder.encode_single(query)
    D, I = index.search(vec.reshape(1, -1), top_k)

    for rank, (score, idx) in enumerate(zip(D[0], I[0])):
        m = metadata[idx]["metadata"]
        desc = m.get("description_hint", "")[:120]
        tags = m.get("search_tags", [])
        tag_str = ", ".join(tags[:8])
        archive = m["archive_name"]
        path = m.get("archive_path", "")

        print(f"  #{rank+1}  [{score:.4f}]")
        print(f"       文件: {archive}")
        print(f"       标签: {tag_str}")
        print(f"       描述: {desc}")
        print(f"       路径: {path}")
        print()

    return D, I


if __name__ == "__main__":
    test_queries = [
        "LightAI 组网 架构",
        "推理加速 Atlas 800",
        "医疗 AI 场景 门诊病历",
        "DeepSeek 大模型推理",
        "KV Cache 跨节点共享",
        "Atlas 800I A2 双机",
    ]
    for q in test_queries:
        search(q, top_k=3)

    search("轻量化AI资源池逻辑组网图", top_k=3)
    print("=" * 60)
    print("  用法: python LLM_Search/vector_store/search_lightai.py")
    print("=" * 60)
