#!/usr/bin/env python3
"""
LLM_Search — 基于向量嵌入的语义搜索引擎
=========================================

独立的向量索引方案，解决 JSON 索引文件过大导致的上下文溢出问题。

架构：
  kb_ai.db / kb_index.json / image_extract_index.json  (现有数据源，只读)
    ↓ 读取
  Embedder (ONNX Runtime 主 / sentence-transformers 备)
    ↓ 文本 → 向量 (512d, bge-small-zh-v1.5)
  VectorStore (FAISS / NumPy)
    ↓ 存储 & 检索
  SemanticSearcher
    ↓ 语义搜索 + 混合评分
  结果输出

模块：
  config.py     — 全局配置（路径、模型、512维参数）
  embedder.py   — 双引擎嵌入：ONNX (本地模型) + ST (备选)
  store.py      — 向量存储引擎（FAISS + NumPy 降级）
  indexer.py    — 多源索引构建（JSON + kb_ai.db + 图片）
  search.py     — 语义搜索引擎（混合评分）
  cli.py        — 统一命令行入口

快速开始：
  # 安装依赖（轻量）
  pip install numpy onnxruntime tokenizers faiss-cpu

  # 从已有 kb_ai.db 构建索引（最快）
  python LLM_Search/cli.py build --from-db

  # 语义搜索
  python LLM_Search/cli.py search "AI方案"

降级方案：
  如果 FAISS 不可用，自动降级为 NumPy 暴力搜索（适用于 < 50K 向量）。
  如果 ONNX 不可用，自动降级为 sentence-transformers。
"""

__version__ = "2.0.0"
__author__ = "PPT Master Team"


# ── 常量导出（无需依赖） ────────────────────────────
from .config import (
    VECTOR_STORE_DIR,
    DEFAULT_MODEL_NAME,
    EMBEDDING_DIM,
    DEFAULT_TOP_K,
)

__all__ = [
    "VECTOR_STORE_DIR",
    "DEFAULT_MODEL_NAME",
    "EMBEDDING_DIM",
    "DEFAULT_TOP_K",
]


# ── 懒加载函数 ─────────────────────────────────────

def get_embedder(*args, **kwargs):
    """延迟导入 Embedder"""
    from .embedder import Embedder
    return Embedder(*args, **kwargs)


def get_vector_store(*args, **kwargs):
    """延迟导入 VectorStore"""
    from .store import VectorStore
    return VectorStore(*args, **kwargs)


def get_index_builder(*args, **kwargs):
    """延迟导入 VectorIndexBuilder"""
    from .indexer import VectorIndexBuilder
    return VectorIndexBuilder(*args, **kwargs)


def get_searcher(*args, **kwargs):
    """延迟导入 SemanticSearcher"""
    from .search import SemanticSearcher
    return SemanticSearcher(*args, **kwargs)
