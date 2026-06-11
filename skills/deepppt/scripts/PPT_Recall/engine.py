#!/usr/bin/env python3
"""
PPT Recall Engine — 完全自包含、零外部项目依赖
================================================
双路径搜索（关键词+AI）+ slide级召回 + COM粘贴合并

工作流：
  1. 扫描 knowledge_base → 生成 kb_index.json（每页文本索引）
  2. 用户搜索 → 读取 JSON 匹配 → 返回匹配的源文件 + 页码
  3. 召回 → COM Copy+PasteSourceFormatting 提取单页
  4. 合并 → COM 优先 / ZIP 兜底，合并多页到一个 PPTX

铁规：
  - 零外部项目依赖：不 import _zip_utils、kb_search 等
  - 搜索只读 JSON 索引
  - COM 操作使用 PasteSourceFormatting，100%保持原格式
  - ZIP 兜底使用 xml.etree.ElementTree，不用 lxml
"""

import os, sys, re, time
from pathlib import Path

# 兼容直接运行 (python engine.py) 和包导入
try:
    from .indexer import scan_and_index, load_index
    from .merge import merge_slides
except ImportError:
    # 直接运行时，确保父目录在 sys.path 中
    _this_dir = Path(__file__).resolve().parent
    _parent_dir = _this_dir.parent
    if str(_parent_dir) not in sys.path:
        sys.path.insert(0, str(_parent_dir))
    from PPT_Recall.indexer import scan_and_index, load_index
    from PPT_Recall.merge import merge_slides


class PPTRecallEngine:
    """PPT 召回族引擎 — 双路径搜索 + 召回 + 合并，完全自包含"""

    def __init__(self, kb_root=None, index_path=None):
        """
        Args:
            kb_root: knowledge_base 目录路径（默认当前目录下的 knowledge_base）
            index_path: JSON 索引文件路径（默认 kb_root 父目录下的 kb_index.json）
        """
        if kb_root:
            self.kb_root = Path(kb_root)
        else:
            # 自动检测: engine.py → PPT_Recall/ → scripts/ → deepppt/ → skills/ → 项目根
            _project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            self.kb_root = _project_root / "knowledge_base"
            if not self.kb_root.exists():
                self.kb_root = Path.cwd() / "knowledge_base"  # 兜底

        if index_path:
            self.index_path = Path(index_path)
        else:
            # 统一放在 knowledge_base/ 下
            self.index_path = _project_root / "knowledge_base" / "kb_index.json"

        self._index = None

    @property
    def index(self):
        """延迟加载索引"""
        if self._index is None and self.index_path.exists():
            try:
                self._index = load_index(self.index_path)
            except Exception:
                self._index = None
        return self._index

    # ── 索引管理 ────────────────────────────────────────

    def build_index(self, force=False):
        """
        构建 slide 级文本索引（首次或 force=True 时执行）

        Args:
            force: 是否强制重建索引

        Returns:
            dict: 索引数据
        """
        if force or not self.index_path.exists() or self.index is None:
            self._index = scan_and_index(self.kb_root, self.index_path)
        else:
            print(f"  索引已存在: {self.index_path}")
            print(f"  {self.index.get('total_pptx', 0)} PPTX, "
                  f"{self.index.get('total_slides', 0)} slides, "
                  f"scanned at {self.index.get('last_scan', 'unknown')}")
        return self._index

    # ── 关键词搜索 ──────────────────────────────────────

    def search_keyword(self, query, top_k=5):
        """
        在 JSON 索引中匹配关键词。

        Args:
            query: 搜索关键词（支持空格/逗号分隔多词）
            top_k: 返回前 K 个结果

        Returns:
            [{file, title, slide_num, text_preview, score, path_abs}, ...]
        """
        if not self.index:
            return []

        terms = [t.strip().lower() for t in re.split(r'[\s,，、]+', query) if t.strip()]
        if not terms:
            return []

        results = []
        files_data = self.index.get('files', {})

        for rel_path, finfo in files_data.items():
            slides = finfo.get('slides', {})
            keywords = finfo.get('slide_keywords', {})

            for snum, slide_text in slides.items():
                text_lower = slide_text.lower()
                kw_list = keywords.get(snum, [])

                # 计分：关键词匹配
                match_count = 0
                for term in terms:
                    term_lower = term.lower()
                    # 优先在 keywords 数组里匹配（精确匹配加权 2x）
                    if any(term_lower == kw.lower() or term_lower in kw.lower()
                           for kw in kw_list):
                        match_count += 2
                    # 也检查全文（加权 1x）
                    elif term_lower in text_lower:
                        match_count += 1

                if match_count > 0:
                    score = match_count / (len(terms) * 2)
                    # 截取关键词周围文字作为预览
                    preview = _extract_preview(slide_text, terms, max_len=120)

                    results.append({
                        'file': rel_path,
                        'title': finfo.get('title', ''),
                        'slide_num': int(snum),
                        'score': round(score, 3),
                        'text_preview': preview,
                        'path_abs': finfo.get('path_abs', ''),
                    })

        results.sort(key=lambda x: (-x['score'], x['file']))
        return results[:top_k]

    # ── AI 搜索（解耦） ────────────────────────────────

    def search_ai(self, query, ai_callable, top_k=5):
        """
        使用外部 AI 函数进行智能搜索。
        模块本身不依赖任何 AI SDK，调用方传入 AI 函数。

        Args:
            query: 搜索查询字符串
            ai_callable: AI 函数，签名：
                ai_callable(query: str, index_data: dict) -> list[dict]
                返回格式同 search_keyword()：
                [{file, title, slide_num, text_preview, score, path_abs}, ...]
            top_k: 返回前 K 个结果

        Returns:
            [{file, title, slide_num, text_preview, score, path_abs}, ...]
        """
        if not self.index:
            return []

        try:
            results = ai_callable(query, self.index)
        except Exception as e:
            print(f"  AI 搜索失败: {e}")
            return []

        if not results:
            return []

        # 确保必要字段存在
        for r in results:
            r.setdefault('score', 0.0)
            r.setdefault('text_preview', '')
            r.setdefault('slide_num', 1)
            r.setdefault('path_abs', '')
            r.setdefault('title', '')
            r.setdefault('file', '')

        # 按 score 降序排列，取 top_k
        results.sort(key=lambda x: -x.get('score', 0))
        return results[:top_k]

    # ── 召回（COM 提取单页） ────────────────────────────

    def recall(self, entry, output_dir=None):
        """
        从源 PPTX 提取指定页为单页 PPTX。
        使用 COM: 打开源 → Copy slide → PasteSourceFormatting 到空白目标 → 关闭源。

        Args:
            entry: search_keyword/search_ai 返回的条目（含 path_abs, slide_num）
            output_dir: 输出目录（默认 kb_root 同级的 output/recall/）

        Returns:
            {'output': 'path/to/slide.pptx', 'source': '...', 'slide_num': N, 'title': '...'}

        Raises:
            FileNotFoundError: 源文件不存在
            RuntimeError: COM 操作失败
        """
        import pythoncom
        import win32com.client as win32

        src_path = Path(entry['path_abs'])
        if not src_path.exists():
            raise FileNotFoundError(f"源文件不存在: {src_path}")

        slide_num = entry['slide_num']

        if output_dir is None:
            output_dir = self.kb_root.parent / "output" / "recall"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{src_path.stem}_p{slide_num}.pptx"

        pythoncom.CoInitialize()
        ppt_app = None
        try:
            ppt_app = win32.Dispatch('PowerPoint.Application')
            ppt_app.Visible = True
            time.sleep(3)

            # 创建空白目标 PPT（默认有一页空白 slide）
            target = ppt_app.Presentations.Add()
            time.sleep(2)

            # 打开源 PPTX
            abs_src = str(src_path.resolve())
            src = ppt_app.Presentations.Open(abs_src, WithWindow=False)
            time.sleep(3)

            # Copy 指定 slide
            src.Slides(slide_num).Copy()
            time.sleep(1)

            # 关闭源（Copy 之后才能安全关闭）
            src.Close()
            time.sleep(0.5)

            # 激活目标窗口
            try:
                target.Windows(1).Activate()
                time.sleep(0.5)
            except Exception:
                pass

            # PasteSourceFormatting — 保留源格式粘贴
            ppt_app.CommandBars.ExecuteMso("PasteSourceFormatting")
            time.sleep(2)

            # 删除默认空白第一页（新建 PPT 总有一页空白，粘贴页在其后）
            if target.Slides.Count > 1:
                target.Slides(1).Delete()
                time.sleep(0.5)

            # 保存
            abs_output = str(output_file.resolve())
            target.SaveAs(abs_output)
            target.Close()

            return {
                'output': str(output_file),
                'source': str(src_path),
                'slide_num': slide_num,
                'title': entry.get('title', ''),
            }

        except Exception as e:
            # 出错时尝试关闭残留窗口
            try:
                if 'target' in dir():
                    target.Close()
            except Exception:
                pass
            try:
                if 'src' in dir():
                    src.Close()
            except Exception:
                pass
            raise RuntimeError(f"COM recall 失败: {e}") from e

        finally:
            try:
                if ppt_app:
                    ppt_app.Quit()
            except Exception:
                pass
            pythoncom.CoUninitialize()

    # ── 合并 ────────────────────────────────────────────

    def merge(self, entries, output_path):
        """
        将多个幻灯片合并为一个多页 PPTX。
        委托给 merge.py，COM 优先 / ZIP 兜底。

        Args:
            entries: [(pptx_path, slide_num), ...] 列表
            output_path: 输出 PPTX 路径

        Returns:
            str: 输出文件路径
        """
        return merge_slides(entries, output_path)

    # ── 一键管道 ────────────────────────────────────────

    def search_and_merge(self, query, output_path, top_k=5,
                         mode='keyword', ai_callable=None):
        """
        一步完成：搜索 → 合并

        Args:
            query: 搜索关键词
            output_path: 输出 PPTX 路径
            top_k: 返回前 K 个结果
            mode: 'keyword' 或 'ai'
            ai_callable: mode='ai' 时必须提供，签名为
                ai_callable(query: str, index_data: dict) -> list[dict]

        Returns:
            str: 输出路径，或 None 如果没有搜索结果
        """
        # 确保索引存在
        self.build_index()

        # 搜索
        if mode == 'ai':
            if ai_callable is None:
                raise ValueError("AI 模式需要提供 ai_callable 参数")
            results = self.search_ai(query, ai_callable, top_k=top_k)
        else:
            results = self.search_keyword(query, top_k=top_k)

        if not results:
            print(f"  未找到结果: {query}")
            return None

        # 构建 entries: [(path_abs, slide_num), ...]
        entries = [(r['path_abs'], r['slide_num']) for r in results]

        for r in results:
            print(f"  [MATCH] {r['title']} p{r['slide_num']} "
                  f"(score: {r['score']}) ← {query}")

        return self.merge(entries, output_path)

    # ── 概览 ────────────────────────────────────────────

    def summary(self):
        """打印索引概览"""
        idx = self.index
        if not idx:
            print("  索引未构建，请先执行 build_index()")
            return

        print(f"\n  KB Index: {self.index_path}")
        print(f"  Root: {idx.get('kb_root', '?')}")
        print(f"  Scanned: {idx.get('last_scan', '?')}")
        print(f"  Files: {idx.get('total_pptx', 0)}, Slides: {idx.get('total_slides', 0)}")
        print()
        for fname, finfo in idx.get('files', {}).items():
            print(f"    [{finfo['slide_count']}p] {fname}")


# ════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════

def _extract_preview(text, terms, max_len=120):
    """在文本中找到关键词首次出现位置，截取周围文字作为预览"""
    text_lower = text.lower()
    best_pos = -1

    for term in terms:
        pos = text_lower.find(term.lower())
        if pos >= 0 and (best_pos < 0 or pos < best_pos):
            best_pos = pos

    if best_pos >= 0:
        start = max(0, best_pos - 30)
        end = min(len(text), best_pos + max_len)
        preview = text[start:end]
        if start > 0:
            preview = '...' + preview
        if end < len(text):
            preview = preview + '...'
        return preview

    return text[:max_len] + ('...' if len(text) > max_len else '')


# ════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    engine = PPTRecallEngine()

    if "--scan" in sys.argv or "--build" in sys.argv:
        engine.build_index(force=True)
        engine.summary()
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        query = sys.argv[1]
        engine.build_index()
        results = engine.search_keyword(query)

        if results:
            print(f"\n  搜索结果 '{query}' ({len(results)}):")
            for i, r in enumerate(results):
                print(f"  [{i+1}] [score={r['score']}] "
                      f"{r['title']} p{r['slide_num']}")
                print(f"       {r['text_preview'][:100]}")
        else:
            print(f"  未找到结果: '{query}'")
    else:
        engine.build_index()
        engine.summary()
