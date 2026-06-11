#!/usr/bin/env python3
"""
向量库去重脚本 (Vector Store Deduplication)
============================================
对 LLM_Search 的 FAISS 向量库进行余弦相似度去重。

原理：
  1. 从 FAISS 索引提取所有向量（L2 归一化，内积 = 余弦相似度）
  2. 计算成对余弦相似度
  3. 贪婪聚类：相似度 > threshold 的归入同一簇，保留首条
  4. 移除重复条目，重建 FAISS 索引

去重策略（按向量库类型）：
  图片 (images):   默认阈值 0.95  — 同一个 PPT 中相似图多，去重更激进
  PPT页 (ppt_slides): 默认阈值 0.99  — PPT 每页内容不同，仅去极相似

用法：
  # 对所有图片向量去重
  python dedup.py images

  # 对所有 PPT 页面向量去重
  python dedup.py ppt_slides

  # 指定自定义阈值
  python dedup.py images --threshold 0.92

  # 干跑模式（仅统计，不实际修改）
  python dedup.py images --dry-run

  # 全部去重
  python dedup.py all

存储位置：
  FAISS 索引: vector_store/{name}.faiss
  元数据:     vector_store/{name}_meta.json
  去重记录:   vector_store/dedup_log.json
"""

import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set

import numpy as np

# ── 配置 ──────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent  # vector_store/
DEDUP_LOG = SCRIPT_DIR / "dedup_log.json"

# 默认阈值（余弦相似度）
DEFAULT_THRESHOLDS = {
    "images": 0.95,      # 图片：去重更激进（PPT 中常有重复图标/背景）
    "ppt_slides": 0.99,  # PPT 页面：仅去极相似（每页内容不同）
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("dedup")


# ══════════════════════════════════════════════════════════
# 向量提取
# ══════════════════════════════════════════════════════════

def load_vectors_and_meta(store_name: str) -> Tuple[np.ndarray, List[Dict]]:
    """从 FAISS 索引和元数据文件加载向量和条目。

    Returns:
        (vectors, metadata): vectors shape=(N, 512), metadata 列表
    """
    faiss_path = SCRIPT_DIR / f"{store_name}.faiss"
    meta_path = SCRIPT_DIR / f"{store_name}_meta.json"

    if not faiss_path.exists():
        raise FileNotFoundError(f"FAISS 索引不存在: {faiss_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"元数据不存在: {meta_path}")

    import faiss

    # 加载 FAISS 索引
    index = faiss.read_index(str(faiss_path))
    n = index.ntotal
    dim = index.d
    vectors = np.zeros((n, dim), dtype=np.float32)
    index.reconstruct_n(0, n, vectors)

    # 加载元数据
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    if len(vectors) != len(metadata):
        logger.warning(
            f"向量数 ({len(vectors)}) 与元数据数 ({len(metadata)}) 不匹配!"
        )

    return vectors, metadata


# ══════════════════════════════════════════════════════════
# 图像文件哈希去重（MD5 级别）
# ══════════════════════════════════════════════════════════

def image_file_hash_dedup(metadata: List[Dict]) -> Tuple[List[int], Dict]:
    """按图片文件 MD5 哈希去重（最严格的去重）。

    多个条目引用同一个图片文件 → 保留第一个。

    Returns:
        (keep_indices, stats): 保留的索引列表和统计信息
    """
    import hashlib

    hash_map = {}  # md5_hash -> first_index
    duplicates_by_hash = {}  # md5_hash -> [duplicate_indices]

    for i, entry in enumerate(metadata):
        archive_path = entry.get("metadata", {}).get("archive_path", "")
        if not archive_path or not Path(archive_path).exists():
            # 文件不存在，保留（无法判断）
            hash_key = f"__missing__{i}"
            if hash_key not in hash_map:
                hash_map[hash_key] = i
            continue

        # 计算文件 MD5
        md5 = hashlib.md5()
        try:
            with open(archive_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    md5.update(chunk)
            file_hash = md5.hexdigest()
        except Exception:
            file_hash = f"__error__{i}"

        if file_hash not in hash_map:
            hash_map[file_hash] = i
        else:
            if file_hash not in duplicates_by_hash:
                duplicates_by_hash[file_hash] = [hash_map[file_hash]]
            duplicates_by_hash[file_hash].append(i)

    # 收集所有重复索引
    all_dupes = set()
    for indices in duplicates_by_hash.values():
        all_dupes.update(indices[1:])  # 保留第一个

    keep_indices = [i for i in range(len(metadata)) if i not in all_dupes]

    stats = {
        "method": "file_md5",
        "total_files": len(hash_map),
        "unique_files": len(hash_map) - len(duplicates_by_hash),
        "duplicate_groups": len(duplicates_by_hash),
        "duplicates_removed": len(all_dupes),
        "duplicate_details": {
            k: [metadata[idx].get("metadata", {}).get("archive_name", "?")
                for idx in v]
            for k, v in duplicates_by_hash.items()
        },
    }

    return keep_indices, stats


# ══════════════════════════════════════════════════════════
# 向量相似度去重（余弦相似度级别）
# ══════════════════════════════════════════════════════════

def cosine_similarity_dedup(
    vectors: np.ndarray,
    metadata: List[Dict],
    threshold: float = 0.95,
) -> Tuple[List[int], Dict]:
    """基于余弦相似度的去重。

    贪婪聚类算法：
      1. 对每个未处理的条目 i，找所有 j > i 且 sim(i, j) > threshold
      2. 将这些 j 标记为 i 的重复
      3. 保留 i，移除所有重复的 j

    Args:
        vectors: shape=(N, dim), 已 L2 归一化的向量
        metadata: 元数据列表
        threshold: 相似度阈值 (0-1)

    Returns:
        (keep_indices, stats): 保留索引列表和统计信息
    """
    n = len(vectors)
    if n == 0:
        return [], {"method": "cosine_similarity", "threshold": threshold}

    # 标记已处理的条目
    processed = set()       # 已被归入某个簇
    cluster_representative = set()  # 簇的代表
    clusters = []           # [(rep_idx, [dup_indices])]

    for i in range(n):
        if i in processed:
            continue

        # i 是一个新簇的代表
        cluster_representative.add(i)

        # 批量计算 i 与所有 j > i 的相似度
        query = vectors[i:i + 1]  # (1, dim)
        remaining = vectors[i + 1:]  # (n-i-1, dim)

        if len(remaining) == 0:
            break

        # 内积 = 余弦相似度（向量已 L2 归一化）
        similarities = np.dot(query, remaining.T).flatten()  # (n-i-1,)

        # 找到相似度超过阈值的
        high_sim_mask = similarities > threshold
        high_sim_indices = np.where(high_sim_mask)[0]

        # 转换为原始索引
        dup_indices = []
        for rel_idx in high_sim_indices:
            abs_idx = i + 1 + int(rel_idx)
            if abs_idx not in processed:
                dup_indices.append(abs_idx)
                processed.add(abs_idx)

        if dup_indices:
            clusters.append((i, dup_indices))
            processed.add(i)  # 代表也已处理
        else:
            # 无重复，单独保留
            processed.add(i)

    # 未被归入任何簇的条目也保留
    keep_indices = sorted(set(range(n)) - set(
        idx for _, dups in clusters for idx in dups
    ))

    # 统计
    total_removed = n - len(keep_indices)
    stats = {
        "method": "cosine_similarity",
        "threshold": threshold,
        "total": n,
        "kept": len(keep_indices),
        "removed": total_removed,
        "clusters": len(clusters),
        "cluster_sizes": [len(dups) + 1 for _, dups in clusters],
        "cluster_details": [
            {
                "representative": metadata[rep].get("source_id", "?"),
                "duplicates": [metadata[d].get("source_id", "?") for d in dups],
            }
            for rep, dups in clusters
        ],
    }

    return keep_indices, stats


# ══════════════════════════════════════════════════════════
# 综合去重：文件哈希 + 向量相似度
# ══════════════════════════════════════════════════════════

def dedup_images(
    vectors: np.ndarray,
    metadata: List[Dict],
    threshold: float = 0.95,
) -> Tuple[np.ndarray, List[Dict], Dict]:
    """图片专用去重：先按文件哈希，再按向量相似度。

    两步策略：
      1. MD5 文件哈希去重（完全相同的图片文件）
      2. 余弦相似度去重（视觉相似的图片）

    Returns:
        (deduped_vectors, deduped_metadata, stats)
    """
    stats = {"stages": {}}
    n_original = len(vectors)

    # Stage 1: 文件 MD5 哈希去重
    logger.info("  Stage 1: 文件 MD5 哈希去重...")
    keep_idx_1, hash_stats = image_file_hash_dedup(metadata)
    stats["stages"]["md5_hash"] = hash_stats
    logger.info(
        f"    保留 {len(keep_idx_1)}/{n_original}, "
        f"移除 {hash_stats['duplicates_removed']} 个文件级重复"
    )

    vectors_1 = vectors[keep_idx_1]
    metadata_1 = [metadata[i] for i in keep_idx_1]

    if len(vectors_1) <= 1:
        stats["total_removed"] = n_original - len(vectors_1)
        stats["total_kept"] = len(vectors_1)
        return vectors_1, metadata_1, stats

    # Stage 2: 余弦相似度去重
    logger.info(
        f"  Stage 2: 余弦相似度去重 (阈值={threshold})..."
    )
    keep_idx_2, cos_stats = cosine_similarity_dedup(
        vectors_1, metadata_1, threshold
    )
    stats["stages"]["cosine_similarity"] = cos_stats
    logger.info(
        f"    保留 {len(keep_idx_2)}/{len(vectors_1)}, "
        f"移除 {cos_stats['removed']} 个语义重复"
    )

    vectors_2 = vectors_1[keep_idx_2]
    metadata_2 = [metadata_1[i] for i in keep_idx_2]

    stats["total_original"] = n_original
    stats["total_removed"] = n_original - len(vectors_2)
    stats["total_kept"] = len(vectors_2)
    stats["removal_rate"] = (
        f"{stats['total_removed'] / n_original * 100:.1f}%"
        if n_original > 0 else "0%"
    )

    return vectors_2, metadata_2, stats


def dedup_ppt(
    vectors: np.ndarray,
    metadata: List[Dict],
    threshold: float = 0.99,
) -> Tuple[np.ndarray, List[Dict], Dict]:
    """PPT 页面去重：仅余弦相似度（不做文件哈希）"""
    stats = {}
    n_original = len(vectors)

    keep_idx, cos_stats = cosine_similarity_dedup(
        vectors, metadata, threshold
    )

    vectors_dedup = vectors[keep_idx]
    metadata_dedup = [metadata[i] for i in keep_idx]

    stats["method"] = "cosine_similarity"
    stats["threshold"] = threshold
    stats["total_original"] = n_original
    stats["total_removed"] = n_original - len(vectors_dedup)
    stats["total_kept"] = len(vectors_dedup)
    stats["stages"] = {"cosine_similarity": cos_stats}

    return vectors_dedup, metadata_dedup, stats


# ══════════════════════════════════════════════════════════
# FAISS 索引重建
# ══════════════════════════════════════════════════════════

def rebuild_faiss_index(
    store_name: str,
    vectors: np.ndarray,
    metadata: List[Dict],
) -> None:
    """用去重后的数据重建 FAISS 索引。"""
    import faiss

    faiss_path = SCRIPT_DIR / f"{store_name}.faiss"
    meta_path = SCRIPT_DIR / f"{store_name}_meta.json"

    dim = vectors.shape[1]

    # 备份原始文件
    backup_faiss = faiss_path.with_suffix(".faiss.bak")
    backup_meta = meta_path.with_suffix(".json.bak")

    if faiss_path.exists():
        faiss_path.rename(backup_faiss)
        logger.info(f"  备份 FAISS: {backup_faiss.name}")
    if meta_path.exists():
        meta_path.rename(backup_meta)
        logger.info(f"  备份 元数据: {backup_meta.name}")

    # 创建新索引
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    faiss.write_index(index, str(faiss_path))

    # 写入元数据
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # 清理备份
    backup_faiss.unlink(missing_ok=True)
    backup_meta.unlink(missing_ok=True)

    logger.info(f"  ✓ 索引已重建: {faiss_path.name} ({len(metadata)} 条)")


# ══════════════════════════════════════════════════════════
# 日志记录
# ══════════════════════════════════════════════════════════

def log_dedup(store_name: str, stats: Dict, dry_run: bool) -> None:
    """记录去重操作到日志文件。"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "store": store_name,
        "dry_run": dry_run,
        "stats": stats,
    }

    # 加载已有日志
    if DEDUP_LOG.exists():
        with open(DEDUP_LOG, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    else:
        logs = []

    logs.append(log_entry)

    # 只保留最近 50 条
    if len(logs) > 50:
        logs = logs[-50:]

    with open(DEDUP_LOG, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════
# 主逻辑
# ══════════════════════════════════════════════════════════

def run_dedup(
    store_name: str,
    threshold: Optional[float] = None,
    dry_run: bool = False,
) -> Dict:
    """对指定向量库执行去重。

    Args:
        store_name: "images" | "ppt_slides"
        threshold: 余弦相似度阈值，None 则使用默认值
        dry_run: 仅统计不修改
    """
    if threshold is None:
        threshold = DEFAULT_THRESHOLDS.get(store_name, 0.95)

    logger.info("=" * 60)
    logger.info(f"向量去重: [{store_name}]  阈值: {threshold}")
    logger.info("=" * 60)

    # 1. 加载数据
    logger.info("[1/4] 加载向量和元数据...")
    vectors, metadata = load_vectors_and_meta(store_name)
    logger.info(f"  加载: {len(vectors)} 条记录, 维度={vectors.shape[1]}")

    # 2. 执行去重
    logger.info("[2/4] 执行去重...")
    start = time.time()

    if store_name == "images":
        deduped_vecs, deduped_meta, stats = dedup_images(
            vectors, metadata, threshold
        )
    else:
        deduped_vecs, deduped_meta, stats = dedup_ppt(
            vectors, metadata, threshold
        )

    elapsed = time.time() - start

    # 3. 输出结果
    logger.info(f"[3/4] 去重结果 ({elapsed:.1f}s):")
    logger.info(f"  原始: {stats.get('total_original', len(vectors))} 条")
    logger.info(f"  保留: {stats.get('total_kept', 0)} 条")
    logger.info(f"  移除: {stats.get('total_removed', 0)} 条")
    if "removal_rate" in stats:
        logger.info(f"  去重率: {stats['removal_rate']}")

    # 详细阶段统计
    for stage_name, stage_stats in stats.get("stages", {}).items():
        if stage_name == "md5_hash":
            logger.info(
                f"    [MD5哈希] 发现 {stage_stats.get('duplicate_groups', 0)} 组重复, "
                f"移除 {stage_stats.get('duplicates_removed', 0)} 条"
            )
        elif stage_name == "cosine_similarity":
            logger.info(
                f"    [余弦相似度] 发现 {stage_stats.get('clusters', 0)} 个簇, "
                f"移除 {stage_stats.get('removed', 0)} 条, "
                f"阈值={stage_stats.get('threshold', '?')}"
            )

    # 4. 保存
    logger.info("[4/4] 保存结果...")
    if dry_run:
        logger.info("  [dry-run] 跳过实际修改")
    else:
        if len(deduped_vecs) > 0:
            rebuild_faiss_index(store_name, deduped_vecs, deduped_meta)
        else:
            logger.warning("  去重后无数据，跳过保存")

    # 记录日志
    log_dedup(store_name, stats, dry_run)

    logger.info("=" * 60)
    logger.info(
        f"✅ 去重完成: {stats.get('total_original', 0)} → "
        f"{stats.get('total_kept', 0)} (移除 {stats.get('total_removed', 0)} 条)"
    )
    logger.info("=" * 60)

    return stats


# ══════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="向量库去重 — 余弦相似度 + 文件哈希去重",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python dedup.py images                  # 图片去重（默认阈值 0.95）
  python dedup.py images --threshold 0.9  # 更激进去重
  python dedup.py ppt_slides              # PPT 页面去重（默认阈值 0.99）
  python dedup.py images --dry-run        # 仅统计不去重
  python dedup.py all                     # 全部去重
        """,
    )

    parser.add_argument(
        "store",
        choices=["images", "ppt_slides", "all"],
        help="向量库名称: images | ppt_slides | all",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=None,
        help="余弦相似度阈值 (默认: images=0.95, ppt_slides=0.99)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="干跑模式，仅统计不实际修改",
    )

    args = parser.parse_args()

    if args.store == "all":
        stores = ["images", "ppt_slides"]
    else:
        stores = [args.store]

    all_stats = {}
    for store in stores:
        try:
            all_stats[store] = run_dedup(
                store,
                threshold=args.threshold,
                dry_run=args.dry_run,
            )
        except FileNotFoundError as e:
            logger.warning(f"跳过 {store}: {e}")
        except Exception as e:
            logger.error(f"{store} 去重失败: {e}", exc_info=True)

    # 汇总
    if len(stores) > 1:
        total_orig = sum(
            s.get("total_original", 0) for s in all_stats.values()
        )
        total_kept = sum(
            s.get("total_kept", 0) for s in all_stats.values()
        )
        total_removed = sum(
            s.get("total_removed", 0) for s in all_stats.values()
        )
        logger.info("=" * 60)
        logger.info("📊 全部汇总")
        logger.info(f"  原始: {total_orig} → 保留: {total_kept} → 移除: {total_removed}")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
