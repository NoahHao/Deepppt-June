#!/usr/bin/env python3
"""
LLM_Search 向量索引构建器
==========================
从多个数据源读取 PPT 页面和图片文本，使用嵌入模型生成向量，存入 FAISS 向量库。

数据源（按优先级）：
  1. kb_index.json — PPT Recall 的 JSON 索引
  2. image_extract_index.json — 图片提取的 JSON 索引
  3. kb_ai.db — 已有的 sqlite-vec 数据库（slides 表）

工作流：
  1. 查找并加载数据源
  2. 提取每页 PPT / 每张图片的文本
  3. 通过 embedder 编码为向量
  4. 存入 VectorStore

完全独立于原有检索代码，只读取现有数据文件。

用法：
  python indexer.py build                 # 构建全部索引（自动选择数据源）
  python indexer.py build --type ppt      # 仅 PPT 页面
  python indexer.py build --type img      # 仅图片
  python indexer.py build --from-db       # 从 kb_ai.db 构建
  python indexer.py build --force         # 强制重建
  python indexer.py stats                 # 查看索引统计
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import (
    KB_INDEX_PATHS,
    IMG_INDEX_PATHS,
    find_existing_json_index,
    LEGACY_DB_PATH,
    PPT_FAISS_INDEX,
    IMG_FAISS_INDEX,
    PPT_META_JSON,
    IMG_META_JSON,
)
# Embedder and VectorStore imported lazily in VectorIndexBuilder

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# 文本提取器
# ═══════════════════════════════════════════════════════


def _extract_ppt_direct(kb_root: Path) -> List[Dict[str, Any]]:
    """直接从 PPTX 文件提取文本（零依赖自举）。

    当 kb_index.json 和 kb_ai.db 都不存在时，
    直接读取 knowledge_base 下的 PPTX 文件，提取 slide 文本。

    使用与 PPT_Recall indexer 相同的方式：读取 ppt/slides/slideN.xml，
    提取 <a:t> 标签中的文本。

    Args:
        kb_root: knowledge_base 目录路径

    Returns:
        与 _extract_ppt_texts 相同格式的条目列表
    """
    import zipfile, re

    kb_root = Path(kb_root)
    if not kb_root.exists():
        return []

    entries = []
    pptx_files = sorted(kb_root.rglob("*.pptx"))

    for pptx_path in pptx_files:
        if pptx_path.name.startswith("~$"):
            continue

        rel_path = str(pptx_path.relative_to(kb_root))
        title = pptx_path.stem

        try:
            with zipfile.ZipFile(pptx_path, 'r') as z:
                slide_names = sorted(
                    [n for n in z.namelist()
                     if re.match(r'ppt/slides/slide\d+\.xml$', n)],
                    key=lambda x: int(re.search(r'slide(\d+)', x).group(1))
                )

                for sn in slide_names:
                    snum = str(int(re.search(r'slide(\d+)', sn).group(1)))
                    xml = z.read(sn).decode('utf-8', errors='replace')

                    # 提取所有 <a:t> 标签内的文本
                    texts = re.findall(r'<a:t[^>]*>([^<]*)</a:t>', xml)
                    slide_text = ' '.join(t for t in texts if t.strip())

                    if not slide_text:
                        continue

                    # 提取关键词（2-30 字符的词组）
                    keywords = []
                    for t in texts:
                        t = t.strip()
                        if 2 <= len(t) <= 30 and not re.match(
                            r'^[\d\s\.\-,;:：；，。、]+$', t
                        ):
                            keywords.append(t)

                    # 构建 embed_text
                    kw_str = " ".join(keywords[:20]) if keywords else ""
                    embed_text = f"{title} {kw_str} {slide_text}"
                    if len(embed_text) > 1000:
                        embed_text = f"{title} {kw_str} {slide_text[:800]}"

                    entries.append({
                        "source_type": "ppt_slide",
                        "source_id": f"{rel_path}::{snum}",
                        "text": embed_text,
                        "display_text": slide_text[:200],
                        "metadata": {
                            "file": rel_path,
                            "title": title,
                            "path_abs": str(pptx_path),
                            "slide_num": int(snum),
                            "slide_count": len(slide_names),
                            "keywords": keywords[:20],
                        },
                    })

        except Exception as e:
            logger.warning(f"读取 PPTX 失败 {pptx_path.name}: {e}")

    logger.info(f"直接读取 PPTX: {len(pptx_files)} 文件, {len(entries)} 页文本")
    return entries


def _extract_ppt_from_db(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """从 kb_ai.db (sqlite-vec) 的 slides 表提取 PPT 页面数据。

    读取已有的 slide 元数据和 embedding，用于向量搜索。

    Returns:
        [{
            "source_type": "ppt_slide",
            "source_id": "source_pptx::slide_id",
            "text": "用于 embedding 的组合文本",
            "display_text": "原始页面预览",
            "metadata": { ... 原始 DB 字段 ... },
            "embedding": np.ndarray or None  # 若已有 embedding
        }, ...]
    """
    if db_path is None:
        db_path = LEGACY_DB_PATH

    if not db_path.exists():
        logger.warning(f"kb_ai.db 不存在: {db_path}")
        return []

    import numpy as np

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # 读取 slides + 关联的 embeddings
    cur.execute("""
        SELECT s.id, s.source_pptx, s.source_name, s.slide_num,
               s.topic, s.industry, s.text_content, s.text_preview,
               e.embedding
        FROM slides s
        LEFT JOIN slide_embeddings e ON s.id = e.slide_id
        ORDER BY s.source_pptx, s.slide_num
    """)

    entries = []
    for row in cur.fetchall():
        sid, src, name, snum, topic, industry, text, preview, emb_blob = row

        # 构建 embed_text
        parts = []
        if topic:
            parts.append(str(topic))
        if name:
            parts.append(str(name))
        if text:
            parts.append(str(text))
        embed_text = " ".join(parts)

        if not embed_text:
            embed_text = preview or ""

        if len(embed_text) > 1000:
            embed_text = embed_text[:1000]

        # 解码已有 embedding (BLOB → float32 array)
        existing_vec = None
        if emb_blob:
            existing_vec = np.frombuffer(emb_blob, dtype=np.float32).copy()

        source_pptx_name = Path(src).name if src else name or ""

        entries.append({
            "source_type": "ppt_slide",
            "source_id": f"{source_pptx_name}::{snum}",
            "text": embed_text,
            "display_text": (preview or "")[:200],
            "metadata": {
                "file": source_pptx_name,
                "title": topic or name or "",
                "path_abs": src or "",
                "slide_num": int(snum or 0),
                "slide_count": 0,  # 由 build 时统计
                "keywords": [],
                "industry": industry or "",
                "slide_id": sid,
            },
            "_embedding": existing_vec,
        })

    conn.close()
    return entries


def _extract_ppt_texts(json_path: Path) -> List[Dict[str, Any]]:
    """从 kb_index.json 提取每页 PPT 的文本和元数据。

    生成用于搜索的文本：文件名 + 页面标题 + 关键词 + 页面文本

    Returns:
        [{
            "source_type": "ppt_slide",
            "source_id": "file_path::slide_num",
            "text": "用于 embedding 的组合文本",
            "display_text": "原始页面文本",
            "metadata": { ... 原始 JSON 字段 ... }
        }, ...]
    """
    with open(json_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    entries = []
    files_data = index.get("files", {})

    for rel_path, finfo in files_data.items():
        title = finfo.get("title", "")
        path_abs = finfo.get("path_abs", "")
        slides = finfo.get("slides", {})
        keywords = finfo.get("slide_keywords", {})

        for snum, slide_text in slides.items():
            kw_list = keywords.get(snum, [])
            kw_str = " ".join(kw_list) if kw_list else ""

            # 组合文本用于 embedding：标题权重最高，关键词次之，文本内容最后
            # 重要信息前置（title 和 keywords 放在前面，让模型更关注）
            embed_text = f"{title} {kw_str} {slide_text}"

            # 截断过长文本（避免超出模型 token 限制）
            if len(embed_text) > 1000:
                embed_text = (
                    f"{title} {kw_str} {slide_text[:800]}"
                )

            entries.append({
                "source_type": "ppt_slide",
                "source_id": f"{rel_path}::{snum}",
                "text": embed_text,
                "display_text": slide_text[:200],
                "metadata": {
                    "file": rel_path,
                    "title": title,
                    "path_abs": path_abs,
                    "slide_num": int(snum),
                    "slide_count": finfo.get("slide_count", 0),
                    "keywords": kw_list,
                },
            })

    return entries


def _extract_image_texts(json_path: Path) -> List[Dict[str, Any]]:
    """从 image_extract_index.json 提取每张图片的文本和元数据。

    生成用于搜索的文本：
      description_hint + context_text + search_tags + source_filename

    Returns:
        [{
            "source_type": "image",
            "source_id": "archive_name",
            "text": "用于 embedding 的组合文本",
            "display_text": "图片描述",
            "metadata": { ... 原始 JSON 字段 ... }
        }, ...]
    """
    with open(json_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    entries = []
    images = index.get("images", {})

    for key, entry in images.items():
        desc = entry.get("description_hint", "") or ""
        context = entry.get("context_text", "") or ""
        tags = entry.get("search_tags", [])
        tag_str = " ".join(tags) if tags else ""
        filename = entry.get("source_filename", "") or ""
        archive_name = entry.get("archive_name", "") or ""

        # 组合文本：描述最重要，标签次之，文件名提供上下文
        embed_text = f"{desc} {tag_str} {filename} {context}"

        if len(embed_text) > 1000:
            embed_text = f"{desc[:200]} {tag_str} {filename} {context[:500]}"

        entries.append({
            "source_type": "image",
            "source_id": archive_name or key,
            "text": embed_text,
            "display_text": desc[:200],
            "metadata": {
                "archive_name": archive_name,
                "archive_path": entry.get("archive_path", ""),
                "source_file": entry.get("source_file", ""),
                "source_filename": filename,
                "format": entry.get("format", ""),
                "width": entry.get("width", 0),
                "height": entry.get("height", 0),
                "slide_number": entry.get("slide_number", ""),
                "slide_title": entry.get("slide_title", ""),
                "search_tags": tags,
                "description_hint": desc,
            },
        })

    return entries


# ═══════════════════════════════════════════════════════
# 索引构建器
# ═══════════════════════════════════════════════════════


class VectorIndexBuilder:
    """向量索引构建器。

    从 JSON 索引读取 → 生成向量 → 存入 VectorStore。

    Usage:
        builder = VectorIndexBuilder()
        builder.build_ppt()
        builder.build_images()
        builder.print_stats()
    """

    def __init__(self, model_name: Optional[str] = None):
        from .embedder import Embedder
        self.embedder = Embedder(model_name=model_name) if model_name else Embedder()
        self.ppt_store: Optional[VectorStore] = None
        self.img_store: Optional[VectorStore] = None

    # ── PPT 页面向量索引 ──────────────────────────────

    def build_ppt(
        self,
        json_path: Optional[Path] = None,
        from_db: bool = False,
        from_pptx: bool = False,
        db_path: Optional[Path] = None,
        kb_root: Optional[Path] = None,
        force: bool = False,
    ) -> VectorStore:
        """构建 PPT 页面向量索引。

        数据源优先级（自动降级）：
          1. from_db=True       → kb_ai.db 的 slides 表
          2. from_pptx=True     → 直接读取 knowledge_base/*.pptx
          3. json_path 指定     → kb_index.json
          4. 自动查找 kb_index.json
          5. 最后兜底：直接读取 knowledge_base 下的 PPTX

        Args:
            json_path: kb_index.json 路径
            from_db: 是否从 SQLite 数据库读取
            from_pptx: 是否直接读取 PPTX 文件
            db_path: 数据库路径
            kb_root: knowledge_base 目录
            force: 是否强制重建
        """
        entries = []

        # 1. 尝试从 DB 读取
        if from_db and not from_pptx:
            db_entries = _extract_ppt_from_db(db_path)
            if db_entries:
                entries = db_entries
                logger.info(f"PPT 索引数据源: kb_ai.db")

        # 2. 尝试从 PPTX 直接读取
        if not entries and (from_pptx or from_db is False):
            if kb_root is None:
                from .config import get_project_root
                kb_root = get_project_root() / "knowledge_base"
            pptx_entries = _extract_ppt_direct(kb_root)
            if pptx_entries:
                entries = pptx_entries
                logger.info(f"PPT 索引数据源: PPTX 文件 (knowledge_base)")

        # 3. 从 JSON 读取
        if not entries:
            if json_path is None:
                json_path = find_existing_json_index(KB_INDEX_PATHS)

            if json_path:
                logger.info(f"PPT 索引数据源: {json_path}")
                entries = _extract_ppt_texts(json_path)

        # 4. 最后兜底：直接从 PPTX 读取（即使没指定 from_pptx）
        if not entries:
            if kb_root is None:
                from .config import get_project_root
                kb_root = get_project_root() / "knowledge_base"
            pptx_entries = _extract_ppt_direct(kb_root)
            if pptx_entries:
                entries = pptx_entries
                logger.info("自动回退: 从 PPTX 文件直接提取")
            else:
                logger.warning("未找到任何 PPT 数据源（JSON / DB / PPTX），跳过")
                return None

        logger.info(f"提取 {len(entries)} 条 PPT 页面文本")

        if not entries:
            logger.warning("没有 PPT 页面数据")
            return None

        from .store import VectorStore

        # 向量存储（force 时清空重建）
        self.ppt_store = VectorStore("ppt_slides")
        if force:
            self.ppt_store.clear()

        # 检查是否有已有 embedding
        has_existing = any(e.get("_embedding") is not None for e in entries)

        if has_existing and not force:
            # 使用已有的 embeddings（从 DB 加载的）
            import numpy as np
            vectors = np.array(
                [e.get("_embedding") for e in entries], dtype=np.float32
            )
            logger.info(f"使用已有嵌入向量 ({len(vectors)} 条, dim={vectors.shape[1]})")
        else:
            # 生成新向量
            texts = [e["text"] for e in entries]
            logger.info(f"正在生成嵌入向量 ({len(texts)} 条)...")
            vectors = self.embedder.encode(texts)

        # 清理临时字段（必须在 add 之前）
        for e in entries:
            e.pop("_embedding", None)

        # 统计每个文件的 slide_count
        file_counts: Dict[str, int] = {}
        for e in entries:
            fname = e["metadata"].get("file", "")
            file_counts[fname] = file_counts.get(fname, 0) + 1
        for e in entries:
            fname = e["metadata"].get("file", "")
            e["metadata"]["slide_count"] = file_counts.get(fname, 0)

        # 存入
        self.ppt_store.add(vectors, entries)
        self.ppt_store.save()

        logger.info(f"PPT 向量索引构建完成: {len(entries)} 条 (引擎: {self.ppt_store.engine_type})")
        return self.ppt_store

    # ── 图片向量索引 ──────────────────────────────────

    def build_images(
        self,
        json_path: Optional[Path] = None,
        force: bool = False,
    ) -> VectorStore:
        """构建图片向量索引。

        Args:
            json_path: image_extract_index.json 路径（默认自动查找）
            force: 是否强制重建
        """
        if json_path is None:
            json_path = find_existing_json_index(IMG_INDEX_PATHS)

        if json_path is None:
            logger.warning("未找到 image_extract_index.json，跳过图片索引构建")
            return None

        logger.info(f"图片索引数据源: {json_path}")

        entries = _extract_image_texts(json_path)
        logger.info(f"提取 {len(entries)} 条图片文本")

        if not entries:
            logger.warning("没有图片数据")
            return None

        from .store import VectorStore

        self.img_store = VectorStore("images")
        if force:
            self.img_store.clear()

        texts = [e["text"] for e in entries]
        logger.info(f"正在生成嵌入向量 ({len(texts)} 条)...")
        vectors = self.embedder.encode(texts)

        self.img_store.add(vectors, entries)
        self.img_store.save()

        logger.info(f"图片向量索引构建完成: {len(entries)} 条")
        return self.img_store

    # ── 一键构建 ──────────────────────────────────────

    def build_all(self, force: bool = False, from_db: bool = False, from_pptx: bool = False) -> Dict[str, VectorStore]:
        """构建全部向量索引"""
        results = {}
        results["ppt"] = self.build_ppt(force=force, from_db=from_db, from_pptx=from_pptx)
        results["images"] = self.build_images(force=force)
        return results

    # ── 统计 ──────────────────────────────────────────

    def print_stats(self) -> None:
        """打印索引统计"""
        from .store import VectorStore
        
        stores = [
            ("PPT 页面", self.ppt_store or VectorStore("ppt_slides")),
            ("图片", self.img_store or VectorStore("images")),
        ]

        print("\n" + "=" * 60)
        print("  LLM_Search 向量索引统计")
        print("=" * 60)
        for label, store in stores:
            print(f"\n  [{label}]")
            print(f"    引擎: {store.engine_type}")
            print(f"    条目: {store.count}")
            print(f"    维度: {store.dimension}")
            print(f"    目录: {store.store_dir}")
        print()


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if len(sys.argv) < 2:
        print("用法:")
        print("  python indexer.py build                 # 构建全部索引（自动选源）")
        print("  python indexer.py build --type ppt      # 仅 PPT")
        print("  python indexer.py build --type img      # 仅图片")
        print("  python indexer.py build --from-db       # 从 kb_ai.db 构建")
        print("  python indexer.py build --from-pptx     # 从 PPTX 直接读取（零依赖）")
        print("  python indexer.py build --force         # 强制重建")
        print("  python indexer.py stats                 # 统计")
        sys.exit(1)

    cmd = sys.argv[1]
    builder = VectorIndexBuilder()

    if cmd == "build":
        force = "--force" in sys.argv
        from_db = "--from-db" in sys.argv
        from_pptx = "--from-pptx" in sys.argv
        idx_type = None
        if "--type" in sys.argv:
            ti = sys.argv.index("--type")
            if ti + 1 < len(sys.argv):
                idx_type = sys.argv[ti + 1]

        if idx_type == "ppt":
            builder.build_ppt(force=force, from_db=from_db, from_pptx=from_pptx)
        elif idx_type == "img":
            builder.build_images(force=force)
        else:
            builder.build_all(force=force, from_db=from_db, from_pptx=from_pptx)

        builder.print_stats()
    elif cmd == "stats":
        builder.print_stats()
    else:
        print(f"未知命令: {cmd}")
