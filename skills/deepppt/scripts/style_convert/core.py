#!/usr/bin/env python3
"""
PPTX 风格转换引擎 v1.0
====================

从 huawei-deepppt/_style_convert.py 解耦而来。
支持：PPTX 文本提取 → AI翻译 → 回写应用 / 白底↔黑底转换。

零外部依赖：zipfile, xml.etree, re, os (Python 标准库)

Usage:
    from style_convert.core import extract_texts, apply_translations, convert_bg

    # 1. 提取所有中文文本
    entries = extract_texts("input.pptx")

    # 2. 交给 AI 翻译 → {中文: English} 字典

    # 3. 回写 + 自动缩字体
    apply_translations("input.pptx", "output.pptx", translation_map)

    # 背景色转换
    convert_bg("input.pptx", "output.pptx", "white_to_black")
"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET

# ── OOXML namespace constants ──
NS_P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
NS_A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'

# ── Color map: white bg → black bg ──
WHITE_TO_BLACK = {
    '1D1D1A': 'FFFFFF', '282828': 'EEEEEE', '333333': 'CCCCCC',
    '666666': 'BBBBBB', '999999': 'DDDDDD', 'DDDDDD': 'FFFFFF',
    '000000': 'FFFFFF', 'C00000': 'FFC000', 'C7000B': 'FF9966',
}
BLACK_TO_WHITE = {v: k for k, v in WHITE_TO_BLACK.items() if len(k) == 6}


# ══════════════════════════════════════════════════════════════
# Text extraction
# ══════════════════════════════════════════════════════════════

def extract_texts(input_path: str, source_lang: str = 'zh') -> list:
    """Extract all text elements from PPTX slides.

    Args:
        input_path: Path to .pptx file
        source_lang: Source language hint ('zh' = extract Chinese, 'any' = all)

    Returns:
        List of (slide_name, element_path, text) tuples
    """
    entries = []
    with zipfile.ZipFile(input_path, 'r') as zin:
        for name in zin.namelist():
            if not re.match(r'ppt/slides/slide\d+\.xml$', name):
                continue
            root = ET.fromstring(zin.read(name))
            t_elems = root.findall(f'.//{NS_A}t')
            for i, t_elem in enumerate(t_elems):
                text = t_elem.text
                if not text or not text.strip():
                    continue
                if source_lang == 'zh':
                    if not any('\u4e00' <= c <= '\u9fff' for c in text):
                        continue
                entries.append((name, f't[{i}]', text.strip()))
    return entries


def extract_unique_texts(input_path: str, source_lang: str = 'zh') -> list[str]:
    """Extract unique text strings (deduplicated)."""
    entries = extract_texts(input_path, source_lang)
    seen = set()
    unique = []
    for _, _, text in entries:
        if text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


# ══════════════════════════════════════════════════════════════
# Translation application
# ══════════════════════════════════════════════════════════════

def _auto_fit_text(root: ET.Element, slide_name: str):
    """Auto-shrink font sizes to prevent English text overflow.

    After translation, English text tends to be longer. This shrinks
    font sizes proportionally to keep text within bounds.
    """
    for t_elem in root.findall(f'.//{NS_A}t'):
        text = (t_elem.text or '').strip()
        if not text or any('\u4e00' <= c <= '\u9fff' for c in text):
            continue

        # Find parent paragraph's default run properties
        para = t_elem
        for _ in range(4):
            para = para.getparent() if hasattr(para, 'getparent') else None
            if para is None or para.tag == f'{NS_A}p':
                break

        # Apply font size shrink based on text length
        l = len(text)
        if l > 80:
            shrink = -6
        elif l > 50:
            shrink = -4
        elif l > 30:
            shrink = -2
        elif l > 15:
            shrink = -1
        else:
            continue

        # Find rPr and adjust sz attribute
        rPr = t_elem.find(f'..//{NS_A}rPr')
        if rPr is None:
            parent_run = t_elem
            for _ in range(3):
                parent_run = parent_run.getparent() if hasattr(parent_run, 'getparent') else None
                if parent_run is None:
                    break
                rPr = parent_run.find(f'{NS_A}rPr')
                if rPr is not None:
                    break

        if rPr is not None:
            sz_attr = rPr.get('sz')
            if sz_attr:
                try:
                    old_sz = int(sz_attr) / 100  # EMU → pt
                    new_sz = max(8, old_sz + shrink)
                    rPr.set('sz', str(int(new_sz * 100)))
                except (ValueError, TypeError):
                    pass

        # Also check font family — switch to Arial for English
        if rPr is not None:
            latin = rPr.find(f'{NS_A}latin')
            if latin is not None:
                latin.set('typeface', 'Arial')


def apply_translations(input_path: str, output_path: str,
                       translation_map: dict[str, str]) -> dict:
    """Replace Chinese text with English translations and apply font adjustments.

    Args:
        input_path: Source .pptx path
        output_path: Output .pptx path
        translation_map: {Chinese_text: English_text} dictionary

    Returns:
        {'applied': N, 'unmapped': [...]}
    """
    if os.path.exists(output_path):
        os.remove(output_path)

    unmapped = []
    applied = 0

    with zipfile.ZipFile(input_path, 'r') as zin:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if re.match(r'ppt/slides/slide\d+\.xml$', name):
                    root = ET.fromstring(data)
                    for t_elem in root.findall(f'.//{NS_A}t'):
                        text = t_elem.text
                        if not text or not text.strip():
                            continue
                        stripped = text.strip()
                        # Try exact match first, then stripped
                        if stripped in translation_map:
                            t_elem.text = translation_map[stripped]
                            applied += 1
                        elif text in translation_map:
                            t_elem.text = translation_map[text]
                            applied += 1
                        elif any('\u4e00' <= c <= '\u9fff' for c in text):
                            unmapped.append(text[:60])

                    _auto_fit_text(root, name)
                    xml_str = ET.tostring(root, encoding='UTF-8').decode('utf-8')
                    zout.writestr(name, xml_str.encode('utf-8'))
                else:
                    zout.writestr(name, data)

    return {'applied': applied, 'unmapped': unmapped}


# ══════════════════════════════════════════════════════════════
# Background color conversion
# ══════════════════════════════════════════════════════════════

def _find_slide_layouts(zipin):
    """Find all slideLayout paths referenced by slides."""
    layouts = set()
    for name in zipin.namelist():
        if re.match(r'ppt/slides/slide\d+\.xml\.rels$', name):
            try:
                rels = zipin.read(name).decode('utf-8')
                matches = re.findall(r'Target="([^"]*slideLayout\d+\.xml)"', rels)
                for m in matches:
                    layout_path = 'ppt/slideLayouts/' + m.split('/')[-1]
                    layouts.add(layout_path)
            except Exception:
                pass
    return layouts or {'ppt/slideLayouts/slideLayout1.xml'}


def _build_bg_element(bg_hex):
    """Build a standard <p:bg> XML element with solid fill."""
    bg = ET.Element(f'{NS_P}bg')
    bgPr = ET.SubElement(bg, f'{NS_P}bgPr')
    solid = ET.SubElement(bgPr, f'{NS_A}solidFill')
    srgb = ET.SubElement(solid, f'{NS_A}srgbClr')
    srgb.set('val', bg_hex)
    ET.SubElement(bgPr, f'{NS_A}effectLst')
    return bg


def _set_csld_bg(root, bg_hex):
    """Insert/replace <p:bg> in a <p:cSld> element. Returns True if changed."""
    cSld = root.find(f'.//{NS_P}cSld')
    if cSld is None:
        return False
    # Remove old backgrounds
    for old_bg in cSld.findall(f'{NS_P}bg'):
        cSld.remove(old_bg)
    # Check if old bg already matches — skip if yes
    bg = _build_bg_element(bg_hex)
    children = list(cSld)
    spTree_idx = next((i for i, c in enumerate(children) if c.tag == f'{NS_P}spTree'), len(children))
    cSld.insert(spTree_idx, bg)
    return True


def _set_layout_bg(zipin, layout_path, bg_hex):
    """Insert/replace <p:bg> node in a slideLayout XML."""
    try:
        xml_bytes = zipin.read(layout_path)
    except Exception:
        return None
    root = ET.fromstring(xml_bytes)
    if _set_csld_bg(root, bg_hex):
        return (layout_path, ET.tostring(root, encoding='UTF-8'))
    return None


def _set_slide_bg(xml_bytes, bg_hex):
    """Insert/replace <p:bg> node in a slide XML (slideN.xml)."""
    root = ET.fromstring(xml_bytes)
    _set_csld_bg(root, bg_hex)
    return ET.tostring(root, encoding='UTF-8')


def _set_master_bg(zipin, master_path, bg_hex):
    """Insert/replace <p:bg> node in a slideMaster XML."""
    try:
        xml_bytes = zipin.read(master_path)
    except Exception:
        return None
    root = ET.fromstring(xml_bytes)
    if _set_csld_bg(root, bg_hex):
        return (master_path, ET.tostring(root, encoding='UTF-8'))
    return None


def _convert_run_color(run_elem, mapping):
    """Convert a single run element's text color."""
    rPr = run_elem.find(f'{NS_A}rPr')
    if rPr is None:
        return
    solidFill = rPr.find(f'{NS_A}solidFill')
    if solidFill is None:
        sf = ET.SubElement(rPr, f'{NS_A}solidFill')
        srgb = ET.SubElement(sf, f'{NS_A}srgbClr')
        srgb.set('val', list(mapping.values())[0])
        return
    srgb = solidFill.find(f'{NS_A}srgbClr')
    if srgb is None:
        return
    old_val = srgb.get('val', '').upper()
    new_val = mapping.get(old_val)
    if new_val:
        srgb.set('val', new_val)


def convert_bg(input_path: str, output_path: str, direction: str = 'white_to_black'):
    """Convert PPTX background between white and black.

    Modifies background at THREE levels to ensure all slides are affected:
      1. Individual slide XMLs (ppt/slides/slideN.xml) — direct override
      2. Slide layout XMLs (ppt/slideLayouts/slideLayoutN.xml) — template level
      3. Slide master XMLs (ppt/slideMasters/slideMasterN.xml) — master level

    Args:
        input_path: Source .pptx
        output_path: Output .pptx
        direction: 'white_to_black' or 'black_to_white'
    """
    mapping = WHITE_TO_BLACK if direction == 'white_to_black' else BLACK_TO_WHITE
    bg_hex = '000000' if direction == 'white_to_black' else 'FFFFFF'

    if os.path.exists(output_path):
        os.remove(output_path)

    with zipfile.ZipFile(input_path, 'r') as zin:
        # ── Phase 1: Pre-process all layouts and masters ──
        modified_layouts = {}
        for lp in [f for f in zin.namelist()
                   if re.match(r'ppt/slideLayouts/slideLayout\d+\.xml$', f)]:
            result = _set_layout_bg(zin, lp, bg_hex)
            if result:
                modified_layouts[result[0]] = result[1]

        modified_masters = {}
        for mp in [f for f in zin.namelist()
                   if re.match(r'ppt/slideMasters/slideMaster\d+\.xml$', f)]:
            result = _set_master_bg(zin, mp, bg_hex)
            if result:
                modified_masters[result[0]] = result[1]

        regex_map = {k.upper(): v for k, v in mapping.items()}
        modified_slides = 0

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name in zin.namelist():
                data = zin.read(name)

                # 1. Modified layouts
                if name in modified_layouts:
                    zout.writestr(name, modified_layouts[name])
                    continue

                # 2. Modified masters
                if name in modified_masters:
                    zout.writestr(name, modified_masters[name])
                    continue

                # 3. Individual slide XMLs — KEY FIX: set bg directly
                if re.match(r'ppt/slides/slide\d+\.xml$', name):
                    xml_str = data.decode('utf-8')
                    # 3a. Text color conversion
                    for old_c, new_c in regex_map.items():
                        xml_str = re.sub(
                            rf'val="{old_c}"', f'val="{new_c}"', xml_str,
                            flags=re.IGNORECASE
                        )
                    root = ET.fromstring(xml_str.encode('utf-8'))
                    for para in root.findall(f'.//{NS_A}p'):
                        for run in para.findall(f'.//{NS_A}r'):
                            _convert_run_color(run, mapping)

                    # 3b. Direct background override on each slide
                    new_xml = _set_slide_bg(ET.tostring(root, encoding='UTF-8'), bg_hex)
                    zout.writestr(name, new_xml)
                    modified_slides += 1
                else:
                    zout.writestr(name, data)

    print(f"[style_convert] Background conversion complete ({direction}): {output_path}")
    print(f"  - Modified {modified_slides} slides directly")
    print(f"  - Modified {len(modified_layouts)} slide layouts")
    print(f"  - Modified {len(modified_masters)} slide masters")


# ══════════════════════════════════════════════════════════════
# Verification gate
# ══════════════════════════════════════════════════════════════

def verify_pptx(input_path: str, expected_bg: str = None,
                lang: str = None) -> dict:
    """Per-page verification gate for PPTX output quality.

    Checks three dimensions per slide:
      1. Background color — has the expected <p:bg> with correct srgbClr val?
      2. Translation completeness — any remaining source-language characters?
      3. Text overflow risk — unusually long texts that may clip or overlap

    Args:
        input_path: PPTX file to verify
        expected_bg: Expected background hex color (e.g. '000000' for black)
        lang: Source language to check for (e.g. 'zh' = look for Chinese chars)
              If None, auto-detects from any CJK characters found.

    Returns:
        {
            'pass': True/False,
            'total_slides': N,
            'slides': [
                {
                    'name': 'ppt/slides/slide1.xml',
                    'slide_num': 1,
                    'bg': {'ok': True/False, 'value': '000000' or None,
                           'expected': '000000' or None},
                    'translation': {'ok': True/False,
                                    'remaining_chinese': 0,
                                    'samples': ['剩余中文示例', ...]},
                    'overflow_risk': {'ok': True/False,
                                      'long_texts': [{'text': '...', 'len': 120}, ...]},
                    'pass': True/False
                }, ...
            ],
            'summary': {'bg_ok': N, 'translation_ok': N, 'overflow_ok': N}
        }
    """
    if not os.path.exists(input_path):
        return {'error': f'File not found: {input_path}', 'pass': False}

    slides = []
    with zipfile.ZipFile(input_path, 'r') as zin:
        slide_names = sorted(
            [n for n in zin.namelist() if re.match(r'ppt/slides/slide\d+\.xml$', n)],
            key=lambda x: int(re.search(r'slide(\d+)', x).group(1))
        )

        for name in slide_names:
            slide_num = int(re.search(r'slide(\d+)', name).group(1))
            xml_str = zin.read(name).decode('utf-8', errors='replace')
            root = ET.fromstring(xml_str.encode('utf-8'))

            # ── Check 1: Background color ──
            bg_info = _verify_slide_bg(root, expected_bg)

            # ── Check 2: Translation completeness ──
            translation_info = _verify_slide_translation(root, lang)

            # ── Check 3: Text overflow risk ──
            overflow_info = _verify_slide_overflow(root)

            # ── Overall page pass ──
            page_pass = (bg_info['ok'] and translation_info['ok']
                         and overflow_info['ok'])

            slides.append({
                'name': name,
                'slide_num': slide_num,
                'bg': bg_info,
                'translation': translation_info,
                'overflow_risk': overflow_info,
                'pass': page_pass,
            })

    # ── Summary ──
    bg_ok = sum(1 for s in slides if s['bg']['ok'])
    trans_ok = sum(1 for s in slides if s['translation']['ok'])
    overflow_ok = sum(1 for s in slides if s['overflow_risk']['ok'])
    all_pass = all(s['pass'] for s in slides)

    return {
        'pass': all_pass,
        'total_slides': len(slides),
        'slides': slides,
        'summary': {
            'bg_ok': bg_ok,
            'bg_total': len(slides),
            'translation_ok': trans_ok,
            'translation_total': len(slides),
            'overflow_ok': overflow_ok,
            'overflow_total': len(slides),
        }
    }


def _verify_slide_bg(root, expected_bg):
    """Check if slide has the expected background color."""
    cSld = root.find(f'.//{NS_P}cSld')
    if cSld is None:
        return {'ok': False, 'value': None, 'expected': expected_bg,
                'error': 'No cSld element found'}

    bg = cSld.find(f'{NS_P}bg')
    if bg is None:
        return {'ok': False, 'value': None, 'expected': expected_bg,
                'error': 'No <p:bg> element — background not set'}

    # Extract the actual color from p:bg → p:bgPr → a:solidFill → a:srgbClr
    bgPr = bg.find(f'{NS_P}bgPr')
    if bgPr is None:
        return {'ok': False, 'value': None, 'expected': expected_bg,
                'error': 'No bgPr in bg element'}

    srgb = bgPr.find(f'.//{NS_A}srgbClr')
    if srgb is None:
        return {'ok': False, 'value': None, 'expected': expected_bg,
                'error': 'No srgbClr — may use non-solid fill'}

    actual_val = srgb.get('val', '').upper()
    if expected_bg:
        ok = actual_val == expected_bg.upper()
        return {'ok': ok, 'value': actual_val, 'expected': expected_bg.upper(),
                'error': None if ok else f'Expected {expected_bg}, got {actual_val}'}
    else:
        return {'ok': True, 'value': actual_val, 'expected': None, 'error': None}


def _verify_slide_translation(root, lang):
    """Check slide for remaining source-language characters."""
    samples = []
    remaining = 0
    for t_elem in root.findall(f'.//{NS_A}t'):
        text = (t_elem.text or '').strip()
        if not text:
            continue
        # Default: detect Chinese characters
        if lang is None or lang == 'zh':
            if any('\u4e00' <= c <= '\u9fff' for c in text):
                remaining += 1
                if len(samples) < 5:
                    samples.append(text[:80])
        elif lang == 'ja':
            if any(('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff')
                   for c in text):
                remaining += 1
                if len(samples) < 5:
                    samples.append(text[:80])

    ok = remaining == 0
    return {'ok': ok, 'remaining_chinese': remaining,
            'samples': samples if remaining > 0 else []}


def _verify_slide_overflow(root, threshold=100):
    """Check for unusually long texts that risk overflow/occlusion."""
    long_texts = []
    for t_elem in root.findall(f'.//{NS_A}t'):
        text = (t_elem.text or '').strip()
        if len(text) > threshold:
            long_texts.append({'text': text[:80] + ('...' if len(text) > 80 else ''),
                               'len': len(text)})

    ok = len(long_texts) == 0
    return {'ok': ok, 'long_texts': long_texts} if not ok else {'ok': True, 'long_texts': []}


# ══════════════════════════════════════════════════════════════
# Batch converter
# ══════════════════════════════════════════════════════════════

def batch_convert(input_path: str, output_dir: str,
                  styles: tuple = ('black', 'english'),
                  translation_map: dict | None = None):
    """Batch convert: black bg + English translation in one call."""
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.basename(input_path).replace('.pptx', '')

    results = {}
    if 'black' in styles:
        out = os.path.join(output_dir, f'{base}_black.pptx')
        convert_bg(input_path, out, 'white_to_black')
        results['black'] = out

    if 'english' in styles and translation_map:
        out = os.path.join(output_dir, f'{base}_english.pptx')
        result = apply_translations(input_path, out, translation_map)
        results['english'] = out
        results['translation_stats'] = result

    return results
