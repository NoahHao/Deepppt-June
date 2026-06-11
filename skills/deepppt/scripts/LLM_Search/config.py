#!/usr/bin/env python3
"""
LLM_Search 全局配置
===================
定义路径、模型参数、向量维度等核心配置。
所有路径基于 deepppt-main 项目根目录自动推导。
"""

import os
from pathlib import Path

# ── 项目根目录（自动推导） ────────────────────────────
# 当前文件: .../skills/deepppt/scripts/LLM_Search/config.py
# 项目根:   .../deepppt-main/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

# ── LLM_Search 自身目录 ─────────────────────────────
LLM_SEARCH_DIR = Path(__file__).resolve().parent

# ── 向量索引存储目录 ──────────────────────────────────
VECTOR_STORE_DIR = LLM_SEARCH_DIR / "vector_store"
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

# PPT 页面向量索引文件
PPT_FAISS_INDEX = VECTOR_STORE_DIR / "ppt_slides.faiss"
PPT_META_JSON = VECTOR_STORE_DIR / "ppt_slides_meta.json"

# 图片向量索引文件
IMG_FAISS_INDEX = VECTOR_STORE_DIR / "images.faiss"
IMG_META_JSON = VECTOR_STORE_DIR / "images_meta.json"

# LightAI 专题图片向量（早期实验数据，独立索引）
LIGHTAI_FAISS_INDEX = VECTOR_STORE_DIR / "lightai_images.faiss"
LIGHTAI_META_JSON = VECTOR_STORE_DIR / "lightai_images_meta.json"

# ── 模型目录 ─────────────────────────────────────────
# 本地 ONNX 模型目录（已预下载）
LOCAL_MODEL_DIR = LLM_SEARCH_DIR / "model" / "model" / "models--Qdrant--bge-small-zh-v1.5" / "snapshots" / "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"

# SQLite 向量数据库（indexer 的数据源之一，与 FAISS 索引放在同一目录便于管理）
LEGACY_DB_PATH = VECTOR_STORE_DIR / "kb_ai.db"

# ── 嵌入模型配置 ─────────────────────────────────────
# 主模型：本地 ONNX BGE-small-zh-v1.5（中文优化，512维）
# ~100MB，无需 PyTorch，已预下载
DEFAULT_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DEFAULT_MODEL_DIM = 512  # bge-small-zh-v1.5 输出维度

# 备选模型（当 ONNX 不可用时）
FALLBACK_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# 向量维度（由默认模型决定）
EMBEDDING_DIM = DEFAULT_MODEL_DIM

# 批处理大小
BATCH_SIZE = 32

# ── 搜索配置 ─────────────────────────────────────────
# 默认返回结果数
DEFAULT_TOP_K = 10

# 混合评分权重：向量相似度 vs 关键词匹配
VECTOR_WEIGHT = 0.7   # 向量相似度权重
KEYWORD_WEIGHT = 0.3  # 关键词匹配权重

# ── JSON 索引路径（统一在 knowledge_base/ 下）──────────
KB_INDEX_PATHS = [
    _PROJECT_ROOT / "knowledge_base" / "kb_index.json",    # 主位置
    _PROJECT_ROOT / "kb_index.json",                       # 旧位置兼容
]

IMG_INDEX_PATHS = [
    _PROJECT_ROOT / "knowledge_base" / "image_extract_index.json",   # 主位置
    _PROJECT_ROOT / "images" / "image_extract_index.json",           # 旧位置兼容
]

# ── 辅助函数 ─────────────────────────────────────────

def get_model_path() -> Path:
    """返回本地 ONNX 模型路径（自动检测）"""
    if LOCAL_MODEL_DIR.exists():
        return LOCAL_MODEL_DIR
    return Path(DEFAULT_MODEL_NAME)


def find_existing_json_index(candidates: list) -> Path:
    """在候选路径中查找第一个存在的 JSON 索引文件"""
    for p in candidates:
        if Path(p).exists():
            return Path(p)
    return None


def get_project_root() -> Path:
    return _PROJECT_ROOT
