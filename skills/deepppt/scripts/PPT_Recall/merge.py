#!/usr/bin/env python3
"""
PPT Recall Slide Merge — COM优先，ZIP兜底（纯标准库，完全自包含）
================================================================
签名：merge_slides(entries, output_path)
  entries: [(pptx_path, slide_num), ...]
  - COM 模式：新建空白白底 PPT → 逐页 Copy+PasteSourceFormatting → 删除默认空白页
  - ZIP 兜底：从源 PPTX 提取指定页 slide + 依赖，合并到新 PPTX

完全独立，不依赖 _zip_utils、kb_search、lxml 等任何外部项目模块。
"""

import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


# ═══════════════════════════════════════════════════════
# 命名空间常量
# ═══════════════════════════════════════════════════════

NS_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
NS_CT = 'http://schemas.openxmlformats.org/package/2006/content-types'

# 注册常用命名空间前缀，确保序列化时格式友好
_ET_NS_MAP = {
    'p': NS_P,
    'r': NS_R,
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
}
for _prefix, _uri in _ET_NS_MAP.items():
    ET.register_namespace(_prefix, _uri)


# ═══════════════════════════════════════════════════════
# COM 模式
# ═══════════════════════════════════════════════════════

def _com_merge(entries, output_path):
    """
    PowerPoint COM 合并：新建空白白底 PPT → 逐页 Copy + PasteSourceFormatting。
    PasteSourceFormatting 等效右键「保留源格式」，100%保持原设计。

    Args:
        entries: [(pptx_path, slide_num), ...]
        output_path: 输出 PPTX 绝对路径
    """
    import pythoncom
    import win32com.client as win32

    pythoncom.CoInitialize()
    ppt_app = None
    try:
        ppt_app = win32.Dispatch('PowerPoint.Application')
        ppt_app.Visible = True
        time.sleep(3)

        # 新建空白白底 PPT（默认有一页空白 slide）
        target = ppt_app.Presentations.Add()
        time.sleep(2)

        for pptx_path, slide_num in entries:
            abs_path = os.path.abspath(pptx_path)

            # 打开源 PPTX
            src = ppt_app.Presentations.Open(abs_path, WithWindow=False)
            time.sleep(3)

            # Copy 指定 slide
            try:
                src.Slides(slide_num).Copy()
            except Exception as copy_err:
                print(f"  [WARN] Copy slide {slide_num} 失败: {copy_err}")
                src.Close()
                continue
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
            try:
                ppt_app.CommandBars.ExecuteMso("PasteSourceFormatting")
            except Exception as paste_err:
                print(f"  [WARN] PasteSourceFormatting 失败: {paste_err}")
                # 尝试普通粘贴作为最后手段
                try:
                    target.Slides.Paste()
                except Exception:
                    print(f"  [ERROR] 粘贴也失败，跳过此页")
                    continue
            time.sleep(2)

        # 删除默认空白第一页（新建 PPT 总有一页空白，粘贴的都在后面）
        # 判断标准：如果页数 > entries 数量，说明有空白页残留
        if target.Slides.Count > len(entries):
            try:
                target.Slides(1).Delete()
                time.sleep(0.5)
            except Exception:
                pass

        # 保存
        abs_output = os.path.abspath(output_path)
        target.SaveAs(abs_output)
        target.Close()

        return output_path

    finally:
        try:
            if ppt_app:
                ppt_app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


# ═══════════════════════════════════════════════════════
# ZIP 模式（COM 不可用时的兜底方案）
# ═══════════════════════════════════════════════════════

def _zip_merge(entries, output_path):
    """
    ZIP 级合并：从源 PPTX 提取指定页 slide + 依赖，合并到一个新 PPTX。
    使用纯标准库 xml.etree.ElementTree，不依赖 lxml。

    策略：
      1. 提取所有源 PPTX 到临时目录
      2. 以第一个源为基础，只保留需要的 slide（重编号为 slide1）
      3. 逐个从其他源复制 slide + 依赖（layout/master/theme/media）
      4. 从零重建 presentation.xml、presentation.xml.rels、[Content_Types].xml
      5. 打包为 PPTX
    """
    work = Path(output_path).parent / f'.merge_zip_{os.getpid()}'
    _cleanup_dir(work)
    work.mkdir(parents=True)

    try:
        # ── Phase 1: 提取所有源 PPTX ──
        src_dirs = []
        for i, (pptx_path, _) in enumerate(entries):
            edir = work / f'src{i}'
            edir.mkdir()
            with zipfile.ZipFile(pptx_path, 'r') as z:
                z.extractall(str(edir))
            src_dirs.append(edir)

        # ── Phase 2: 构建基座（使用第一个源） ──
        base = work / 'base'
        shutil.copytree(str(src_dirs[0]), str(base))

        first_slide_num = entries[0][1]
        # 删除不需要的 slide
        _keep_only_slide(base, first_slide_num)
        # 重命名目标 slide 为 slide1
        _rename_slide(base, first_slide_num, 1)

        # ── Phase 3: 从其他源添加 slides ──
        slide_count = 1  # 基座已有 slide1
        for i in range(1, len(entries)):
            src_dir = src_dirs[i]
            _, slide_num = entries[i]
            slide_count += 1
            _add_slide_with_deps(src_dir, slide_num, base, slide_count)

        # ── Phase 4: 重建结构文件 ──
        _rebuild_pres_and_rels(base, slide_count)
        _rebuild_content_types(base)

        # ── Phase 5: 打包 ──
        return _package_pptx(base, output_path)

    finally:
        _cleanup_dir(work)


# ── ZIP 辅助函数 ──────────────────────────────────────

def _cleanup_dir(d):
    """安全删除目录"""
    d = Path(d)
    if d.exists():
        try:
            shutil.rmtree(str(d))
        except Exception:
            pass


def _scan_slides(base_dir):
    """扫描 base_dir 中所有 slide XML，返回排序后的 slide 编号列表"""
    slides_dir = base_dir / 'ppt' / 'slides'
    nums = []
    if slides_dir.exists():
        for f in slides_dir.iterdir():
            m = re.match(r'slide(\d+)\.xml$', f.name)
            if m:
                nums.append(int(m.group(1)))
    nums.sort()
    return nums


def _keep_only_slide(base_dir, keep_num):
    """
    从 base_dir 中删除所有不需要的 slide XML 及其 rels、notesSlides。
    只保留 slide{keep_num}.xml。
    """
    slides_dir = base_dir / 'ppt' / 'slides'
    rels_dir = slides_dir / '_rels'

    # 删除多余的 slide
    if slides_dir.exists():
        for f in list(slides_dir.iterdir()):
            if f.is_file() and f.suffix == '.xml':
                m = re.match(r'slide(\d+)\.xml$', f.name)
                if m and int(m.group(1)) != keep_num:
                    f.unlink()
                    # 删除对应的 rels
                    if rels_dir.exists():
                        rels_file = rels_dir / f'{f.name}.rels'
                        if rels_file.exists():
                            rels_file.unlink()

    # 删除所有 notesSlides
    notes_dir = base_dir / 'ppt' / 'notesSlides'
    if notes_dir.exists():
        shutil.rmtree(str(notes_dir))
    notes_rels_dir = base_dir / 'ppt' / 'notesSlides'
    # _rels 在 notesSlides 内部，上面已删除

    # 清理 notesSlides 在 _rels 中的残留
    slides_rels_dir = base_dir / 'ppt' / 'slides' / '_rels'
    if slides_rels_dir.exists():
        for f in list(slides_rels_dir.iterdir()):
            # 删除不属于保留 slide 的 rels
            m = re.match(r'slide(\d+)\.xml\.rels$', f.name)
            if m and int(m.group(1)) != keep_num:
                f.unlink()


def _rename_slide(base_dir, old_num, new_num):
    """将 slide{old_num}.xml 重命名为 slide{new_num}.xml，包括 rels"""
    if old_num == new_num:
        return

    slides_dir = base_dir / 'ppt' / 'slides'
    rels_dir = slides_dir / '_rels'

    # 重命名 slide XML
    old_slide = slides_dir / f'slide{old_num}.xml'
    new_slide = slides_dir / f'slide{new_num}.xml'
    if old_slide.exists():
        old_slide.rename(new_slide)

    # 重命名 slide rels
    old_rels = rels_dir / f'slide{old_num}.xml.rels'
    new_rels = rels_dir / f'slide{new_num}.xml.rels'
    if old_rels.exists():
        if not rels_dir.exists():
            rels_dir.mkdir(parents=True, exist_ok=True)
        old_rels.rename(new_rels)


def _add_slide_with_deps(src_dir, slide_num, base_dir, new_num):
    """
    从 src_dir 复制 slide{slide_num} 及其依赖到 base_dir，编号为 new_num。
    同时复制引用的 layout/master/theme/media（跳过已存在的文件）。
    """
    src_slide = src_dir / 'ppt' / 'slides' / f'slide{slide_num}.xml'
    src_rels = src_dir / 'ppt' / 'slides' / '_rels' / f'slide{slide_num}.xml.rels'

    if not src_slide.exists():
        print(f"  [WARN] slide{slide_num}.xml 不存在于 {src_dir}")
        return False

    # 复制 slide XML
    dst_slide = base_dir / 'ppt' / 'slides' / f'slide{new_num}.xml'
    dst_slide.write_bytes(src_slide.read_bytes())

    # 复制 slide rels
    if src_rels.exists():
        dst_rels_dir = base_dir / 'ppt' / 'slides' / '_rels'
        dst_rels_dir.mkdir(parents=True, exist_ok=True)
        dst_rels = dst_rels_dir / f'slide{new_num}.xml.rels'
        rels_data = src_rels.read_bytes()
        dst_rels.write_bytes(rels_data)

        # 解析 rels，复制引用的 layout/master/theme 等文件
        _copy_rels_targets(rels_data, src_dir, base_dir, 'ppt/slides')

    # 复制所有 media（图片等）— 跳过已存在的
    src_media = src_dir / 'ppt' / 'media'
    if src_media.exists():
        dst_media = base_dir / 'ppt' / 'media'
        dst_media.mkdir(parents=True, exist_ok=True)
        for mf in src_media.iterdir():
            if mf.is_file():
                dmf = dst_media / mf.name
                if not dmf.exists():
                    shutil.copy2(str(mf), str(dmf))

    # 复制所有 slideLayouts（跳过已存在的）
    src_layouts = src_dir / 'ppt' / 'slideLayouts'
    if src_layouts.exists():
        dst_layouts = base_dir / 'ppt' / 'slideLayouts'
        dst_layouts.mkdir(parents=True, exist_ok=True)
        for item in src_layouts.rglob('*'):
            if item.is_file():
                rel = item.relative_to(src_layouts)
                dst_item = dst_layouts / rel
                if not dst_item.exists():
                    dst_item.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(item), str(dst_item))

    # 复制所有 slideMasters（跳过已存在的）
    src_masters = src_dir / 'ppt' / 'slideMasters'
    if src_masters.exists():
        dst_masters = base_dir / 'ppt' / 'slideMasters'
        dst_masters.mkdir(parents=True, exist_ok=True)
        for item in src_masters.rglob('*'):
            if item.is_file():
                rel = item.relative_to(src_masters)
                dst_item = dst_masters / rel
                if not dst_item.exists():
                    dst_item.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(item), str(dst_item))

    # 复制所有 theme（跳过已存在的）
    src_theme = src_dir / 'ppt' / 'theme'
    if src_theme.exists():
        dst_theme = base_dir / 'ppt' / 'theme'
        dst_theme.mkdir(parents=True, exist_ok=True)
        for item in src_theme.rglob('*'):
            if item.is_file():
                rel = item.relative_to(src_theme)
                dst_item = dst_theme / rel
                if not dst_item.exists():
                    dst_item.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(item), str(dst_item))

    return True


def _copy_rels_targets(rels_data, src_dir, base_dir, rels_context):
    """
    解析 rels XML，将引用的 Target 文件从 src_dir 复制到 base_dir。
    rels_context: rels 文件所在的目录（如 'ppt/slides'），用于解析相对路径。
    """
    try:
        root = ET.fromstring(rels_data)
    except ET.ParseError:
        return

    for rel in root:
        target = rel.get('Target', '')
        if not target or target.startswith('http'):
            continue

        # 解析 target 路径（相对于 rels 文件所在目录）
        resolved = os.path.normpath(os.path.join(str(src_dir / rels_context), target))
        src_file = Path(resolved)

        if not src_file.exists() or not src_file.is_file():
            continue

        # 计算在 base 中的相对路径
        try:
            rel_path = str(src_file.relative_to(src_dir)).replace('\\', '/')
        except ValueError:
            continue

        dst_file = base_dir / rel_path
        if not dst_file.exists():
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_file), str(dst_file))

            # 递归复制该文件的 rels（OOXML 的 rels 在 _rels 子目录中）
            src_parent = src_file.parent
            src_rels_dir = src_parent / '_rels'
            src_file_rels = src_rels_dir / f'{src_file.name}.rels'
            if src_file_rels.exists():
                dst_rels_dir = dst_file.parent / '_rels'
                dst_rels_dir.mkdir(parents=True, exist_ok=True)
                dst_file_rels = dst_rels_dir / f'{dst_file.name}.rels'
                if not dst_file_rels.exists():
                    nested_rels_data = src_file_rels.read_bytes()
                    dst_file_rels.write_bytes(nested_rels_data)
                    # 递归处理嵌套依赖
                    new_context = str(Path(rel_path).parent).replace('\\', '/')
                    _copy_rels_targets(nested_rels_data, src_dir, base_dir, new_context)


def _rebuild_pres_and_rels(base_dir, slide_count):
    """
    从零重建 ppt/presentation.xml 和 ppt/_rels/presentation.xml.rels。
    使用字符串拼接避免 ElementTree 命名空间问题。
    """
    ppt_dir = base_dir / 'ppt'

    # ── 扫描 slideMaster ──
    master_dir = ppt_dir / 'slideMasters'
    master_nums = []
    if master_dir.exists():
        for f in sorted(master_dir.iterdir()):
            m = re.match(r'slideMaster(\d+)\.xml$', f.name)
            if m:
                master_nums.append(int(m.group(1)))

    # ── 扫描 theme ──
    theme_dir = ppt_dir / 'theme'
    theme_nums = []
    if theme_dir.exists():
        for f in sorted(theme_dir.iterdir()):
            m = re.match(r'theme(\d+)\.xml$', f.name)
            if m:
                theme_nums.append(int(m.group(1)))

    # ── 分配 rId ──
    rid_counter = 1
    slide_rids = {}
    for i in range(slide_count):
        snum = i + 1
        slide_rids[snum] = f'rId{rid_counter}'
        rid_counter += 1

    master_rids = {}
    for mnum in master_nums:
        master_rids[mnum] = f'rId{rid_counter}'
        rid_counter += 1

    theme_rids = {}
    for tnum in theme_nums:
        theme_rids[tnum] = f'rId{rid_counter}'
        rid_counter += 1

    # ── 写入 presentation.xml ──
    pres_lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<p:presentation xmlns:p="{NS_P}" xmlns:r="{NS_R}" '
        f'saveSubsetFonts="1" autoCompressPictures="0">',
    ]

    # sldMasterIdLst
    if master_rids:
        pres_lines.append('<p:sldMasterIdLst>')
        for mnum, rid in sorted(master_rids.items()):
            # slideMaster 的 id 通常从 2147483647 递减
            sid = 2147483647 - mnum + 1
            pres_lines.append(
                f'<p:sldMasterId id="{sid}" r:id="{rid}"/>'
            )
        pres_lines.append('</p:sldMasterIdLst>')

    # sldIdLst
    pres_lines.append('<p:sldIdLst>')
    for snum, rid in sorted(slide_rids.items()):
        sid = 255 + snum
        pres_lines.append(f'<p:sldId id="{sid}" r:id="{rid}"/>')
    pres_lines.append('</p:sldIdLst>')

    pres_lines.append('</p:presentation>')

    pres_path = ppt_dir / 'presentation.xml'
    pres_path.write_text('\n'.join(pres_lines), encoding='utf-8')

    # ── 写入 presentation.xml.rels ──
    rels_lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<Relationships xmlns="{NS_REL}">',
    ]

    # Slide relationships
    for snum, rid in sorted(slide_rids.items()):
        rels_lines.append(
            f'<Relationship Id="{rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            f'Target="slides/slide{snum}.xml"/>'
        )

    # slideMaster relationships
    for mnum, rid in sorted(master_rids.items()):
        rels_lines.append(
            f'<Relationship Id="{rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" '
            f'Target="slideMasters/slideMaster{mnum}.xml"/>'
        )

    # theme relationships
    for tnum, rid in sorted(theme_rids.items()):
        rels_lines.append(
            f'<Relationship Id="{rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" '
            f'Target="theme/theme{tnum}.xml"/>'
        )

    rels_lines.append('</Relationships>')

    rels_dir = ppt_dir / '_rels'
    rels_dir.mkdir(parents=True, exist_ok=True)
    rels_path = rels_dir / 'presentation.xml.rels'
    rels_path.write_text('\n'.join(rels_lines), encoding='utf-8')

    # ── 确保 _rels/.rels 存在（包级别关系） ──
    root_rels_dir = base_dir / '_rels'
    root_rels_path = root_rels_dir / '.rels'
    if not root_rels_path.exists():
        root_rels_dir.mkdir(parents=True, exist_ok=True)
        root_rels_lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            f'<Relationships xmlns="{NS_REL}">',
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="ppt/presentation.xml"/>',
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
            'Target="docProps/core.xml"/>',
            '<Relationship Id="rId3" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
            'Target="docProps/app.xml"/>',
            '</Relationships>',
        ]
        root_rels_path.write_text('\n'.join(root_rels_lines), encoding='utf-8')


def _rebuild_content_types(base_dir):
    """
    从零重建 [Content_Types].xml，根据 base_dir 中实际存在的文件生成。
    """
    # 标准 Default 条目
    defaults = {
        'rels': 'application/vnd.openxmlformats-package.relationships+xml',
        'xml': 'application/xml',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'bmp': 'image/bmp',
        'tif': 'image/tiff',
        'tiff': 'image/tiff',
        'wmf': 'image/x-wmf',
        'emf': 'image/x-emf',
        'svg': 'image/svg+xml',
        'mp4': 'video/mp4',
        'avi': 'video/avi',
    }

    overrides = {}

    # 扫描所有文件
    for root, dirs, files in os.walk(str(base_dir)):
        for fn in files:
            full = os.path.join(root, fn)
            arc = '/' + os.path.relpath(full, str(base_dir)).replace('\\', '/')

            # 判断 Content Type
            if re.search(r'/slides/slide\d+\.xml$', arc):
                ct = 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'
                overrides[arc] = ct
            elif re.search(r'/slideLayouts/slideLayout\d+\.xml$', arc):
                ct = 'application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml'
                overrides[arc] = ct
            elif re.search(r'/slideMasters/slideMaster\d+\.xml$', arc):
                ct = 'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml'
                overrides[arc] = ct
            elif re.search(r'/theme/theme\d+\.xml$', arc):
                ct = 'application/vnd.openxmlformats-officedocument.theme+xml'
                overrides[arc] = ct
            elif arc.endswith('/presentation.xml'):
                ct = 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'
                overrides[arc] = ct
            elif arc.endswith('/app.xml'):
                ct = 'application/vnd.openxmlformats-officedocument.extended-properties+xml'
                overrides[arc] = ct
            elif arc.endswith('/core.xml'):
                ct = 'application/vnd.openxmlformats-package.core-properties+xml'
                overrides[arc] = ct
            elif arc.endswith('/styles.xml'):
                ct = 'application/vnd.openxmlformats-officedocument.presentationml.styles+xml'
                overrides[arc] = ct
            elif arc.endswith('/viewProps.xml'):
                ct = 'application/vnd.openxmlformats-officedocument.presentationml.viewProperties+xml'
                overrides[arc] = ct
            elif arc.endswith('/presProps.xml'):
                ct = 'application/vnd.openxmlformats-officedocument.presentationml.presProperties+xml'
                overrides[arc] = ct
            elif arc.endswith('/tableStyles.xml'):
                ct = 'application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml'
                overrides[arc] = ct

    # 写入
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<Types xmlns="{NS_CT}">',
    ]

    # Default 条目
    for ext, ct in sorted(defaults.items()):
        lines.append(f'<Default Extension="{ext}" ContentType="{ct}"/>')

    # Override 条目
    for part_name, ct in sorted(overrides.items()):
        lines.append(f'<Override PartName="{part_name}" ContentType="{ct}"/>')

    lines.append('</Types>')

    ct_path = base_dir / '[Content_Types].xml'
    ct_path.write_text('\n'.join(lines), encoding='utf-8')


def _package_pptx(base_dir, output_path):
    """将 base_dir 打包为 PPTX（ZIP 格式）"""
    if os.path.exists(output_path):
        os.unlink(output_path)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for root, dirs, files in os.walk(str(base_dir)):
            for fn in files:
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, str(base_dir)).replace('\\', '/')
                zout.write(full, arc)

    return output_path


# ═══════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════

def merge_slides(entries, output_path):
    """
    将多个幻灯片合并为一个多页 PPTX。
    COM 优先（PasteSourceFormatting），COM 不可用时自动回退 ZIP 合并。

    Args:
        entries: [(pptx_path, slide_num), ...] 列表
            pptx_path: 源 PPTX 文件路径
            slide_num: 要提取的页码（从 1 开始）
        output_path: 输出 PPTX 文件路径

    Returns:
        str: 输出文件路径

    Raises:
        ValueError: 没有有效的源文件
    """
    # 过滤无效路径
    valid_entries = [(str(p), int(n)) for p, n in entries if os.path.exists(str(p))]
    if not valid_entries:
        raise ValueError("没有有效的源 PPTX 文件")

    # 确保输出目录存在
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)

    # 尝试 COM 合并
    try:
        result = _com_merge(valid_entries, output_path)
        # 快速验证：检查输出的 PPTX 是否包含足够的 slide
        with zipfile.ZipFile(result, 'r') as z:
            slides = [n for n in z.namelist()
                      if re.match(r'ppt/slides/slide\d+\.xml$', n)]
            if len(slides) >= len(valid_entries):
                print(f"  COM 合并成功: {len(slides)} 页 → {output_path}")
                return result
            else:
                print(f"  COM 合并验证失败: 期望 {len(valid_entries)} 页, 实际 {len(slides)} 页")
    except Exception as e:
        print(f"  COM 合并失败 ({e})，回退到 ZIP 合并...")

    # ZIP 兜底
    result = _zip_merge(valid_entries, output_path)
    with zipfile.ZipFile(result, 'r') as z:
        slides = [n for n in z.namelist()
                  if re.match(r'ppt/slides/slide\d+\.xml$', n)]
        print(f"  ZIP 合并成功: {len(slides)} 页 → {output_path}")

    return result
