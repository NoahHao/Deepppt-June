---
description: Split long PDFs into context-safe chunks for the PPT generation pipeline. Preserves chapter/section integrity so each chunk maps to a coherent deck subset. Triggers on /split-pdf or when the user asks to "拆分PDF", "切割长文档", "split pdf".
---

# PDF Smart Splitter Workflow

> **Purpose**: Split a long PDF (>10 pages) into context-safe chunks before feeding into the PPT Master pipeline. Each chunk preserves chapter/section integrity — no topic is split mid-flow.

> **Independent workflow**: runs before SKILL.md Step 1. The output `_chunks/` directory feeds directly into the pipeline, either sequentially or in parallel.

## When to Run

| Situation | Action |
|---|---|
| PDF > 10 pages | Run this workflow **before** SKILL.md Step 1 |
| User says "拆分PDF" / "切割长文档" / "split pdf" | Run this workflow |
| `pdf_to_md.py` output is too large (>50KB Markdown) | Rerun source with split chunks |
| PDF ≤ 10 pages | Skip — use SKILL.md Step 1 directly |

## Quick Command

```
/split-pdf <pdf_file> [--max-pages N] [--model MODEL_ID]
```

Examples:
```
/split-pdf "AI DC白皮书.pdf"
/split-pdf "报告.pdf" --max-pages 8
/split-pdf "论文.pdf" --model gpt-4o
```

---

## Step 1: Model Sniffing (automatic)

The splitter auto-detects the backend model:

| Source | Priority |
|---|---|
| `--model` CLI flag | 🔴 Highest |
| `MODEL_ID` / `LLM_MODEL` env var | 🟡 Medium |
| Known model matching | 🟢 Fallback |

**Safe chunk formula:**
```
ctx_available = context_window × 0.9        # 10% safety margin
working_budget = ctx_available − 50,000     # fixed overhead (skill + script + prompts)
tokens_per_page = 800 chars × 1.5 tokens    # ~1,200 tokens/page
safe_pages = working_budget ÷ 1,200         # round down, clamp [3, 15]
```

> ⚠️ **宁可少，不能多** — the formula deliberately underestimates. Skill code, quality-check prompts, and SVG output all consume context beyond the raw PDF text.

---

## Step 2: Execute the splitter

```bash
python3 ${SKILL_DIR}/scripts/source_to_md/pdf_splitter.py <pdf_file> [--max-pages N]
```

**What it does:**
1. Detects model context window
2. Finds chapter boundaries ("第X章" patterns + font-size heuristics)
3. Splits oversized chapters at sub-section boundaries
4. Writes individual PDF chunks to `<pdf_dir>/_chunks/`
5. Outputs `split_manifest.json` with chunk metadata

**Output structure:**
```
<pdf_dir>/_chunks/
├── chunk_01_p1-6_frontmatter.pdf
├── chunk_02_p7-10_第1章_ai宏观驱动力.pdf
├── chunk_03_p11-18_第2章_企业ai.pdf
├── chunk_04_p19-24_第3章_dc演进.pdf
├── ...
├── chunk_0N_pXX-XX_...pdf
└── split_manifest.json
```

**Manifest format:**
```json
{
  "source_pdf": "/path/to/original.pdf",
  "total_pages": 54,
  "model_info": {"model_id": "deepseek-v3", "context_window": 128000},
  "safe_pages_per_chunk": 10,
  "total_chunks": 8,
  "chunks": [
    {
      "id": 1,
      "title": "前言与目录",
      "pages_range": "p1-6",
      "page_count": 6,
      "filename": "chunk_01_p1-6_frontmatter.pdf",
      "path": "/path/to/_chunks/chunk_01_...pdf"
    }
  ]
}
```

---

## Step 3: Feed chunks into the pipeline

### 3a. Sequential processing (default)

Process chunks one at a time through the standard SKILL.md pipeline:

```
For each chunk in split_manifest.json:
    SKILL.md Step 1: pdf_to_md.py <chunk>.pdf
    SKILL.md Step 2: project_manager.py init <project>_chunk_N
    SKILL.md Step 4-7: Strategist → Executor → Export
```

### 3b. Parallel processing (concurrent mode)

When multiple model instances are available, run chunks in parallel:

```
For N concurrent instances:
    Instance 1: process chunks 1, 5, 9, ...
    Instance 2: process chunks 2, 6, 10, ...
    Instance 3: process chunks 3, 7, 11, ...
    Instance 4: process chunks 4, 8, 12, ...
```

> ⚠️ **Concurrent safety**: each chunk runs in its own project directory (`<project>_chunk_N/`). No file conflicts.

**Concurrency limits** — auto-detect available instances:

| Signal | Max concurrent |
|---|---|
| `CONCURRENT_INSTANCES` env var | User-specified |
| WorkBuddy CloudStudio sandboxes | 4 |
| Single VM / local | 1 |
| Claude Code with `--session` | Up to 5 |

---

## Notes

- **First-run safety**: always `--analyze` first to review the split plan before executing.
- **Chapter integrity**: the splitter never breaks a chapter mid-flow. Oversized chapters are split at sub-section boundaries.
- **Context budget**: the formula errs on the conservative side. If chunks seem too small, reduce `--max-pages` manually.
- **Post-processing**: after all chunks are processed, merge the generated PPTX files or deliver them as a deck series.
