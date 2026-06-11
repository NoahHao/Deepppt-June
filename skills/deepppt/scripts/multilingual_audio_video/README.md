# Multilingual Audio-Video Generation

一键流水线：讲解词 → 语音合成 → PPTX 导出（嵌入旁白+自动翻页计时）。

## 快速使用

```bash
# 完整流水线
python3 scripts/multilingual_audio_video/orchestrator.py <project> --voice <voice>

# 仅某一步
python3 scripts/multilingual_audio_video/orchestrator.py <project> --split-only
python3 scripts/multilingual_audio_video/orchestrator.py <project> --voice ja-JP-NanamiNeural --audio-only
python3 scripts/multilingual_audio_video/orchestrator.py <project> --export-only
```

## 触发方式

在对话中说 `/Audio Gen` 或 "生成讲解词及语音" 即可触发完整工作流。

## 流水线

```
notes/total.md        audio/slide_*.mp3        exports/*.pptx
     ↑                      ↑                       ↑
  [Step 1]              [Step 2]                [Step 3]
  AI 生成多语言       total_md_split.py        svg_to_pptx.py
  讲解词              notes_to_audio.py        --recorded-narration
```

## 关键保证

**音频播完才翻页** — 使用 mutagen 读取 MP3 真实时长（支持 VBR），设置精确的 `advTm`。
