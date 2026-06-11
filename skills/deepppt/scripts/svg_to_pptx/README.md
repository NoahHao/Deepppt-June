# svg_to_pptx — PPTX 导出引擎

将 SVG 文件转换为原生 PowerPoint 格式。

## 入口

```bash
python3 scripts/svg_to_pptx.py <project_path>
```

## 选项

| 参数 | 说明 |
|------|------|
| `-s output` / `-s final` | 指定 SVG 源目录（默认 auto: svg_output → native PPTX） |
| `--merge-paragraphs` | 合并段落为可编辑文本块 |
| `--svg-snapshot` | 额外生成 SVG 预览 PPTX |
| `-t <effect>` | 页面切换动画 (fade/push/wipe/none) |
| `-a <effect>` | 元素入场动画 (auto/fade/none/mixed) |
| `--animation-trigger` | 动画启动方式 (on-click/with-previous/after-previous) |
| `--recorded-narration` | 嵌入旁白音频 |

## 输出

```
exports/<project>_<timestamp>.pptx     ← 原生 PPTX（主输出）
backup/<timestamp>/svg_output/         ← SVG 源快照
```
