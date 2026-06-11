#!/usr/bin/env python3
"""
image_extract 索引器 — 建立富语义图片索引 JSON
================================================
输出 image_index.json，结构与 PPT_Recall 的 kb_index.json 互补。

索引存放位置：
  文件级：projects/<project>/images/image_extract_index.json
  知识库级：knowledge_base/.kb_img_index/image_index.json

索引字段：
  - source: 来源文件信息
  - location: 图片在文件中的位置（页码/段落）
  - visual: 视觉属性（格式、尺寸）
  - context: 上下文文本（自然语言搜索的关键字段）
  - search_tags: 自动提取的关键词标签
  - dedup: 哈希去重信息

使用方式：
  python indexer.py scan <directory> [--kb-mode]
  python indexer.py scan <file> [--output <json_path>]
"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .extractor import extract_images, ExtractedImage


# ═══════════════════════════════════════════════════════
# 标签提取
# ═══════════════════════════════════════════════════════

def _extract_search_tags(img: ExtractedImage) -> List[str]:
    """从图片的元数据中提取搜索标签"""
    tags = set()
    
    # 格式标签
    tags.add(img.format)
    
    # 来源文件标签
    source_stem = Path(img.source_filename).stem
    # 提取中文词
    chinese_words = re.findall(r'[\u4e00-\u9fff]+', source_stem)
    tags.update(chinese_words)
    
    # 从上下文文本中提取有意义的中英文关键词
    if img.context_text:
        # 中文词（2-8字）
        cn_words = re.findall(r'[\u4e00-\u9fff]{2,8}', img.context_text)
        tags.update(cn_words)
        # 英文词（3-20字母）
        en_words = re.findall(r'\b[a-zA-Z]{3,20}\b', img.context_text)
        tags.update(w.lower() for w in en_words)
    
    # 从归档名中提取
    archive_parts = img.archive_name.split('_')
    for part in archive_parts:
        if re.match(r'^[\u4e00-\u9fff\w]+$', part):
            tags.add(part)
    
    return sorted(t for t in tags if t)


def _extract_description_hint(img: ExtractedImage) -> str:
    """生成图片的描述提示（用于搜索展示）"""
    parts = []
    if img.slide_title:
        parts.append(img.slide_title[:80])
    if img.context_text:
        parts.append(img.context_text[:120])
    return ' | '.join(parts) if parts else img.archive_name


# ═══════════════════════════════════════════════════════
# 索引结构构建
# ═══════════════════════════════════════════════════════

def _build_image_entry(img: ExtractedImage) -> dict:
    """将 ExtractedImage 转换为 JSON 可序列化的字典"""
    # 处理标题（优先用 slide_title，其次从 context 截取）
    title = ""
    if img.slide_title:
        title = img.slide_title.strip()
    elif img.context_text:
        # 取第一行作为标题
        first_line = img.context_text.split('\n')[0].strip()
        if len(first_line) > 5:
            title = first_line[:80]
    
    return {
        "source_file": img.source_file,
        "source_filename": img.source_filename,
        "archive_name": img.archive_name,
        "format": img.format,
        "size_bytes": img.size_bytes,
        "width": img.width,
        "height": img.height,
        "content_hash": img.content_hash,
        
        # 位置信息
        "slide_number": img.slide_number,
        "paragraph_index": img.paragraph_index,
        "slide_title": title,
        
        # 上下文（搜索核心字段）
        "context_text": img.context_text[:500] if img.context_text else "",
        "description_hint": _extract_description_hint(img),
        
        # 关键词标签
        "search_tags": _extract_search_tags(img),
        
        # 时间
        "extracted_at": img.extracted_at,
    }


# ═══════════════════════════════════════════════════════
# 扫描与索引（扫描目录下的文件）
# ═══════════════════════════════════════════════════════

def scan_and_index(target_path, output_path=None, verbose=True, archive_dir=None):
    """
    扫描目录或文件，提取图片并建立索引 JSON。
    
    Args:
        target_path: 目标路径（目录或文件）
        output_path: JSON 索引输出路径
        verbose: 是否打印进度
        archive_dir: 图片归档目录（默认 target_path 父目录下的 images/archive/）
    
    Returns:
        dict: 索引数据
    """
    target = Path(target_path)
    if not target.exists():
        raise FileNotFoundError(f"目标不存在: {target}")
    
    # 如果是文件，收集该文件
    # 如果是目录，扫描所有支持的文档
    files_to_process = []
    if target.is_file():
        ext = target.suffix.lower()
        if ext in ('.docx', '.pptx', '.pdf'):
            files_to_process.append(target)
    else:
        for ext in ('.docx', '.pptx', '.pdf'):
            files_to_process.extend(sorted(target.rglob(f'*{ext}')))
    
    # 过滤临时文件
    files_to_process = [f for f in files_to_process if not f.name.startswith('~$')]
    
    if not files_to_process:
        if verbose:
            print(f"  未找到支持的文档文件")
        return _empty_index(str(target))
    
    # 确定归档目录
    if archive_dir is None:
        if target.is_file():
            archive_dir = target.parent / 'images' / 'archive'
        else:
            archive_dir = target / 'images' / 'archive'
    archive_dir = Path(archive_dir)
    
    # 输出路径默认值
    if output_path is None:
        if target.is_file():
            output_path = target.parent / 'images' / 'image_extract_index.json'
        else:
            output_path = target / 'images' / 'image_extract_index.json'
    output_path = Path(output_path)
    
    all_images = []
    file_stats = {}  # source_file → {count, total_bytes}
    
    for filepath in files_to_process:
        try:
            images = extract_images(str(filepath))
            all_images.extend(images)
            
            total_bytes = sum(img.size_bytes for img in images)
            file_stats[str(filepath)] = {
                "image_count": len(images),
                "total_bytes": total_bytes,
            }
            
            # 保存图片到归档目录（按 content_hash 去重）
            seen_hashes_in_file = set()
            for img in images:
                archive_path = archive_dir / img.archive_name
                if img.content_hash not in seen_hashes_in_file:
                    seen_hashes_in_file.add(img.content_hash)
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    archive_path.write_bytes(img.data)
                else:
                    # 确保重复图片的归档文件也存在
                    if not archive_path.exists():
                        archive_path.parent.mkdir(parents=True, exist_ok=True)
                        archive_path.write_bytes(img.data)

            if verbose:
                print(f"  [{len(images)} img / {_format_bytes(total_bytes)}] {filepath.name}")

        except Exception as e:
            if verbose:
                print(f"  [ERR] {filepath.name}: {e}")

    # 建立索引数据 — 按 content_hash 去重，保留归档路径最短的条目
    images_dict = {}
    hash_to_key = {}  # content_hash → key (已选择的)
    for img in all_images:
        key = Path(img.archive_name).stem
        h = img.content_hash
        if h not in hash_to_key:
            # 首次出现，直接加入
            entry = _build_image_entry(img)
            entry["archive_path"] = str(archive_dir / img.archive_name)
            images_dict[key] = entry
            hash_to_key[h] = key
        else:
            # 已存在相同哈希值，比较归档路径长度，保留较短的那个
            existing_key = hash_to_key[h]
            existing_entry = images_dict[existing_key]
            existing_path = existing_entry["archive_path"]
            new_path = str(archive_dir / img.archive_name)
            if len(new_path) < len(existing_path):
                # 新路径更短（通常表示来自更原始的源文件），替换
                entry = _build_image_entry(img)
                entry["archive_path"] = new_path
                # 保留已有的 key 但更新内容
                images_dict[existing_key] = entry
            # 如果新路径不更短，则忽略此次重复

    # 计算文件去重统计（基于 content_hash）
    all_hashes = [img.content_hash for img in all_images]
    unique_hashes = set(all_hashes)
    duplicate_count = len(all_images) - len(unique_hashes)
    
    index_data = {
        "index_type": "image_extract",
        "version": "1.0",
        "kb_root": str(target),
        "last_scan": datetime.now().isoformat(),
        "total_files": len(files_to_process),
        "total_images": len(images_dict),
        "total_duplicates_removed": duplicate_count,
        "archive_root": str(archive_dir),
        "files": file_stats,
        "images": images_dict,
    }
    
    # 保存 JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    if verbose:
        print(f"\n  索引已保存: {output_path}")
        print(f"  处理 {len(files_to_process)} 个文件, "
              f"提取 {len(images_dict)} 张唯一图片"
              f"{f' (+{duplicate_count} 重复已去重)' if duplicate_count else ''}")
        print(f"  归档目录: {archive_dir}")
    
    return index_data


def _empty_index(root):
    return {
        "index_type": "image_extract",
        "version": "1.0",
        "kb_root": root,
        "last_scan": datetime.now().isoformat(),
        "total_files": 0,
        "total_images": 0,
        "total_duplicates_removed": 0,
        "archive_root": "",
        "files": {},
        "images": {},
    }


def _format_bytes(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# ═══════════════════════════════════════════════════════
# 加载与合并索引
# ═══════════════════════════════════════════════════════

def load_index(index_path):
    """加载已保存的 JSON 索引"""
    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  python indexer.py scan <directory_or_file> [--output <json_path>]")
        print("  python indexer.py scan <directory_or_file> [--kb-mode]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "scan":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        if not target:
            print("请指定扫描目标")
            sys.exit(1)
        
        output = None
        if "--output" in sys.argv:
            idx = sys.argv.index("--output")
            if idx + 1 < len(sys.argv):
                output = sys.argv[idx + 1]
        
        scan_and_index(target, output)
    else:
        print(f"未知命令: {cmd}")
