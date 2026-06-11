#!/usr/bin/env python3
"""
search_and_fill — LLM_Search + mirror_fill 集成层
==================================================

将 LLM_Search 的语义搜索结果直接串联到 mirror_fill 的填充流程。

核心工作流:
  1. 用户提供待填充的新文本列表
  2. 对每个文本片段调用 LLM_Search 搜索最相似的源幻灯片
  3. 根据搜索结果创建 MirrorFiller
  4. 逐页执行填充操作

类:
    ExecutorBase         — 集成层抽象基类（prepare → execute → validate）
    SearchAndFillFiller  — 搜索→填充 具体实现
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 修改 sys.path 以便导入 LLM_Search
_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _THIS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from LLM_Search.search import SemanticSearcher
from .filler import MirrorFiller


# ═══════════════════════════════════════════════════════
# ExecutorBase — 集成层抽象基类
# ═══════════════════════════════════════════════════════

class ExecutorBase:
    """集成层抽象基类，定义三阶段生命周期。

    子类需实现:
        _search_new_texts(self, text: str, top_k: int) → List[Dict]
        search_and_fill_all(self) → List[Dict]
    """

    def __init__(self):
        self._results: List[Dict[str, Any]] = []
        self._fill_results: List[Dict[str, Any]] = []

    def prepare(self):
        """准备阶段：初始化资源、验证依赖"""
        raise NotImplementedError

    def execute(self):
        """执行阶段：运行核心逻辑"""
        raise NotImplementedError

    def validate(self):
        """验证阶段：检查结果完整性"""
        raise NotImplementedError

    def _search_new_texts(self, text: str, top_k: int = 3) -> List[Dict]:
        """搜索新文本（子类实现）"""
        raise NotImplementedError

    def search_and_fill_all(self) -> List[Dict]:
        """搜索并填充全部（子类实现）"""
        raise NotImplementedError


# ═══════════════════════════════════════════════════════
# SearchAndFillFiller — 搜索→填充 具体实现
# ═══════════════════════════════════════════════════════

@dataclass
class SearchResultItem:
    """搜索结果条目"""
    display_text: str
    source_type: str
    score: float
    vector_score: float
    metadata: Dict[str, Any]
    source_pptx: Optional[str] = None  # 实际 PPTX 路径（解析后）
    slide_num: int = 1


class SearchAndFillFiller(ExecutorBase):
    """将语义搜索和镜像填充串联起来的执行器。

    用法:
        filler = SearchAndFillFiller.from_text_with_search(
            new_pptx_texts=["文本1", "文本2"],
            layout="left_right",
            top_k=3,
        )
        results = filler.search_and_fill_all()
    """

    def __init__(
        self,
        new_pptx_texts: List[str],
        search_results: List[List[SearchResultItem]],
        layout: str = "left_right",
        debug: bool = False,
    ):
        super().__init__()
        self.new_pptx_texts = new_pptx_texts
        self.search_results = search_results
        self.layout = layout
        self.debug = debug
        self._fillers: List[MirrorFiller] = []

    # ── 工厂方法 ──────────────────────────────────

    @classmethod
    def from_text_with_search(
        cls,
        new_pptx_texts: List[str],
        layout: str = "left_right",
        top_k: int = 3,
        debug: bool = False,
    ) -> "SearchAndFillFiller":
        """工厂方法：通过文本列表 + 语义搜索创建 SearchAndFillFiller。

        对每个文本片段执行 LLM_Search 语义搜索，
        将搜索结果自动转换为 SearchResultItem 列表，
        返回已初始化的 SearchAndFillFiller 实例。

        Args:
            new_pptx_texts: 待填充的新文本列表
            layout: 布局预设名（默认 "left_right"）
            top_k: 每个文本搜索返回的最相似结果数
            debug: 是否打印调试信息

        Returns:
            SearchAndFillFiller 实例（已填充 search_results，但未执行生命周期）
        """
        # 初始化语义搜索
        searcher = SemanticSearcher()

        all_search_results: List[List[SearchResultItem]] = []

        for i, text in enumerate(new_pptx_texts):
            if debug:
                print(f"[from_text_with_search] 🔍 搜索 #{i}: {text[:80]}")

            raw_results = searcher.search(text, mode="ppt", top_k=top_k)
            ppt_results = raw_results.get("ppt", [])

            items: List[SearchResultItem] = []
            for r in ppt_results:
                meta = r.get("metadata", {}) or {}

                # 提取源 PPTX 路径
                source_pptx = meta.get("path_abs") or meta.get("file", "")
                if not source_pptx:
                    # 尝试从 metadata 嵌套结构中查找
                    source_pptx = meta.get("metadata", {}).get("path_abs", "")

                # 提取 slide 页码
                slide_num = int(meta.get("slide_num", 1))

                items.append(SearchResultItem(
                    display_text=r.get("display_text", ""),
                    source_type=r.get("source_type", "ppt"),
                    score=r.get("score", 0.0),
                    vector_score=r.get("vector_score", 0.0),
                    metadata=meta,
                    source_pptx=source_pptx,
                    slide_num=slide_num,
                ))

            if not items and debug:
                print(f"[from_text_with_search] ⚠️ 文本 #{i} 无搜索结果")

            all_search_results.append(items)

            if debug:
                print(f"[from_text_with_search]   → {len(items)} 条结果")

        return cls(
            new_pptx_texts=new_pptx_texts,
            search_results=all_search_results,
            layout=layout,
            debug=debug,
        )

    # ── 三阶段生命周期 ──────────────────────────────

    def prepare(self):
        """准备阶段：验证搜索结果和输入文本合法性"""
        n_texts = len(self.new_pptx_texts)
        n_results = len(self.search_results)

        if n_texts == 0:
            raise ValueError("new_pptx_texts 不能为空")

        if n_results < n_texts:
            raise ValueError(
                f"search_results ({n_results}) 数量少于 "
                f"new_pptx_texts ({n_texts})"
            )

        if self.debug:
            print(f"[search_and_fill] 准备就绪: {n_texts} 个文本, "
                  f"{n_results} 条搜索结果")

    def execute(self):
        """执行阶段：遍历文本→搜索→创建MirrorFiller→填充"""
        self._fillers = []
        for i, text in enumerate(self.new_pptx_texts):
            results = self.search_results[i] if i < len(self.search_results) else []

            if not results:
                if self.debug:
                    print(f"[search_and_fill] ⚠️ 文本 #{i} 无搜索结果，跳过: "
                          f"{text[:60]}")
                continue

            # 取最佳结果创建 MirrorFiller
            best = results[0]
            if not best.source_pptx or not Path(best.source_pptx).exists():
                if self.debug:
                    print(f"[search_and_fill] ⚠️ 文本 #{i} 源文件不存在，跳过: "
                          f"{best.source_pptx}")
                continue

            filler = MirrorFiller(
                src_pptx=best.source_pptx,
                slide_num=best.slide_num,
                layout=self.layout,
            )
            self._fillers.append(filler)

            if self.debug:
                print(f"[search_and_fill] ✅ 文本 #{i}: "
                      f"{Path(best.source_pptx).name} p{best.slide_num} "
                      f"(score={best.score:.3f})")

    def validate(self) -> List[Dict[str, Any]]:
        """验证阶段：检查填充结果并返回报告"""
        reports = []
        for i, filler in enumerate(self._fillers):
            info = filler.info()
            reports.append({
                "index": i,
                "src_pptx": info["src_pptx"],
                "slide_num": info["slide_num"],
                "layout": info["layout"],
                "text": self.new_pptx_texts[i] if i < len(self.new_pptx_texts) else "",
            })

        self._results = reports
        return reports

    def search_and_fill_all(
        self,
        output_dir: str | Path = "output",
        prefix: str = "filled_",
    ) -> List[Dict[str, Any]]:
        """执行完整的搜索→填充→输出流程。

        遍历每个文本→根据已有搜索结果创建 MirrorFiller→
        执行填充→保存 PPTX→收集结果。

        Args:
            output_dir: 输出目录（自动创建）
            prefix: 输出文件前缀

        Returns:
            List[Dict]: 每项含 {"index", "text", "src_pptx", "slide_num",
                                 "output_path", "applied_count", "success"}
        """
        # 1) 准备
        self.prepare()
        # 2) 执行（创建 MirrorFiller 实例）
        self.execute()

        if not self._fillers:
            if self.debug:
                print("[search_and_fill] ⚠️ 没有可用的填充任务，跳过")
            return []

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results: List[Dict[str, Any]] = []
        for i, filler in enumerate(self._fillers):
            text = self.new_pptx_texts[i] if i < len(self.new_pptx_texts) else f"text_{i}"
            # 生成短文件名（取前40字符作为文件名）
            safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in text)[:40]
            out_file = output_path / f"{prefix}{i:03d}_{safe_name}.pptx"

            try:
                # 填充: 直接用新文本替换最佳搜索结果中区域的文本
                filler.fill(
                    self.layout,
                    {"right": {text: text}},  # 实际场景中可传入更细化的映射
                )
                saved = filler.save(str(out_file))
                applied = len(saved)  # save 返回 Path，查找替换计数

                results.append({
                    "index": i,
                    "text": text,
                    "src_pptx": str(filler.src_pptx),
                    "slide_num": filler.slide_num,
                    "output_path": str(saved),
                    "success": True,
                })

                if self.debug:
                    print(f"[search_and_fill] ✅ 输出 #{i}: {saved.name}")

            except Exception as e:
                results.append({
                    "index": i,
                    "text": text,
                    "src_pptx": str(filler.src_pptx),
                    "slide_num": filler.slide_num,
                    "output_path": "",
                    "success": False,
                    "error": str(e),
                })
                if self.debug:
                    print(f"[search_and_fill] ❌ #{i} 填充失败: {e}")

        # 3) 验证
        self._fill_results = self.validate()
        return results
