---
description: Generate multi-language speaker notes and TTS audio narration, then export a video-ready PPTX with embedded timings. Triggers on /Audio Gen, "生成讲解词及语音", "generate audio narration", "多语言配音".
---

# Multilingual Audio-Video Generation Workflow

> **Purpose**: From SVGs to narrated PPTX — generate speaker notes in any language, synthesize per-slide audio, and export a video-ready PowerPoint with **guaranteed audio-before-advance timings**.

> **Lazy-loaded**: this workflow only loads when explicitly invoked via `/Audio Gen` or equivalent trigger phrases. It does NOT run as part of the main PPT pipeline.

## When to Run

| Trigger | Action |
|---------|--------|
| `/Audio Gen` | Run this workflow |
| "生成讲解词及语音" | Run this workflow |
| "generate audio narration" | Run this workflow |
| "多语言配音" / "日文配音" / "英文旁白" | Run this workflow |
| User just wants PPTX export (no audio) | Skip — use SKILL.md Step 7 directly |

---

## Step 0: Language Confirmation (BLOCKING)

⛔ **BLOCKING**: before anything else, ask the user for the target language.

Ask once, bundled:

> 检测到项目有 **N** 页 SVG。请确认以下配置：
>
> - **输出语言**：中文 / English / 日本語 / 한국어 / Deutsch / Français / ...
> - **音色**：根据语言自动推荐（如日文推荐 `ja-JP-NanamiNeural`（女声））
> - **语速**：默认 `+0%`
>
> 直接回"好"用推荐值，或指定语言和音色。

**Voice defaults by language:**

| Language | Recommended Female | Recommended Male |
|----------|--------------------|--------------------|
| 中文 (zh-CN) | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunjianNeural` |
| English (en-US) | `en-US-JennyNeural` | `en-US-GuyNeural` |
| 日本語 (ja-JP) | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| 한국어 (ko-KR) | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |

---

## Step 1: Generate Speaker Notes

AI reads all SVG files from `svg_output/` and writes speaker notes in the target language to `notes/total.md`.

**Format:**
```markdown
## slide_01 (page title)
<2-4 sentences of narration in target language>

## slide_02 (page title)
<2-4 sentences of narration in target language>
```

**Rules:**
- Match the deck's tone (professional, technical for whitepapers; friendly for marketing)
- 2-4 sentences per slide — enough to convey key points, short enough for audience attention
- Write in the user's chosen language throughout

**✅ Checkpoint: `notes/total.md` written. Proceed to Step 2.**

---

## Step 2: Execute Pipeline (no interaction needed)

Run the orchestrator — it chains 3 stages:

```bash
python3 ${SKILL_DIR}/scripts/multilingual_audio_video/orchestrator.py <project_path> \
  --voice <chosen-voice> --rate <chosen-rate>
```

**What it does:**
1. `total_md_split.py` → `notes/total.md` → `notes/slide_01.md` ... `slide_N.md`
2. `notes_to_audio.py --voice <voice>` → `audio/slide_01.mp3` ... `slide_N.mp3`
3. `svg_to_pptx.py --recorded-narration audio --animation-trigger after-previous` → PPTX

**Audio-before-advance guarantee (CRITICAL):**

The PPTX export uses `mutagen` to read each MP3's actual duration, then sets `advTm` on each slide transition to `duration + 0.5s`. This ensures:
- The slide **never** advances before the audio finishes
- A 0.5s buffer prevents abrupt cuts

> ⚠️ **Do NOT skip the mutagen check.** Without it, VBR MP3s from edge-tts will have durations underestimated by ~40%, causing mid-audio slide cuts. The orchestrator auto-installs mutagen if missing.

---

## Step 3: Completion Report

Output:
```
## ✅ Multilingual Audio-Video Generation Complete

| Item | Value |
|------|-------|
| Language | Japanese (ja-JP) |
| Voice | ja-JP-NanamiNeural (Female) |
| Audio files | 12/12 generated |
| Output PPTX | exports/<name>_<timestamp>.pptx |
| Slide timings | Guaranteed: audio finishes before advance |

**Next**: Open in PowerPoint → Slide Show → Use Recorded Timings and Narrations.
```

---

## Technical Reference

### Orchestrator script

```bash
# Full pipeline (most common)
python3 scripts/multilingual_audio_video/orchestrator.py <project> --voice <shortname>

# Single stage reruns
python3 scripts/multilingual_audio_video/orchestrator.py <project> --audio-only --voice <voice>
python3 scripts/multilingual_audio_video/orchestrator.py <project> --export-only
```

### Duration accuracy (mutagen)

The orchestrator and `pptx_narration.py` use a 3-tier duration probe:
1. `ffprobe` (most accurate, if installed)
2. `mutagen` (VBR-safe, pure Python)
3. Xing header fallback (last resort)

This guarantees accurate slide timings regardless of whether ffmpeg is installed.
