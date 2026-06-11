#!/usr/bin/env python3
"""
extract_arch.py -- Extract architecture diagrams from PPTX slide 1
==================================================================
Usage:
  python extract_arch.py <pptx_path> [output_dir]

Features:
  1. Parse slide1.xml to find all image shapes with position/size
  2. Filter out full-slide backgrounds (cx>=12M and cy>=6.8M EMU)
  3. Extract remaining images as architecture diagrams
  4. Place on white background (handle transparency via Pillow)
"""

import os
import re
import sys
import zipfile
from pathlib import Path
from io import BytesIO

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

EMU_PER_PX = 914400 / 96


def emu_to_px(emu_val):
    return int(emu_val / EMU_PER_PX)


def parse_slide1_images(pptx_path):
    """Parse slide1 to find all image shapes with position/size in EMU."""
    with zipfile.ZipFile(pptx_path, 'r') as z:
        slide_xml = z.read('ppt/slides/slide1.xml').decode('utf-8', errors='replace')
        try:
            rels_xml = z.read('ppt/slides/_rels/slide1.xml.rels').decode('utf-8', errors='replace')
        except Exception:
            rels_xml = ""

    shapes = []
    tag_starts = list(re.finditer(r'<(p:sp|p:pic|p:graphicFrame)\b', slide_xml))

    for start_m in tag_starts:
        tag_name = start_m.group(1)
        start_pos = start_m.start()

        # Track depth to find matching closing tag
        depth = 1
        search_pos = start_m.end()
        end_pos = -1
        open_tag = f'<{tag_name}'
        close_tag = f'</{tag_name}>'

        while depth > 0 and search_pos < len(slide_xml):
            next_open = slide_xml.find(open_tag, search_pos)
            next_close = slide_xml.find(close_tag, search_pos)
            if next_close == -1:
                break
            if next_open != -1 and next_open < next_close:
                depth += 1
                search_pos = next_open + len(open_tag)
            else:
                depth -= 1
                search_pos = next_close + len(close_tag)
                if depth == 0:
                    end_pos = next_close + len(close_tag)

        if end_pos == -1:
            continue

        block = slide_xml[start_pos:end_pos]

        # Find image reference
        blip_match = re.search(r'<a:blip[^>]*r:embed="([^"]+)"', block)
        if not blip_match:
            continue

        embed_id = blip_match.group(1)

        target_match = re.search(
            rf'Id="{re.escape(embed_id)}"[^>]*Target="([^"]+)"',
            rels_xml
        )
        if not target_match:
            continue

        target = target_match.group(1)
        internal_name = Path(target).name

        # Find xfrm in spPr (for p:pic, spPr comes after blipFill)
        spPr_match = re.search(r'<p:spPr\b[^>]*>.*?</p:spPr>', block, re.DOTALL)
        if not spPr_match:
            spPr_match = re.search(r'<p:grpSpPr\b[^>]*>.*?</p:grpSpPr>', block, re.DOTALL)
        if not spPr_match:
            continue

        spPr = spPr_match.group()
        xfrm_match = re.search(r'<a:xfrm\b.*?</a:xfrm>', spPr, re.DOTALL)
        if not xfrm_match:
            continue

        xfrm_text = xfrm_match.group()
        off_match = re.search(r'<a:off[^>]*x="(\d+)"[^>]*y="(\d+)"', xfrm_text)
        ext_match = re.search(r'<a:ext[^>]*cx="(\d+)"[^>]*cy="(\d+)"', xfrm_text)

        x = int(off_match.group(1)) if off_match else 0
        y = int(off_match.group(2)) if off_match else 0
        cx = int(ext_match.group(1)) if ext_match else 0
        cy = int(ext_match.group(2)) if ext_match else 0

        # Full-slide background: covers > 60% of standard 16:9 slide
        slide_w = 12192000
        slide_h = 6858000
        coverage = (cx * cy) / (slide_w * slide_h)
        is_bg = coverage >= 0.6

        shapes.append({
            'internal_name': internal_name,
            'x': x, 'y': y,
            'cx': cx, 'cy': cy,
            'x_px': emu_to_px(x),
            'y_px': emu_to_px(y),
            'w_px': emu_to_px(cx),
            'h_px': emu_to_px(cy),
            'coverage': coverage,
            'is_background': is_bg,
            'embed_id': embed_id,
            'target': target,
        })

    return shapes


def save_with_white_bg(img_data, out_path):
    """Save image data to file, compositing onto white background if transparent."""
    if not HAS_PILLOW:
        with open(out_path, 'wb') as f:
            f.write(img_data)
        return

    img = Image.open(BytesIO(img_data))

    if img.mode in ('RGBA', 'LA', 'PA'):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'RGBA':
            bg.paste(img, mask=img.split()[3])
        elif img.mode == 'PA':
            img = img.convert('RGBA')
            bg.paste(img, mask=img.split()[3])
        else:
            bg.paste(img)
        bg.save(out_path)
    elif img.mode == 'P':
        img = img.convert('RGBA')
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        bg.save(out_path)
    elif img.mode != 'RGB':
        img.convert('RGB').save(out_path)
    else:
        img.save(out_path)


def extract_arch_images(pptx_path, output_dir, verbose=True):
    """Extract architecture diagrams from PPTX slide 1."""
    pptx_path = Path(pptx_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    shapes = parse_slide1_images(pptx_path)

    if verbose:
        print(f"\n{'='*60}")
        print(f"File: {pptx_path.name}")
        print(f"Slide 1 image shapes: {len(shapes)}")
        print(f"{'='*60}")

    bg_shapes = [s for s in shapes if s['is_background']]
    arch_shapes = [s for s in shapes if not s['is_background']]

    if verbose:
        for s in shapes:
            tag = "[BG]" if s['is_background'] else "[ARCH]"
            print(f"  {tag} {s['internal_name']} "
                  f"pos=({s['x_px']},{s['y_px']})px "
                  f"size={s['w_px']}x{s['h_px']}px "
                  f"coverage={s['coverage']:.1%}")

    if not arch_shapes:
        print("\n  WARNING: No architecture images found (all images are backgrounds)")
        if shapes:
            print("  -> Hint: All slide 1 images cover >60% of the slide")
        return []

    output_files = []
    with zipfile.ZipFile(pptx_path, 'r') as z:
        for i, s in enumerate(arch_shapes):
            internal_name = s['internal_name']
            media_path = f"ppt/media/{internal_name}"
            try:
                img_data = z.read(media_path)
            except KeyError:
                print(f"  [ERROR] Image not in archive: {media_path}")
                continue

            base_name = pptx_path.stem
            out_name = f"{base_name}_slide1_arch{i+1}_{internal_name}"
            out_path = output_dir / out_name

            if HAS_PILLOW:
                img = Image.open(BytesIO(img_data))
                if verbose:
                    print(f"  {internal_name}: stored={img.size[0]}x{img.size[1]}px, "
                          f"display={s['w_px']}x{s['h_px']}px, "
                          f"mode={img.mode}")

            save_with_white_bg(img_data, out_path)
            output_files.append(str(out_path))

            if verbose:
                print(f"  [SAVED] {out_path}")

    return output_files


# ═══════════ CLI ═══════════
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    pptx_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) >= 3 else str(
        Path(__file__).parent / "arch_output"
    )

    if not os.path.exists(pptx_path):
        print(f"[ERROR] File not found: {pptx_path}")
        sys.exit(1)

    files = extract_arch_images(pptx_path, output_dir, verbose=True)

    print(f"\n{'='*60}")
    print(f"DONE: {len(files)} architecture diagram(s) extracted")
    print(f"Output: {output_dir}")
    for f in files:
        print(f"  -> {f}")
