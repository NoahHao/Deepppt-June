# knowledge_base 定时扫描与自动流水线 — 使用说明

## 概述

`knowledge_base` 目录下的定时扫描任务会自动检测新增/修改的 PPTX 文件，并**自动触发**四条全量流水线：

| Pipeline | 功能 | 脚本来源 | 耗时 |
|----------|------|---------|------|
| 1. PPTX → JSON | 扫描 PPTX，提取每页文本和关键词，生成 `kb_index.json` | `PPT_Recall/indexer.py` | ~0.2s |
| 2. 图片提取 | 从 PPTX 提取所有图片，去重归档，生成 `image_extract_index.json` | `image_extract/indexer.py` | ~2s |
| 3. 向量库创建 | 通过 ONNX 模型编码文本和图片为 512 维向量，存入 FAISS 索引 | `LLM_Search/cli.py build` | ~30s |
| 4. 向量去重 | 余弦相似度 + 文件 MD5 哈希去重，消除语义/文件级重复 | `LLM_Search/vector_store/dedup.py` | ~1s |

## 文件结构

```
knowledge_base/
├── file_watcher.py              ← 定时扫描器（核心）
├── run_pipelines.py             ← 全量流水线编排
├── start_watcher.bat            ← 一键启动脚本（守护进程）
├── install_scheduled_task.ps1   ← Windows 计划任务安装脚本
├── watch_state.json             ← 扫描状态（自动生成）
├── pipeline.log                 ← 流水线日志（自动生成）
├── watcher.log                  ← 扫描器日志（自动生成）
├── customer_cases/
│   └── 客户案例.pptx
├── product_intro/
│   └── 产品能力.pptx
├── solution_intro/
│   └── 解决方案能力.pptx
└── 趋势&痛点&挑战.pptx
```

## 快速开始

### 方式一：守护进程模式（推荐测试使用）

双击 `start_watcher.bat` 或在命令行运行：

```bash
cd knowledge_base
python file_watcher.py --daemon
```

程序会持续运行，**每1小时**自动扫描一次。检测到新文件时自动触发全部流水线。

自定义扫描间隔（如30分钟）：
```bash
python file_watcher.py --daemon --interval 1800
```

停止：按 `Ctrl+C`。

### 方式二：Windows 计划任务（推荐生产使用）

**以管理员身份**打开 PowerShell，运行：

```powershell
cd knowledge_base
.\install_scheduled_task.ps1
```

这会创建一个名为 `PPT_Master_KnowledgeBase_Watcher` 的计划任务，每小时自动执行一次扫描。

自定义间隔（如30分钟）：
```powershell
.\install_scheduled_task.ps1 -IntervalMinutes 30
```

查看/管理任务：打开 `taskschd.msc`（任务计划程序），搜索 `PPT_Master`。

卸载任务：
```powershell
.\install_scheduled_task.ps1 -Remove
```

### 方式三：手动触发

```bash
# 单次扫描 + 自动触发流水线
python file_watcher.py --once

# 仅检测变更，不触发流水线（预览模式）
python file_watcher.py --dry-run

# 查看当前扫描状态
python file_watcher.py --status

# 重置状态（将所有文件视为新文件）
python file_watcher.py --reset
```

### 方式四：直接运行流水线（跳过扫描检测）

```bash
# 运行全部四条流水线
python run_pipelines.py

# 仅运行 Pipeline 3 + 4（向量库 + 去重）
python run_pipelines.py --skip-ppt --skip-img

# 仅运行 Pipeline 3（向量库，不去重）
python run_pipelines.py --skip-ppt --skip-img --skip-dedup

# 仅运行去重
python run_pipelines.py --skip-ppt --skip-img --skip-vec

# 跳过向量库（仅 PPTX→JSON + 图片提取）
python run_pipelines.py --skip-vec
```

## 工作流程

```
┌──────────────────┐
│ 定时器触发        │  每小时 / 手动触发
│ (daemon/计划任务) │
└────────┬─────────┘
         ▼
┌──────────────────┐
│ file_watcher.py  │  扫描 knowledge_base 下所有 *.pptx
│ 扫描检测         │  - 计算 MD5 哈希
│                  │  - 与 watch_state.json 比对
└────────┬─────────┘
         ▼
    ┌────┴────┐
    │ 有变更？ │
    └────┬────┘
    是   │   否 → 跳过，记录日志
         ▼
┌──────────────────┐
│ run_pipelines.py │  依次执行三条流水线
│                  │
│  ① PPTX→JSON     │  scan_and_index() → kb_index.json
│  ② 图片提取      │  scan_and_index() → image_extract_index.json
│  ③ 向量库创建    │  subprocess → LLM_Search cli.py build
│  ④ 向量去重      │  subprocess → dedup.py (余弦相似度+文件哈希)
└──────────────────┘
```

## 向量去重说明

Pipeline 4 在每次向量库构建完成后**自动触发**，对 FAISS 索引中的重复条目进行清理。

### 去重策略

| 阶段 | 方法 | 目标库 | 默认阈值 |
|------|------|--------|----------|
| Stage 1 | MD5 文件哈希 | images | 精确匹配（相同文件 100% 去重） |
| Stage 2 | 余弦相似度 | images | 0.95（同一 PPT 中相似图去重） |
| Cosine | 余弦相似度 | ppt_slides | 0.99（仅去极相似页面） |

### 实测效果（230 张图片）

```
原始: 230 条
  → MD5哈希: 230 条 (移除 0 个文件级重复)
  → 余弦相似度: 41 条 (移除 189 个语义重复, 35 个簇)
去重率: 82.2%
```

### 手动触发去重

```bash
cd LLM_Search/vector_store
python dedup.py images                    # 图片去重
python dedup.py ppt_slides                # PPT 页面去重
python dedup.py all                       # 全部去重
python dedup.py images --threshold 0.92   # 更激进去重
python dedup.py images --dry-run          # 仅统计不修改
```

### 去重日志

去重操作记录保存在 `LLM_Search/vector_store/dedup_log.json`，保留最近 50 条记录。

## 变更检测机制

- **首次扫描**：所有 PPTX 文件都被视为"新增"
- **后续扫描**：通过 **MD5 文件哈希** 检测内容变更（修改 PPTX 后重新保存也会被检测到）
- **文件删除**：删除 PPTX 文件后，状态会自动清理

> **注意**：流水线采用**全量重建**策略——每次检测到变更都会对整个 `knowledge_base` 重新执行全部任务。这确保索引数据始终与文件内容一致。

## 运行环境要求

| 组件 | 需求 |
|------|------|
| Pipeline 1 & 2 | Python 3.x（任意版本） |
| Pipeline 3 | **Python 3.10** + numpy + onnxruntime + tokenizers + faiss-cpu |
| 操作系统 | Windows（计划任务）/ Linux（守护进程） |

**LLM_Search 模块**（Pipeline 3）已自带完整环境配置：
- 依赖安装在 `C:\Python310\` 下
- 模型文件位于 `LLM_Search/model/` 目录
- 向量库输出到 `LLM_Search/vector_store/` 目录

## 日志查看

```bash
# 扫描器日志
type knowledge_base\watcher.log

# 流水线日志
type knowledge_base\pipeline.log
```

## 常见问题

**Q: 首次运行会触发流水线吗？**
A: 会。首次运行会检测到所有 PPTX 文件为"新增"，自动触发全量流水线。

**Q: 流水线失败怎么办？**
A: 查看 `pipeline.log` 日志文件获取详细错误信息。下次扫描时如果文件再次变更，会重新触发。

**Q: 如何临时禁用自动触发？**
A: 使用 `--dry-run` 模式：`python file_watcher.py --once --dry-run`

**Q: 向量库模块运行慢怎么办？**
A: Pipeline 3 约 30 秒（31 页 + 230 张图片的 512 维向量编码），属于正常范围。首次运行需加载 ONNX 模型。

**Q: 如何只处理特定子目录？**
A: 流水线默认扫描 `knowledge_base` 下**所有** PPTX 文件。如需限制范围，目前需在 `run_pipelines.py` 中修改过滤逻辑。
