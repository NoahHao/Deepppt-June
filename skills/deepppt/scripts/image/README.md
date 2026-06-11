# image — 图片处理工具

图片分析、生成、搜索和后期处理的独立脚本。

## 脚本清单

| 脚本 | 用途 | 调用示例 |
|------|------|----------|
| `rotate_images.py` | 图片旋转处理 | `python scripts/image/rotate_images.py` |
| `gemini_watermark_remover.py` | Gemini 生成图片水印移除 | `python scripts/image/gemini_watermark_remover.py` |

## 关联模块

| 子目录 | 功能 |
|--------|------|
| `../image_backends/` | AI 图片生成后端（14个提供商） |
| `../image_sources/` | 网页图片搜索提供商 |
| `../image_gen.py` | AI 图片生成 CLI 入口 |
| `../image_search.py` | 网页图片搜索 CLI 入口 |
| `../analyze_images.py` | 图片分析 CLI 入口 |
