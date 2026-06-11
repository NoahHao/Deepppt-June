# style_convert — PPTX 风格与语言转换

白底↔黑底颜色转换 + 中文→多语言翻译 + 自动字体适配。

## 命令行

```bash
# 提取中文文本（交 AI 翻译）
python scripts/style_convert/orchestrator.py extract input.pptx -o texts.json

# 应用翻译
python scripts/style_convert/orchestrator.py apply input.pptx output.pptx -m translations.json

# 背景色转换
python scripts/style_convert/orchestrator.py bg input.pptx output.pptx --to black

# 批量：翻译 + 背景
python scripts/style_convert/orchestrator.py batch input.pptx out_dir/ -m translations.json --convert-bg
```

## 触发方式

对话中说 `/style_convert`、`风格转换`、`翻译PPT` 即可触发完整工作流。
