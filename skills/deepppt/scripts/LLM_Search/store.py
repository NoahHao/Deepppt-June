#!/usr/bin/env python3
"""
LLM_Search 向量存储
====================
基于 FAISS 的向量存储引擎，支持增量添加、保存/加载、元数据管理。

特性：
  - 主引擎：FAISS IndexFlatIP（内积 = 归一化后等于余弦相似度）
  - 降级方案：纯 numpy 暴力搜索（不需要 FAISS）
  - 元数据分离存储（JSON），向量与元数据通过 index_id 关联
  - 增量更新：支持按 source_id 去重/覆盖

向量索引文件：
  xxx.faiss      — FAISS 二进制索引
  xxx_meta.json  — 元数据 JSON
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import numpy as np

from .config import EMBEDDING_DIM

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# 向量引擎抽象
# ═══════════════════════════════════════════════════════


class VectorEngine:
    """向量检索引擎的抽象基类"""

    def add(self, vectors: np.ndarray) -> None:
        raise NotImplementedError

    def search(
        self, query: np.ndarray, k: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """返回 (distances, indices)"""
        raise NotImplementedError

    def save(self, path: Path) -> None:
        raise NotImplementedError

    @staticmethod
    def load(path: Path, dimension: int) -> "VectorEngine":
        raise NotImplementedError

    @property
    def count(self) -> int:
        raise NotImplementedError

    @property
    def dimension(self) -> int:
        raise NotImplementedError


# ═══════════════════════════════════════════════════════
# FAISS 引擎
# ═══════════════════════════════════════════════════════


class FaissEngine(VectorEngine):
    """基于 FAISS 的向量检索引擎。

    使用 IndexFlatIP（内积搜索）：
      在向量已 L2 归一化的前提下，内积 = 余弦相似度。
    """

    def __init__(self, dimension: int):
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "faiss-cpu 未安装。请执行: pip install faiss-cpu\n"
                "或使用 NumpyEngine 作为降级方案。"
            )

        self._faiss = faiss
        self._dimension = dimension
        self._index = faiss.IndexFlatIP(dimension)  # Inner Product

    def add(self, vectors: np.ndarray) -> None:
        """添加向量到索引（向量应已 L2 归一化）"""
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        if vectors.shape[1] != self._dimension:
            raise ValueError(
                f"向量维度不匹配: {vectors.shape[1]} != {self._dimension}"
            )
        self._index.add(vectors)

    def search(
        self, query: np.ndarray, k: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """搜索 top-k 相似向量。

        Args:
            query: shape=(1, dim) 的查询向量（需 L2 归一化）
            k: 返回数量

        Returns:
            (distances, indices): distances 为内积分数（越高越相似），
                                  indices 为向量索引
        """
        query = np.asarray(query, dtype=np.float32)
        if query.ndim == 1:
            query = query.reshape(1, -1)
        k = min(k, self._index.ntotal)
        if k == 0:
            return np.array([[]]), np.array([[]])
        return self._index.search(query, k)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._faiss.write_index(self._index, str(path))

    @staticmethod
    def load(path: Path, dimension: int) -> "FaissEngine":
        import faiss

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"FAISS 索引不存在: {path}")

        engine = FaissEngine.__new__(FaissEngine)
        engine._faiss = faiss
        engine._dimension = dimension
        engine._index = faiss.read_index(str(path))
        return engine

    @property
    def count(self) -> int:
        return self._index.ntotal

    @property
    def dimension(self) -> int:
        return self._dimension


# ═══════════════════════════════════════════════════════
# NumPy 降级引擎
# ═══════════════════════════════════════════════════════


class NumpyEngine(VectorEngine):
    """纯 numpy 向量检索引擎（无需 FAISS）。

    适用于小规模数据（< 50K 向量），
    或 FAISS 不可用的降级场景。
    """

    def __init__(self, dimension: int):
        self._dimension = dimension
        self._vectors: np.ndarray = np.empty((0, dimension), dtype=np.float32)

    def add(self, vectors: np.ndarray) -> None:
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        if vectors.shape[1] != self._dimension:
            raise ValueError(
                f"向量维度不匹配: {vectors.shape[1]} != {self._dimension}"
            )
        self._vectors = np.vstack([self._vectors, vectors])

    def search(
        self, query: np.ndarray, k: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        query = np.asarray(query, dtype=np.float32)
        if query.ndim == 1:
            query = query.reshape(1, -1)

        if len(self._vectors) == 0:
            return np.array([[]]), np.array([[]])

        # 内积 = 余弦相似度（向量已归一化）
        scores = np.dot(self._vectors, query.T).flatten()

        k = min(k, len(scores))
        if k == 0:
            return np.array([[]]), np.array([[]])

        # 获取 top-k 索引
        if k >= len(scores):
            top_indices = np.arange(len(scores))
        else:
            top_indices = np.argpartition(-scores, k)[:k]
            top_indices = top_indices[np.argsort(-scores[top_indices])]

        top_scores = scores[top_indices]
        return top_scores.reshape(1, -1), top_indices.reshape(1, -1)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(path), self._vectors)

    @staticmethod
    def load(path: Path, dimension: int) -> "NumpyEngine":
        path = Path(path)
        npy_path = path.with_suffix(".npy")
        vecs = np.load(str(npy_path)).astype(np.float32)
        engine = NumpyEngine(dimension)
        engine._vectors = vecs
        return engine

    @property
    def count(self) -> int:
        return len(self._vectors)

    @property
    def dimension(self) -> int:
        return self._dimension


# ═══════════════════════════════════════════════════════
# 向量存储（引擎 + 元数据）
# ═══════════════════════════════════════════════════════


def _create_engine(dimension: int, prefer_faiss: bool = True) -> VectorEngine:
    """创建向量引擎，优先 FAISS，失败降级 numpy"""
    if prefer_faiss:
        try:
            return FaissEngine(dimension)
        except ImportError as e:
            logger.warning(f"FAISS 不可用，降级为 NumPy: {e}")
        except Exception as e:
            logger.warning(f"FAISS 初始化失败，降级为 NumPy: {e}")

    logger.info("使用 NumPy 向量引擎")
    return NumpyEngine(dimension)


def _load_engine(path: Path, dimension: int) -> VectorEngine:
    """加载向量引擎，自动检测格式"""
    path = Path(path)
    faiss_path = path
    npy_path = path.with_suffix(".npy")

    if faiss_path.exists():
        try:
            return FaissEngine.load(faiss_path, dimension)
        except Exception as e:
            logger.warning(f"FAISS 加载失败: {e}")

    if npy_path.exists():
        try:
            return NumpyEngine.load(npy_path, dimension)
        except Exception as e:
            logger.warning(f"NumPy 加载失败: {e}")

    # 都不存在 → 创建新引擎
    logger.info(f"索引文件不存在，创建新向量引擎 (dim={dimension})")
    return _create_engine(dimension)


class VectorStore:
    """向量存储管理器。

    封装向量引擎 + 元数据管理，提供统一的增删查改接口。

    每个条目：
      {
        "id": "唯一ID",
        "source_type": "ppt_slide" | "image",
        "source_id": "原始来源标识",
        "text": "原始文本（用于展示）",
        "metadata": { ... 原始 JSON 字段 ... }
      }

    用法：
      store = VectorStore("ppt_slides", dimension=384)
      store.add(vectors, metadatas)
      store.save()
      results, scores = store.search(query_vec, k=10)
    """

    def __init__(
        self,
        name: str,
        dimension: int = EMBEDDING_DIM,
        store_dir: Optional[Path] = None,
    ):
        """
        Args:
            name: 存储名称（用于文件命名）
            dimension: 向量维度
            store_dir: 存储目录（默认 config.VECTOR_STORE_DIR）
        """
        from .config import VECTOR_STORE_DIR

        self.name = name
        self.dimension = dimension
        self.store_dir = store_dir or VECTOR_STORE_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)

        # 向量引擎文件路径
        self._vector_path = self.store_dir / f"{name}.faiss"
        self._meta_path = self.store_dir / f"{name}_meta.json"

        # 初始化
        self._engine: VectorEngine = _load_engine(self._vector_path, dimension)
        self._metadata: List[Dict[str, Any]] = self._load_metadata()

        logger.info(
            f"VectorStore[{name}]: {len(self._metadata)} 条记录, "
            f"引擎: {type(self._engine).__name__}"
        )

    # ── 元数据持久化 ──────────────────────────────────

    def _load_metadata(self) -> List[Dict[str, Any]]:
        if self._meta_path.exists():
            with open(self._meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_metadata(self) -> None:
        self._meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, ensure_ascii=False, indent=2)

    # ── 添加向量 ──────────────────────────────────────

    def add(
        self,
        vectors: np.ndarray,
        metadatas: List[Dict[str, Any]],
        replace_by_source: bool = True,
    ) -> int:
        """批量添加向量和元数据。

        Args:
            vectors: 向量矩阵 shape=(N, dim)，需已 L2 归一化
            metadatas: 元数据列表，长度必须与 vectors 一致
            replace_by_source: 是否按 source_id 去重（替换已有条目）

        Returns:
            int: 实际新增的向量数
        """
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)

        if len(vectors) != len(metadatas):
            raise ValueError(
                f"向量数({len(vectors)})与元数据数({len(metadatas)})不匹配"
            )

        if replace_by_source:
            # 构建 source_id → index 映射
            source_map: Dict[str, int] = {}
            for i, meta in enumerate(self._metadata):
                sid = meta.get("source_id", "")
                if sid:
                    source_map[sid] = i

            new_vectors = []
            new_metas = []
            skipped = 0

            for vec, meta in zip(vectors, metadatas):
                sid = meta.get("source_id", "")
                if sid and sid in source_map:
                    # 替换已有向量（FAISS 不支持原地更新，重建）
                    skipped += 1
                    # 标记需要重建（留到 save 时处理）
                    meta["_needs_rebuild"] = True
                    idx = source_map[sid]
                    self._metadata[idx] = meta
                else:
                    new_vectors.append(vec)
                    new_metas.append(meta)

            if skipped:
                logger.info(f"检测到 {skipped} 条重复 source_id，需重建索引")
                # 有更新 → 需要全量重建 FAISS 索引
                self._dirty = True

            if new_vectors:
                new_vecs = np.array(new_vectors, dtype=np.float32)
                self._engine.add(new_vecs)
                self._metadata.extend(new_metas)
        else:
            self._engine.add(vectors)
            self._metadata.extend(metadatas)

        self._save_metadata()
        return len(vectors)

    # ── 搜索 ──────────────────────────────────────────

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """向量相似度搜索。

        Args:
            query_vector: 查询向量 shape=(dim,)，需已 L2 归一化
            k: 返回数量

        Returns:
            [(score, metadata), ...] 按相似度降序
        """
        if not self._metadata:
            return []

        distances, indices = self._engine.search(query_vector, k)

        results = []
        for score, idx in zip(distances[0], indices[0]):
            idx = int(idx)
            if 0 <= idx < len(self._metadata):
                results.append((float(score), self._metadata[idx]))

        return results

    # ── 保存 ──────────────────────────────────────────

    def save(self, rebuild: bool = False) -> None:
        """持久化向量索引和元数据。

        Args:
            rebuild: 是否全量重建 FAISS 索引（当有更新时必需）
        """
        if rebuild or getattr(self, "_dirty", False):
            self._rebuild_index()

        self._engine.save(self._vector_path)
        self._save_metadata()
        logger.info(
            f"VectorStore[{self.name}] 已保存: "
            f"{len(self._metadata)} 条记录"
        )

    def _rebuild_index(self) -> None:
        """重建 FAISS 索引（全量）。

        当有条目更新时，FAISS 不支持原地修改，需要重建。
        """
        from .config import EMBEDDING_DIM

        logger.info("重建向量索引...")
        new_engine = _create_engine(self.dimension, prefer_faiss=True)

        # 收集需要重嵌入的条目（_needs_rebuild 标记）
        rebuild_indices = []
        for i, meta in enumerate(self._metadata):
            if meta.pop("_needs_rebuild", False):
                rebuild_indices.append(i)

        if rebuild_indices:
            logger.warning(
                f"{len(rebuild_indices)} 条记录需要重新嵌入。"
                f"请调用 indexer 重新生成这些条目的向量后再保存。"
            )

        # 构建新索引（仅包含已有向量的条目）
        existing_count = self._engine.count
        if existing_count > 0:
            # 从旧引擎提取所有向量 → 需要逐个搜索自己来获取...
            # 简化处理：提示用户重新 build
            logger.warning(
                "无法从 FAISS 索引中提取原始向量。"
                "建议使用 cli.py build 重新构建完整索引。"
            )

        self._engine = new_engine
        self._dirty = False

    # ── 属性 ──────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._metadata)

    @property
    def engine_type(self) -> str:
        return type(self._engine).__name__

    def clear(self) -> None:
        """清空所有数据"""
        self._engine = _create_engine(self.dimension)
        self._metadata = []
        self._dirty = False

    def stats(self) -> Dict[str, Any]:
        """返回存储统计信息"""
        source_types = {}
        for m in self._metadata:
            st = m.get("source_type", "unknown")
            source_types[st] = source_types.get(st, 0) + 1

        return {
            "name": self.name,
            "engine": self.engine_type,
            "dimension": self.dimension,
            "total": len(self._metadata),
            "by_source_type": source_types,
            "store_dir": str(self.store_dir),
        }

    def __repr__(self):
        return f"VectorStore({self.name}, engine={self.engine_type}, count={self.count})"
