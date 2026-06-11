#!/usr/bin/env python3
"""
PDF Smart Splitter — Intelligent PDF Chunking for Long-Document PPT Generation

Splits a long PDF into context-safe chunks while preserving chapter/section
integrity. Integrates with the PPT Master pipeline to prevent information
loss when processing large source documents.

Key features:
1. Model Sniffer — detects backend model, estimates safe context budget
2. Smart Chapter Detection — finds "第X章" markers + TOC-based page ranges
3. Sub-Chapter Splitting — splits oversized chapters at section boundaries
4. Concurrent Orchestration — generates parallel-ready chunk manifests

Usage:
    # Analyze only (no splitting)
    python3 scripts/pdf_splitter.py <pdf_file> --analyze

    # Split with auto-detected model context
    python3 scripts/pdf_splitter.py <pdf_file> --max-pages 10

    # Split with explicit model specification
    python3 scripts/pdf_splitter.py <pdf_file> --model deepseek-v3 --max-pages 10

Output:
    <pdf_dir>/_chunks/
    ├── chunk_01_p1-6_frontmatter.pdf
    ├── chunk_02_p7-10_ch1_ai_macro.pdf
    ├── chunk_03_p11-18_ch2_enterprise_ai.pdf
    ├── chunk_04_p19-24_ch3a_dc_evolution.pdf
    ├── chunk_05_p25-29_ch3b_system_moore.pdf
    ├── chunk_06_p30-39_ch4a_planning.pdf
    ├── chunk_07_p40-48_ch4b_construction.pdf
    ├── chunk_08_p49-54_ch5_initiatives.pdf
    └── split_manifest.json

Dependencies:
    PyMuPDF (fitz) — included in deepppt/requirements.txt
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import fitz
except ImportError:
    print("ERROR: PyMuPDF is required. Install: pip install PyMuPDF", file=sys.stderr)
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════
# Model Sniffer — Context Window Budget Estimation
# ═══════════════════════════════════════════════════════════════════════════

# Known model context window sizes (tokens)
MODEL_CTX_WINDOWS = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "o1": 200_000,
    "o3-mini": 200_000,
    # Anthropic
    "claude-3.5-sonnet": 200_000,
    "claude-3.5-haiku": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
    # Google
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.0-pro": 2_000_000,
    "gemini-1.5-pro": 2_000_000,
    "gemini-1.5-flash": 1_000_000,
    # DeepSeek
    "deepseek-v3": 128_000,
    "deepseek-v4-pro": 128_000,
    "deepseek-r1": 128_000,
    # GLM / KIMI
    "glm-4": 128_000,
    "kimi": 128_000,
    # Hunyuan / Minimax
    "hunyuan": 32_000,
    "minimax": 32_000,
}

# Conservative per-page token estimates (Chinese text, ~800 chars/page typical)
AVG_TOKENS_PER_PDF_PAGE = 800  # average Chinese chars per page → ~1200 tokens

# Fixed context overhead (tokens) — system prompts, skill code, Python scripts
SYSTEM_OVERHEAD_TOKENS = {
    "skill_code": 25_000,      # SKILL.md + workflow docs
    "script_code": 8_000,      # Python scripts loaded in context
    "system_prompt": 12_000,   # Role definitions, safety rules
    "output_formatting": 5_000,  # SVG code, PPTX directives
}
TOTAL_FIXED_OVERHEAD = sum(SYSTEM_OVERHEAD_TOKENS.values())  # ~50K

# Per-chunk overhead — intermediate processing instructions
PER_CHUNK_OVERHEAD = 15_000  # strategist discussion + quality check prompts

# Safety margin — leave this much headroom
SAFETY_MARGIN_PCT = 0.10  # 10%


def detect_model() -> dict:
    """Detect the current backend model from environment and known sources.
    
    Returns a dict with model info, or best-guess defaults.
    """
    info = {
        "model_id": "unknown",
        "context_window": 128_000,  # conservative default
        "source": "default",
    }

    # Check env vars (various platforms)
    for env_var in [
        "MODEL_ID", "LLM_MODEL", "ANTHROPIC_MODEL", "OPENAI_MODEL",
        "CODEBUDDY_MODEL", "CLAUDE_MODEL", "COPILOT_MODEL",
    ]:
        val = os.environ.get(env_var)
        if val:
            info["model_id"] = val.lower()
            info["source"] = f"env:{env_var}"
            break

    # Match against known models
    model_lower = info["model_id"]
    for known, ctx in MODEL_CTX_WINDOWS.items():
        if known in model_lower:
            info["context_window"] = ctx
            info["source"] = f"matched:{known}"
            break

    return info


def compute_safe_chunk_pages(
    context_window: int,
    max_pages: Optional[int] = None,
) -> int:
    """Compute the maximum safe PDF pages per chunk.
    
    Formula:
        ctx_available = context_window * (1 - SAFETY_MARGIN)
        working_budget = ctx_available - TOTAL_FIXED_OVERHEAD
        safe_pages = working_budget / (AVG_TOKENS_PER_PDF_PAGE * 1.5 + per_chunk)
    
    Then clamp to [3, max_pages] and round down.
    """
    ctx_available = int(context_window * (1.0 - SAFETY_MARGIN_PCT))
    working_budget = ctx_available - TOTAL_FIXED_OVERHEAD - PER_CHUNK_OVERHEAD

    # Each PDF page ≈ 800 chars → ~1200 tokens (Chinese: ~1.5 tokens/char)
    tokens_per_page = AVG_TOKENS_PER_PDF_PAGE * 1.5
    safe_pages = max(3, working_budget // tokens_per_page)

    # User-specified cap
    if max_pages and max_pages > 0:
        safe_pages = min(safe_pages, max_pages)

    # Never exceed 15 pages even with huge context (quality degradation)
    safe_pages = min(safe_pages, 15)

    return safe_pages


# ═══════════════════════════════════════════════════════════════════════════
# Chapter Detection
# ═══════════════════════════════════════════════════════════════════════════

# Primary pattern: "第X章" or "第 X 章"
CHAPTER_RE = re.compile(r'第\s*(\d+)\s*章\s*(.+?)(?:\n|$|)', re.MULTILINE)

# Secondary patterns for sub-sections within chapters
SUBSECTION_RE = re.compile(r'^[（(]?[一二三四五六七八九十]+[）)]\s*[、，]?\s*(.+)', re.MULTILINE)
SUBSECTION_NUM_RE = re.compile(r'^(\d+)[\.\、]\s*(.+)', re.MULTILINE)

# Meta-section markers (not chapters, but useful boundaries)
META_MARKERS = [
    (re.compile(r'^前言\s*$', re.MULTILINE), 'frontmatter'),
    (re.compile(r'^目录\s*$', re.MULTILINE), 'toc'),
    (re.compile(r'^附录\s*', re.MULTILINE), 'appendix'),
]


def _page_text(page) -> str:
    """Extract clean text from a PDF page."""
    return page.get_text("text")


def _find_chapters(doc: fitz.Document) -> list[dict]:
    """Find all chapter boundaries and return page ranges.
    
    Returns list of {chapter_num, title, start_page, end_page, page_count}
    """
    chapters = []

    for i in range(doc.page_count):
        text = _page_text(doc[i])
        m = CHAPTER_RE.search(text)
        if m:
            chapters.append({
                "chapter_num": int(m.group(1)),
                "title": m.group(2).strip(),
                "start_page": i,  # 0-indexed
                "end_page": None,
            })

    # Compute end pages (chapter N ends at chapter N+1 start - 1)
    for j in range(len(chapters)):
        if j + 1 < len(chapters):
            chapters[j]["end_page"] = chapters[j + 1]["start_page"] - 1
        else:
            chapters[j]["end_page"] = doc.page_count - 1
        chapters[j]["page_count"] = chapters[j]["end_page"] - chapters[j]["start_page"] + 1

    return chapters


def _find_frontmatter(doc: fitz.Document, first_chapter_page: int) -> dict | None:
    """Detect front matter (preface, TOC) before the first chapter."""
    if first_chapter_page <= 1:
        return None

    # Check for useful content in pages 0 to first_chapter_page-1
    front_pages = list(range(0, first_chapter_page))
    has_content = False
    for i in front_pages:
        text = _page_text(doc[i]).strip()
        if len(text) > 50:  # non-trivial content
            has_content = True
            break

    if has_content and len(front_pages) >= 1:
        return {
            "title": "前言与目录",
            "start_page": 0,
            "end_page": first_chapter_page - 1,
            "page_count": first_chapter_page,
            "is_frontmatter": True,
        }

    return None


def _find_subsections(doc: fitz.Document, start_page: int, end_page: int) -> list[dict]:
    """Find sub-section boundaries within a chapter.
    
    Looks for:
    - Large-font text (potential section headers)
    - Numbered sections: "一、", "二、" or "1.", "2."
    """
    subsections = []

    for i in range(start_page, end_page + 1):
        text = _page_text(doc[i])

        # Check for numbered Chinese subsections
        m = SUBSECTION_RE.search(text)
        if m:
            subsections.append({
                "page": i,
                "title": m.group(1).strip(),
            })
            continue

        # Check font sizes to find potential section headers
        blocks = doc[i].get_text("dict")["blocks"]
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("size", 0) >= 16:  # large font = potential header
                        header_text = span.get("text", "").strip()
                        if len(header_text) > 2 and len(header_text) < 60:
                            subsections.append({
                                "page": i,
                                "title": header_text,
                            })
                            break
                if subsections and subsections[-1]["page"] == i:
                    break
            if subsections and subsections[-1]["page"] == i:
                break

    return subsections


# ═══════════════════════════════════════════════════════════════════════════
# Splitting Logic
# ═══════════════════════════════════════════════════════════════════════════

def split_chapter(
    chapter: dict,
    max_pages: int,
    doc: fitz.Document,
) -> list[dict]:
    """Split a single chapter into chunks ≤ max_pages.

    Strategy:
    1. If chapter fits → single chunk
    2. Use sub-section boundaries as preferred split points
    3. Fall back to even splitting when no subs found
    4. Merge tiny chunks (≤ 1 page) with neighbours
    """
    if chapter["page_count"] <= max_pages:
        return [chapter]

    subs = _find_subsections(doc, chapter["start_page"], chapter["end_page"])

    # Build chunks using subs as preferred boundaries
    chunks = []
    chunk_start = chapter["start_page"]

    for sub in subs:
        sub_page = sub["page"]
        # If including this sub would make chunk too big, finalize current chunk
        if sub_page - chunk_start >= max_pages:
            # Current chunk has grown too large — finalize before this sub
            chunk_end = sub_page - 1
            # But ensure we don't create a chunk smaller than 3 pages
            if chunk_end - chunk_start + 1 < 3 and chunk_start < sub_page:
                # Too small — let it grow into the next sub
                continue
            chunks.append(_make_chunk(chapter, chunk_start, chunk_end))
            chunk_start = sub_page

    # Final chunk: remaining pages
    if chunk_start <= chapter["end_page"]:
        chunks.append(_make_chunk(chapter, chunk_start, chapter["end_page"]))

    # If sub-based splitting didn't work, force-split
    if len(chunks) <= 1:
        chunks = _force_split(chapter, max_pages)

    # Post-process: force-split any chunk that still exceeds max_pages
    final_chunks = []
    for c in chunks:
        if c["page_count"] > max_pages:
            final_chunks.extend(_force_split(
                {"chapter_num": c.get("chapter_num"), "title": c["title"],
                 "start_page": c["start_page"], "end_page": c["end_page"],
                 "page_count": c["page_count"]},
                max_pages
            ))
        else:
            final_chunks.append(c)

    # Merge tiny chunks
    final_chunks = _merge_tiny_chunks(final_chunks)

    return final_chunks


def _make_chunk(chapter: dict, start: int, end: int) -> dict:
    """Create a chunk dict from a chapter and page range."""
    return {
        "title": _make_chunk_title(chapter, start, end, []),
        "start_page": start,
        "end_page": end,
        "page_count": end - start + 1,
        "chapter_num": chapter.get("chapter_num"),
    }


def _force_split(chapter: dict, max_pages: int) -> list[dict]:
    """Evenly split a chapter into chunks, each ≤ max_pages.
    Distributes pages evenly to avoid tiny final chunks."""
    total = chapter["page_count"]
    start = chapter["start_page"]
    end = chapter["end_page"]
    
    # Calculate optimal chunk count and page distribution
    num_chunks = (total + max_pages - 1) // max_pages  # ceil division
    base_size = total // num_chunks
    remainder = total % num_chunks
    
    chunks = []
    pos = start
    for i in range(num_chunks):
        # Extra page goes to early chunks
        size = base_size + (1 if i < remainder else 0)
        chunk_end = min(pos + size - 1, end)
        chunks.append(_make_chunk(chapter, pos, chunk_end))
        pos = chunk_end + 1
    
    return chunks


def _merge_tiny_chunks(chunks: list[dict]) -> list[dict]:
    """Merge chunks with ≤ 1 page into neighbours."""
    if len(chunks) <= 1:
        return chunks
    
    result = []
    i = 0
    while i < len(chunks):
        c = chunks[i]
        if c["page_count"] <= 1 and result:
            # Merge into previous chunk
            prev = result[-1]
            prev["end_page"] = c["end_page"]
            prev["page_count"] = prev["end_page"] - prev["start_page"] + 1
            prev["title"] = _make_chunk_title(
                {"chapter_num": c.get("chapter_num"), "title": prev.get("title", "")},
                prev["start_page"], prev["end_page"], []
            )
        elif c["page_count"] <= 1 and i + 1 < len(chunks):
            # Merge into next chunk
            nxt = chunks[i + 1]
            nxt["start_page"] = c["start_page"]
            nxt["page_count"] = nxt["end_page"] - nxt["start_page"] + 1
            nxt["title"] = _make_chunk_title(
                {"chapter_num": c.get("chapter_num"), "title": nxt.get("title", "")},
                nxt["start_page"], nxt["end_page"], []
            )
            # prepend to result (nxt becomes the merged chunk)
            result.append(nxt)
            i += 1  # skip nxt since we already processed it
        else:
            result.append(c)
        i += 1
    
    return result


def _make_chunk_title(chapter: dict, start: int, end: int, subs: list) -> str:
    """Generate a descriptive title for a chunk."""
    ch_label = f"第{chapter.get('chapter_num','?')}章" if chapter.get("chapter_num") else ""
    main = chapter.get("title", "")[:30]
    if subs:
        sub_titles = "/".join(s.get("title", "")[:10] for s in subs[:3])
        return f"{ch_label} {main} ({sub_titles})".strip()
    return f"{ch_label} {main}".strip()


def _sanitize_filename(title: str) -> str:
    """Convert a title to a safe filename slug."""
    slug = title.strip()
    # Keep only Chinese chars, ASCII letters, digits, underscores
    slug = re.sub(r'[^\u4e00-\u9fff\w\s]', '', slug)
    slug = re.sub(r'\s+', '_', slug)
    return slug[:50] or "chunk"


# ═══════════════════════════════════════════════════════════════════════════
# Main Splitter
# ═══════════════════════════════════════════════════════════════════════════

def split_pdf(
    pdf_path: str,
    max_pages: Optional[int] = None,
    output_dir: Optional[str] = None,
    model_ctx: Optional[int] = None,
) -> dict:
    """Main entry point: split a PDF into context-safe chunks.
    
    Args:
        pdf_path: Path to the PDF file
        max_pages: User-specified max pages per chunk (auto-detected if None)
        output_dir: Output directory (default: <pdf_dir>/_chunks/)
        model_ctx: Explicit model context window size (auto-detected if None)
    
    Returns:
        Manifest dict with chunk info
    """
    pdf_file = Path(pdf_path).resolve()
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_file}")

    model_info = detect_model()
    if model_ctx is None:
        model_ctx = model_info["context_window"]

    safe_pages = compute_safe_chunk_pages(model_ctx, max_pages)

    if output_dir is None:
        output_dir = pdf_file.parent / "_chunks"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_file))
    total_pages = doc.page_count

    # Step 1: Find chapter boundaries
    chapters = _find_chapters(doc)

    # Step 2: Detect front matter
    first_ch = chapters[0]["start_page"] if chapters else total_pages
    frontmatter = _find_frontmatter(doc, first_ch)

    # Step 3: Build chunk list
    all_chunks = []
    chunk_index = 1

    if frontmatter and frontmatter["page_count"] > 0:
        slug = _sanitize_filename(frontmatter["title"])
        all_chunks.append({
            "id": chunk_index,
            "title": frontmatter["title"],
            "start_page": frontmatter["start_page"],
            "end_page": frontmatter["end_page"],
            "page_count": frontmatter["page_count"],
            "pages_range": f"p{frontmatter['start_page']+1}-{frontmatter['end_page']+1}",
            "filename": f"chunk_{chunk_index:02d}_{frontmatter['start_page']+1}-{frontmatter['end_page']+1}_{slug}.pdf",
            "is_frontmatter": True,
        })
        chunk_index += 1

    for ch in chapters:
        sub_chunks = split_chapter(ch, safe_pages, doc)
        for sc in sub_chunks:
            slug = _sanitize_filename(sc["title"] or f"ch{ch.get('chapter_num','')}p{sc['start_page']+1}")
            all_chunks.append({
                "id": chunk_index,
                "title": sc["title"],
                "start_page": sc["start_page"],
                "end_page": sc["end_page"],
                "page_count": sc["page_count"],
                "pages_range": f"p{sc['start_page']+1}-{sc['end_page']+1}",
                "filename": f"chunk_{chunk_index:02d}_{sc['start_page']+1}-{sc['end_page']+1}_{slug}.pdf",
                "chapter_num": sc.get("chapter_num"),
            })
            chunk_index += 1

    # Step 4: Write split PDFs
    for chunk in all_chunks:
        out_path = output_dir / chunk["filename"]
        _write_pdf_range(doc, chunk["start_page"], chunk["end_page"], str(out_path))
        chunk["path"] = str(out_path)
        chunk["size_bytes"] = out_path.stat().st_size

    # Step 5: Write manifest
    manifest = {
        "source_pdf": str(pdf_file),
        "total_pages": total_pages,
        "model_info": model_info,
        "safe_pages_per_chunk": safe_pages,
        "total_chunks": len(all_chunks),
        "chunks": all_chunks,
    }

    manifest_path = output_dir / "split_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    doc.close()

    return manifest


def _write_pdf_range(doc: fitz.Document, start: int, end: int, output_path: str):
    """Write a page range as a new PDF file."""
    new_doc = fitz.open()
    new_doc.insert_pdf(doc, from_page=start, to_page=end)
    new_doc.save(output_path)
    new_doc.close()


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    # Fix Windows GBK console encoding issues
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="PDF Smart Splitter — chunk long PDFs for PPT generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Max pages per chunk (auto: based on model context)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Explicit model ID (e.g. deepseek-v3, gpt-4o, claude-3.5-sonnet)",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Output directory for chunks (default: <pdf_dir>/_chunks/)",
    )
    parser.add_argument(
        "--analyze", action="store_true",
        help="Analyze only — show model info and chapter structure, no splitting",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Model detection
    model_info = detect_model()
    model_ctx = model_info["context_window"]

    if args.model:
        model_lower = args.model.lower()
        for known, ctx in MODEL_CTX_WINDOWS.items():
            if known in model_lower or model_lower in known:
                model_ctx = ctx
                model_info = {"model_id": known, "context_window": ctx, "source": "cli"}
                break

    safe_pages = compute_safe_chunk_pages(model_ctx, args.max_pages)

    if args.json:
        # JSON output mode
        if args.analyze:
            doc = fitz.open(args.pdf)
            chapters = _find_chapters(doc)
            doc.close()
            result = {
                "model": model_info,
                "safe_pages_per_chunk": safe_pages,
                "total_pages": len(chapters),
                "chapters": [
                    {"num": c["chapter_num"], "title": c["title"],
                     "pages": f"{c['start_page']+1}-{c['end_page']+1}",
                     "page_count": c["page_count"]}
                    for c in chapters
                ],
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            manifest = split_pdf(args.pdf, args.max_pages, args.output_dir, model_ctx)
            print(json.dumps({
                "model": model_info,
                "safe_pages_per_chunk": safe_pages,
                "total_chunks": manifest["total_chunks"],
                "chunks": [
                    {"id": c["id"], "title": c["title"], "pages": c["pages_range"],
                     "pages_count": c["page_count"], "file": c["filename"]}
                    for c in manifest["chunks"]
                ],
            }, ensure_ascii=False, indent=2))
        return 0

    # Human-readable output
    print("=" * 60)
    print("  PDF Smart Splitter")
    print("=" * 60)
    print(f"\n  Source: {args.pdf}")
    print(f"  Model:  {model_info['model_id']} ({model_info['source']})")
    print(f"  Context window: {model_ctx:,} tokens")
    print(f"  System overhead: {TOTAL_FIXED_OVERHEAD:,} tokens")
    print(f"  Safe pages/chunk: {safe_pages} (≤ {args.max_pages or 'auto'})")
    print()

    if args.analyze:
        doc = fitz.open(args.pdf)
        print(f"  Total pages: {doc.page_count}")
        chapters = _find_chapters(doc)
        frontmatter = _find_frontmatter(doc, chapters[0]["start_page"] if chapters else 0)

        if frontmatter:
            print(f"\n  [封面/前言/目录]  第{frontmatter['start_page']+1}-{frontmatter['end_page']+1}页  ({frontmatter['page_count']}页)")

        for ch in chapters:
            status = "OK" if ch["page_count"] <= safe_pages else "OVER"
            print(f"  [第{ch['chapter_num']}章] {ch['title']}")
            print(f"           第{ch['start_page']+1}-{ch['end_page']+1}页  ({ch['page_count']}页)  {status}")
            if ch["page_count"] > safe_pages:
                subs = _find_subsections(doc, ch["start_page"], ch["end_page"])
                if subs:
                    print(f"           子节: {len(subs)} 个")
                    for s in subs[:5]:
                        print(f"              p{s['page']+1}: {s['title'][:40]}")
                    if len(subs) > 5:
                        print(f"              ... +{len(subs)-5} more")

        doc.close()
        return 0

    # Full split
    manifest = split_pdf(args.pdf, args.max_pages, args.output_dir, model_ctx)

    print(f"  Split into {manifest['total_chunks']} chunk(s):\n")
    for chunk in manifest["chunks"]:
        marker = "[FM]" if chunk.get("is_frontmatter") else f"Ch{chunk.get('chapter_num','?')}"
        print(f"  [{marker}] {chunk['title']}")
        print(f"         {chunk['pages_range']}  ({chunk['page_count']}页)  →  {chunk['filename']}")
        print()

    manifest_path = Path(args.output_dir or Path(args.pdf).parent / "_chunks") / "split_manifest.json"
    print(f"  Manifest: {manifest_path}")
    print(f"  Done. {manifest['total_chunks']} chunk(s) written.\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
