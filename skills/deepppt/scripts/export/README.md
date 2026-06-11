# export — 导出与后处理工具

PPT 生成流水线 Step 7 相关的后处理和导出脚本。

## 脚本清单

| 脚本 | 用途 | 调用示例 |
|------|------|----------|
| `svg_quality_checker.py` | SVG 质量检查（12项规范校验） | `python scripts/export/svg_quality_checker.py <project>` |
| `svg_position_calculator.py` | 图表坐标校准（bar/line/pie/radar） | `python scripts/export/svg_position_calculator.py calc bar ...` |
| `total_md_split.py` | 演讲者备注按页拆分 | `python scripts/export/total_md_split.py <project>` |
| `check_annotations.py` | SVG 批注检查与应用 | `python scripts/export/check_annotations.py <project>` |
| `latex_render.py` | LaTeX 公式渲染为 PNG | `python scripts/export/latex_render.py <project>` |
| `batch_validate.py` | 批量项目验证 | `python scripts/export/batch_validate.py` |

## 兼容性

顶层 `scripts/` 目录保留了向后兼容的薄包装，旧路径仍然可用：
- `scripts/svg_quality_checker.py` → `scripts/export/svg_quality_checker.py`
- `scripts/total_md_split.py` → `scripts/export/total_md_split.py`
- 等等
