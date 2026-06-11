# PPT Quality Check — PPT 内容质量检查工具

对 PPTX 文件执行全面的内容层面质量检查，输出结构化的 JSON 报告。

---

## 目录

- [快速使用](#快速使用)
- [检查能力清单](#检查能力清单)
- [目录结构](#目录结构)
- [输出报告格式](#输出报告格式)
- [定制化指南](#定制化指南)
  - [调整检查阈值](#调整检查阈值)
  - [新增自定义检查项](#新增自定义检查项)
  - [配置 Gate Check 模板](#配置-gate-check-模板)
  - [修改文本分词逻辑](#修改文本分词逻辑)
- [与 SVG Quality Check 的关系](#与-svg-quality-check-的关系)
- [常见问题](#常见问题)

---

## 快速使用

```bash
cd "PPT Quality Check"

# 基础用法：仅内容质量检查
python main.py sample.pptx

# 指定源文档（用于关键词覆盖检查）
python main.py sample.pptx -s source_text.md

# 同时使用 Gate Check（框架匹配 + 内容质量）
python main.py sample.pptx -t configs/product_pitch.yaml

# 指定报告输出路径
python main.py sample.pptx -r report.json
```

> **退出码**：0 = 通过（无 ERROR），1 = 存在 ERROR 级别问题。可集成到 CI 流水线。

---

## 检查能力清单

共 **9 项检查**，分为三个严重级别：

### ERROR 级别（阻断性问题，必须修复）

| ID | 检查项 | 检测逻辑 | 典型场景 |
|---|---|---|---|
| **C1** | 占位符残留 | 正则搜索 `{{XXX}}`、`{TITLE}`、`#{XXX}` 等模板标记 | AI 生成时部分占位符未被填充 |
| **C2** | 空页检测 | 页面中文有效字符 < 10 个 | 只放了背景装饰图，忘记了内容 |
| **C7** | 文本编码质量 | 检测 Unicode 替换字符 `�` | 跨系统传输/编码配置错误 |

### WARNING 级别（应关注，建议修复）

| ID | 检查项 | 检测逻辑 | 典型场景 |
|---|---|---|---|
| **C3** | 类型-内容匹配 | 第 1 页缺标题、最后页缺致谢/Q&A | 封面太简陋、结尾戛然而止 |
| **C4** | 内容冗余 | 相邻页 TF 余弦相似度 > 0.75 | AI 卡住重复生成、两页内容雷同 |
| **C5** | 页码连续性 | 文件名编号是否连续递增 | 插页后序号断裂 |
| **C8** | 首尾闭环 | 是否有封面页 + 结尾页 | 缺少 PPT 的标准起止结构 |
| **C9** | 文本离群检测 | 页面内某段文字与同页其他内容的 TF 相似度极低 | 脚注放错页、粘贴了一段无关内容 |

### INFO 级别（参考信息）

| ID | 检查项 | 检测逻辑 | 典型场景 |
|---|---|---|---|
| **C6** | 源文档关键词覆盖 | 原始材料 Top-20 关键词在 PPT 中的出现率 | 验证内容是否覆盖了原始要点的关键信息 |

---

## 目录结构

```
PPT Quality Check/
  README.md          ← 本文件
  main.py            ← 统一入口（内容检查 + Gate Check）
  requirements.txt   ← 依赖（python-pptx, pyyaml）

  engine/
    __init__.py
    parser.py                      ← PPTX 文本提取（标题/正文/全部文本）
    matcher.py                     ← 阶段匹配（Gate Check 核心）
    gate_checker.py                ← 框架匹配检查（病·药·效·行动等）
    content_quality_checker.py     ← 内容质量检查（C1-C9 全部实现）

  configs/                         ← Gate Check 模板配置
    schema.yaml                    ← 配置规范说明
    product_pitch.yaml             ← 产品推介（病·药·效·行动）
    investment_review.yaml         ← 投资评审
    strategy_proposal.yaml         ← 策略提案
    biz_review_meeting.yaml        ← 业务复盘
    project_initiation.yaml        ← 项目立项
```

---

## 输出报告格式

```json
{
  "file": "sample.pptx",
  "checks": {
    "content_quality": {
      "file": "sample.pptx",
      "total_pages": 8,
      "summary": {
        "total_issues": 5,
        "error_count": 0,
        "warning_count": 5,
        "info_count": 0,
        "passed": true,
        "check_types": {
          "C1_placeholder": false,
          "C2_empty": false,
          "C3_type_match": true,
          "C4_redundancy": false,
          "C5_continuity": false,
          "C6_source_coverage": false,
          "C7_encoding": false,
          "C8_structure": true,
          "C9_outlier": true
        }
      },
      "issues": [
        {
          "type": "C9_OUTLIER",
          "page": 3,
          "text": "与主题无关的脚注文本...",
          "avg_similarity": 0.002,
          "global_avg": 0.175,
          "detail": "文本块与同页其他内容不相关 (相似度 0.002 vs 全局 0.175)"
        }
      ]
    },
    "gate_check": { ... }    // 仅在使用 -t 参数时出现
  }
}
```

每个 issue 对象的关键字段：
- `type`：检查项类型（C1_PLACEHOLDER / C2_EMPTY_PAGE / ... / C9_OUTLIER）
- `page`：所在页码
- `detail`：人类可读的问题描述
- `text` / `text_sample`：有问题的文本片段

---

## 定制化指南

### 调整检查阈值

所有可调参数集中在 `engine/content_quality_checker.py` 顶部：

```python
# C4 内容冗余 — 相似度阈值（0.0 ~ 1.0）
threshold: float = 0.75   # 降低 = 更敏感，升高 = 更宽松

# C9 文本离群 — 异常相似度阈值
outlier_threshold: float = 0.05   # 低于此值标记为离群

# C9 文本离群 — 过滤函数
# 跳过过短文本：len(text) < 4
# 跳过脚注/水印：top_emu > 5800000 且 font_size_pt < 12
```

| 场景 | 建议阈值 |
|---|---|
| PPT 内容多样性高（学术/培训） | C4 上调至 0.85，C9 下调至 0.03 |
| PPT 内容结构化（商业计划书） | C4 保持 0.75，C9 保持 0.05 |
| PPT 页数多（>30页） | C4 增加上下文窗口，只检测相邻 3 页内的重复 |

### 新增自定义检查项

按以下模板在 `ContentQualityChecker.check()` 方法中添加：

```python
# 1. 在 engine/content_quality_checker.py 中定义检查函数
def _check_my_custom_rule(shapes_data: List[Dict]) -> Optional[Dict]:
    """C10: 我的自定义检查。"""
    # 你的检测逻辑
    if condition_failed:
        return {
            'type': 'C10_CUSTOM',
            'detail': '问题描述',
        }
    return None

# 2. 在 ContentQualityChecker.check() 的逐页循环中调用
for page_data in all_shapes:
    ...
    result = _check_my_custom_rule(shapes)
    if result:
        result['page'] = page_num
        all_issues.append(result)

# 3. 在 Python 中指定严重级别（error_types / warning_types / info_types）
warning_types = {..., 'C10_CUSTOM'}
```

**可用的辅助工具：**

| 函数 | 用途 |
|---|---|
| `_tokenize(text)` | 中文 n-gram 分词（2-gram + 3-gram） |
| `_compute_tf(texts)` | 计算文本集合的词频 |
| `_cosine_similarity(v1, v2)` | 两个 Counter 的余弦相似度 |
| 每个页面的 `shapes_data` | `[{'text': str, 'font_size_pt': float, 'left_emu': int, 'top_emu': int}, ...]` |

**检查项命名规范：**
- ERROR 级别：`C{编号}_{大写描述}`
- WARNING 级别：同上，加入 `warning_types` 集合
- INFO 级别：同上，加入 `info_types` 集合

### 配置 Gate Check 模板

Gate Check 用于检查 PPT 是否遵循特定演示框架（如产品宣讲的「病·药·效·行动」结构）。

**模板文件示例（YAML）：**

```yaml
meta:
  id: my_meeting_type
  name: "我的场景名称"
  version: "1.0"

gate_policy:
  strict_order: true         # 是否强制阶段顺序
  allow_skipped_stages: false # 是否允许跳阶段
  max_unmatched_pages: 2     # 允许最多几页无法匹配
  min_match_score: 3         # 匹配最低得分

stages:
  - id: stage_1
    label: "阶段标签"
    role: context            # 角色：context/complication/answer/evidence/action
    keywords: [关键词1, 关键词2, 关键词3]
    synonyms: [近义词1, 近义词2]
    required: true           # 是否必须出现
    order: 1                 # 出现顺序
    min_pages: 1
    max_pages: 2
    must_precede: [stage_0]  # 必须在哪些阶段之后出现
```

自定义步骤：
1. 复制 `configs/product_pitch.yaml`
2. 修改 `meta.name` 和 `stages` 列表
3. 调整 `gate_policy` 中的严格度参数
4. 运行 `python main.py sample.pptx -t configs/my_template.yaml`

### 修改文本分词逻辑

默认使用 **中文 2-3 n-gram** 分词（不依赖 jieba），适合大多数场景。如需更高精度：

```python
# 替换 _tokenize() 函数中的分词逻辑
import jieba  # 需先 pip install jieba

def _tokenize(text: str) -> List[str]:
    words = jieba.cut(text)
    return [w for w in words if len(w) >= 2 and w.strip() and w not in STOP_WORDS]
```

---

## 与 SVG Quality Check 的关系

```
PPT 生成流程中的两个质量门：

SVG 生成 → svg_quality_checker.py（形式检查：SVG 规范、字体、颜色等）
         ↓ 通过
         → content_quality_checker.py（内容检查：本文档）
         ↓ 通过
         → finalize_svg.py → svg_to_pptx.py
```

| 维度 | SVG Quality Check | PPT Quality Check（本工具） |
|---|---|---|
| 检查对象 | SVG 文件 | PPTX 文件 |
| 检查类型 | 形式/技术 | 内容/语义 |
| 运行阶段 | SVG 生成后 | 导出后（或独立运行） |
| 依赖 | ElementTree, 项目内部模块 | python-pptx, pyyaml |
| 位置 | `scripts/svg_quality_checker.py` | `scripts/PPT Quality Check/main.py` |

两者互补，不重复。

---

## 常见问题

### Q: 为什么 C9 会把标题标记为离群？

标题（如"产品介绍"）和数据指标（如"40% TCO 降低"）在 n-gram 层面语义不同。这是预期行为——WARNING 级别意味着"建议人工确认"，不表示一定有错误。可根据你的场景上调阈值。

### Q: 能不能集成到 PPT Master 生成流水线中？

可以。在 SKILL.md 的 Executor 阶段后，`finalize_svg.py` 之前，运行：

```bash
python "PPT Quality Check/main.py" <project>/exports/<name>.pptx
if [ $? -ne 0 ]; then
  echo "内容质量检查未通过，请修复后重试"
  exit 1
fi
```

### Q: 中文字体名称能不能自定义？

能。修改 `parser.py` 中的 `_get_shape_texts()` 方法，增加对特定字体族的过滤或权重调整。

### Q: 报告能输出 CSV/Excel 格式吗？

目前仅支持 JSON。如需其他格式，可在 `main.py` 中增加 `--format csv` 参数，调用 `csv.DictWriter` 将 issues 列表写入文件。
