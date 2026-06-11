#!/usr/bin/env python3
"""
PPT Recall Indexer — 扫描 knowledge_base，建立 slide 级文本索引 JSON
==================================================================
输出 kb_index.json，后续搜索直接从 JSON 匹配，不再重复读取 PPTX。

数据结构：
{
  "kb_root": "/path/to/knowledge_base",
  "last_scan": "2026-06-05T16:52:00",
  "total_pptx": 4,
  "total_slides": 31,
  "files": {
    "relative/path/name.pptx": {
      "title": "页面标题或文件名",
      "slide_count": 10,
      "path_abs": "/abs/path/name.pptx",
      "slides": {
        "1": "第1页提取的所有文本...",
        "2": "第2页提取的所有文本...",
      },
      "slide_keywords": {
        "1": ["keyword1", "keyword2"],
        "2": ["keyword3"],
      }
    }
  }
}
"""

import json, os, re, zipfile, hashlib
from pathlib import Path
from datetime import datetime


def scan_and_index(kb_root, output_path=None, verbose=True):
    """
    扫描 knowledge_base 下的所有 PPTX，建立 slide 级文本索引。
    
    Args:
        kb_root: knowledge_base 目录路径
        output_path: JSON 索引输出路径（默认 kb_root/../kb_index.json）
        verbose: 是否打印进度
    
    Returns:
        dict: 索引数据
    """
    kb_root = Path(kb_root)
    if not kb_root.exists():
        raise FileNotFoundError(f"KB root not found: {kb_root}")
    
    if output_path is None:
        output_path = kb_root / "kb_index.json"  # 统一放在 knowledge_base/ 下
    output_path = Path(output_path)
    
    files_index = {}
    total_slides = 0
    
    for pptx_path in sorted(kb_root.rglob("*.pptx")):
        if pptx_path.name.startswith("~$"):
            continue
        
        rel_path = str(pptx_path.relative_to(kb_root))
        
        slides = {}
        slide_kw = {}
        slide_count = 0
        
        try:
            with zipfile.ZipFile(pptx_path, 'r') as z:
                slide_names = sorted(
                    [n for n in z.namelist() 
                     if re.match(r'ppt/slides/slide\d+\.xml$', n)],
                    key=lambda x: int(re.search(r'slide(\d+)', x).group(1))
                )
                slide_count = len(slide_names)
                
                for sn in slide_names:
                    snum = str(int(re.search(r'slide(\d+)', sn).group(1)))
                    xml = z.read(sn).decode('utf-8', errors='replace')
                    
                    # 提取所有 <a:t> 标签内的文本
                    texts = re.findall(r'<a:t[^>]*>([^<]*)</a:t>', xml)
                    full_text = ' '.join(t for t in texts if t.strip())
                    
                    # 提取有意义的关键词（长度 2-30 的中文/英文词）
                    keywords = []
                    for t in texts:
                        t = t.strip()
                        if 2 <= len(t) <= 30 and not re.match(r'^[\d\s\.\-,;:：；，。、]+$', t):
                            keywords.append(t)
                    
                    slides[snum] = full_text
                    slide_kw[snum] = keywords
            
            total_slides += slide_count
            
            files_index[rel_path] = {
                "title": pptx_path.stem,
                "slide_count": slide_count,
                "path_abs": str(pptx_path),
                "slides": slides,
                "slide_keywords": slide_kw,
            }
            
            if verbose:
                print(f"  [{slide_count}p] {rel_path}")
                
        except Exception as e:
            if verbose:
                print(f"  [ERR] {rel_path}: {e}")
    
    index_data = {
        "kb_root": str(kb_root),
        "last_scan": datetime.now().isoformat(),
        "total_pptx": len(files_index),
        "total_slides": total_slides,
        "files": files_index,
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    if verbose:
        print(f"\n  索引已保存: {output_path}")
        print(f"  {len(files_index)} 个 PPTX, {total_slides} 页")
    
    return index_data


def load_index(index_path):
    """加载已保存的 JSON 索引"""
    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# CLI
if __name__ == "__main__":
    import sys
    kb = sys.argv[1] if len(sys.argv) > 1 else None
    out = sys.argv[2] if len(sys.argv) > 2 else None
    
    if kb:
        scan_and_index(kb, out)
    else:
        print("Usage: python indexer.py <knowledge_base_path> [index_output_path]")
