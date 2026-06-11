#!/usr/bin/env python3
"""
LLM_Search 语义搜索
====================
基于向量嵌入的语义搜索引擎，支持 PPT 页面搜索和图片搜索。

特性：
  - 语义搜索：理解自然语言查询意图（不只是关键词匹配）
  - 混合评分：向量相似度 (0.7) + 关键词增强 (0.3)
  - 双模式：PPT 页面搜索 / 图片搜索
  - 结果格式化输出

用法：
  python search.py "金融行业架构图"                  # 搜索 PPT 页面
  python search.py "数据中心拓扑" --mode image       # 搜索图片
  python search.py "云计算方案" --top-k 5            # 指定返回数量
  python search.py "AI组网" --mode both              # 同时搜索
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

from .config import (
    DEFAULT_TOP_K,
    VECTOR_WEIGHT,
    KEYWORD_WEIGHT,
)
# Embedder and VectorStore imported lazily in SemanticSearcher

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# 混合评分器
# ═══════════════════════════════════════════════════════


class HybridScorer:
    """混合评分器：向量相似度 + 关键词匹配。

    向量相似度提供语义理解能力，
    关键词匹配提供精确匹配的增强。
    """

    def __init__(
        self,
        vector_weight: float = VECTOR_WEIGHT,
        keyword_weight: float = KEYWORD_WEIGHT,
    ):
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight

    def score(
        self,
        query: str,
        vector_score: float,
        entry_text: str,
        entry_metadata: Dict[str, Any],
    ) -> float:
        """计算混合评分。

        Args:
            query: 原始查询文本
            vector_score: 向量相似度（0-1，已归一化）
            entry_text: 条目文本（用于关键词匹配）
            entry_metadata: 条目元数据

        Returns:
            float: 混合评分 (0-1)
        """
        kw_score = self._keyword_score(query, entry_text, entry_metadata)

        # 加权组合
        final = (
            self.vector_weight * vector_score
            + self.keyword_weight * kw_score
        )

        return min(final, 1.0)

    def _keyword_score(
        self,
        query: str,
        entry_text: str,
        entry_metadata: Dict[str, Any],
    ) -> float:
        """计算关键词匹配分数 (0-1)"""
        query_lower = query.lower()
        text_lower = entry_text.lower() if entry_text else ""

        # 分词
        tokens = _tokenize(query_lower)
        if not tokens:
            return 0.0

        matched = 0
        total_weight = 0

        for token in tokens:
            weight = 1.0
            # 长词权重更高（更具体的匹配）
            if len(token) >= 4:
                weight = 1.5

            total_weight += weight

            if token in text_lower:
                matched += weight
                continue

            # 额外检查 metadata 中的字段
            title = (entry_metadata.get("title", "") or "").lower()
            keywords = entry_metadata.get("keywords", []) or []
            tags = entry_metadata.get("search_tags", []) or []
            filename = (entry_metadata.get("source_filename", "") or "").lower()

            if any(token in kw.lower() for kw in keywords):
                matched += weight * 0.8
            elif any(token in t.lower() for t in tags):
                matched += weight * 0.8
            elif token in title:
                matched += weight * 0.7
            elif token in filename:
                matched += weight * 0.5

        return matched / total_weight if total_weight > 0 else 0.0


def _tokenize(text: str) -> List[str]:
    """智能分词（同 image_extract 的分词逻辑）"""
    tokens = set()

    # 中文词组
    words = re.findall(r'[\u4e00-\u9fff]+', text)
    for w in words:
        tokens.add(w)
        if len(w) >= 4:
            for wlen in range(2, 5):
                for i in range(len(w) - wlen + 1):
                    tokens.add(w[i:i + wlen])

    # 英文单词
    tokens.update(w.lower() for w in re.findall(r'\b[a-zA-Z]{2,30}\b', text))
    # 数字
    tokens.update(re.findall(r'\d+', text))

    return list(tokens)


# ═══════════════════════════════════════════════════════
# 语义搜索引擎
# ═══════════════════════════════════════════════════════


class SemanticSearcher:
    """语义搜索引擎。

    封装 embedding + vector store + hybrid scoring，
    提供统一搜索接口。

    Usage:
        searcher = SemanticSearcher()
        results = searcher.search("金融架构图", mode="ppt")
        searcher.print_results(results)
    """

    def __init__(self, model_name: Optional[str] = None):
        from .embedder import Embedder
        self.embedder = Embedder(model_name=model_name) if model_name else Embedder()
        self.scorer = HybridScorer()

        self._ppt_store: Optional[VectorStore] = None
        self._img_store: Optional[VectorStore] = None

    @property
    def ppt_store(self) -> "VectorStore":
        if self._ppt_store is None:
            from .store import VectorStore
            self._ppt_store = VectorStore("ppt_slides")
        return self._ppt_store

    @property
    def img_store(self) -> "VectorStore":
        if self._img_store is None:
            from .store import VectorStore
            self._img_store = VectorStore("images")
        return self._img_store

    # ── 搜索入口 ──────────────────────────────────────

    def search(
        self,
        query: str,
        mode: str = "ppt",
        top_k: int = DEFAULT_TOP_K,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """语义搜索。

        Args:
            query: 自然语言查询
            mode: "ppt" | "image" | "both"
            top_k: 每种模式返回的结果数

        Returns:
            {"ppt": [...], "images": [...]}
        """
        results = {}

        if mode in ("ppt", "both"):
            results["ppt"] = self._search_ppt(query, top_k)

        if mode in ("image", "both"):
            results["images"] = self._search_images(query, top_k)

        return results

    def _search_ppt(
        self, query: str, top_k: int
    ) -> List[Dict[str, Any]]:
        """搜索 PPT 页面"""
        store = self.ppt_store
        if store.count == 0:
            logger.warning("PPT 向量索引为空，请先执行 build")
            return []

        return self._vector_search(query, store, top_k)

    def _search_images(
        self, query: str, top_k: int
    ) -> List[Dict[str, Any]]:
        """搜索图片"""
        store = self.img_store
        if store.count == 0:
            logger.warning("图片向量索引为空，请先执行 build")
            return []

        return self._vector_search(query, store, top_k)

    def _vector_search(
        self,
        query: str,
        store: VectorStore,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """核心向量搜索 + 混合评分"""
        # 1. 编码查询
        query_vec = self.embedder.encode_single(query)

        # 2. 向量检索（取 top_k * 3 候选，再用混合评分重排）
        candidates = store.search(query_vec, k=min(top_k * 3, store.count))

        if not candidates:
            return []

        # 3. 混合评分重排
        scored = []
        for vec_score, meta in candidates:
            entry_text = meta.get("text", "")
            hybrid = self.scorer.score(query, vec_score, entry_text, meta)

            scored.append({
                "score": round(hybrid, 4),
                "vector_score": round(float(vec_score), 4),
                "source_type": meta.get("source_type", ""),
                "source_id": meta.get("source_id", ""),
                "display_text": meta.get("display_text", ""),
                "metadata": meta.get("metadata", {}),
            })

        # 按混合评分重排
        scored.sort(key=lambda x: -x["score"])

        return scored[:top_k]

    # ── 格式化输出 ────────────────────────────────────

    def print_results(
        self,
        results: Dict[str, List[Dict[str, Any]]],
        query: str = "",
    ) -> None:
        """格式化打印搜索结果"""
        print(f"\n{'=' * 60}")
        print(f"  语义搜索: \"{query}\"")
        print(f"{'=' * 60}")

        for mode, items in results.items():
            label = "PPT 页面" if mode == "ppt" else "图片"
            print(f"\n  [{label}] 共 {len(items)} 条结果")

            if not items:
                print("    (无结果)")
                continue

            for i, item in enumerate(items, 1):
                meta = item["metadata"]
                vs = item["vector_score"]
                hs = item["score"]

                print(f"\n  #{i} (向量: {vs:.3f}, 混合: {hs:.3f})")

                if mode == "ppt":
                    print(f"     文件: {meta.get('file', '?')}")
                    print(f"     标题: {meta.get('title', '?')}")
                    print(f"     页码: {meta.get('slide_num', '?')}")
                    print(f"     路径: {meta.get('path_abs', '?')}")
                else:
                    print(f"     图片: {meta.get('archive_name', '?')}")
                    print(f"     格式: {meta.get('format', '?')}")
                    print(f"     尺寸: {meta.get('width', 0)}×{meta.get('height', 0)}")
                    print(f"     描述: {(meta.get('description_hint', '') or '')[:120]}")
                    print(f"     路径: {meta.get('archive_path', '?')}")

                display = item.get("display_text", "")
                if display:
                    print(f"     内容: {display[:100]}")

        print()

    def stats(self) -> Dict[str, Any]:
        """返回搜索引擎统计"""
        return {
            "ppt_store": self.ppt_store.stats(),
            "img_store": self.img_store.stats(),
            "embedder": str(self.embedder),
        }


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if len(sys.argv) < 2:
        print("用法:")
        print('  python search.py "查询文本"')
        print('  python search.py "金融架构图" --mode image')
        print('  python search.py "AI方案" --mode both --top-k 5')
        sys.exit(1)

    query = sys.argv[1]
    mode = "ppt"
    top_k = DEFAULT_TOP_K

    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode = sys.argv[idx + 1]

    if "--top-k" in sys.argv:
        idx = sys.argv.index("--top-k")
        if idx + 1 < len(sys.argv):
            top_k = int(sys.argv[idx + 1])

    searcher = SemanticSearcher()
    results = searcher.search(query, mode=mode, top_k=top_k)
    searcher.print_results(results, query)
