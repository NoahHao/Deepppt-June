#!/usr/bin/env python3
"""
image_extract 归档去重工具 — 清理 archive 中重复图片并重建索引
==============================================================
功能：
  1. 扫描 archive 目录，按 SHA256 content_hash 识别重复文件
  2. 删除重复文件，保留归档名长度最短的一条（通常来自最原始的源文件）
  3. 同步更新关联的 index JSON（删除重复条目）
  4. 提供预览模式（--preview）：只显示重复，不执行删除

使用方式：
  python dedup.py <archive_dir> [--index <index_json>] [--preview] [--verbose]

示例：
  python dedup.py projects/华为LightAI/images/archive/ --preview
  python dedup.py projects/华为LightAI/images/archive/
  python dedup.py projects/华为LightAI/images/archive/ --index projects/华为LightAI/images/image_extract_index.json
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def compute_hash(filepath: Path) -> str:
    """计算文件的 SHA256 哈希"""
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def scan_archive(archive_dir: Path, verbose: bool = True) -> Tuple[List[Dict], int, int]:
    """
    扫描归档目录，按 content_hash 分组，识别重复文件。
    
    Returns:
        (duplicate_groups, total_files, unique_files)
        duplicate_groups: list of dicts, each with 'hash', 'files' (每个文件: {name, path, size})
    """
    if not archive_dir.exists():
        print(f"错误: 目录不存在: {archive_dir}")
        return [], 0, 0
    
    # 收集所有文件及其哈希
    hash_map: Dict[str, list] = {}
    all_files = sorted(archive_dir.iterdir())
    
    for fpath in all_files:
        if not fpath.is_file():
            continue
        # 跳过非图片文件
        ext = fpath.suffix.lower()
        if ext not in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.svg', '.webp', '.emf', '.wmf'):
            continue
        try:
            h = compute_hash(fpath)
            hash_map.setdefault(h, []).append(fpath)
        except Exception as e:
            if verbose:
                print(f"  [WARN] 无法读取 {fpath.name}: {e}")
    
    total = sum(len(v) for v in hash_map.values())
    unique = len(hash_map)
    
    # 找出有重复的组
    duplicate_groups = []
    for h, files in hash_map.items():
        if len(files) > 1:
            # 按文件名长度排序（优先保留较短的文件名）
            sorted_files = sorted(files, key=lambda f: (len(f.stem), f.stem))
            kept = sorted_files[0]  # 保留的（最短文件名）
            to_remove = sorted_files[1:]  # 待删除的
            duplicate_groups.append({
                'hash': h[:16],
                'kept': kept,
                'to_remove': to_remove,
            })
    
    return duplicate_groups, total, unique


def update_index(index_path: Path, archive_dir: Path, removed_names: set, verbose: bool = True):
    """
    从索引 JSON 中删除已移除的归档文件条目。
    
    Args:
        index_path: 索引 JSON 路径
        archive_dir: 归档目录路径
        removed_names: 已删除的文件名集合
    """
    if not index_path.exists():
        if verbose:
            print(f"  索引文件不存在，跳过: {index_path}")
        return
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index = json.load(f)
    
    images = index.get('images', {})
    before = len(images)
    
    # 构建 文件名(去除拓展名) → 全名的映射
    removed_stems = set()
    for name in removed_names:
        stem = Path(name).stem
        removed_stems.add(stem)
    
    # 删除匹配的条目
    keys_to_remove = set()
    for key, entry in images.items():
        if key in removed_stems:
            keys_to_remove.add(key)
        elif entry.get('archive_name', '') in removed_names:
            key2 = Path(entry['archive_name']).stem
            if key2 not in removed_stems:
                keys_to_remove.add(key)
    
    for key in keys_to_remove:
        del images[key]
    
    after = len(images)
    removed_count = before - after
    
    if removed_count > 0:
        index['total_images'] = after
        index['total_duplicates_removed'] = index.get('total_duplicates_removed', 0) + removed_count
        
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        
        if verbose:
            print(f"  索引已更新: 移除 {removed_count} 个重复条目 (从 {before} 到 {after})")
    else:
        if verbose:
            print(f"  索引无需更新")


def deduplicate(archive_dir: str, index_path: str = None, preview: bool = False, verbose: bool = True):
    """
    主入口：对归档目录进行去重。
    
    Args:
        archive_dir: 归档目录路径
        index_path: 可选的索引 JSON 路径（自动检测）
        preview: 预览模式（只显示不删除）
        verbose: 是否打印详细信息
    """
    archive_path = Path(archive_dir)
    
    print(f"📁 扫描归档目录: {archive_path}")
    
    groups, total, unique = scan_archive(archive_path, verbose)
    
    print(f"  总文件数: {total}")
    print(f"  唯一文件数: {unique}")
    print(f"  重复文件组: {len(groups)}")
    
    if not groups:
        print("\n✅ 没有重复文件，无需去重。")
        return
    
    # 显示重复组
    total_saved_bytes = 0
    all_to_remove = []
    
    print(f"\n{'='*60}")
    print(f"{'重复文件详情':^60}")
    print(f"{'='*60}")
    
    for i, g in enumerate(groups, 1):
        kept = g['kept']
        to_remove = g['to_remove']
        
        print(f"\n  组 #{i} (hash={g['hash']}...)")
        print(f"    ✅ 保留: {kept.name} ({kept.stat().st_size:,} bytes)")
        for f in to_remove:
            sz = f.stat().st_size
            print(f"    ❌ 删除: {f.name} ({sz:,} bytes)")
            total_saved_bytes += sz
            all_to_remove.append(f)
    
    print(f"\n{'='*60}")
    print(f"  共 {len(all_to_remove)} 个重复文件, 可释放 {total_saved_bytes:,} bytes "
          f"({total_saved_bytes/1024/1024:.1f} MB)")
    
    if preview:
        print(f"\n🔍 预览模式 -- 未执行任何删除操作。")
        print(f"   移除 --preview 参数执行实际去重。")
        return
    
    # 执行去重
    print(f"\n{'='*60}")
    print(f"{'开始去重...':^60}")
    print(f"{'='*60}")
    
    removed_names = set()
    removed_count = 0
    for f in all_to_remove:
        try:
            f.unlink()
            removed_names.add(f.name)
            removed_count += 1
            if verbose:
                print(f"  ✅ 已删除: {f.name}")
        except Exception as e:
            print(f"  ❌ 删除失败 {f.name}: {e}")
    
    print(f"\n  成功删除 {removed_count} 个重复文件")
    
    # 更新索引
    if index_path:
        index_p = Path(index_path)
    else:
        # 自动检测索引位置
        candidates = [
            archive_path.parent / 'image_extract_index.json',
            archive_path.parent.parent / 'images' / 'image_extract_index.json',
        ]
        index_p = None
        for c in candidates:
            if c.exists():
                index_p = c
                break
    
    if index_p:
        print(f"\n{'='*60}")
        print(f"{'更新索引...':^60}")
        print(f"{'='*60}")
        update_index(index_p, archive_path, removed_names, verbose)
    else:
        print(f"\n  未找到索引文件，跳过索引更新。")
        print(f"  可指定: --index <索引JSON路径>")
    
    print(f"\n✅ 去重完成！")


if __name__ == "__main__":
    # 简单 CLI
    args = sys.argv[1:]
    
    if not args or '--help' in args or '-h' in args:
        print(__doc__)
        sys.exit(0)
    
    archive_dir = args[0]
    index_path = None
    preview = False
    verbose = True
    
    if '--index' in args:
        idx = args.index('--index')
        if idx + 1 < len(args):
            index_path = args[idx + 1]
    
    if '--preview' in args:
        preview = True
    
    if '--quiet' in args:
        verbose = False
    
    deduplicate(archive_dir, index_path, preview, verbose)
