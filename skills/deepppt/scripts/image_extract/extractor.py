#!/usr/bin/env python3
"""
image_extract 提取引擎 — 从 DOCX/PPTX/PDF 提取图片
====================================================
完全自包含，只依赖 Python 标准库（zipfile, hashlib, re）。
PDF 提取需要 PyMuPDF（fitz），但会优雅回退。

图片命名规则: {源文件名缩写}_{位置标记}_{内部名}
  例: 技术建议书_P01_image1.png, lightai-配图_S02_image1.tiff
"""

import hashlib
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ── PDF 提取尝试导入 ──
try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


@dataclass
class ExtractedImage:
    """提取的单张图片信息"""
    source_file: str           # 原始来源文件路径
    source_filename: str       # 原始文件名（不含路径）
    internal_name: str         # OOXML 内部名（如 image1.png）
    archive_name: str          # 归档后的文件名（含路径前缀）
    format: str                # 文件格式（自动检测）
    size_bytes: int            # 大小
    width: Optional[int] = None      # 宽度像素（如果有）
    height: Optional[int] = None     # 高度像素（如果有）
    content_hash: str = ""     # SHA256 哈希，用于去重
    slide_number: Optional[int] = None   # PPTX 页码
    paragraph_index: Optional[int] = None  # DOCX 段落索引
    context_text: str = ""     # 图片附近的上下文文本
    slide_title: str = ""      # PPTX 页标题
    extracted_at: str = ""     # 提取时间
    data: bytes = field(repr=False, default=b"")  # 二进制数据（不序列化）


# ═══════════════════════════════════════════════════════
# 路径辅助
# ═══════════════════════════════════════════════════════

def _safe_slug(name: str, max_len: int = 30) -> str:
    """将文件名转成简短安全的标签（不含路径后缀）"""
    # 去掉扩展名
    base = Path(name).stem
    # 只保留中文、字母、数字，下划线代替空格
    slug = re.sub(r'[^\u4e00-\u9fff\w]', '_', base)
    slug = re.sub(r'_+', '_', slug).strip('_')
    # 截断
    if len(slug) > max_len:
        slug = slug[:max_len]
    return slug if slug else "image"


def _compute_hash(data: bytes) -> str:
    """计算 SHA256 哈希"""
    return hashlib.sha256(data).hexdigest()


def _detect_format(data: bytes, internal_name: str) -> str:
    """根据魔数和扩展名检测格式"""
    # 优先用扩展名
    ext = Path(internal_name).suffix.lower().lstrip('.')
    if ext in ('png', 'jpg', 'jpeg', 'gif', 'bmp', 'tif', 'tiff', 'svg', 'wmf', 'emf', 'webp'):
        return ext
    # 魔数检测
    if data[:4] == b'\x89PNG':
        return 'png'
    if data[:2] in (b'\xff\xd8',):
        return 'jpg'
    if data[:4] in (b'GIF8',):
        return 'gif'
    if data[:2] == b'BM':
        return 'bmp'
    return 'bin'


# ═══════════════════════════════════════════════════════
# DOCX 提取
# ═══════════════════════════════════════════════════════

def _extract_docx_texts(z) -> dict:
    """从 DOCX 中提取所有段落的文本，返回 段落索引->文本 映射"""
    para_texts = {}
    try:
        xml = z.read('word/document.xml').decode('utf-8', errors='replace')
        # 提取所有段落及其文本
        paras = re.findall(r'<w:p[ >].*?</w:p>', xml, re.DOTALL)
        for i, para_xml in enumerate(paras):
            texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', para_xml)
            full_text = ''.join(t for t in texts if t.strip())
            if full_text.strip():
                para_texts[str(i)] = full_text.strip()
    except Exception:
        pass
    return para_texts


def _extract_from_docx(filepath: Path) -> List[ExtractedImage]:
    """从 DOCX 提取所有嵌入图片，并关联段落上下文"""
    results = []
    source_slug = _safe_slug(filepath.stem)
    
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            # 获取所有 media 文件
            media_names = sorted(
                [n for n in z.namelist() if n.startswith('word/media/') and not n.endswith('/')],
                key=lambda x: x.lower()
            )
            
            # 获取所有段落文本
            para_texts = _extract_docx_texts(z)
            
            # 解析 document.xml 建立 blip embed_id -> media 文件映射
            doc_xml = ""
            try:
                doc_xml = z.read('word/document.xml').decode('utf-8', errors='replace')
            except Exception:
                pass
            
            # 建立 media 文件所在段落索引的映射
            # 方法：扫描 document.xml 中的段落，找到 <w:drawing> 或 <wp:inline>/<wp:anchor> 中的图片引用
            paras_with_images = {}  # media_internal_name -> paragraph_text
            para_to_media = {}      # para_index -> list of media names
            
            paras = re.findall(r'<w:p[ >].*?</w:p>', doc_xml, re.DOTALL)
            for para_idx, para_xml in enumerate(paras):
                # 检查该段落是否包含图片（<w:drawing>）
                if '<w:drawing' not in para_xml:
                    continue
                # 提取该段落的所有文本
                para_texts_in = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', para_xml)
                para_full_text = ''.join(t for t in para_texts_in if t.strip())
                
                # 从段落中提取 <a:blip r:embed="..."> 
                blip_embeds = re.findall(r'<a:blip[^>]*r:embed="([^"]+)"', para_xml)
                if not blip_embeds:
                    continue
                
                # 读取 word/_rels/document.xml.rels 解析 embed_id -> Target
                try:
                    rels_xml = z.read('word/_rels/document.xml.rels').decode('utf-8', errors='replace')
                except Exception:
                    continue
                
                for embed_id in blip_embeds:
                    rel_match = re.search(
                        rf'Id="{re.escape(embed_id)}"[^>]*Target="([^"]+)"',
                        rels_xml
                    )
                    if rel_match:
                        target = rel_match.group(1)
                        media_name = Path(target).name
                        if media_name not in para_to_media:
                            para_to_media[media_name] = []
                        para_to_media.setdefault(media_name, []).append({
                            'para_index': para_idx,
                            'context': para_full_text,
                        })
            
            # 再尝试读取 image_manifest.json (旧版兼容)
            para_contexts = {}
            try:
                manifest_str = z.read('word/media/image_manifest.json').decode('utf-8')
                import json
                manifest = json.loads(manifest_str)
                for item in manifest:
                    if 'filename' in item and 'paragraph_index' in item:
                        para_contexts[item['filename']] = item
            except Exception:
                pass
            
            for idx, media_name in enumerate(media_names):
                try:
                    data = z.read(media_name)
                except Exception:
                    continue
                
                internal_name = Path(media_name).name
                img_format = _detect_format(data, internal_name)
                content_hash = _compute_hash(data)
                
                # 获取上下文 — 优先从 document.xml 解析的结果获取
                para_idx = None
                context = ""
                para_infos = para_to_media.get(internal_name, [])
                if para_infos:
                    info = para_infos[0]
                    para_idx = info['para_index']
                    context = info['context']
                
                # 如果 document.xml 解析没有结果，回退到 manifest
                if not context and internal_name in para_contexts:
                    info = para_contexts[internal_name]
                    para_idx = info.get('paragraph_index')
                    context = info.get('paragraph_context', '')
                
                # 如果还是没有上下文，尝试用序号查找附近段落
                if not context:
                    # 启发式：从 para_texts 中找
                    if para_idx is not None and str(para_idx) in para_texts:
                        context = para_texts[str(para_idx)]
                    else:
                        # 尝试从所有段落中找——简单取前后3个段落
                        all_para_indices = sorted(
                            [int(k) for k in para_texts.keys()],
                            key=lambda x: abs(x - (para_idx or idx * 10))
                        )
                        context = ' | '.join(
                            para_texts.get(str(pi), '')
                            for pi in all_para_indices[:3]
                            if pi >= (para_idx or idx * 10) - 1 and pi <= (para_idx or idx * 10) + 3
                        )
                
                # 计算归档名
                loc_tag = f"P{idx+1:02d}"
                if para_idx is not None:
                    loc_tag = f"P{para_idx:02d}"
                archive_name = f"{source_slug}_{loc_tag}_{internal_name}"
                
                img = ExtractedImage(
                    source_file=str(filepath),
                    source_filename=filepath.name,
                    internal_name=internal_name,
                    archive_name=archive_name,
                    format=img_format,
                    size_bytes=len(data),
                    content_hash=content_hash,
                    paragraph_index=para_idx,
                    context_text=context,
                    extracted_at=datetime.now().isoformat(),
                    data=data,
                )
                results.append(img)
    
    except Exception as e:
        print(f"  [ERR] DOCX 提取失败 {filepath.name}: {e}")
    
    return results


# ═══════════════════════════════════════════════════════
# PPTX 提取
# ═══════════════════════════════════════════════════════

def _extract_pptx_slide_texts(z):
    """从 PPTX 中提取每页的文本内容"""
    slide_texts = {}
    try:
        slide_names = sorted(
            [n for n in z.namelist() if re.match(r'ppt/slides/slide\d+\.xml$', n)],
            key=lambda x: int(re.search(r'slide(\d+)', x).group(1))
        )
        for sn in slide_names:
            snum = str(int(re.search(r'slide(\d+)', sn).group(1)))
            xml = z.read(sn).decode('utf-8', errors='replace')
            texts = re.findall(r'<a:t[^>]*>([^<]*)</a:t>', xml)
            full_text = ' '.join(t for t in texts if t.strip())
            slide_texts[snum] = full_text
    except Exception:
        pass
    return slide_texts


def _extract_from_pptx(filepath: Path) -> List[ExtractedImage]:
    """从 PPTX 提取所有嵌入图片"""
    results = []
    source_slug = _safe_slug(filepath.stem)
    
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            # 获取每页文本
            slide_texts = _extract_pptx_slide_texts(z)
            
            # 获取媒体文件
            media_names = sorted(
                [n for n in z.namelist() if n.startswith('ppt/media/') and not n.endswith('/')],
                key=lambda x: x.lower()
            )
            
            # 建立 image 到 slide 的映射：从 slide XML 中查找 <p:blipFill> 或 <a:blip> 的 r:embed
            # 参考 OOXML 结构：slide.xml 中 <a:blip r:embed="rIdX"> → 通过 slide.xml.rels 找到 media 文件
            slide_image_map = {}  # internal_name → slide_number
            slide_image_context = {}  # internal_name → context_text
            
            slide_names = sorted(
                [n for n in z.namelist() if re.match(r'ppt/slides/slide\d+\.xml$', n)],
                key=lambda x: int(re.search(r'slide(\d+)', x).group(1))
            )
            
            for sn in slide_names:
                snum = int(re.search(r'slide(\d+)', sn).group(1))
                xml = z.read(sn).decode('utf-8', errors='replace')
                
                # 提取所有 <a:blip r:embed="..."> 的 embed id
                blip_embeds = re.findall(r'<a:blip[^>]*r:embed="([^"]+)"', xml)
                if not blip_embeds:
                    continue
                
                # 读取该 slide 的 rels 文件
                rels_name = f'ppt/slides/_rels/{Path(sn).name}.rels'
                try:
                    rels_xml = z.read(rels_name).decode('utf-8', errors='replace')
                except Exception:
                    continue
                
                for embed_id in blip_embeds:
                    # 在 rels 中查找 Target
                    rel_match = re.search(
                        rf'Id="{re.escape(embed_id)}"[^>]*Target="([^"]+)"',
                        rels_xml
                    )
                    if rel_match:
                        target = rel_match.group(1)
                        # Target 可能是相对路径如 "../media/image1.png"
                        media_name = Path(target).name
                        slide_image_map[media_name] = snum
                        
                        # 上下文文本
                        context = slide_texts.get(str(snum), '')
                        slide_image_context[media_name] = context
            
            for media_name in media_names:
                try:
                    data = z.read(media_name)
                except Exception:
                    continue
                
                internal_name = Path(media_name).name
                img_format = _detect_format(data, internal_name)
                content_hash = _compute_hash(data)
                
                slide_num = slide_image_map.get(internal_name)
                context = slide_image_context.get(internal_name, '')
                slide_text = slide_texts.get(str(slide_num), '') if slide_num else ''
                
                loc_tag = f"S{slide_num:02d}" if slide_num else f"M{len(results)+1:02d}"
                archive_name = f"{source_slug}_{loc_tag}_{internal_name}"
                
                img = ExtractedImage(
                    source_file=str(filepath),
                    source_filename=filepath.name,
                    internal_name=internal_name,
                    archive_name=archive_name,
                    format=img_format,
                    size_bytes=len(data),
                    content_hash=content_hash,
                    slide_number=slide_num,
                    slide_title=slide_text[:100] if slide_text else '',
                    context_text=context,
                    extracted_at=datetime.now().isoformat(),
                    data=data,
                )
                results.append(img)
    
    except Exception as e:
        print(f"  [ERR] PPTX 提取失败 {filepath.name}: {e}")
    
    return results


# ═══════════════════════════════════════════════════════
# PDF 提取
# ═══════════════════════════════════════════════════════

def _extract_from_pdf(filepath: Path) -> List[ExtractedImage]:
    """从 PDF 提取图片（使用 PyMuPDF）"""
    results = []
    source_slug = _safe_slug(filepath.stem)
    
    if not HAS_FITZ:
        print(f"  [WARN] PyMuPDF 未安装，跳过 PDF: {filepath.name}")
        print(f"         安装: pip install PyMuPDF")
        return results
    
    try:
        doc = fitz.open(str(filepath))
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # 获取页面文本作为上下文
            page_text = page.get_text("text")[:500]
            
            # 提取图片
            image_list = page.get_images(full=True)
            
            for img_idx, img_info in enumerate(image_list):
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                data = base_image["image"]
                ext = base_image["ext"]  # png, jpeg, etc.
                width = base_image.get("width")
                height = base_image.get("height")
                
                img_format = ext if ext in ('png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff') else 'png'
                content_hash = _compute_hash(data)
                internal_name = f"pdf_page{page_num+1}_img{img_idx+1}.{img_format}"
                loc_tag = f"P{page_num+1:02d}"
                archive_name = f"{source_slug}_{loc_tag}_{internal_name}"
                
                img = ExtractedImage(
                    source_file=str(filepath),
                    source_filename=filepath.name,
                    internal_name=internal_name,
                    archive_name=archive_name,
                    format=img_format,
                    size_bytes=len(data),
                    width=width,
                    height=height,
                    content_hash=content_hash,
                    slide_number=page_num + 1,
                    context_text=page_text,
                    extracted_at=datetime.now().isoformat(),
                    data=data,
                )
                results.append(img)
        
        doc.close()
    
    except Exception as e:
        print(f"  [ERR] PDF 提取失败 {filepath.name}: {e}")
    
    return results


# ═══════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════

SUPPORTED_EXTENSIONS = {
    '.docx': _extract_from_docx,
    '.pptx': _extract_from_pptx,
    '.pdf': _extract_from_pdf,
}


def extract_images(filepath: str) -> List[ExtractedImage]:
    """
    从文件提取所有嵌入图片（自动检测格式）。
    
    Args:
        filepath: 文件路径（DOCX/PPTX/PDF）
    
    Returns:
        List[ExtractedImage]: 提取的图片列表
    
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不支持的文件格式
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")
    
    ext = path.suffix.lower()
    extractor = SUPPORTED_EXTENSIONS.get(ext)
    if extractor is None:
        raise ValueError(f"不支持的文件格式: {ext}（支持: {', '.join(SUPPORTED_EXTENSIONS.keys())}）")
    
    images = extractor(path)
    
    # 去重：相同 content_hash 只保留第一个
    seen_hashes = set()
    unique_images = []
    for img in images:
        if img.content_hash not in seen_hashes:
            seen_hashes.add(img.content_hash)
            unique_images.append(img)
        else:
            # 标记为重复
            img.content_hash = img.content_hash  # 保留信息但不会加入 unique
    
    return unique_images


# ═══════════════════════════════════════════════════════
# CLI 测试
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python extractor.py <file_path>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    images = extract_images(filepath)
    print(f"\n  提取 {len(images)} 张图片从 {Path(filepath).name}:")
    for img in images:
        dup = ""
        print(f"    {img.archive_name} ({img.format}, {img.size_bytes} bytes) "
              f"hash={img.content_hash[:12]}...")
        if img.slide_number:
            print(f"      → 页码 {img.slide_number}")
        if img.context_text:
            print(f"      → 上下文: {img.context_text[:80]}...")
