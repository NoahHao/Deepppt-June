# Scripts 目录 — 原子功能索引

每个子目录对应一个独立的原子功能模块。所有脚本从 `${SKILL_DIR}/scripts/` 调用。

## 核心模块（顶层）

这些脚本被多处引用，保持在顶层以避免破坏导入路径。

| 脚本 | 用途 | 命令行调用 |
|------|------|-----------|
| `project_manager.py` | 项目初始化/导入/管理 | `python scripts/project_manager.py init <name>` |
| `project_utils.py` | 项目工具函数（库模块） | （被其他脚本导入） |
| `config.py` | 全局配置/CANVAS_FORMATS | （被其他脚本导入） |
| `error_helper.py` | 错误处理辅助 | （被其他脚本导入） |
| `_zip_utils.py` | ZIP/PPTX素材提取 | （被其他脚本导入） |

## 原子功能子目录

| 子目录 | 功能 | 入口命令 |
|--------|------|----------|
| [`source_to_md/`](source_to_md/) | PDF/DOCX/URL/PPTX→Markdown 转换 + PDF智能裁剪 | `pdf_to_md.py`, `doc_to_md.py`, `pdf_splitter.py` |
| [`svg_editor/`](svg_editor/) | Flask Web 预览编辑器 + 协同批注 + 共享审核 | `svg_editor/server.py` |
| [`svg_to_pptx/`](svg_to_pptx/) | SVG → PPTX 导出引擎 | `svg_to_pptx.py` |
| [`svg_finalize/`](svg_finalize/) | SVG 后处理(图标嵌入/图片处理/路径优化) | `finalize_svg.py` |
| [`pptx_to_svg/`](pptx_to_svg/) | PPTX 解析 → SVG | `pptx_to_svg.py` |
| [`export/`](export/) | 导出与后处理（质检/坐标/备注/公式/批注） | `svg_quality_checker.py`, `total_md_split.py` |
| [`tools/`](tools/) | 独立工具（KB搜索/爬虫/视觉审查/模板注册） | `kb_search.py`, `visual_review.py` |
| [`image/`](image/) | 图片处理（旋转/水印） | `rotate_images.py`, `gemini_watermark_remover.py` |
| [`image_backends/`](image_backends/) | AI 图片生成后端(14个提供商) | `image_gen.py --manifest` |
| [`image_sources/`](image_sources/) | 网页图片搜索提供商 | `image_search.py` |
| [`tts_backends/`](tts_backends/) | 语音合成后端(5个提供商) | `notes_to_audio.py` |
| [`multilingual_audio_video/`](multilingual_audio_video/) | 多语言讲解词+配音+PPTX导出流水线 | `orchestrator.py` （一键：split→audio→export） |
| [`template_import/`](template_import/) | PPTX 模板导入/注册 | `pptx_template_import.py`, `register_template.py` |

## 独立工具脚本（顶层）

这些脚本独立可调用，不依赖复杂的内部导入：

| 脚本 | 用途 | 命令行示例 |
|------|------|-----------|
| `svg_quality_checker.py` | SVG 质量检查 | `python scripts/svg_quality_checker.py <project>` |
| `svg_position_calculator.py` | 图表坐标校准 | `python scripts/svg_position_calculator.py calc bar` |
| `total_md_split.py` | 演讲者备注拆分 | `python scripts/total_md_split.py <project>` |
| `finalize_svg.py` | SVG 后处理统一入口 | `python scripts/finalize_svg.py <project>` |
| `svg_to_pptx.py` | 导出 PPTX 入口 | `python scripts/svg_to_pptx.py <project>` |
| `analyze_images.py` | 图片分析 | `python scripts/analyze_images.py <images_dir>` |
| `image_gen.py` | AI 图片生成 | `python scripts/image_gen.py --manifest ...` |
| `image_search.py` | 网页图片搜索 | `python scripts/image_search.py ...` |
| `latex_render.py` | LaTeX 公式渲染 | `python scripts/latex_render.py <project>` |
| `batch_validate.py` | 批量验证 | `python scripts/batch_validate.py` |
| `check_annotations.py` | SVG 标注检查 | `python scripts/check_annotations.py <project>` |
| `update_spec.py` | spec_lock.md 变更传播 | `python scripts/update_spec.py <project>` |
| `kb_search.py` | KB 知识库搜索 | `python scripts/kb_search.py "关键词"` |
| `web_ppt_crawler.py` | 网页 PPT 素材爬虫 | `python scripts/web_ppt_crawler.py --query "XX"` |
| `notes_to_audio.py` | 备注转语音 | `python scripts/notes_to_audio.py <project>` |
| `visual_review.py` | 视觉审查 | `python scripts/visual_review.py <project>` |
| `pptx_animations.py` | PPTX 动画效果库 | （被 svg_to_pptx 导入） |
| `animation_config.py` | 动画配置管理 | `python scripts/animation_config.py scaffold <project>` |
| `rotate_images.py` | 图片旋转 | `python scripts/rotate_images.py` |
| `gemini_watermark_remover.py` | Gemini 水印移除 | `python scripts/gemini_watermark_remover.py` |

## Python 版本说明

Windows 上使用 `python` 而非 `python3`（python.org 安装版不提供 `python3.exe`）。
