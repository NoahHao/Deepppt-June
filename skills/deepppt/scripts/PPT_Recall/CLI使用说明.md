# ppt_recall CLI 使用说明

## 目录结构

```
ppt_recall/
├── engine.py          ← 主引擎：关键词搜索 + 召回 + 合并
├── indexer.py         ← 索引器：扫描 PPTX，构建 kb_index.json
├── merge.py           ← 合并器：COM/ZIP 双引擎合并幻灯片
└── __init__.py        ← 模块入口
```

## 快速开始

### 方式 1：engine.py（推荐，一键搜索）

```bash
cd skills/deepppt/scripts/

# 自动建索引 + 关键词搜索
python ppt_recall/engine.py "人工智能"

# 多关键词 AND 搜索
python ppt_recall/engine.py "数据中心 架构"

# 强制重建索引
python ppt_recall/engine.py --scan

# 仅建索引 + 打印概览（不搜索）
python ppt_recall/engine.py
```

### 方式 2：先建索引，再搜索

```bash
# 步骤1: 扫描 PPTX 文件，构建 JSON 索引
python ppt_recall/indexer.py ../knowledge_base

# 指定自定义输出路径
python ppt_recall/indexer.py ../knowledge_base ../kb_index.json

# 步骤2: 用 engine 搜索
python ppt_recall/engine.py "人工智能"
```

## 工作流

```
                        indexer.py               engine.py "关键词"
PPTX 文件目录 ──────→ kb_index.json ──────→ 匹配的 slide 列表
(knowledge_base)       (JSON 索引)           (文件 + 页码 + 分数)
```

`engine.py` 会自动检测 `kb_index.json` 是否存在，不存在则自动调用 indexer 构建索引。

## 编程 API

```python
from ppt_recall import PPTRecallEngine

engine = PPTRecallEngine(kb_root="../knowledge_base")

# 关键词搜索
results = engine.search_keyword("人工智能", top_k=5)
# → [{file, title, slide_num, text_preview, score, path_abs}, ...]

# 语义搜索（需传入 AI 函数）
results = engine.search_ai("语义查询", ai_callable=my_func, top_k=5)

# 召回单页 → 输出 PPTX
output = engine.recall(results[0], output_dir="output/")

# 合并多页 → 输出 PPTX
path = engine.merge_slides([(pptx, slide), ...], "merged.pptx")

# 一键搜索 + 合并
path = engine.search_and_merge("关键词", "output.pptx", top_k=5)
```

```python
from ppt_recall import scan_and_index, load_index

# 构建索引
data = scan_and_index("../knowledge_base", "../kb_index.json")

# 加载已有索引
data = load_index("../kb_index.json")
```

```python
from ppt_recall import merge_slides

# 合并多张 slide → 单个 PPTX
path = merge_slides([("source.pptx", 3), ("source2.pptx", 5)], "merged.pptx")
```

## 索引文件结构 (`kb_index.json`)

```json
{
  "kb_root": "/path/to/knowledge_base",
  "last_scan": "2026-06-05T16:52:00",
  "total_pptx": 4,
  "total_slides": 31,
  "files": {
    "relative/name.pptx": {
      "title": "文件名",
      "slide_count": 10,
      "path_abs": "/abs/path/name.pptx",
      "slides": { "1": "第1页文本...", "2": "第2页文本..." },
      "slide_keywords": { "1": ["关键", "词"], "2": [...] }
    }
  }
}
```

## 与其他模块的关系

| 模块 | 搜索方式 | 定位 |
|------|---------|------|
| `ppt_recall/engine.py` | **关键词**精确匹配 | 快速文本搜索 |
| `LLM_Search/search.py` | **向量语义** + 混合评分 | 语义模糊搜索 |
| `mirror_fill/auto_fill.py` | 搜索 → 分组 → 填充 → 输出 | 一键替换架构图文字 |

如需语义模糊搜索，使用 `LLM_Search` 或 `mirror_fill`。
