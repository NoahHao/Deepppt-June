---
description: Convert PPTX between languages (Chinese→English/Japanese/French/etc.) and background themes (white↔black). Triggers on /style_convert, "风格转换", "翻译PPT", "translate pptx".
---

# Style Convert Workflow

> **Purpose**: Translate PPTX text content between languages and convert background color themes. Extracts all Chinese text, hands it to AI for translation, then applies the translated text back with automatic font resizing.

> **Lazy-loaded**: triggers only on `/style_convert` or when user mentions "翻译PPT", "风格转换", "多语言翻译".

## When to Run

| Trigger | Action |
|---------|--------|
| `/style_convert` | Run this workflow |
| "翻译PPT" / "translate pptx" / "翻成英文" | Run this workflow |
| "黑白底转换" / "dark mode" | Run bg conversion only |

---

## Step 0: Confirmation (BLOCKING)

Ask the user once:

> 检测到 PPTX 文件。请确认：
> - **目标语言**：English / Français / 日本語 / 한국어 / ...
> - **背景色**：保持不变 / 转为黑底 / 转为白底
> - **输出路径**：默认 `<原文件名>_<语言>.pptx`

---

## Step 1: Extract text

```bash
python3 ${SKILL_DIR}/scripts/style_convert/orchestrator.py extract <input.pptx> -o <project>/texts_to_translate.json
```

---

## Step 2: AI Translation

Read `texts_to_translate.json`. The AI translates the `"texts"` array in full, producing a `{Chinese: TargetLanguage}` JSON map.

Write the map to `translations.json`.

---

## Step 3: Apply translations + font adapt

```bash
python3 ${SKILL_DIR}/scripts/style_convert/orchestrator.py apply <input.pptx> <output.pptx> -m translations.json
```

If the user also requested background conversion:

```bash
python3 ${SKILL_DIR}/scripts/style_convert/orchestrator.py bg <output.pptx> <final.pptx> --to black
```

**Auto-Verification Gate** (built into `apply` and `bg` commands):
- Background color — checks `<p:bg>` `srgbClr` on every slide
- Translation completeness — scans for residual source-language chars
- Text overflow risk — flags long texts (>100 chars) that may clip/overlap
- Background now modified at 3 layers: slide XML + slideLayout + slideMaster
- Add `--no-verify` to skip. Standalone: `orchestrator.py verify <file> --bg 000000`

---

## Step 4: Report

```
## ✅ Style Convert Complete
- Source: input.pptx (N slides)
- Translation: Chinese → <language> (M texts translated)
- Fonts auto-adapted for target language
- Output: output.pptx
```
