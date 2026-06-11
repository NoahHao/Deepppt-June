# tools — 独立工具脚本

不直接参与主流水线、但提供辅助功能的独立工具。

## 脚本清单

| 脚本 | 用途 | 调用示例 |
|------|------|----------|
| `kb_search.py` | KB 知识库搜索（本地+网页PPT素材） | `python scripts/tools/kb_search.py "关键词"` |
| `web_ppt_crawler.py` | 网页 PPT 素材爬虫 | `python scripts/tools/web_ppt_crawler.py --query "XX"` |
| `visual_review.py` | 逐页视觉审查 | `python scripts/tools/visual_review.py <project>` |
| `update_repo.py` | 仓库更新工具 | `python scripts/tools/update_repo.py` |
| `update_spec.py` | spec_lock.md 变更传播 | `python scripts/tools/update_spec.py <project>` |
| `generate_examples_index.py` | 示例索引生成 | `python scripts/tools/generate_examples_index.py` |
| `register_template.py` | 模板注册（牌组/布局/品牌） | `python scripts/tools/register_template.py <id> --kind deck` |

## 兼容性

顶层 `scripts/` 目录保留了向后兼容的薄包装。
